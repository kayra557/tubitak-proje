"""DEMO veri kaynağı.

Google Earth Engine hesabı bağlanmadan da sitenin çalışabilmesi için
Sentinel-2 NDVI davranışını taklit eden *yapay* veri üretir:
  * mevsimsel döngü (bölgenin ana ürününe göre zirve ayı),
  * yıldan yıla hafif azalan eğilim,
  * Türkiye'de bilinen kurak yıllar (2021, 2025) etkisi,
  * tarla ölçeğinde mekânsal çeşitlilik ve sulanan alanlar.

Bu değerler GERÇEK ÖLÇÜM DEĞİLDİR; arayüz ve analiz zincirini göstermek içindir.
Gerçek veri için README'deki GEE kurulumunu yapın.
"""
from __future__ import annotations

import hashlib
import math
from functools import lru_cache

from . import analysis
from .config import REGIONS
from .sources_common import latest_month, month_range

# Yıla özgü iklim etkisi (pozitif = yağışlı, negatif = kurak)
YEAR_EFFECT = {2017: 0.00, 2018: -0.03, 2019: 0.03, 2020: -0.01, 2021: -0.10,
               2022: 0.00, 2023: 0.02, 2024: -0.03, 2025: -0.09, 2026: -0.05}
TREND_PER_YEAR = -0.006


def _hash01(*parts) -> float:
    h = hashlib.md5("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:4], "little") / 2**32


def _smooth(lat: float, lon: float, k: float) -> float:
    """0..1 arası yumuşak mekânsal alan (sahte 'tarla deseni')."""
    v = (math.sin(lat * 7.3 * k + lon * 3.1) * math.cos(lon * 5.7 * k - lat * 2.3)
         + 0.5 * math.sin(lat * 17.0 * k - lon * 13.0))
    return (v + 1.5) / 3.0


def _region_peak(lat: float, lon: float) -> int:
    for reg in REGIONS.values():
        if analysis.point_in_polygon(lon, lat, reg["polygon"]):
            return reg["peak_month"]
    return 5


def _is_cropland(lat: float, lon: float) -> bool:
    # Tuz Gölü ve çevresi: tarım dışı
    if (lat - 38.75) ** 2 + ((lon - 33.40) * 0.8) ** 2 < 0.16:
        return False
    return _smooth(lat, lon, 1.9) > 0.28


def ndvi_at(lat: float, lon: float, year: int, month: int, peak: int | None = None) -> float:
    peak = peak or _region_peak(lat, lon)
    base = 0.12 + 0.08 * _smooth(lat, lon, 1.0)
    irrigated = _smooth(lat + 3, lon - 2, 2.7) > 0.72
    amp = (0.30 + 0.30 * _smooth(lat, lon, 1.4)) * (1.25 if irrigated else 1.0)
    d = min(abs(month - peak), 12 - abs(month - peak))
    season = math.exp(-(d ** 2) / (2 * 1.6 ** 2))
    # kuraklık en çok büyüme mevsiminde etkiler; sulanan alanlar daha dirençli
    sensitivity = 0.4 if irrigated else 1.0
    local_sens = 0.7 + 0.6 * _smooth(lat - 1, lon + 1, 3.3)
    # yağış mekânsal olarak düzensizdir: her yıl farklı bölgeler farklı etkilenir
    local_year = (_smooth(lat + year * 0.37, lon - year * 0.53, 0.9) - 0.5) * 0.18
    climate = ((YEAR_EFFECT.get(year, -0.04) + TREND_PER_YEAR * (year - 2017)) * local_sens
               + local_year) * sensitivity
    noise = (_hash01(round(lat, 3), round(lon, 3), year, month) - 0.5) * 0.04
    val = base + amp * season * (1 + climate * 3) + climate * 0.3 + noise
    return round(max(-0.1, min(0.92, val)), 4)


class DemoSource:
    mode = "demo"
    label = "Demo (yapay veri)"

    def latest(self):
        return latest_month()

    def region_map(self, region_id: str, year: int, month: int) -> dict:
        return _region_map_cached(region_id, year, month)

    def region_monthly(self, region_id: str) -> list[dict]:
        return _region_monthly_cached(region_id, self.latest())

    def point_monthly(self, lat: float, lon: float) -> list[dict]:
        peak = _region_peak(lat, lon)
        out = []
        for y, m in month_range(self.latest()):
            out.append({"t": f"{y}-{m:02d}", "ndvi": ndvi_at(lat, lon, y, m, peak)})
        return out


@lru_cache(maxsize=64)
def _region_map_cached(region_id: str, year: int, month: int) -> dict:
    reg = REGIONS[region_id]
    latest_y, _ = latest_month()
    features = []
    for cell in analysis.grid_cells(reg["polygon"]):
        lat, lon = cell["lat"], cell["lon"]
        if not _is_cropland(lat, lon):
            continue
        cur = ndvi_at(lat, lon, year, month, reg["peak_month"])
        hist = [ndvi_at(lat, lon, y, month, reg["peak_month"]) for y in range(2017, latest_y + 1)
                if (y, month) <= latest_month()]
        v = analysis.vci(cur, hist)
        prev = ndvi_at(lat, lon, year - 1, month, reg["peak_month"]) if year > 2017 else None
        cls = analysis.classify_vci(v)
        features.append(analysis.cell_feature(cell, {
            "ndvi": round(cur, 3),
            "vci": round(v, 1) if v is not None else None,
            "ndvi_change": round(cur - prev, 3) if prev is not None else None,
            "class": cls["key"], "class_label": cls["label"], "color": cls["color"],
        }))
    return {"type": "FeatureCollection", "features": features}


@lru_cache(maxsize=16)
def _region_monthly_cached(region_id: str, latest: tuple[int, int]) -> list[dict]:
    reg = REGIONS[region_id]
    cells = [c for c in analysis.grid_cells(reg["polygon"], step=0.2) if _is_cropland(c["lat"], c["lon"])]
    out = []
    for y, m in month_range(latest):
        vals = [ndvi_at(c["lat"], c["lon"], y, m, reg["peak_month"]) for c in cells]
        out.append({"t": f"{y}-{m:02d}", "ndvi": round(sum(vals) / len(vals), 4)})
    return out
