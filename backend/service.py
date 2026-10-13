"""Veri kaynağını seçer ve ham NDVI verisinden analiz sonuçları üretir."""
from __future__ import annotations

import logging
from collections import defaultdict

from . import analysis, places
from .config import DATA_MODE, REGIONS
from .demo_source import DemoSource

log = logging.getLogger(__name__)
_source = None
_source_error = None


def source():
    global _source, _source_error
    if _source is None:
        if DATA_MODE != "demo":
            try:
                from .gee_source import GEESource
                _source = GEESource()
                log.info("Google Earth Engine bağlantısı kuruldu.")
            except Exception as exc:
                _source_error = str(exc)
                if DATA_MODE == "gee":
                    raise
                log.warning("GEE kullanılamıyor, demo veriye geçiliyor: %s", exc)
        if _source is None:
            _source = DemoSource()
    return _source


def status() -> dict:
    src = source()
    y, m = src.latest()
    return {"mode": src.mode, "label": src.label, "latest": {"year": y, "month": m},
            "gee_error": _source_error}


def regions() -> list[dict]:
    return [{"id": rid, "name": r["name"], "center": r["center"], "zoom": r["zoom"],
             "peak_month": r["peak_month"],
             "polygon": r["polygon"]} for rid, r in REGIONS.items()]


def region_map(region_id: str, year: int, month: int) -> dict:
    data = source().region_map(region_id, year, month)
    return {**data, "summary": analysis.summarize_cells(data["features"]),
            "region": region_id, "year": year, "month": month}


def drought_history(region_id: str, month: int) -> list[dict]:
    """Seçilen ay için her yıl kurak (VCI < 35) tarım alanı oranı."""
    from .config import FIRST_YEAR

    ly, lm = source().latest()
    out = []
    for y in range(FIRST_YEAR, ly + 1):
        if (y, month) > (ly, lm):
            break
        s = analysis.summarize_cells(source().region_map(region_id, y, month)["features"])
        out.append({"year": y, "drought_percent": s["drought_percent"], "mean_vci": s["mean_vci"],
                    "mean_ndvi": s["mean_ndvi"]})
    return out


def _analyze_series(series: list[dict], peak_month: int) -> dict:
    """Aylık NDVI serisinden yıllık büyüme mevsimi ortalaması, eğilim ve klimatoloji."""
    from .sources_common import season_months

    by_month = defaultdict(list)
    by_year = defaultdict(dict)
    for row in series:
        y, m = map(int, row["t"].split("-"))
        by_year[y][m] = row["ndvi"]
        if row["ndvi"] is not None:
            by_month[m].append(row["ndvi"])
    clim = [round(sum(v) / len(v), 4) if v else None for v in (by_month[m] for m in range(1, 13))]
    pheno = analysis.phenology(clim)
    peak = pheno["peak_month"] if pheno else peak_month
    smonths = season_months(peak)

    yearly = []
    for y in sorted(by_year):
        vals = [by_year[y].get(m) for m in smonths]
        # Zirve Ocak/Aralık'a denk gelirse mevsim yıl sınırını aşabilir; basitlik için aynı yıl alınır
        if all(v is not None for v in vals):
            yearly.append({"year": y, "season_ndvi": round(sum(vals) / len(vals), 4)})
    trend = analysis.linear_trend([r["year"] for r in yearly], [r["season_ndvi"] for r in yearly])
    if trend:
        trend = {k: round(v, 5) for k, v in trend.items()}
    return {"monthly": series, "climatology": clim, "phenology": pheno,
            "season_months": smonths, "yearly": yearly, "trend": trend}


def region_timeseries(region_id: str) -> dict:
    reg = REGIONS[region_id]
    return {"region": region_id, **_analyze_series(source().region_monthly(region_id), reg["peak_month"])}


def point_report(lat: float, lon: float) -> dict:
    src = source()
    series = src.point_monthly(lat, lon)
    peak = 5
    region_id = None
    for rid, reg in REGIONS.items():
        if analysis.point_in_polygon(lon, lat, reg["polygon"]):
            peak, region_id = reg["peak_month"], rid
            break
    res = _analyze_series(series, peak)
    # Son ayın VCI'si: aynı ayın tüm yıllarıyla kıyas
    last = next((r for r in reversed(series) if r["ndvi"] is not None), None)
    current = None
    if last:
        y, m = map(int, last["t"].split("-"))
        same_month = [r["ndvi"] for r in series if int(r["t"][5:]) == m]
        v = analysis.vci(last["ndvi"], same_month)
        cls = analysis.classify_vci(v)
        prev = next((r["ndvi"] for r in series if r["t"] == f"{y - 1}-{m:02d}"), None)
        current = {"t": last["t"], "ndvi": last["ndvi"], "vci": round(v, 1) if v is not None else None,
                   "class": cls["key"], "class_label": cls["label"], "color": cls["color"],
                   "ndvi_change": round(last["ndvi"] - prev, 3) if prev is not None else None}
        res["advice"] = analysis.farmer_advice(v, res["trend"], res["phenology"], m)
    return {"lat": lat, "lon": lon, "region": region_id, "nearest_place": places.nearest(lat, lon),
            "current": current, **res}
