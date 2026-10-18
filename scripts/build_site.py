"""Statik siteyi üretir (GitHub Pages gibi sunucusuz yerlerde 7/24 yayın için).

Tüm haritalar, grafikler ve hücre raporları önceden hesaplanıp JSON dosyası olarak
yazılır; site açılırken hiçbir hesaplama veya Earth Engine sorgusu yapılmaz.

    python -m scripts.build_site               # data/store'daki gerçek veriyle (yoksa demo)
    python -m scripts.build_site --demo        # yapay veriyle
    python -m scripts.build_site --out _site
"""
import argparse
import datetime as dt
import json
import logging
import os
import shutil
from pathlib import Path

from backend import places, service, store
from backend.config import GEE_KEY_FILE, REGIONS, ROOT
from backend.demo_source import DemoSource
from backend.sources_common import month_range
from backend.store_source import StoreSource

log = logging.getLogger("build_site")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def pick_source(force_demo: bool):
    if not force_demo:
        stores = store.load_all()
        if set(stores) == set(REGIONS) and all(st["source"] == "gee" for st in stores.values()):
            try:
                return StoreSource(stores)
            except ValueError as exc:
                log.warning("Kayıtlı veri kullanılamadı (%s); demo veriyle üretiliyor.", exc)
        else:
            log.warning("data/store'da tüm bölgeler için gerçek veri yok; demo veriyle üretiliyor.")
    return DemoSource()


def copy_frontend(out: Path) -> None:
    shutil.copytree(ROOT / "frontend" / "static", out / "static", dirs_exist_ok=True)
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    html = html.replace('<script src="static/app.js"></script>',
                        '<script>window.KG_STATIC = true;</script>\n<script src="static/app.js"></script>')
    if "KG_STATIC" not in html:
        raise RuntimeError("index.html içinde app.js etiketi bulunamadı")
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")


def build_rasters(src, api: Path) -> dict:
    """Son ayın 10 m'den üretilmiş NDVI/VCI görüntüleri (yalnızca GEE anahtarı varsa)."""
    if src.mode != "gee" or not GEE_KEY_FILE:
        return {}
    try:
        from backend.gee_source import GEESource
        gee = GEESource()
    except Exception as exc:
        log.warning("Raster görüntüleri atlandı (GEE bağlanamadı): %s", exc)
        return {}
    y, m = src.latest()
    out = {}
    for rid in REGIONS:
        try:
            t = gee.raster_thumbs(rid, y, m)
        except Exception as exc:
            log.warning("[%s] raster görüntüsü alınamadı: %s", rid, exc)
            continue
        for name in ("ndvi", "vci"):
            (api / "raster").mkdir(parents=True, exist_ok=True)
            (api / "raster" / f"{rid}-{name}.png").write_bytes(t[name])
        out[rid] = {"period": f"{y}-{m:02d}", "bounds": t["bounds"],
                    "ndvi": f"api/raster/{rid}-ndvi.png", "vci": f"api/raster/{rid}-vci.png"}
    return out


def build(out: Path, force_demo: bool = False, with_raster: bool = True) -> dict:
    src = pick_source(force_demo)
    service.set_source(src)
    if out.exists():
        shutil.rmtree(out)
    api = out / "api"
    copy_frontend(out)

    latest = src.latest()
    months = month_range(latest)
    stats = {"maps": 0, "cells": 0}
    for rid in REGIONS:
        log.info("[%s] haritalar…", rid)
        for y, m in months:
            write_json(api / "map" / rid / f"{y}-{m:02d}.json", service.region_map(rid, y, m))
            stats["maps"] += 1
        write_json(api / "timeseries" / f"{rid}.json", service.region_timeseries(rid))
        for m in range(1, 13):
            write_json(api / "drought-history" / rid / f"{m}.json", service.drought_history(rid, m))
        # Her tarım hücresi için tarla raporu (tıklanınca açılan panel)
        for f in service.region_map(rid, *latest)["features"]:
            p = f["properties"]
            write_json(api / "cell" / rid / f"{p['id']}.json", service.point_report(p["lat"], p["lon"]))
            stats["cells"] += 1

    write_json(api / "regions.json", service.regions())
    write_json(api / "places.json", places.as_json())
    alerts_state = store.STORE_DIR / "alerts_state.json"
    public = json.loads(alerts_state.read_text(encoding="utf-8"))["public"] if alerts_state.exists() else []
    write_json(api / "alerts.json", public if src.mode == "gee" else [])

    status = service.status()
    status.update({
        "static": True,
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "subscribe_form_url": os.environ.get("ABONE_FORM_URL") or None,
        "raster": build_rasters(src, api) if with_raster else {},
    })
    write_json(api / "status.json", status)
    log.info("Site hazır: %s (%d harita, %d hücre raporu, mod: %s)", out, stats["maps"], stats["cells"], src.mode)
    return {**stats, "mode": src.mode}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "_site"))
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--no-raster", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build(Path(a.out), a.demo, not a.no_raster)


if __name__ == "__main__":
    main()
