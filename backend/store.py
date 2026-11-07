"""Uydu verisi deposu: her bölgenin ızgara hücreleri için aylık NDVI değerleri.

`data/store/<bölge>.json` dosyalarında tutulur ve repoya kaydedilir. Böylece
Google Earth Engine'e her ay yalnızca yeni ay için sorgu gider; site ve
analizler bu dosyalardan üretilir.

Dosya yapısı:
    {
      "region": "konya",
      "source": "gee",
      "grid_step": 0.1,
      "polygon_hash": "...",
      "cells": [{"id", "lat", "lon", "bbox", "crop"}],   # crop = tarım alanı oranı (0..1)
      "months": {"2017-01": [hücre sırasıyla NDVI veya null], ...},
      "updated_at": "..."
    }
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from .config import DATA_DIR, GRID_STEP, REGIONS

STORE_DIR = DATA_DIR / "store"
# Tarım alanı oranı bunun altındaki hücreler analize girmez
MIN_CROP = 0.05


def polygon_hash(region_id: str) -> str:
    return hashlib.sha1(json.dumps(REGIONS[region_id]["polygon"]).encode()).hexdigest()[:12]


def path(region_id: str) -> Path:
    return STORE_DIR / f"{region_id}.json"


def load(region_id: str) -> dict | None:
    p = path(region_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_all() -> dict[str, dict]:
    """Bölge sınırı ve ızgara boyutu güncel olan depoları döner."""
    out = {}
    for rid in REGIONS:
        st = load(rid)
        if st and is_current(st, rid):
            out[rid] = st
    return out


def is_current(st: dict, region_id: str) -> bool:
    return st.get("grid_step") == GRID_STEP and st.get("polygon_hash") == polygon_hash(region_id)


def new_store(region_id: str, source: str, cells: list[dict]) -> dict:
    return {"region": region_id, "source": source, "grid_step": GRID_STEP,
            "polygon_hash": polygon_hash(region_id), "cells": cells, "months": {}, "updated_at": None}


def set_month(st: dict, key: str, values: list[float | None]) -> None:
    st["months"][key] = [round(v, 4) if isinstance(v, (int, float)) else None for v in values]


def save(st: dict) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    st["months"] = dict(sorted(st["months"].items()))
    st["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    tmp = path(st["region"]).with_suffix(".tmp")
    # Okunabilir ama küçük: her ay bir satır
    lines = [f'{json.dumps(k)}: {json.dumps(v, separators=(",", ":"))}' for k, v in st["months"].items()]
    head = {k: v for k, v in st.items() if k != "months"}
    text = json.dumps(head, ensure_ascii=False, separators=(",", ":"))[:-1]
    text += ',\n"months": {\n' + ",\n".join(lines) + "\n}}\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path(st["region"]))


def latest_key(st: dict) -> str | None:
    """Herhangi bir hücrede verisi olan en son ay (YYYY-MM)."""
    keys = [k for k, v in st["months"].items() if any(x is not None for x in v)]
    return max(keys) if keys else None
