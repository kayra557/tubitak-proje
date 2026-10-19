# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **TÜBİTAK 2204 jürisi ve öğretmenler:** projeyi sunumda, bilgisayar ya da projeksiyon ekranında inceler. Yöntemin bilimsel olup olmadığına ve sonuçların okunabilir olmasına bakar.
- **Çiftçiler:** çoğunlukla telefondan, kendi tarlasının ve bölgesinin bu ay ne kadar kurak olduğuna bakar; isterse kuraklık uyarısına abone olur.

Kullanıcı yanıtı (2026-10-19): iki kitle de eşit önemde. Açılışta en çok öne çıkması gereken şey kuraklık haritası.

## Product Purpose

KuraklıkGözü, ücretsiz ve açık Sentinel-2 uydu verisini Google Earth Engine ile işleyerek Konya Kapalı Havzası,
Gediz ve Büyük Menderes havzalarındaki tarım alanlarında bitki örtüsünü (NDVI) izler. Her ayı aynı ayın 2017'den
bu yana en kötü ve en iyi değeriyle kıyaslayarak (VCI) kuruyan alanları haritada işaretler ve abone çiftçiye uyarı
gönderir. Başarı: bir ziyaretçinin birkaç saniyede "bu ay havzanın ne kadarı kurak" sorusunun cevabını görmesi.

## Positioning

Aynı ayı geçmiş yıllarla kıyaslayan VCI sayesinde "bu tarla normalde bu ay yeşil olmalıydı ama değil" durumunu
yakalar; yalnızca ESA WorldCover'a göre tarım alanı olan pikseller sayılır. Sunucusuz çalışır, her ay kendiliğinden
güncellenir ve ücretsizdir.

## Operating Context

- Statik site olarak GitHub Pages'te yayınlanır (`scripts/build_site.py`); yerelde Flask sunucusuyla da çalışır (`backend/app.py`).
- Veri her ayın 5'inde GitHub Actions ile güncellenir. Earth Engine anahtarı yoksa site **demo (yapay) veriyle** yayınlanır ve bunu açıkça yazmalıdır.
- Abonelik statik yayında Google Formu ile, yerelde sitedeki formla toplanır.
- Arayüz Türkçedir.

## Capabilities and Constraints

- Havza başına ~10 km'lik ızgara hücreleri (VCI, NDVI, geçen yıla göre değişim), 2017'den bugüne aylık seri, yıllık büyüme mevsimi eğilimi, fenoloji, yıllara göre kurak alan oranı, tarla (hücre) raporu ve öneriler, QGIS için GeoJSON indirme.
- Leaflet ve Chart.js projenin içinde (`frontend/static/vendor/`); site altlık harita karoları hariç internetsiz açılabilmeli.
- `scripts/build_site.py`, `index.html` içindeki `<script src="static/app.js"></script>` etiketini arar; bu etiket değişmemeli.
- VCI sınıfları ve renkleri `backend/config.py` içinde tanımlıdır (şiddetli < 20, orta 20–35, hafif 35–50, sağlıklı ≥ 50).

## Brand Commitments

- Adı: **KuraklıkGözü**. Proje: TÜBİTAK 2204 Lise Öğrencileri Araştırma Projeleri, Yazılım; tematik alan İklim Değişikliği / Ekolojik Denge.

## Evidence on Hand

- Gerçek uydu verisi henüz repoda yok (`data/store/` boş); şu an gösterilen her şey demo verisidir. Kullanıcı yorumu, basın, kullanıcı sayısı gibi kanıtlar yoktur ve uydurulmamalıdır.
- `docs/ekran-goruntusu.png`: sitenin ekran görüntüsü.

## Product Principles

1. Verinin kaynağı ve sınırları her zaman dürüstçe söylenir (demo modu, ızgara ölçeği, önerilerin bilgilendirme amaçlı olduğu).
2. Önce cevap: açılan ekran havzanın bu ayki kuraklık durumunu harita ve tek bir sayıyla verir.
3. Bilimsel yöntem jüri için açıkça anlatılır, çiftçi için sade dille özetlenir.
4. Telefonda da tam çalışır.

## Accessibility & Inclusion

- Renk körü kullanıcılar için kuraklık sınıfları renge ek olarak yazıyla ve sayıyla da verilir.
