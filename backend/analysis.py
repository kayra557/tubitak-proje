"""Veri kaynağından bağımsız analiz fonksiyonları.

NDVI  = (NIR - Kırmızı) / (NIR + Kırmızı)
  Sağlıklı bitki yakın kızılötesini (NIR) güçlü yansıtır, kırmızıyı emer → NDVI yüksek.
  Kuru toprak ikisini de benzer yansıtır → NDVI düşük.

VCI   = (NDVI - NDVI_min) / (NDVI_max - NDVI_min) * 100   (Kogan, 1995)
  Bir yerin bu ayki NDVI'sini, aynı ayın geçmiş yıllardaki en kötü (min) ve
  en iyi (max) değeriyle kıyaslar. Böylece "bu toprak zaten çıplak mı, yoksa
  normalde yeşil olması gerekirken mi kurudu?" sorusu cevaplanır.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

from .config import GRID_STEP, VCI_CLASSES

MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
             "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def ndvi(nir: float, red: float) -> float | None:
    if nir is None or red is None or (nir + red) == 0:
        return None
    return (nir - red) / (nir + red)


def vci(current: float | None, history: Iterable[float | None]) -> float | None:
    vals = [v for v in history if v is not None]
    if current is None or not vals:
        return None
    lo, hi = min(vals + [current]), max(vals + [current])
    if hi - lo < 1e-6:
        return 50.0
    return max(0.0, min(100.0, (current - lo) / (hi - lo) * 100))


def classify_vci(value: float | None) -> dict:
    if value is None:
        return {"key": "veri_yok", "label": "Veri yok", "color": "#9e9e9e"}
    for upper, key, label, color in VCI_CLASSES:
        if value < upper:
            return {"key": key, "label": label, "color": color}
    return {"key": "saglikli", "label": "Sağlıklı", "color": "#1a9850"}


def linear_trend(xs: Sequence[float], ys: Sequence[float | None]) -> dict | None:
    """En küçük kareler doğrusu. Eğim (yıllık değişim) ve R² döner."""
    pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
    if len(pts) < 3:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    slope = sxy / sxx if sxx else 0.0
    intercept = my - slope * mx
    ss_tot = sum((p[1] - my) ** 2 for p in pts)
    ss_res = sum((p[1] - (intercept + slope * p[0])) ** 2 for p in pts)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return {
        "slope": slope,
        "intercept": intercept,
        "r2": r2,
        "percent_per_year": (slope / my * 100) if my else 0.0,
    }


def point_in_polygon(lon: float, lat: float, polygon: Sequence[Sequence[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def grid_cells(polygon, step: float = GRID_STEP):
    """Poligonun içine merkezi düşen kare hücreleri üretir."""
    lons = [p[0] for p in polygon]
    lats = [p[1] for p in polygon]
    x0 = math.floor(min(lons) / step) * step
    y0 = math.floor(min(lats) / step) * step
    cells = []
    y = y0
    while y < max(lats):
        x = x0
        while x < max(lons):
            cx, cy = x + step / 2, y + step / 2
            if point_in_polygon(cx, cy, polygon):
                cells.append({
                    "id": f"{round(cx, 4)}_{round(cy, 4)}",
                    "lon": round(cx, 4),
                    "lat": round(cy, 4),
                    "bbox": [round(x, 4), round(y, 4), round(x + step, 4), round(y + step, 4)],
                })
            x += step
        y += step
    return cells


def cell_feature(cell: dict, props: dict) -> dict:
    x0, y0, x1, y1 = cell["bbox"]
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon",
                     "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]},
        "properties": {"id": cell["id"], "lat": cell["lat"], "lon": cell["lon"], **props},
    }


def summarize_cells(features: list[dict]) -> dict:
    counts = {"siddetli": 0, "orta": 0, "hafif": 0, "saglikli": 0, "veri_yok": 0}
    ndvis, vcis = [], []
    for f in features:
        p = f["properties"]
        counts[p["class"]] = counts.get(p["class"], 0) + 1
        if p.get("ndvi") is not None:
            ndvis.append(p["ndvi"])
        if p.get("vci") is not None:
            vcis.append(p["vci"])
    total = sum(v for k, v in counts.items() if k != "veri_yok") or 1
    return {
        "cell_count": len(features),
        "counts": counts,
        "percent": {k: round(v / total * 100, 1) for k, v in counts.items() if k != "veri_yok"},
        "drought_percent": round((counts["siddetli"] + counts["orta"]) / total * 100, 1),
        "mean_ndvi": round(sum(ndvis) / len(ndvis), 3) if ndvis else None,
        "mean_vci": round(sum(vcis) / len(vcis), 1) if vcis else None,
    }


def phenology(monthly_climatology: Sequence[float | None]) -> dict | None:
    """12 aylık ortalama NDVI eğrisinden yeşillenme / zirve / hasat aylarını çıkarır."""
    vals = list(monthly_climatology)
    if len(vals) != 12 or any(v is None for v in vals):
        return None
    peak = max(range(12), key=lambda i: vals[i])
    low = min(range(12), key=lambda i: vals[i])
    amp = vals[peak] - vals[low]
    if amp < 0.05:
        return {"peak_month": peak + 1, "green_up_month": None, "senescence_month": None, "amplitude": amp}
    thr = vals[low] + 0.3 * amp
    # Zirveden geriye doğru giderek eşiğin altına ilk düşülen ay → yeşillenme başlangıcı
    green = peak
    for k in range(1, 12):
        i = (peak - k) % 12
        if vals[i] < thr:
            green = (i + 1) % 12
            break
    senes = peak
    for k in range(1, 12):
        i = (peak + k) % 12
        if vals[i] < thr:
            senes = i
            break
    return {"peak_month": peak + 1, "green_up_month": green + 1,
            "senescence_month": senes + 1, "amplitude": round(amp, 3)}


def in_season(month: int, peak_month: int) -> bool:
    """Büyüme mevsimi: zirve ayından 2 ay önce – 1 ay sonra (ör. zirve Mayıs → Mart–Haziran).

    Bu dönem dışında (hasat sonrası, ekim öncesi) tarlalar çoğunlukla çıplaktır ve VCI
    kuraklık hakkında güvenilir bilgi vermez.
    """
    d = (month - peak_month) % 12
    return d >= 10 or d <= 1


def season_label(peak_month: int) -> str:
    first = MONTHS_TR[(peak_month - 3) % 12]
    last = MONTHS_TR[peak_month % 12]
    return f"{first}–{last}"


def farmer_advice(vci_value: float | None, trend: dict | None, pheno: dict | None,
                  month: int) -> list[str]:
    """Kural tabanlı, bilgilendirme amaçlı öneriler (ziraat mühendisi tavsiyesinin yerini tutmaz)."""
    tips = []
    cls = classify_vci(vci_value)["key"]
    if cls == "siddetli":
        tips.append("Bitki örtüsü aynı ayın geçmiş yıllarına göre en kötü düzeyde. "
                    "Sulama planını gözden geçirin; mümkünse damla/yağmurlama sulamaya geçin.")
    elif cls == "orta":
        tips.append("Belirgin su stresi var. Toprak nemini kontrol edin, sulama aralığını kısaltmayı düşünün.")
    elif cls == "hafif":
        tips.append("Hafif stres belirtisi var. Önümüzdeki 2-3 hafta uydu takibini sürdürün.")
    elif cls == "saglikli":
        tips.append("Bitki gelişimi bu mevsim için normal veya normalin üstünde.")
    if trend and trend["percent_per_year"] < -1:
        tips.append(f"Bu alanda büyüme mevsimi NDVI'si yılda ortalama %{abs(trend['percent_per_year']):.1f} "
                    "azalıyor. Kuraklığa dayanıklı çeşitler ve su tasarruflu sulama uzun vadede önemli.")
    if pheno and pheno.get("green_up_month"):
        g = pheno["green_up_month"]
        tips.append(f"Uydu geçmişine göre bu alanda bitkiler genelde {MONTHS_TR[g - 1]} ayında yeşillenmeye "
                    f"başlıyor ve {MONTHS_TR[pheno['peak_month'] - 1]} ayında en yeşil hâline ulaşıyor. "
                    "Ekim zamanını bu takvime ve yerel ziraat müdürlüğünün önerisine göre planlayın.")
    return tips
