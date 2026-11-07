"""QGIS için veri dışa aktarımı.

  python -m scripts.export_qgis konya 2025 5            → GeoJSON ızgara (her modda çalışır)
  python -m scripts.export_qgis konya 2025 5 --geotiff  → 30 m NDVI+VCI GeoTIFF'i Google Drive'a (GEE gerekir)

GeoJSON'u QGIS'te "Katman > Katman Ekle > Vektör Katman" ile açın ve
"vci" alanına göre "Kademeli" sembolojiyle renklendirin.
"""
import argparse
import json

from backend import service
from backend.config import DATA_DIR

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("region")
    ap.add_argument("year", type=int)
    ap.add_argument("month", type=int)
    ap.add_argument("--geotiff", action="store_true")
    a = ap.parse_args()
    if a.geotiff:
        src = service.source()
        if src.mode != "gee":
            raise SystemExit("GeoTIFF dışa aktarımı için Google Earth Engine bağlantısı gerekli (bkz. README).")
        print("GEE görevi başlatıldı:", src.export_geotiff(a.region, a.year, a.month),
              "→ https://code.earthengine.google.com/tasks adresinden takip edin.")
    else:
        data = service.region_map(a.region, a.year, a.month)
        data.pop("tiles", None)
        data.pop("summary", None)
        out = DATA_DIR / "export" / f"{a.region}_{a.year}_{a.month:02d}_kuraklik.geojson"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print("Yazıldı:", out)
