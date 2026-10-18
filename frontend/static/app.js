/* KuraklıkGözü – istemci tarafı */
"use strict";

const MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
  "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
const CLASSES = [
  { key: "saglikli", label: "Sağlıklı (VCI ≥ 50)", color: "#1a9850" },
  { key: "hafif", label: "Hafif stres (35–50)", color: "#fddb6d" },
  { key: "orta", label: "Orta kuraklık (20–35)", color: "#ef8a62" },
  { key: "siddetli", label: "Şiddetli kuraklık (< 20)", color: "#b2182b" },
];
const NDVI_RAMP = ["#a50026", "#d73027", "#f46d43", "#fdae61", "#fee08b",
  "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850", "#006837"];
const CHANGE_RAMP = ["#b2182b", "#ef8a62", "#fddbc7", "#f7f7f7", "#d9f0d3", "#7fbf7b", "#1b7837"];

const $ = (id) => document.getElementById(id);
const state = { status: null, regions: [], region: "konya", year: null, month: null, layer: "vci",
  mapData: null, playing: false, point: null };
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
const regionObj = () => state.regions.find((r) => r.id === state.region);
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function cellColor(p) {
  if (state.layer === "ndvi") return p.ndvi === null ? "#9e9e9e" : ramp(NDVI_RAMP, p.ndvi / 0.8);
  if (state.layer === "change") return p.ndvi_change === null ? "#9e9e9e" : ramp(CHANGE_RAMP, (p.ndvi_change + 0.2) / 0.4);
  return p.color;
}

// ---------------------------------------------------------------- harita
let map, gridLayer, outlineLayer, rasterLayer, pointMarker, placeLayer;

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
}

// İl adları her zaman, ilçe adları yakınlaşınca (zoom ≥ 9) görünür
function nearestPlace(lat, lon) {
  let best = null;
  for (const p of state.places || []) {
    const dx = (p.lon - lon) * 111.32 * Math.cos(lat * Math.PI / 180), dy = (p.lat - lat) * 110.57;
    const d = Math.hypot(dx, dy);
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
}

function updatePlaceVisibility() {
  map.getContainer().classList.toggle("show-ilce", map.getZoom() >= 9);
}

function drawGrid() {
  if (gridLayer) gridLayer.remove();
  const d = state.mapData;
  gridLayer = L.geoJSON(d, {
    style: (f) => ({ color: cellColor(f.properties), weight: 0.4, fillColor: cellColor(f.properties),
      fillOpacity: $("raster").checked ? 0.0 : 0.62, opacity: $("raster").checked ? 0.3 : 0.8 }),
    onEachFeature: (f, layer) => {
      const p = f.properties;
      layer.bindTooltip(
        `<b>${esc(p.class_label)}</b><br>NDVI: ${fmt(p.ndvi)} · VCI: ${fmt(p.vci, 0)}` +
        (p.ndvi_change !== null ? `<br>Geçen yıla göre: ${p.ndvi_change > 0 ? "+" : ""}${fmt(p.ndvi_change)}` : ""),
        { sticky: true });
      layer.on("click", (e) => { L.DomEvent.stopPropagation(e); loadPoint(e.latlng.lat, e.latlng.lng); });
    },
  }).addTo(map);
  drawLegend();
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

function drawLegend() {
  const el = $("legend");
  if (state.layer === "vci") {
    el.innerHTML = "<b>Kuraklık durumu (VCI)</b>" + CLASSES.map((c) =>
      `<div class="item"><span class="sw" style="background:${c.color}"></span>${c.label}</div>`).join("");
  } else if (state.layer === "ndvi") {
    el.innerHTML = `<b>NDVI (bitki örtüsü)</b><div class="ramp" style="background:linear-gradient(90deg,${NDVI_RAMP.join(",")})"></div>
      <div class="ends"><span>0 çıplak toprak</span><span>0.8 yoğun bitki</span></div>`;
  } else {
    el.innerHTML = `<b>NDVI değişimi (geçen yılın aynı ayına göre)</b><div class="ramp" style="background:linear-gradient(90deg,${CHANGE_RAMP.join(",")})"></div>
      <div class="ends"><span>−0.2 kuruma</span><span>+0.2 iyileşme</span></div>`;
  }
}

function renderStats() {
  const s = state.mapData.summary;
  $("s-drought").textContent = s.cell_count ? `%${s.drought_percent}` : "–";
  $("s-vci").textContent = fmt(s.mean_vci, 0);
  $("s-ndvi").textContent = fmt(s.mean_ndvi);
  $("class-bars").innerHTML = CLASSES.slice().reverse().map((c) => {
    const pct = s.percent[c.key] ?? 0;
    return `<div class="bar"><span>${c.label.split(" (")[0]}</span>
      <div class="track"><div class="fill" style="width:${pct}%;background:${c.color}"></div></div>
      <span class="pct">%${pct}</span></div>`;
  }).join("");
}

async function loadMap() {
  $("map-loading").hidden = false;
  try {
    state.mapData = await api(URLS.map(state.region, state.year, state.month));
    drawGrid();
    drawRaster();
    renderStats();
    $("export").href = URLS.exportMap(state.region, state.year, state.month);
    $("export").setAttribute("download", `${state.region}_${state.year}_${pad2(state.month)}_kuraklik.geojson`);
  } catch (e) {
    alert("Harita yüklenemedi: " + e.message);
  } finally {
    $("map-loading").hidden = true;
  }
}

// ---------------------------------------------------------------- grafikler
function chartDefaults() {
  Chart.defaults.color = cssVar("--muted");
  Chart.defaults.borderColor = cssVar("--line");
  Chart.defaults.font.family = "system-ui, sans-serif";
  Chart.defaults.plugins.legend.labels.boxWidth = 12;
}

function setChart(id, config) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart($(id), config);
}

async function loadTimeseries() {
  document.querySelectorAll(".region-name").forEach((el) => (el.textContent = regionObj().name));
  const ts = await api(URLS.timeseries(state.region));

  setChart("c-monthly", {
    type: "line",
    data: { labels: ts.monthly.map((r) => r.t),
      datasets: [{ label: "Ortalama NDVI", data: ts.monthly.map((r) => r.ndvi), borderColor: "#1a9850",
        backgroundColor: "rgba(26,152,80,.15)", fill: true, pointRadius: 0, tension: 0.3, spanGaps: true }] },
    options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      scales: { y: { min: 0, title: { display: true, text: "NDVI" } }, x: { ticks: { maxTicksLimit: 12 } } } },
  });

  const yrs = ts.yearly.map((r) => r.year);
  const t = ts.trend;
  setChart("c-yearly", {
    data: { labels: yrs, datasets: [
      { type: "bar", label: `Büyüme mevsimi NDVI (${ts.season_months.map((m) => MONTHS[m - 1].slice(0, 3)).join("–")})`,
        data: ts.yearly.map((r) => r.season_ndvi),
        backgroundColor: ts.yearly.map((r) => ramp(NDVI_RAMP, r.season_ndvi / 0.8)) },
      ...(t ? [{ type: "line", label: "Eğilim", data: yrs.map((y) => t.intercept + t.slope * y),
        borderColor: "#b2182b", borderDash: [6, 4], pointRadius: 0 }] : []),
    ] },
    options: { maintainAspectRatio: false, scales: { y: { min: 0 } } },
  });
  $("trend-text").textContent = t
    ? `Eğilim: yılda %${Math.abs(t.percent_per_year).toFixed(1)} ${t.percent_per_year < 0 ? "azalma" : "artış"} ` +
      `(R² = ${t.r2.toFixed(2)}, ${yrs[0]}–${yrs[yrs.length - 1]}).`
    : "Eğilim için yeterli yıl yok.";

  // Bu yıl vs. ortalama
  const ly = state.status.latest.year;
  const thisYear = Array.from({ length: 12 }, (_, i) => {
    const row = ts.monthly.find((r) => r.t === `${ly}-${String(i + 1).padStart(2, "0")}`);
    return row ? row.ndvi : null;
  });
  setChart("c-clim", {
    type: "line",
    data: { labels: MONTHS.map((m) => m.slice(0, 3)), datasets: [
      { label: "Ortalama yıl (2017–)", data: ts.climatology, borderColor: "#7a8a7f", borderDash: [5, 4], pointRadius: 2 },
      { label: String(ly), data: thisYear, borderColor: "#b2182b", backgroundColor: "#b2182b", pointRadius: 3 },
    ] },
    options: { maintainAspectRatio: false, scales: { y: { min: 0 } } },
  });
  const p = ts.phenology;
  $("pheno-text").textContent = p && p.green_up_month
    ? `Bitki takvimi: yeşillenme ${MONTHS[p.green_up_month - 1]}, zirve ${MONTHS[p.peak_month - 1]}, ` +
      `hasat/kuruma ${MONTHS[p.senescence_month - 1]}.`
    : "Ortalama yıl ile bu yılın karşılaştırması.";
}

async function loadDroughtHistory() {
  $("dh-month").textContent = MONTHS[state.month - 1];
  $("dh-load").hidden = true;
  const box = $("c-drought").parentElement;
  box.style.opacity = 0.5;
  try {
    const rows = await api(URLS.droughtHistory(state.region, state.month));
    setChart("c-drought", {
      type: "bar",
      data: { labels: rows.map((r) => r.year), datasets: [{ label: "Kurak tarım alanı (%)",
        data: rows.map((r) => r.drought_percent),
        backgroundColor: rows.map((r) => ramp(["#1a9850", "#fddb6d", "#ef8a62", "#b2182b"], r.drought_percent / 100)) }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { y: { min: 0, max: 100, ticks: { callback: (v) => `%${v}` } } } },
    });
  } finally {
    box.style.opacity = 1;
  }
}

// ---------------------------------------------------------------- tarla analizi
async function loadPoint(lat, lon) {
  state.point = { lat, lon };
  if (pointMarker) pointMarker.remove();
  pointMarker = L.marker([lat, lon]).addTo(map);
  const sec = $("tarla");
  sec.hidden = false;
  $("p-coord").textContent = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  $("p-place").textContent = "";
  $("p-status").innerHTML = "Uydu geçmişi getiriliyor…";
  $("p-status").style.background = "#7a8a7f";
  $("p-advice").innerHTML = "";
  sec.scrollIntoView({ behavior: "smooth", block: "nearest" });
  let r;
  try {
    if (STATIC) {
      const cell = findCell(lat, lon);
      if (!cell) throw new Error("Bu nokta, seçili bölgedeki izlenen tarım alanlarının dışında. Haritadaki renkli karelerden birine tıklayın.");
      r = await api(URLS.cell(state.region, cell.id));
    } else {
      r = await api(URLS.point(lat, lon));
    }
  } catch (e) {
    $("p-status").textContent = e.message;
    if (charts["p-chart"]) { charts["p-chart"].destroy(); delete charts["p-chart"]; }
    return;
  }
  // Statik raporlar kare merkezine göre üretilir; yakın yerleşimi tıklanan noktaya göre yeniden bul
  const np = (STATIC && nearestPlace(lat, lon)) || r.nearest_place;
  if (np) {
    $("p-place").textContent = np.type === "il"
      ? `${np.name} il merkezine ${np.distance_km} km`
      : `${np.name} (${np.province}) ilçesine ${np.distance_km} km`;
  }
  const c = r.current;
  if (c) {
    const [y, m] = c.t.split("-").map(Number);
    $("p-status").style.background = c.color;
    $("p-status").style.color = c.class === "hafif" ? "#2a1d00" : "#fff";
    $("p-status").innerHTML = `<div>${MONTHS[m - 1]} ${y} durumu</div><div class="cls">${esc(c.class_label)}</div>
      <div class="nums"><span>NDVI <b>${fmt(c.ndvi)}</b></span><span>VCI <b>${fmt(c.vci, 0)}</b>/100</span>
      ${c.ndvi_change !== null ? `<span>Geçen yıl: <b>${c.ndvi_change > 0 ? "+" : ""}${fmt(c.ndvi_change)}</b></span>` : ""}</div>`;
  } else {
    $("p-status").textContent = "Bu nokta için yeterli bulutsuz görüntü yok (tarım alanı dışında olabilir).";
  }
  $("p-advice").innerHTML = (r.advice || []).map((t) => `<li>${esc(t)}</li>`).join("");
  setChart("p-chart", {
    type: "line",
    data: { labels: r.monthly.map((x) => x.t), datasets: [
      { label: cellScale() ? "Bu karenin NDVI'si" : "Bu tarlanın NDVI'si", data: r.monthly.map((x) => x.ndvi), borderColor: "#1a9850",
        pointRadius: 0, tension: 0.3, spanGaps: true },
      { label: "Aynı ayın ortalaması", data: r.monthly.map((x) => r.climatology[Number(x.t.slice(5)) - 1]),
        borderColor: "#7a8a7f", borderDash: [4, 4], pointRadius: 0 },
    ] },
    options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      scales: { y: { min: 0 }, x: { ticks: { maxTicksLimit: 10 } } } },
  });
}

// ---------------------------------------------------------------- uyarılar
const cellScale = () => state.status && state.status.point_scale === "cell";

async function loadSubscriptions() {
  if (STATIC) return;
  const subs = await api(URLS.subscriptions());
  $("sub-list").innerHTML = subs.length ? subs.map((s) => `<li>
      <div><b>${esc(s.field_name || "Tarla")}</b> – ${esc(s.name)}
        <div class="meta">${s.lat.toFixed(4)}, ${s.lon.toFixed(4)} · eşik VCI ${s.threshold}${s.email ? " · " + esc(s.email) : ""}</div></div>
      <span><button data-go="${s.lat},${s.lon}" class="secondary">Göster</button>
      <button data-del="${s.id}" class="secondary">Sil</button></span></li>`).join("")
    : `<li class="empty">Henüz abone tarla yok.</li>`;
}

async function loadAlerts() {
  const list = await api(URLS.alerts());
  // Statik yayında kişisel bilgi içermeyen özet gösterilir
  const text = (a) => a.message || `${a.place}: ${a.class_label} (VCI ${fmt(a.vci, 0)}, ${a.period})`;
  const when = (a) => (a.created_at || a.date || "").replace("T", " ");
  $("alert-list").innerHTML = list.length ? list.map((a) => `<li>${esc(text(a))}
      <div class="meta">${esc(when(a))} · iletim: ${esc(a.delivered)}</div></li>`).join("")
    : `<li class="empty">${STATIC ? "Henüz uyarı gönderilmedi. Abone tarlalar her ayın başında uydu verisiyle kontrol edilir."
      : 'Henüz uyarı yok. "Uyarıları şimdi kontrol et" ile abone tarlaları tarayın.'}</li>`;
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
      else alert("Abonelik formu henüz ayarlanmadı.");
      return;
    }
    const f = $("sub-form");
    f.lat.value = state.point.lat.toFixed(5);
    f.lon.value = state.point.lon.toFixed(5);
    $("uyari").scrollIntoView({ behavior: "smooth" });
    f.name.focus();
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
    const del = e.target.dataset.del, go = e.target.dataset.go;
    if (del && confirm("Abonelik silinsin mi?")) {
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
    const btn = e.target;
    btn.disabled = true; btn.textContent = "Uydu verisi kontrol ediliyor…";
    try {
      const r = await api("api/alerts/check", { method: "POST" });
      btn.textContent = `${r.checked} tarla tarandı, ${r.new_alerts.length} yeni uyarı`;
      loadAlerts();
    } catch (err) {
      btn.textContent = "Hata: " + err.message;
    } finally {
      setTimeout(() => { btn.disabled = false; btn.textContent = "Uyarıları şimdi kontrol et"; }, 3500);
    }
  });
}

// ---------------------------------------------------------------- kontroller
function fillYearMonth() {
  const { year: ly, month: lm } = state.status.latest;
  $("year").innerHTML = "";
  for (let y = ly; y >= 2017; y--) $("year").add(new Option(y, y));
  $("year").value = state.year;
  $("month").innerHTML = "";
  MONTHS.forEach((m, i) => {
    const o = new Option(m, i + 1);
    o.disabled = state.year === ly && i + 1 > lm;
    $("month").add(o);
  });
  $("month").value = state.month;
}

async function play() {
  if (state.playing) { state.playing = false; return; }
  state.playing = true;
  $("play").textContent = "■ Durdur";
  const { year: ly, month: lm } = state.status.latest;
  for (let y = 2017; y <= ly && state.playing; y++) {
    if (y === ly && state.month > lm) break;
    state.year = y;
    fillYearMonth();
    await loadMap();
    await new Promise((r) => setTimeout(r, 1100));
  }
  state.playing = false;
  $("play").textContent = "▶ Yılları oynat";
}

function bindControls() {
  $("region").addEventListener("change", async (e) => {
    state.region = e.target.value;
    const r = regionObj();
    map.setView(r.center, r.zoom);
    drawOutline();
    await loadMap();
    loadTimeseries();
    if (!state.status.live) loadDroughtHistory(); else resetDroughtHistory();
  });
  $("year").addEventListener("change", (e) => {
    state.year = Number(e.target.value);
    const { year: ly, month: lm } = state.status.latest;
    if (state.year === ly && state.month > lm) state.month = lm;
    fillYearMonth();
    loadMap();
  });
  $("month").addEventListener("change", (e) => {
    state.month = Number(e.target.value);
    loadMap();
    if (!state.status.live) loadDroughtHistory(); else resetDroughtHistory();
  });
  document.querySelectorAll("input[name=layer]").forEach((el) => el.addEventListener("change", (e) => {
    state.layer = e.target.value;
    drawGrid(); drawRaster();
  }));
  $("raster").addEventListener("change", () => { drawGrid(); drawRaster(); });
  $("play").addEventListener("click", play);
  $("dh-load").addEventListener("click", loadDroughtHistory);
}

function resetDroughtHistory() {
  // GEE modunda her yıl için ayrı uydu analizi gerektiğinden isteğe bağlı
  if (charts["c-drought"]) { charts["c-drought"].destroy(); delete charts["c-drought"]; }
  $("dh-month").textContent = MONTHS[state.month - 1];
  $("dh-load").hidden = false;
}

async function init() {
  chartDefaults();
  initMap();
  bindControls();
  bindAlerts();
  [state.status, state.regions] = await Promise.all([api(URLS.status()), api(URLS.regions())]);
  api(URLS.places()).then(drawPlaces).catch(() => {});
  const st = state.status;
  const badge = $("mode-badge");
  badge.textContent = st.label;
  badge.className = "badge " + st.mode;
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

  state.year = state.status.latest.year;
  // Varsayılan olarak bölgenin büyüme mevsimi zirvesini göster (en anlamlı karşılaştırma)
  const r0 = state.regions.find((r) => r.id === state.region);
  state.month = r0.peak_month <= state.status.latest.month ? r0.peak_month : state.status.latest.month;
  state.regions.forEach((r) => $("region").add(new Option(r.name, r.id)));
  fillYearMonth();
  map.setView(r0.center, r0.zoom);
  drawOutline();
  await loadMap();
  loadTimeseries();
  if (!state.status.live) loadDroughtHistory(); else resetDroughtHistory();
  loadSubscriptions();
  loadAlerts();
}

init().catch((e) => alert("Uygulama başlatılamadı: " + e.message));
