"""Depodaki (data/store) aylık ızgara NDVI değerlerinden çalışan veri kaynağı.

Analiz için Earth Engine'e bağlanmaz; bu yüzden hızlıdır ve internet olmadan da
çalışır. Statik site üretimi ve demo modu bu sınıfı kullanır.
"""
from __future__ import annotations

from . import analysis
from .config import REGIONS
from .sources_common import month_range
from .store import MIN_CROP, latest_key


class StoreSource:
    mode = "gee"
    label = "Google Earth Engine (Sentinel-2)"
    # Tıklanan nokta için hücre (≈10 km) ortalaması döner, tek tarla değil
    point_scale = "cell"
    live = False

    def __init__(self, stores: dict[str, dict]):
        if not stores:
            raise ValueError("Depoda veri yok")
        self.stores = stores
        self._active = {rid: [i for i, c in enumerate(st["cells"]) if (c.get("crop") or 0) >= MIN_CROP]
                        for rid, st in stores.items()}
        # Tüm bölgelerde bulunan en son ay
        keys = [latest_key(st) for st in stores.values()]
        if not all(keys):
            raise ValueError("Depoda ölçümü olmayan bölge var")
        y, m = map(int, min(keys).split("-"))
        self._latest = (y, m)

    # ---- yardımcılar ----------------------------------------------------------

    def latest(self) -> tuple[int, int]:
        return self._latest

    def coverage(self) -> dict:
        expected = [f"{y}-{m:02d}" for y, m in month_range(self.latest())]
        have = sum(1 for st in self.stores.values() for k in expected if k in st["months"])
        total = len(expected) * len(self.stores)
        return {"months_have": have, "months_expected": total, "complete": have >= total}

    def _series_for_cell(self, rid: str, i: int) -> list[dict]:
        months = self.stores[rid]["months"]
        out = []
        for y, m in month_range(self.latest()):
            vals = months.get(f"{y}-{m:02d}")
            out.append({"t": f"{y}-{m:02d}", "ndvi": vals[i] if vals else None})
        return out

    def find_cell(self, lat: float, lon: float) -> tuple[str, int] | None:
        for rid, st in self.stores.items():
            for i in self._active[rid]:
                x0, y0, x1, y1 = st["cells"][i]["bbox"]
                if x0 <= lon < x1 and y0 <= lat < y1:
                    return rid, i
        return None

    # ---- veri kaynağı arayüzü ---------------------------------------------------

    def region_map(self, region_id: str, year: int, month: int) -> dict:
        st = self.stores[region_id]
        months = st["months"]
        key = f"{year}-{month:02d}"
        cur_vals = months.get(key)
        prev_vals = months.get(f"{year - 1}-{month:02d}")
        latest = "%d-%02d" % self._latest
        hist_keys = [k for k in months if k.endswith(f"-{month:02d}") and k <= latest]
        features = []
        for i in self._active[region_id]:
            cell = st["cells"][i]
            cur = cur_vals[i] if cur_vals else None
            prev = prev_vals[i] if prev_vals else None
            v = analysis.vci(cur, [months[k][i] for k in hist_keys])
            cls = analysis.classify_vci(v)
            features.append(analysis.cell_feature(cell, {
                "ndvi": round(cur, 3) if cur is not None else None,
                "vci": round(v, 1) if v is not None else None,
                "ndvi_change": round(cur - prev, 3) if cur is not None and prev is not None else None,
                "crop_fraction": round(cell.get("crop") or 0, 2),
                "class": cls["key"], "class_label": cls["label"], "color": cls["color"],
            }))
        return {"type": "FeatureCollection", "features": features}

    def region_monthly(self, region_id: str) -> list[dict]:
        """Bölgenin aylık ortalama NDVI'si (hücreler tarım alanı oranıyla ağırlıklı)."""
        st = self.stores[region_id]
        weights = {i: st["cells"][i]["crop"] for i in self._active[region_id]}
        out = []
        for y, m in month_range(self.latest()):
            vals = st["months"].get(f"{y}-{m:02d}")
            num = den = 0.0
            if vals:
                for i, w in weights.items():
                    if vals[i] is not None:
                        num += vals[i] * w
                        den += w
            out.append({"t": f"{y}-{m:02d}", "ndvi": round(num / den, 4) if den else None})
        return out

    def point_monthly(self, lat: float, lon: float) -> list[dict]:
        hit = self.find_cell(lat, lon)
        return self._series_for_cell(*hit) if hit else []


def cells_for_region(region_id: str) -> list[dict]:
    return analysis.grid_cells(REGIONS[region_id]["polygon"])
