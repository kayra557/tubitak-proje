"""Google Earth Engine veri kaynağı (gerçek Sentinel-2 verisi).

Kullanılan veri setleri:
  * COPERNICUS/S2_SR_HARMONIZED – Sentinel-2 L2A yüzey yansıtımı (10 m, ~5 günde bir)
  * ESA/WorldCover/v200        – 10 m arazi örtüsü; sadece "tarım alanı" (sınıf 40) pikselleri analize girer

İşlem zinciri:
  1. Bölge + tarih aralığı için Sentinel-2 görüntüleri filtrelenir
  2. SCL (sahne sınıflandırma) bandıyla bulut, gölge, kar pikselleri maskelenir
  3. NDVI = (B8 - B4) / (B8 + B4) hesaplanır
  4. Ay içindeki tüm görüntülerin medyanı alınarak aylık kompozit üretilir
  5. Aynı ayın 2017'den bu yana min/max değerleriyle VCI (kuraklık indeksi) hesaplanır
  6. Sonuçlar ızgara hücrelerine ortalanıp haritaya gönderilir
"""
from __future__ import annotations

import hashlib
import json
import logging

from . import analysis
from .config import (CACHE_DIR, FIRST_YEAR, GEE_KEY_FILE, GEE_PROJECT,
                     GEE_SERVICE_ACCOUNT, REGIONS)
from .sources_common import latest_month, month_range

log = logging.getLogger(__name__)

NDVI_PALETTE = ["#a50026", "#d73027", "#f46d43", "#fdae61", "#fee08b",
                "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850", "#006837"]
VCI_PALETTE = ["#b2182b", "#ef8a62", "#fddb6d", "#a6d96a", "#1a9850"]


def _disk_cache(key: str, producer):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / (hashlib.sha1(key.encode()).hexdigest() + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    value = producer()
    path.write_text(json.dumps(value), encoding="utf-8")
    return value


class GEESource:
    mode = "gee"
    label = "Google Earth Engine (Sentinel-2)"

    def __init__(self):
        import ee  # sadece GEE modunda gerekli

        self.ee = ee
        if GEE_SERVICE_ACCOUNT and GEE_KEY_FILE:
            creds = ee.ServiceAccountCredentials(GEE_SERVICE_ACCOUNT, GEE_KEY_FILE)
            ee.Initialize(creds, project=GEE_PROJECT)
        else:
            ee.Initialize(project=GEE_PROJECT)
        self.cropland = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map").eq(40)
        # Bağlantıyı hemen doğrula; başarısızsa çağıran demo moda düşer
        ee.Number(1).getInfo()

    # ---- Earth Engine yapı taşları -------------------------------------------------

    def _ndvi_image(self, img):
        ee = self.ee
        scl = img.select("SCL")
        # 4 = bitki, 5 = çıplak toprak, 7 = sınıflandırılmamış; bulut/gölge/kar/su dışarıda
        clear = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(7))
        return (img.normalizedDifference(["B8", "B4"]).rename("NDVI")
                .updateMask(clear).updateMask(self.cropland)
                .set("system:time_start", img.get("system:time_start")))

    def _monthly(self, geom, start):
        """`start` (ee.Date) ayının medyan NDVI kompoziti. Görüntü yoksa tamamen maskeli."""
        ee = self.ee
        col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
               .filterBounds(geom)
               .filterDate(start, start.advance(1, "month"))
               .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
               .map(self._ndvi_image))
        empty = ee.Image.constant(0).toFloat().rename("NDVI").updateMask(ee.Image(0))
        return ee.Image(ee.Algorithms.If(col.size().gt(0), col.median().toFloat(), empty))

    def _vci(self, geom, year: int, month: int):
        ee = self.ee
        last_y, last_m = latest_month()
        years = [y for y in range(FIRST_YEAR, last_y + 1) if (y, month) <= (last_y, last_m)]
        hist = ee.ImageCollection([self._monthly(geom, ee.Date.fromYMD(y, month, 1)) for y in years])
        cur = self._monthly(geom, ee.Date.fromYMD(year, month, 1))
        nmin, nmax = hist.min(), hist.max()
        vci = (cur.subtract(nmin).divide(nmax.subtract(nmin).max(0.01))
               .multiply(100).clamp(0, 100).rename("VCI"))
        return cur, vci

    def _region_geom(self, region_id):
        return self.ee.Geometry.Polygon([REGIONS[region_id]["polygon"]])

    # ---- Dışa açık arayüz ----------------------------------------------------------

    def latest(self):
        return latest_month()

    def region_map(self, region_id: str, year: int, month: int) -> dict:
        key = f"map|{region_id}|{year}|{month}|{latest_month()}"
        data = _disk_cache(key, lambda: self._region_map(region_id, year, month))
        # Karo URL'leri birkaç saat geçerli olduğu için her seferinde yeniden üretilir
        try:
            data["tiles"] = self._tiles(region_id, year, month)
        except Exception as exc:  # karo üretilemese de ızgara verisi gösterilebilir
            log.warning("Karo URL'si alınamadı: %s", exc)
        return data

    def _tiles(self, region_id, year, month):
        geom = self._region_geom(region_id)
        cur, vci = self._vci(geom, year, month)
        ndvi_map = cur.clip(geom).getMapId({"min": 0, "max": 0.8, "palette": NDVI_PALETTE})
        vci_map = vci.clip(geom).getMapId({"min": 0, "max": 100, "palette": VCI_PALETTE})
        return {"ndvi": ndvi_map["tile_fetcher"].url_format,
                "vci": vci_map["tile_fetcher"].url_format}

    def _region_map(self, region_id, year, month):
        ee = self.ee
        geom = self._region_geom(region_id)
        cur, vci = self._vci(geom, year, month)
        prev = self._monthly(geom, ee.Date.fromYMD(year - 1, month, 1)) if year > FIRST_YEAR else None
        img = cur.addBands(vci).addBands(self.cropland.rename("crop").unmask(0))
        if prev is not None:
            img = img.addBands(cur.subtract(prev).rename("change"))
        cells = analysis.grid_cells(REGIONS[region_id]["polygon"])
        fc = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Rectangle(c["bbox"]), {"id": c["id"]}) for c in cells
        ])
        stats = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=200, tileScale=4)
        by_id = {f["properties"]["id"]: f["properties"] for f in stats.getInfo()["features"]}
        features = []
        for cell in cells:
            p = by_id.get(cell["id"], {})
            if (p.get("crop") or 0) < 0.05:
                continue  # tarım alanı yok denecek kadar az
            v = p.get("VCI")
            cls = analysis.classify_vci(v)
            features.append(analysis.cell_feature(cell, {
                "ndvi": _r(p.get("NDVI"), 3),
                "vci": _r(v, 1),
                "ndvi_change": _r(p.get("change"), 3),
                "crop_fraction": _r(p.get("crop"), 2),
                "class": cls["key"], "class_label": cls["label"], "color": cls["color"],
            }))
        return {"type": "FeatureCollection", "features": features}

    def _series(self, geom, scale):
        ee = self.ee
        months = month_range(latest_month())
        start = ee.Date.fromYMD(FIRST_YEAR, 1, 1)

        def one(i):
            d = start.advance(i, "month")
            val = self._monthly(geom, d).reduceRegion(
                reducer=ee.Reducer.mean(), geometry=geom, scale=scale,
                maxPixels=1e10, bestEffort=True, tileScale=4).get("NDVI")
            return ee.Feature(None, {"t": d.format("YYYY-MM"), "ndvi": val})

        fc = ee.FeatureCollection(ee.List.sequence(0, len(months) - 1).map(one))
        return [{"t": f["properties"]["t"], "ndvi": _r(f["properties"].get("ndvi"), 4)}
                for f in fc.getInfo()["features"]]

    def region_monthly(self, region_id: str) -> list[dict]:
        key = f"series|{region_id}|{latest_month()}"
        return _disk_cache(key, lambda: self._series(self._region_geom(region_id), 500))

    def point_monthly(self, lat: float, lon: float) -> list[dict]:
        key = f"point|{lat:.4f}|{lon:.4f}|{latest_month()}"
        # ~3 hektarlık bir tarla büyüklüğü
        geom = self.ee.Geometry.Point([lon, lat]).buffer(100)
        return _disk_cache(key, lambda: self._series(geom, 10))

    def export_geotiff(self, region_id: str, year: int, month: int, folder="TUBITAK_Kuraklik"):
        """NDVI + VCI rasterını QGIS'te açmak üzere Google Drive'a GeoTIFF olarak gönderir."""
        geom = self._region_geom(region_id)
        cur, vci = self._vci(geom, year, month)
        task = self.ee.batch.Export.image.toDrive(
            image=cur.addBands(vci).clip(geom), description=f"{region_id}_{year}_{month:02d}_ndvi_vci",
            folder=folder, region=geom, scale=30, crs="EPSG:4326", maxPixels=1e11)
        task.start()
        return task.id


def _r(v, n):
    return round(v, n) if isinstance(v, (int, float)) else None
