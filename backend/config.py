"""Uygulama ayarları ve izlenen bölgeler.

Bölge sınırları havzaların yaklaşık (sadeleştirilmiş) poligonlarıdır.
Resmî DSİ havza sınırları elinizdeyse `data/regions/<id>.geojson` dosyası
olarak koyabilirsiniz; uygulama onu otomatik olarak kullanır.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "uyarilar.db"))
CACHE_DIR = DATA_DIR / "cache"

# Google Earth Engine kimlik bilgileri (bkz. README)
GEE_PROJECT = os.environ.get("GEE_PROJECT")
GEE_SERVICE_ACCOUNT = os.environ.get("GEE_SERVICE_ACCOUNT")
GEE_KEY_FILE = os.environ.get("GEE_KEY_FILE")
# "demo" verilirse GEE hiç denenmez
DATA_MODE = os.environ.get("DATA_MODE", "auto")

# E-posta uyarıları (boş bırakılırsa uyarılar sadece sitede gösterilir)
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER or "")

# Sentinel-2 L2A verisi Türkiye için 2017'den beri tutarlı şekilde mevcut
FIRST_YEAR = 2017

# Izgara hücre boyutu (derece). 0.1° ≈ 9 x 11 km
GRID_STEP = 0.1

# Bitkisel Durum İndeksi (VCI, Kogan 1995) sınıfları
VCI_CLASSES = [
    # (üst sınır, anahtar, etiket, renk)
    (20, "siddetli", "Şiddetli kuraklık", "#b2182b"),
    (35, "orta", "Orta kuraklık", "#ef8a62"),
    (50, "hafif", "Hafif stres", "#fddb6d"),
    (101, "saglikli", "Sağlıklı", "#1a9850"),
]

_DEFAULT_REGIONS = {
    "konya": {
        "name": "Konya Kapalı Havzası",
        "center": [37.95, 33.1],
        "zoom": 8,
        # Ana ürün: kışlık buğday/arpa, şeker pancarı, mısır
        "peak_month": 5,
        "polygon": [
            [31.45, 38.05], [31.75, 38.75], [32.45, 39.25], [33.30, 39.30],
            [34.10, 39.05], [34.75, 38.55], [34.85, 37.85], [34.35, 37.25],
            [33.55, 36.95], [32.70, 37.05], [32.05, 37.35], [31.60, 37.70],
            [31.45, 38.05],
        ],
    },
    "gediz": {
        "name": "Gediz Havzası",
        "center": [38.65, 28.2],
        "zoom": 9,
        # Üzüm, pamuk, mısır, zeytin
        "peak_month": 6,
        "polygon": [
            [26.80, 38.55], [27.05, 38.85], [27.70, 38.95], [28.40, 39.20],
            [29.10, 39.25], [29.55, 39.00], [29.45, 38.65], [28.90, 38.45],
            [28.20, 38.35], [27.55, 38.40], [27.05, 38.40], [26.80, 38.55],
        ],
    },
    "menderes": {
        "name": "Büyük Menderes Havzası",
        "center": [37.85, 28.6],
        "zoom": 8,
        # Pamuk, incir, zeytin, mısır
        "peak_month": 7,
        "polygon": [
            [27.25, 37.55], [27.35, 37.95], [27.95, 38.15], [28.65, 38.25],
            [29.40, 38.30], [30.10, 38.25], [30.30, 37.95], [29.95, 37.55],
            [29.30, 37.35], [28.60, 37.35], [27.90, 37.40], [27.25, 37.55],
        ],
    },
}


def _load_regions():
    regions = {}
    for rid, reg in _DEFAULT_REGIONS.items():
        reg = dict(reg)
        custom = DATA_DIR / "regions" / f"{rid}.geojson"
        if custom.exists():
            gj = json.loads(custom.read_text(encoding="utf-8"))
            geom = gj["features"][0]["geometry"] if gj.get("type") == "FeatureCollection" else gj.get("geometry", gj)
            if geom["type"] == "Polygon":
                reg["polygon"] = geom["coordinates"][0]
        regions[rid] = reg
    return regions


REGIONS = _load_regions()
