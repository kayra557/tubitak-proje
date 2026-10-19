/* KuraklıkGözü – istemci tarafı */
"use strict";

const MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
  "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
// Şiddetliden sağlıklıya: lejant, yığılmış çubuk ve tarla durumu aynı sırayı kullanır
const CLASSES = [
  { key: "siddetli", label: "Şiddetli kuraklık", range: "VCI 20'nin altı", color: "#b2182b" },
  { key: "orta", label: "Orta kuraklık", range: "20–35", color: "#ef8a62" },
  { key: "hafif", label: "Hafif stres", range: "35–50", color: "#fddb6d" },
  { key: "saglikli", label: "Sağlıklı", range: "50 ve üstü", color: "#1a9850" },
];
const NDVI_RAMP = ["#a50026", "#d73027", "#f46d43", "#fdae61", "#fee08b",
  "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850", "#006837"];
const CHANGE_RAMP = ["#b2182b", "#ef8a62", "#fddbc7", "#f7f7f7", "#d9f0d3", "#7fbf7b", "#1b7837"];

const $ = (id) => document.getElementById(id);
const state = { status: null, regions: [], region: "konya", year: null, month: null, layer: "vci",
  mapData: null, playing: false, point: null, places: [], history: null };
const charts = {};

// ---------------------------------------------------------------- yardımcılar
// Statik yayında (GitHub Pages) veriler önceden üretilmiş JSON dosyalarından okunur,
// yerel Flask sunucusunda ise API'den. Yollar göreli: site bir alt klasörde de çalışır.
const STATIC = !!window.KG_STATIC;
const pad2 = (n) => String(n).padStart(2, "0");
const URLS = STATIC ? {
  status: () => "api/status.json",
  regions: () => "api/regions.json",
  places: () => "api/places.json",
  map: (r, y, m) => `api/map/${r}/${y}-${pad2(m)}.json`,
  exportMap: (r, y, m) => `api/map/${r}/${y}-${pad2(m)}.json`,
  timeseries: (r) => `api/timeseries/${r}.json`,
  droughtHistory: (r, m) => `api/drought-history/${r}/${m}.json`,
  cell: (r, id) => `api/cell/${r}/${id}.json`,
  alerts: () => "api/alerts.json",
} : {
  status: () => "api/status",
  regions: () => "api/regions",
  places: () => "api/places",
  map: (r, y, m) => `api/map?region=${r}&year=${y}&month=${m}`,
  exportMap: (r, y, m) => `api/export.geojson?region=${r}&year=${y}&month=${m}`,
  timeseries: (r) => `api/timeseries?region=${r}`,
  droughtHistory: (r, m) => `api/drought-history?region=${r}&month=${m}`,
  point: (lat, lon) => `api/point?lat=${lat}&lon=${lon}`,
  alerts: () => "api/alerts",
  subscriptions: () => "api/subscriptions",
};

async function api(path, opts) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `Veri alınamadı (${res.status})`);
  return body;
}

// Statik modda tıklanan noktayı içeren ızgara hücresini bulur
function findCell(lat, lon) {
  for (const f of (state.mapData && state.mapData.features) || []) {
    const ring = f.geometry.coordinates[0];
    const [x0, y0] = ring[0], [x1, y1] = ring[2];
    if (lon >= x0 && lon < x1 && lat >= y0 && lat < y1) return f.properties;
  }
  return null;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function ramp(colors, t) {
  t = Math.max(0, Math.min(1, t));
  const x = t * (colors.length - 1), i = Math.min(Math.floor(x), colors.length - 2), f = x - i;
  const a = hexToRgb(colors[i]), b = hexToRgb(colors[i + 1]);
  return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(",")})`;
}
const fmt = (v, d = 2) => (v === null || v === undefined ? "–" : Number(v).toFixed(d));
// Kurak alan payı her yerde aynı biçimde (tam sayı) yazılır: başlık, büyük sayı ve yıl şeridi aynı değeri gösterir
const pct = (v) => (v === null || v === undefined ? "–" : `%${Math.round(v)}`);
const signed = (v, d = 2) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d);
const regionObj = () => state.regions.find((r) => r.id === state.region);
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const periodText = (y = state.year, m = state.month) => `${MONTHS[m - 1]} ${y}`;

function cellColor(p) {
  if (state.layer === "ndvi") return p.ndvi === null ? "#9e9e9e" : ramp(NDVI_RAMP, p.ndvi / 0.8);
  if (state.layer === "change") return p.ndvi_change === null ? "#9e9e9e" : ramp(CHANGE_RAMP, (p.ndvi_change + 0.2) / 0.4);
  return p.color;
}

// ---------------------------------------------------------------- harita
let map, gridLayer, outlineLayer, rasterLayer, pointMarker, placeLayer, selectedCell;

function initMap() {
  map = L.map("map", { zoomControl: true, preferCanvas: true }).setView([38.5, 31], 7);
  const sat = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 18, attribution: "Uydu altlık © Esri" });
  const osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 18, attribution: "© OpenStreetMap" });
  sat.addTo(map);
  // Şehir/ilçe adları ve il sınırları: kuraklık karelerinin üstünde dursun, tıklamayı engellemesin
  map.createPane("labels");
  map.getPane("labels").style.zIndex = 650;
  map.getPane("labels").style.pointerEvents = "none";
  const labels = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    { pane: "labels", maxZoom: 18, attribution: "Yer adları © Esri" });

  placeLayer = L.layerGroup().addTo(map);
  L.control.layers({ "Uydu görüntüsü": sat, "Sokak haritası": osm },
    { "İl ve ilçe adları (Türkçe)": placeLayer, "Esri yer adları ve sınırlar": labels },
    { position: "topright" }).addTo(map);
  map.on("zoomend", updatePlaceVisibility);
  L.control.scale({ imperial: false }).addTo(map);
  map.on("click", (e) => loadPoint(e.latlng.lat, e.latlng.lng));
  // Tarla paneli açılınca harita kartı uzar; Leaflet'e yeni boyutu bildir
  new ResizeObserver(() => map.invalidateSize({ pan: false })).observe($("map"));
}

// İl adları her zaman, ilçe adları yakınlaşınca (zoom ≥ 9) görünür
function distanceKm(lat, lon, p) {
  const dx = (p.lon - lon) * 111.32 * Math.cos(lat * Math.PI / 180), dy = (p.lat - lat) * 110.57;
  return Math.hypot(dx, dy);
}

function nearestPlace(lat, lon) {
  let best = null;
  for (const p of state.places) {
    const d = distanceKm(lat, lon, p);
    if (!best || d < best.distance_km) best = { ...p, distance_km: Math.round(d * 10) / 10 };
  }
  return best;
}

function drawPlaces(list) {
  state.places = list;
  list.forEach((p) => {
    L.marker([p.lat, p.lon], {
      interactive: false, keyboard: false, pane: "labels",
      icon: L.divIcon({ className: `place-label ${p.type}`, html: `<span>${esc(p.name)}</span>`, iconSize: null }),
    }).addTo(placeLayer);
  });
  updatePlaceVisibility();
  if (state.mapData) renderRank();
}

function updatePlaceVisibility() {
  map.getContainer().classList.toggle("show-ilce", map.getZoom() >= 9);
}

function drawGrid() {
  if (gridLayer) gridLayer.remove();
  const d = state.mapData;
  const raster = $("raster").checked;
  gridLayer = L.geoJSON(d, {
    style: (f) => ({ color: cellColor(f.properties), weight: 0.4, fillColor: cellColor(f.properties),
      fillOpacity: raster ? 0.0 : 0.66, opacity: raster ? 0.3 : 0.8 }),
    onEachFeature: (f, layer) => {
      const p = f.properties;
      layer.bindTooltip(
        `<b>${esc(p.class_label)}</b><br><span class="num">NDVI ${fmt(p.ndvi)} · VCI ${fmt(p.vci, 0)}` +
        (p.ndvi_change !== null ? ` · geçen yıla göre ${signed(p.ndvi_change)}` : "") + "</span>",
        { sticky: true, direction: "top", offset: [0, -8] });
      layer.on("click", (e) => { L.DomEvent.stopPropagation(e); loadPoint(e.latlng.lat, e.latlng.lng); });
    },
  }).addTo(map);
  drawLegend();
  markSelectedCell();
}

function drawRaster() {
  if (rasterLayer) { rasterLayer.remove(); rasterLayer = null; }
  if (!$("raster").checked) return;
  const attribution = "Sentinel-2 / Google Earth Engine";
  if (STATIC) {
    // Statik yayında sadece son ayın görüntüsü vardır
    const ri = (state.status.raster || {})[state.region];
    if (!ri || ri.period !== `${state.year}-${pad2(state.month)}`) return;
    rasterLayer = L.imageOverlay(state.layer === "ndvi" ? ri.ndvi : ri.vci, ri.bounds,
      { opacity: 0.85, attribution }).addTo(map);
  } else {
    const tiles = state.mapData && state.mapData.tiles;
    if (!tiles) return;
    rasterLayer = L.tileLayer(state.layer === "ndvi" ? tiles.ndvi : tiles.vci, { opacity: 0.85, attribution }).addTo(map);
  }
  if (gridLayer) gridLayer.bringToFront();
}

function drawOutline() {
  if (outlineLayer) outlineLayer.remove();
  const r = regionObj();
  outlineLayer = L.polygon(r.polygon.map(([lon, lat]) => [lat, lon]),
    { color: "#ffffff", weight: 2, dashArray: "6 4", fill: false, interactive: false }).addTo(map);
}

// Tıklanan kareyi (statik yayında raporun ölçeği) haritada çerçeveler
function markSelectedCell() {
  if (selectedCell) { selectedCell.remove(); selectedCell = null; }
  if (!state.point || !STATIC) return;
  const id = (findCell(state.point.lat, state.point.lon) || {}).id;
  const f = id && state.mapData.features.find((x) => x.properties.id === id);
  if (!f) return;
  selectedCell = L.geoJSON(f, { style: { color: "#ffffff", weight: 2.5, fill: false }, interactive: false }).addTo(map);
}

// Lejant haritanın altında durur ve sınıf paylarını da taşır (her renk, haritadaki karenin rengidir)
function drawLegend() {
  const el = $("legend");
  if (state.layer === "vci") {
    const s = state.mapData.summary;
    const p = (k) => (s.cell_count ? s.percent[k] ?? 0 : 0);
    el.innerHTML = `<p class="legend-title">Tarım alanlarının kuraklık durumu, ${periodText()}</p>
      <div class="stack" role="img" aria-label="${CLASSES.map((c) => `${c.label} ${pct(p(c.key))}`).join(", ")}">
        ${CLASSES.map((c) => `<span style="flex-grow:${p(c.key)};background:${c.color}"></span>`).join("")}</div>
      <div class="legend-items">${CLASSES.map((c) => `<div class="legend-item">
        <span class="sw" style="background:${c.color}"></span><span>${c.label}</span>
        <b class="num">${s.cell_count ? pct(p(c.key)) : "–"}</b><small>${c.range}</small></div>`).join("")}</div>`;
  } else if (state.layer === "ndvi") {
    el.innerHTML = `<p class="legend-title">NDVI, bitki örtüsünün yoğunluğu</p>${steps(NDVI_RAMP)}
      <div class="ramp-ticks num"><span>0 çıplak toprak</span><span>0.4</span><span>0.8 yoğun bitki</span></div>`;
  } else {
    el.innerHTML = `<p class="legend-title">NDVI değişimi, geçen yılın aynı ayına göre</p>${steps(CHANGE_RAMP)}
      <div class="ramp-ticks num"><span>−0.2 kuruma</span><span>0</span><span>+0.2 iyileşme</span></div>`;
  }
}

// Sürekli renk ölçeği, haritadaki renklerle aynı duraklarda basamaklı çubuk olarak
const steps = (colors) => `<div class="ramp">${colors.map((c) => `<span style="background:${c}"></span>`).join("")}</div>`;

function renderStats() {
  const s = state.mapData.summary;
  $("s-drought").textContent = s.cell_count ? pct(s.drought_percent) : "–";
  $("s-when").textContent = `${periodText()} · VCI 35'in altındaki tarım alanlarının payı`;
  $("s-vci").textContent = fmt(s.mean_vci, 0);
  $("s-ndvi").textContent = fmt(s.mean_ndvi);
  $("s-cells").textContent = s.cell_count;
  renderCompare();
  renderRank();
}

// Kareleri en yakın il/ilçe merkezine göre gruplar; kurak payı en yüksek yerleşimler başta
function renderRank() {
  const list = $("rank-list");
  if (!state.places.length) { list.innerHTML = `<li class="empty">Yerleşim listesi yükleniyor…</li>`; return; }
  const groups = new Map();
  for (const f of state.mapData.features) {
    const p = f.properties;
    if (p.vci === null) continue;
    const np = nearestPlace(p.lat, p.lon);
    if (!np || np.distance_km > 60) continue;
    const g = groups.get(np.name) || { place: np, n: 0, dry: 0, vci: 0 };
    g.n += 1; g.vci += p.vci;
    if (p.class === "siddetli" || p.class === "orta") g.dry += 1;
    groups.set(np.name, g);
  }
  const rows = [...groups.values()].filter((g) => g.n >= 3)
    .map((g) => ({ ...g, share: g.dry / g.n * 100, meanVci: g.vci / g.n }))
    .sort((a, b) => b.share - a.share || a.meanVci - b.meanVci).slice(0, 5);
  list.innerHTML = rows.length ? rows.map((r) => `<li><button type="button" data-lat="${r.place.lat}" data-lon="${r.place.lon}">
      <span class="nm">${esc(r.place.name)}<small>${r.place.type === "il" ? "il merkezi" : esc(r.place.province)} · ${r.n} kare</small></span>
      <span class="pc num">${pct(r.share)}</span>
      <span class="tr"><i style="width:${r.share}%"></i></span></button></li>`).join("")
    : `<li class="empty">Bu ay için yeterli kare yok.</li>`;
}

let loadingTimer;
async function loadMap() {
  const box = $("map-loading");
  // Hızlı yüklemelerde gösterge yanıp sönmesin: yalnızca 200 ms'den uzun sürerse görünür
  clearTimeout(loadingTimer);
  loadingTimer = setTimeout(() => {
    box.className = "map-loading";
    box.textContent = "Uydu verisi işleniyor…";
    box.hidden = false;
  }, 200);
  try {
    state.mapData = await api(URLS.map(state.region, state.year, state.month));
    drawGrid();
    drawRaster();
    renderStats();
    renderFinding();
    renderYears();
    $("export").href = URLS.exportMap(state.region, state.year, state.month);
    $("export").setAttribute("download", `${state.region}_${state.year}_${pad2(state.month)}_kuraklik.geojson`);
    clearTimeout(loadingTimer);
    box.hidden = true;
  } catch (e) {
    clearTimeout(loadingTimer);
    box.hidden = false;
    box.className = "map-loading err";
    box.innerHTML = `Harita yüklenemedi: ${esc(e.message)} <button type="button">Tekrar dene</button>`;
    box.querySelector("button").addEventListener("click", loadMap);
  }
}

// ---------------------------------------------------------------- bulgu ve yıl şeridi
const historyReady = () => state.history && state.history.region === state.region && state.history.month === state.month;

function renderFinding() {
  const el = $("finding");
  const s = state.mapData.summary;
  if (!s.cell_count) { el.textContent = `${periodText()} için bulutsuz uydu görüntüsü yok.`; return; }
  // Kırmızı yalnızca tarım alanının en az üçte biri kurakken: küçük bir pay iyi haberdir
  const share = s.drought_percent >= 35 ? `<span class="bad">${pct(s.drought_percent)}</span>` : pct(s.drought_percent);
  let text = `${periodText()}: tarım alanlarının ${share}'${suffix(s.drought_percent)} kurak.`;
  const rows = historyReady() ? state.history.rows.filter((r) => r.drought_percent !== null) : [];
  if (rows.length) {
    const sorted = rows.slice().sort((a, b) => b.drought_percent - a.drought_percent);
    const rank = sorted.findIndex((r) => r.year === state.year) + 1;
    const first = rows[0] && rows[0].year;
    const since = `${first}'${ablative(first)} bu yana`;
    const mon = MONTHS[state.month - 1];
    if (rank === 1) text += ` ${since} en kurak ${mon}.`;
    else if (rank > 1 && rank <= 3) text += ` ${since} en kurak ${["", "", "ikinci", "üçüncü"][rank]} ${mon}.`;
    else if (rank > 0) {
      const avg = rows.reduce((a, r) => a + r.drought_percent, 0) / rows.length;
      text += ` ${first}–${rows[rows.length - 1].year} ${mon} ortalaması ${pct(avg)}.`;
    }
  }
  el.innerHTML = text;
}

// Türkçe ekler sayının okunuşundaki son kelimeye göre seçilir: "%69'u", "%40'ı", "%6'sı"; "2019'dan", "2023'ten"
const VOWELS = "aeıioöuü";
function lastWord(n) {
  n = Math.round(Math.abs(n));
  if (n === 0) return "sıfır";
  if (n % 1000 === 0) return "bin";
  if (n % 100 === 0) return "yüz";
  const last = n % 10, tens = Math.floor(n / 10) % 10;
  return last ? ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"][last]
    : ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"][tens];
}
const lastVowel = (w) => [...w].reverse().find((c) => VOWELS.includes(c));
function suffix(v) {  // belirtme hâli: -(s)ı/i/u/ü
  const w = lastWord(v);
  const harm = { a: "ı", ı: "ı", e: "i", i: "i", o: "u", u: "u", ö: "ü", ü: "ü" }[lastVowel(w)];
  return (VOWELS.includes(w[w.length - 1]) ? "s" : "") + harm;
}
function ablative(v) {  // ayrılma hâli: -dan/den/tan/ten
  const w = lastWord(v);
  const back = "aıou".includes(lastVowel(w));
  return ("fstkçşhp".includes(w[w.length - 1]) ? "t" : "d") + (back ? "an" : "en");
}

function renderCompare() {
  const el = $("s-compare");
  if (!historyReady() || !state.mapData.summary.cell_count) { el.textContent = ""; return; }
  const prev = state.history.rows.find((r) => r.year === state.year - 1);
  if (!prev || prev.drought_percent === null) { el.textContent = ""; return; }
  const now = Math.round(state.mapData.summary.drought_percent), before = Math.round(prev.drought_percent);
  const diff = now - before;
  const word = diff < 0 ? `<span class="good">${Math.abs(diff)} puan az</span>` : diff > 0
    ? `<span class="bad">${diff} puan fazla</span>` : "aynı";
  el.innerHTML = `${MONTHS[state.month - 1]} ${prev.year}: <b class="num">${pct(before)}</b> · geçen yıla göre ${word}`;
}

function renderYears() {
  const strip = $("year-strip");
  const { year: ly, month: lm } = state.status.latest;
  $("dh-month").textContent = MONTHS[state.month - 1];
  const ready = historyReady();
  const byYear = new Map(ready ? state.history.rows.map((r) => [r.year, r.drought_percent]) : []);
  const years = [];
  for (let y = 2017; y <= ly; y++) years.push(y);
  strip.innerHTML = years.map((y) => {
    const future = y === ly && state.month > lm;
    const v = byYear.get(y);
    const h = v === undefined || v === null ? 0 : Math.max(2, v);
    return `<button type="button" class="yr" role="radio" aria-checked="${y === state.year}" data-year="${y}" ${future ? "disabled" : ""}
      aria-label="${y}${v !== undefined && v !== null ? `, kurak alan ${pct(v)}` : ""}">
      <span class="v num">${future ? "" : v !== undefined && v !== null ? pct(v) : ready ? "–" : ""}</span>
      <span class="col"><i style="height:${h}%"></i></span>
      <span class="y num">${y}</span></button>`;
  }).join("");
  $("dh-wait").hidden = ready || !state.status.live;
}

async function loadDroughtHistory() {
  const key = { region: state.region, month: state.month };
  const btn = $("dh-load");
  btn.disabled = true; btn.textContent = "Hesaplanıyor…";
  try {
    const rows = await api(URLS.droughtHistory(key.region, key.month));
    if (key.region !== state.region || key.month !== state.month) return; // bu sırada seçim değişti
    state.history = { ...key, rows };
    renderYears(); renderFinding(); renderCompare();
  } catch (e) {
    $("dh-wait").hidden = false;
    $("dh-wait").querySelector("p").textContent = "Kuraklık geçmişi alınamadı: " + e.message;
  } finally {
    btn.disabled = false; btn.textContent = "Kuraklık geçmişini hesapla";
  }
}

// ---------------------------------------------------------------- grafikler
function chartDefaults() {
  Chart.defaults.color = cssVar("--muted");
  Chart.defaults.borderColor = cssVar("--grid");
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.font.size = 12;
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.elements.line.borderWidth = 2;
  Chart.defaults.elements.line.tension = 0;
  Chart.defaults.elements.point.radius = 0;
  Chart.defaults.elements.point.hoverRadius = 4;
  Object.assign(Chart.defaults.plugins.tooltip, {
    backgroundColor: "#ffffff", titleColor: cssVar("--text"), bodyColor: cssVar("--text"),
    borderColor: cssVar("--border"), borderWidth: 1, cornerRadius: 6, padding: 8, caretSize: 0,
    boxWidth: 8, boxHeight: 8, boxPadding: 4, titleFont: { weight: "600" },
  });
}

// Eksen çizgisi yok, 4–5 soluk ızgara çizgisi, y ekseni sıfırdan
const axes = (y = {}, x = {}) => ({
  y: { min: 0, border: { display: false }, ticks: { maxTicksLimit: 5, padding: 6 }, ...y },
  x: { grid: { display: false }, border: { color: cssVar("--control") }, ticks: { maxRotation: 0, autoSkipPadding: 18 }, ...x },
});

function setChart(id, config) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart($(id), config);
}

async function loadTimeseries() {
  document.querySelectorAll(".region-name").forEach((el) => (el.textContent = regionObj().name));
  const ts = await api(URLS.timeseries(state.region));
  const veg = cssVar("--veg"), ink = "#8c877f", text = cssVar("--text");
  const ly = state.status.latest.year;
  $("k-latest").textContent = String(ly);
  $("k-clim-latest").textContent = String(ly);

  // Aylık seri: son yıl yeşil, önceki yıllar gri; x ekseninde yalnız ocak ayları (yıllar)
  setChart("c-monthly", {
    type: "line",
    data: { labels: ts.monthly.map((r) => r.t),
      datasets: [{ label: "Ortalama NDVI", data: ts.monthly.map((r) => r.ndvi), borderColor: ink, spanGaps: true,
        segment: { borderColor: (c) => (ts.monthly[c.p1DataIndex].t.startsWith(String(ly)) ? veg : ink) } }] },
    options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { callbacks: {
        title: (it) => { const [y, m] = it[0].label.split("-"); return `${MONTHS[Number(m) - 1]} ${y}`; },
        label: (it) => ` NDVI ${fmt(it.parsed.y)}` } } },
      scales: axes({ max: 0.8, ticks: { stepSize: 0.2, maxTicksLimit: 5 } }, { ticks: { autoSkip: false, maxRotation: 0,
        callback: (v, i) => (ts.monthly[i].t.endsWith("-01") ? ts.monthly[i].t.slice(0, 4) : null) } }) },
  });

  const yrs = ts.yearly.map((r) => r.year);
  const t = ts.trend;
  const season = ts.season_months.map((m) => MONTHS[m - 1]).join("–");
  setChart("c-yearly", {
    data: { labels: yrs, datasets: [
      { type: "bar", label: `Büyüme mevsimi (${season})`, data: ts.yearly.map((r) => r.season_ndvi),
        backgroundColor: yrs.map((y) => (y === ly ? veg : "#cfcac2")), borderRadius: { topLeft: 2, topRight: 2 },
        maxBarThickness: 36 },
      ...(t ? [{ type: "line", label: "Eğilim", data: yrs.map((y) => t.intercept + t.slope * y),
        borderColor: text, borderDash: [5, 4], borderWidth: 1.5 }] : []),
    ] },
    options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { callbacks: { label: (it) => ` ${it.dataset.label}: ${fmt(it.parsed.y)}` } } },
      // Dar ekranda yılların biri atlanır ama son yıl (yeşil sütun) her zaman yazılır
      scales: axes({ ticks: { maxTicksLimit: 5 } }, { ticks: { autoSkip: false, maxRotation: 0,
        callback: (v, i) => (window.innerWidth < 600 && (yrs.length - 1 - i) % 2 ? null : yrs[i]) } }) },
  });
  const tEl = $("trend-text");
  if (t) {
    const down = t.percent_per_year < 0;
    tEl.innerHTML = `${season} ortalaması ${yrs[0]}–${yrs[yrs.length - 1]} arasında yılda ` +
      `<b class="${down ? "bad-text" : "good-text"}">%${Math.abs(t.percent_per_year).toFixed(1)} ${down ? "azalıyor" : "artıyor"}</b>` +
      ` <span class="num">(R² ${t.r2.toFixed(2)})</span>.`;
  } else {
    tEl.textContent = "Eğilim için yeterli yıl yok.";
  }

  // Bu yıl ve ortalama yıl
  const thisYear = Array.from({ length: 12 }, (_, i) => {
    const row = ts.monthly.find((r) => r.t === `${ly}-${pad2(i + 1)}`);
    return row ? row.ndvi : null;
  });
  setChart("c-clim", {
    type: "line",
    data: { labels: MONTHS.map((m) => m.slice(0, 3)), datasets: [
      { label: `Ortalama yıl (${yrs[0]}–)`, data: ts.climatology, borderColor: ink, borderDash: [5, 4] },
      { label: String(ly), data: thisYear, borderColor: veg, pointRadius: 2.5, pointBackgroundColor: veg },
    ] },
    options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { callbacks: { label: (it) => ` ${it.dataset.label}: ${fmt(it.parsed.y)}` } } },
      scales: axes({ ticks: { maxTicksLimit: 5 } }) },
  });
  const p = ts.phenology;
  $("pheno-text").textContent = p && p.green_up_month
    ? `Bitki takvimi: yeşillenme ${MONTHS[p.green_up_month - 1]}, zirve ${MONTHS[p.peak_month - 1]}, ` +
      `hasat ve kuruma ${MONTHS[p.senescence_month - 1]}.`
    : "Bu yılın NDVI eğrisi, 2017'den bu yana ortalama yılla.";
}

// ---------------------------------------------------------------- tarla analizi
function showView(which) {
  $("side-basin").hidden = which !== "basin";
  $("tarla").hidden = which !== "tarla";
}

async function loadPoint(lat, lon) {
  state.point = { lat, lon };
  if (pointMarker) pointMarker.remove();
  pointMarker = L.circleMarker([lat, lon], { radius: 6, color: "#ffffff", weight: 2.5, fillColor: "#191816", fillOpacity: 1 }).addTo(map);
  markSelectedCell();
  showView("tarla");
  if (window.matchMedia("(max-width: 1100px)").matches) $("tarla").scrollIntoView({ behavior: "smooth", block: "start" });
  $("p-coord").textContent = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  $("p-place").textContent = "";
  $("p-status").innerHTML = `<p class="loading">Uydu geçmişi getiriliyor…</p>`;
  $("p-advice").innerHTML = "";
  let r;
  try {
    if (STATIC) {
      const cell = findCell(lat, lon);
      if (!cell) throw new Error("Bu nokta, seçili havzada izlenen tarım alanlarının dışında. Haritadaki renkli karelerden birine tıklayın.");
      r = await api(URLS.cell(state.region, cell.id));
    } else {
      r = await api(URLS.point(lat, lon));
    }
  } catch (e) {
    $("p-status").innerHTML = `<p class="err">${esc(e.message)}</p>`;
    if (charts["p-chart"]) { charts["p-chart"].destroy(); delete charts["p-chart"]; }
    return;
  }
  // Statik raporlar kare merkezine göre üretilir; yakın yerleşimi tıklanan noktaya göre yeniden bul
  const np = (STATIC && state.places.length && nearestPlace(lat, lon)) || r.nearest_place;
  if (np) {
    $("p-place").textContent = np.type === "il"
      ? `${np.name} il merkezine ${np.distance_km} km`
      : `${np.name} (${np.province}) ilçesine ${np.distance_km} km`;
  }
  const c = r.current;
  if (c) {
    const [y, m] = c.t.split("-").map(Number);
    $("p-status").innerHTML = `<p class="when">Son uydu ölçümü: ${MONTHS[m - 1]} ${y}</p>
      <p class="cls"><span class="sw" style="background:${c.color}"></span>${esc(c.class_label)}</p>
      <dl class="kpis">
        <div><dt>NDVI</dt><dd class="num">${fmt(c.ndvi)}</dd></div>
        <div><dt>VCI</dt><dd class="num">${fmt(c.vci, 0)}<small>/100</small></dd></div>
        <div><dt>Geçen yıla göre</dt><dd class="num">${c.ndvi_change !== null ? signed(c.ndvi_change) : "–"}</dd></div>
      </dl>`;
  } else {
    $("p-status").innerHTML = `<p class="err">Bu nokta için yeterli bulutsuz görüntü yok (tarım alanı dışında olabilir).</p>`;
  }
  $("p-advice").innerHTML = (r.advice || []).map((t) => `<li>${esc(t)}</li>`).join("");
  const veg = cssVar("--veg");
  setChart("p-chart", {
    type: "line",
    data: { labels: r.monthly.map((x) => x.t), datasets: [
      { label: cellScale() ? "Bu kare" : "Bu tarla", data: r.monthly.map((x) => x.ndvi), borderColor: veg, borderWidth: 1.5, spanGaps: true },
      { label: "Aynı ayın ortalaması", data: r.monthly.map((x) => r.climatology[Number(x.t.slice(5)) - 1]),
        borderColor: "#8c877f", borderDash: [4, 4], borderWidth: 1.5 },
    ] },
    options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { callbacks: {
        title: (it) => { const [yy, mm] = it[0].label.split("-"); return `${MONTHS[Number(mm) - 1]} ${yy}`; },
        label: (it) => ` ${it.dataset.label}: ${fmt(it.parsed.y)}` } } },
      scales: axes({ ticks: { maxTicksLimit: 4 } }, { ticks: { autoSkip: false, maxRotation: 0,
        callback: (v, i) => { const t = r.monthly[i].t; return t.endsWith("-01") && Number(t.slice(0, 4)) % 3 === 2 ? t.slice(0, 4) : null; } } }) },
  });
}

// ---------------------------------------------------------------- uyarılar
const cellScale = () => state.status && state.status.point_scale === "cell";

async function loadSubscriptions() {
  if (STATIC) return;
  const subs = await api(URLS.subscriptions());
  $("sub-list").innerHTML = subs.length ? subs.map((s) => `<li>
      <div class="row-main"><div><b>${esc(s.field_name || "Tarla")}</b> · ${esc(s.name)}</div>
      <span class="row-actions"><button data-go="${s.lat},${s.lon}" class="btn ghost" type="button">Göster</button>
      <button data-del="${s.id}" class="btn ghost" type="button">Sil</button></span></div>
      <div class="meta num">${s.lat.toFixed(4)}, ${s.lon.toFixed(4)} · eşik VCI ${s.threshold}${s.email ? " · " + esc(s.email) : ""}</div></li>`).join("")
    : `<li class="empty">Henüz abone tarla yok.</li>`;
}

async function loadAlerts() {
  const list = await api(URLS.alerts());
  // Statik yayında kişisel bilgi içermeyen özet gösterilir
  const text = (a) => a.message || `${a.place}: ${a.class_label} (VCI ${fmt(a.vci, 0)}, ${a.period})`;
  const when = (a) => (a.created_at || a.date || "").replace("T", " ");
  $("alert-list").innerHTML = list.length ? list.map((a) => `<li>${esc(text(a))}
      <div class="meta num">${esc(when(a))} · iletim: ${esc(a.delivered)}</div></li>`).join("")
    : `<li class="empty">${STATIC ? "Henüz uyarı gönderilmedi. Abone tarlalar her ayın başında uydu verisiyle kontrol edilir."
      : "Henüz uyarı yok. Abone tarlaları taramak için Şimdi kontrol et'e basın."}</li>`;
}

// Google Formu bağlantısındaki ENLEM/BOYLAM yer tutucularını tıklanan noktayla doldurur
function formUrl(lat, lon) {
  const u = state.status.subscribe_form_url;
  if (!u) return null;
  return u.replace("ENLEM", lat === undefined ? "" : lat.toFixed(5))
    .replace("BOYLAM", lon === undefined ? "" : lon.toFixed(5));
}

function bindAlerts() {
  $("p-subscribe").addEventListener("click", () => {
    if (STATIC) {
      const u = formUrl(state.point.lat, state.point.lon);
      if (u) window.open(u, "_blank", "noopener");
      else $("uyari").scrollIntoView({ behavior: "smooth" });
      return;
    }
    const f = $("sub-form");
    f.lat.value = state.point.lat.toFixed(5);
    f.lon.value = state.point.lon.toFixed(5);
    $("uyari").scrollIntoView({ behavior: "smooth" });
    f.name.focus({ preventScroll: true });
  });
  $("sub-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target, msg = $("sub-msg");
    const body = Object.fromEntries(new FormData(f));
    try {
      await api("api/subscriptions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      msg.className = "msg ok";
      msg.textContent = "Abonelik oluşturuldu. Tarlanız her ay uydu verisiyle kontrol edilecek.";
      f.reset();
      loadSubscriptions();
    } catch (err) {
      msg.className = "msg err";
      msg.textContent = err.message;
    }
  });
  $("sub-list").addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const del = b.dataset.del, go = b.dataset.go;
    if (del && confirm("Bu tarlanın aboneliği silinsin mi?")) {
      await api(`api/subscriptions/${del}`, { method: "DELETE" });
      loadSubscriptions(); loadAlerts();
    } else if (go) {
      const [lat, lon] = go.split(",").map(Number);
      map.setView([lat, lon], 11);
      $("harita").scrollIntoView({ behavior: "smooth" });
      loadPoint(lat, lon);
    }
  });
  $("check-alerts").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true; btn.textContent = "Kontrol ediliyor…";
    try {
      const r = await api("api/alerts/check", { method: "POST" });
      btn.textContent = `${r.checked} tarla tarandı, ${r.new_alerts.length} yeni uyarı`;
      loadAlerts();
    } catch (err) {
      btn.textContent = "Hata: " + err.message;
    } finally {
      setTimeout(() => { btn.disabled = false; btn.textContent = "Şimdi kontrol et"; }, 3500);
    }
  });
}

// ---------------------------------------------------------------- kontroller
function fillMonths() {
  const { year: ly, month: lm } = state.status.latest;
  $("month").innerHTML = "";
  MONTHS.forEach((m, i) => {
    const o = new Option(m, i + 1);
    o.disabled = state.year === ly && i + 1 > lm;
    $("month").add(o);
  });
  $("month").value = state.month;
}

function renderRegionTabs() {
  $("region-tabs").innerHTML = state.regions.map((r) => `<button type="button" role="radio" data-region="${r.id}"
    aria-checked="${r.id === state.region}">${esc(r.name.replace(/ Havzası$/, ""))}</button>`).join("");
  $("region-title").textContent = regionObj().name;
  document.title = `${regionObj().name} · KuraklıkGözü`;
}

function setPlayButton(on) {
  $("play").querySelector("use").setAttribute("href", on ? "#i-stop" : "#i-play");
  $("play").querySelector("span").textContent = on ? "Durdur" : "Yılları oynat";
}

async function play() {
  if (state.playing) { state.playing = false; return; }
  state.playing = true;
  setPlayButton(true);
  const { year: ly, month: lm } = state.status.latest;
  for (let y = 2017; y <= ly && state.playing; y++) {
    if (y === ly && state.month > lm) break;
    state.year = y;
    fillMonths();
    await loadMap();
    await new Promise((r) => setTimeout(r, 1100));
  }
  state.playing = false;
  setPlayButton(false);
}

async function regionChanged() {
  const r = regionObj();
  renderRegionTabs();
  closePoint();
  map.setView(r.center, r.zoom);
  drawOutline();
  await loadMap();
  loadTimeseries();
  monthChanged(false);
}

// Seçili ay değişince yıl şeridinin verisi (her yılın kurak alan payı) yeniden gelir
function monthChanged(reloadMap = true) {
  if (reloadMap) loadMap();
  if (!state.status.live) loadDroughtHistory();
  else renderYears();
}

function closePoint() {
  state.point = null;
  if (pointMarker) { pointMarker.remove(); pointMarker = null; }
  if (selectedCell) { selectedCell.remove(); selectedCell = null; }
  showView("basin");
}

function bindControls() {
  $("region-tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-region]");
    if (!b || b.dataset.region === state.region) return;
    state.region = b.dataset.region;
    regionChanged();
  });
  $("region-tabs").addEventListener("keydown", (e) => arrowKeys(e, "#region-tabs button"));
  $("month").addEventListener("change", (e) => {
    state.month = Number(e.target.value);
    monthChanged();
  });
  $("year-strip").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-year]");
    if (!b || b.disabled) return;
    state.playing = false;
    state.year = Number(b.dataset.year);
    fillMonths();
    loadMap();
  });
  $("year-strip").addEventListener("keydown", (e) => arrowKeys(e, "#year-strip button:not(:disabled)"));
  document.querySelectorAll("input[name=layer]").forEach((el) => el.addEventListener("change", (e) => {
    state.layer = e.target.value;
    drawGrid(); drawRaster();
  }));
  $("raster").addEventListener("change", () => { drawGrid(); drawRaster(); });
  $("play").addEventListener("click", play);
  $("dh-load").addEventListener("click", loadDroughtHistory);
  $("p-back").addEventListener("click", closePoint);
  $("rank-list").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-lat]");
    if (!b) return;
    map.flyTo([Number(b.dataset.lat), Number(b.dataset.lon)], 10, { duration: 0.6 });
    if (window.matchMedia("(max-width: 1100px)").matches) $("harita").scrollIntoView({ behavior: "smooth" });
  });
  const bar = document.querySelector(".bar");
  const onScroll = () => bar.classList.toggle("scrolled", window.scrollY > 4);
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
}

// Radyo grubu gibi davranan düğme dizilerinde ok tuşlarıyla gezinme
function arrowKeys(e, selector) {
  if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
  const items = [...document.querySelectorAll(selector)];
  const i = items.indexOf(document.activeElement);
  if (i < 0) return;
  e.preventDefault();
  const next = items[(i + (e.key === "ArrowRight" ? 1 : -1) + items.length) % items.length];
  next.focus();
  next.click();
}

async function init() {
  chartDefaults();
  initMap();
  bindControls();
  bindAlerts();
  [state.status, state.regions] = await Promise.all([api(URLS.status()), api(URLS.regions())]);
  api(URLS.places()).then(drawPlaces).catch(() => { $("rank-list").innerHTML = `<li class="empty">Yerleşim listesi alınamadı.</li>`; });
  const st = state.status;
  const badge = $("mode-badge");
  badge.textContent = st.mode === "demo" ? "Demo verisi" : st.label;
  badge.title = st.label;
  badge.className = "source " + st.mode;
  $("demo-banner").hidden = st.mode !== "demo";
  const cov = st.coverage;
  if (st.mode === "gee" && cov && !cov.complete) {
    $("coverage-banner").hidden = false;
    $("coverage-banner").textContent = `Geçmiş uydu verisi yükleniyor: ${cov.months_have}/${cov.months_expected} ay hazır. ` +
      "Tamamlanana kadar kuraklık (VCI) karşılaştırmaları eksik yıllara dayanır.";
  }
  $("raster-opt").hidden = !(st.live || Object.keys(st.raster || {}).length);
  $("p-scale").hidden = !cellScale();
  if (st.built_at) {
    $("updated").textContent = `Son güncelleme: ${new Date(st.built_at).toLocaleString("tr-TR")} · ` +
      `Uydu verisi: ${MONTHS[st.latest.month - 1]} ${st.latest.year} sonuna kadar.`;
  }
  if (STATIC) {
    $("sub-form").hidden = true;
    $("sub-static").hidden = false;
    $("check-alerts").hidden = true;
    $("sub-title").hidden = true;
    $("sub-list").hidden = true;
    $("sub-intro").hidden = true;
    const u = formUrl();
    if (u) $("form-link").href = u;
    else { $("form-link").hidden = true; $("form-missing").hidden = false; }
  }

  state.year = st.latest.year;
  // Varsayılan olarak bölgenin büyüme mevsimi zirvesini göster (en anlamlı karşılaştırma)
  const r0 = state.regions.find((r) => r.id === state.region);
  state.month = r0.peak_month <= st.latest.month ? r0.peak_month : st.latest.month;
  renderRegionTabs();
  fillMonths();
  map.setView(r0.center, r0.zoom);
  drawOutline();
  await loadMap();
  loadTimeseries();
  monthChanged(false);
  loadSubscriptions();
  loadAlerts();
  // Grafikler yazı tipi yüklenmeden çizildiyse Overpass ile yeniden çiz
  document.fonts.ready.then(() => Object.values(charts).forEach((c) => c.update("none")));
}

init().catch((e) => {
  $("finding").textContent = "Uygulama başlatılamadı: " + e.message;
});
