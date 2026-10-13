# KuraklıkGözü 🛰️ – Uydu ile Tarımsal Kuraklık İzleme

**TÜBİTAK 2204 – Yazılım** · Tematik alan: *Küresel Isınma ve İklim Değişikliği / Ekolojik Denge*

Türkiye'de kuraklık her yıl daha kötüleşiyor. Konya Kapalı Havzası, Gediz ve Büyük Menderes havzaları su
kıtlığı riskine yaklaşıyor; çiftçiler hangi arazinin kuruduğunu çoğu zaman geç fark ediyor.
Bu proje, **ücretsiz ve açık Sentinel-2 uydu verisini** Google Earth Engine ile işleyerek tarım alanlarındaki
bitki örtüsünü (NDVI) izleyen, kuruyan alanları haritada işaretleyen ve abone olan çiftçiye
**uyarı gönderen** bir web sitesidir.

## Nasıl çalışıyor?

| Adım | Ne oluyor | Kodda nerede |
|---|---|---|
| 1. Uydu fotoğraf çeker | Sentinel-2 Türkiye'yi ~5 günde bir 10 m çözünürlükte görüntüler | `COPERNICUS/S2_SR_HARMONIZED` |
| 2. Python ile işlenir | Bulut/gölge pikselleri atılır, NDVI = (B8 − B4)/(B8 + B4) hesaplanır, aylık medyan kompozit üretilir | `backend/gee_source.py` |
| 3. Otomatik hesaplanır | Her ayın NDVI'si aynı ayın 2017'den beri min/max'ı ile kıyaslanır → **VCI** kuraklık indeksi. Sadece ESA WorldCover'a göre tarım alanı olan pikseller sayılır | `backend/analysis.py` |
| 4. Haritada gösterilir | Yeşil = sağlıklı, kırmızı = kurak. Tarla tıklanınca geçmiş + öneri; abone çiftçiye e-posta | `frontend/`, `backend/alerts.py` |

### Kullanılan bilimsel yöntem

- **NDVI** (Normalize Fark Bitki İndeksi): Sağlıklı yaprak yakın kızılötesini (NIR, B8) güçlü yansıtır,
  kırmızı ışığı (B4) fotosentez için emer. Kuru toprakta bu fark azalır. Değer −1…+1; tarımda 0.2 altı çıplak/kuru,
  0.5 üstü yoğun bitki.
- **VCI** (Bitkisel Durum İndeksi, Kogan 1995): `VCI = (NDVI − NDVImin) / (NDVImax − NDVImin) × 100`.
  Aynı ayın geçmiş yıllarıyla kıyasladığı için "bu tarla normalde bu ay yeşil olmalıydı ama değil" durumunu yakalar.
  Sınıflar: < 20 şiddetli kuraklık · 20–35 orta · 35–50 hafif stres · ≥ 50 sağlıklı.
- **Eğilim analizi**: Her yılın büyüme mevsimi (zirve ayı ± 1 ay) ortalama NDVI'sine en küçük kareler doğrusu
  uydurulur; yıllık % değişim ve R² raporlanır.
- **Fenoloji**: Ortalama aylık NDVI eğrisinden yeşillenme, zirve ve hasat ayları çıkarılır (ekim takvimine yardımcı).

## Sitenin özellikleri

- 3 havza (Konya, Gediz, Büyük Menderes) için ~10 km'lik ızgarada kuraklık haritası (VCI / NDVI / geçen yıla göre değişim)
- GEE modunda 10 m çözünürlüklü gerçek NDVI/VCI raster katmanı
- **"Yılları oynat"**: aynı ayın 2017'den bugüne kuraklık haritasını animasyonla gösterir
- Grafikler: aylık NDVI serisi, yıldan yıla büyüme mevsimi + eğilim çizgisi, yıllara göre kurak alan oranı, bu yıl vs. ortalama yıl
- **Tarla analizi**: haritada herhangi bir noktaya tıklayın → 2017'den bugüne NDVI geçmişi, güncel durum ve öneriler
- **Çiftçi uyarı sistemi**: konum + eşik ile abonelik, aylık otomatik kontrol, e-posta bildirimi (aynı dönem için tekrar göndermez)
- **QGIS için dışa aktarma**: GeoJSON (sitedeki "QGIS için indir" düğmesi) veya 30 m GeoTIFF (`scripts/export_qgis.py`)

## Kurulum

```bash
pip install -r requirements.txt
python -m backend.app
# Tarayıcıda: http://localhost:5000
```

Google Earth Engine bağlı değilse site otomatik olarak **demo moduna** geçer: Sentinel-2 davranışını taklit eden
**yapay** veri gösterir ve sayfanın üstünde bunu açıkça belirtir. Sunum öncesi arayüzü denemek için kullanışlıdır,
ama **projede sonuç olarak demo verisini kullanmayın** — gerçek analiz için aşağıdaki GEE kurulumunu yapın.

Leaflet ve Chart.js projenin içinde (`frontend/static/vendor/`) olduğundan site, altlık harita hariç internetsiz de açılır.

### Google Earth Engine'i bağlama (gerçek uydu verisi)

1. <https://earthengine.google.com> adresinden **ticari olmayan / eğitim** amaçlı kayıt olun ve bir Google Cloud projesi oluşturun.
2. Kendi bilgisayarınızda:
   ```bash
   earthengine authenticate
   export GEE_PROJECT=sizin-proje-id
   python -m backend.app
   ```
3. Sunucuda çalıştırmak için servis hesabı kullanın:
   ```bash
   export GEE_PROJECT=sizin-proje-id
   export GEE_SERVICE_ACCOUNT=hesap@proje.iam.gserviceaccount.com
   export GEE_KEY_FILE=/yol/gee-key.json
   ```
4. Sayfanın sağ üstünde **"Google Earth Engine (Sentinel-2)"** yazısını görmelisiniz.

İlk sorgular uydu verisi işlendiği için birkaç dakika sürebilir; sonuçlar `data/cache/` içinde saklanır.
`DATA_MODE=gee` verirseniz GEE bağlanamadığında demo yerine hata verir; `DATA_MODE=demo` her zaman demo kullanır.

### E-posta uyarıları

```bash
export SMTP_HOST=smtp.gmail.com SMTP_PORT=587
export SMTP_USER=adres@gmail.com SMTP_PASSWORD=uygulama-sifresi
```

Ayarlanmazsa uyarılar yalnızca sitedeki "Uyarılar" listesinde görünür. Her ay otomatik kontrol için:

```bash
# cron: her ayın 3'ünde 08:00
0 8 3 * *  cd /proje/yolu && python -m scripts.check_alerts
```

### QGIS ile çalışma

```bash
python -m scripts.export_qgis konya 2025 5             # data/export/*.geojson
python -m scripts.export_qgis konya 2025 5 --geotiff   # Google Drive'a NDVI+VCI GeoTIFF (GEE gerekli)
```

QGIS'te *Katman → Katman Ekle → Vektör Katman* ile GeoJSON'u açıp `vci` alanına göre *Kademeli* semboloji uygulayın.

## Proje yapısı

```
backend/
  app.py           Flask sunucusu ve REST API
  config.py        Bölgeler, eşikler, ortam değişkenleri
  gee_source.py    Google Earth Engine: Sentinel-2, bulut maskesi, NDVI, VCI, harita karoları
  demo_source.py   GEE yokken yapay veri üretici
  analysis.py      NDVI, VCI, sınıflandırma, eğilim, fenoloji, öneriler
  service.py       Veri kaynağı seçimi ve analiz katmanı
  alerts.py        Abonelik + uyarı (SQLite, e-posta)
frontend/          index.html, static/app.js, static/style.css (Leaflet + Chart.js)
scripts/           check_alerts.py (cron), export_qgis.py
tests/             pytest testleri  →  python -m pytest
```

### API

| Uç nokta | Açıklama |
|---|---|
| `GET /api/status` | Veri modu ve en son ay |
| `GET /api/regions` | İzlenen havzalar |
| `GET /api/map?region=konya&year=2025&month=5` | Izgara GeoJSON + özet (+ GEE raster karo URL'leri) |
| `GET /api/timeseries?region=konya` | Aylık seri, yıllık büyüme mevsimi, eğilim, fenoloji |
| `GET /api/drought-history?region=konya&month=5` | Yıllara göre kurak alan oranı |
| `GET /api/point?lat=37.9&lon=32.6` | Tek tarla raporu ve öneriler |
| `GET /api/export.geojson?...` | QGIS için indirme |
| `GET/POST /api/subscriptions`, `DELETE /api/subscriptions/<id>` | Çiftçi abonelikleri |
| `GET /api/alerts`, `POST /api/alerts/check` | Uyarılar / kontrolü tetikle |

## Sınırlamalar ve geliştirme fikirleri

- Havza sınırları sadeleştirilmiş poligonlardır; resmî DSİ sınırlarını `data/regions/<id>.geojson` olarak eklerseniz otomatik kullanılır.
- NDVI düşüşünün tek nedeni kuraklık değildir (hasat, nadas, ürün değişimi). VCI aynı ayı kıyasladığı için bu etkiyi azaltır ama tamamen yok etmez; sonuçları yağış verisiyle (ör. CHIRPS) doğrulamak güçlü bir ek olur.
- Landsat 8/9 eklenerek eğilim analizi 2013'e kadar uzatılabilir; toprak nemi için Sentinel-1 radar verisi eklenebilir.
- Öneriler kural tabanlı ve bilgilendirme amaçlıdır; ziraat mühendisi tavsiyesinin yerini tutmaz.

## Veri kaynakları ve lisanslar

Copernicus Sentinel-2 (ESA) · ESA WorldCover 10 m 2021 (CC BY 4.0) · Google Earth Engine ·
Leaflet (BSD-2) · Chart.js (MIT) · Altlık: Esri World Imagery, OpenStreetMap.
