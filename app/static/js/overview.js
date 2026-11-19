// C:\aimlmini\app\static\js\overview.js
// Overview page: choropleth map, filters, metric switch, four band small
// multiples, difference and volume views, zone panel, ranking table, URL state.
import { fetchJSON, fmtMin, fmtShare, fmtInt, THEME, baseChart, axisCommon } from './common.js';

const state = {
  band: 'all', severity: 'all', metric: 'median', view: 'single', zone: null,
};
const BANDS = ['overnight', 'morning', 'midday', 'evening'];
const MIN_INCIDENTS = 30;

let geojson = null;        // boundary features, fetched once
let mainLayer = null;      // Leaflet layer on the main map
let mainMap = null;
let bandLayers = {};       // four band small multiples
let bandMaps = {};
let currentZones = {};     // zone -> record for the active filter
let zoneMeta = {};         // zone -> borough from geo properties

const METRIC_INFO = {
  median: { label: 'Median', unit: 'min', fmt: fmtMin },
  p90: { label: '90th percentile', unit: 'min', fmt: fmtMin },
  share_over_10: { label: 'Share over 10 minutes', unit: '%', fmt: fmtShare },
};

// ---------- URL state so a view can be shared ----------

function readURL() {
  const q = new URLSearchParams(location.search);
  if (BANDS.includes(q.get('band'))) state.band = q.get('band');
  if (q.get('sev')) state.severity = q.get('sev');
  if (['median', 'p90', 'share_over_10'].includes(q.get('metric'))) state.metric = q.get('metric');
  if (['single', 'bands', 'diff', 'volume'].includes(q.get('view'))) state.view = q.get('view');
  if (q.get('zone')) state.zone = q.get('zone');
}

function writeURL() {
  const q = new URLSearchParams();
  if (state.band !== 'all') q.set('band', state.band);
  if (state.severity !== 'all') q.set('sev', state.severity);
  if (state.metric !== 'median') q.set('metric', state.metric);
  if (state.view !== 'single') q.set('view', state.view);
  if (state.zone) q.set('zone', state.zone);
  const url = q.toString() ? `${location.pathname}?${q}` : location.pathname;
  history.replaceState(null, '', url);
}

// ---------- colour scales ----------

function quantileClasses(values, k = 5) {
  const v = [...values].sort((a, b) => a - b);
  const breaks = [];
  for (let i = 1; i < k; i++) {
    const pos = (v.length - 1) * (i / k);
    const lo = Math.floor(pos), hi = Math.ceil(pos);
    breaks.push(v[lo] + (v[hi] - v[lo]) * (pos - lo));
  }
  return breaks;
}

function colourFor(value, breaks, invert = false) {
  if (value === undefined || value === null || Number.isNaN(value)) return THEME.nodata;
  let idx = breaks.findIndex(b => value <= b);
  if (idx === -1) idx = 4;
  return invert ? THEME.ramp[4 - idx] : THEME.ramp[idx];
}

function legendHTML(breaks, unit, invert = false) {
  const swatches = invert ? [...THEME.ramp].reverse() : THEME.ramp;
  const edges = [Math.min(...borders(breaks)), ...breaks, Math.max(...borders(breaks))];
  function borders(bs) {
    return bs.map(b => (unit === 'min' ? b.toFixed(1) : Math.round(b * 100) + '%'));
  }
  return `<div class="legend"><div class="ramp">${swatches.map(c => `<span style="background:${c}"></span>`).join('')}</div>
    <div class="ticks"><span>${edges[0]}</span><span>${edges[1]}</span><span>${edges[2]}</span><span>${edges[3]}</span><span>${edges[4]}</span></div>
    <div class="small" style="margin-top:4px">${unit === 'min' ? 'Minutes' : 'Share of incidents'}</div>
    <div class="small"><span class="nodata-swatch"></span>Not enough data</div></div>`;
}

function styleFor(feature, breaks, metricKey, invert = false) {
  const rec = currentZones[feature.properties.modzcta];
  const sparse = !rec || rec.count < MIN_INCIDENTS;
  return {
    color: '#FFFFFF', weight: 0.6, fillOpacity: 0.9,
    fillColor: sparse ? THEME.nodata : colourFor(rec ? rec[metricKey] : null, breaks, invert),
  };
}

// ---------- main map ----------

function restyleMain() {
  const key = state.view === 'volume' ? 'count' : state.metric;
  const invert = state.view === 'volume';
  const values = Object.values(currentZones)
    .filter(r => r.count >= MIN_INCIDENTS)
    .map(r => r[key]);
  const breaks = quantileClasses(values);
  mainLayer.setStyle(f => styleFor(f, breaks, key, invert));
  document.getElementById('map-caption').innerHTML =
    `${METRIC_INFO[state.view === 'volume' ? 'median' : state.metric].label} by zone, ${labelForFilter()}. ` +
    `Zones with fewer than ${MIN_INCIDENTS} incidents are grey.`;
  let legend = document.querySelector('.legend-wrap');
  if (!legend) {
    legend = document.createElement('div');
    legend.className = 'legend-wrap';
    const corner = L.control({ position: 'bottomright' });
    corner.onAdd = () => legend;
    corner.addTo(mainMap);
  }
  const legendValues = Object.values(currentZones).filter(r => r.count >= MIN_INCIDENTS).map(r => r[key]);
  const lb = quantileClasses(legendValues);
  legend.innerHTML = legendHTML(lb, state.view === 'volume' ? 'count' : (state.metric === 'share_over_10' ? '%' : 'min'), invert);
}

function labelForFilter() {
  const bandNames = { all: 'all hours', overnight: 'overnight', morning: 'morning', midday: 'midday', evening: 'evening' };
  const sev = state.severity === 'all' ? 'all severities' : `severity ${state.severity}`;
  return `${bandNames[state.band]}, ${sev}`;
}

async function loadZonesAndRestyle() {
  const data = await fetchJSON(`/api/zones?hour_band=${state.band}&severity=${state.severity}`);
  currentZones = {};
  for (const z of data.zones) currentZones[z.zone] = z;
  updateSummary(data.summary);
  restyleMain();
  writeURL();
}

function updateSummary(s) {
  document.getElementById('sum-median').innerHTML = `${s.median.toFixed(1)}<span class="unit">min</span>`;
  document.getElementById('sum-p90').innerHTML = `${s.p90.toFixed(1)}<span class="unit">min</span>`;
  document.getElementById('sum-share').textContent = fmtShare(s.share_over_10);
  document.getElementById('sum-count').textContent = fmtInt(s.count);
}

function initMainMap() {
  mainMap = L.map('map', { attributionControl: true }).setView([40.72, -73.95], 10);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap contributors, &copy; CARTO',
    maxZoom: 19,
  }).addTo(mainMap);
  mainLayer = L.geoJSON(geojson, {
    style: f => ({ color: '#FFFFFF', weight: 0.6, fillOpacity: 0.9, fillColor: THEME.nodata }),
    onEachFeature: (feature, layer) => {
      layer.on('mouseover', () => showTooltip(feature, layer));
      layer.on('mouseout', () => layer.closePopup());
      layer.on('click', () => selectZone(feature.properties.modzcta));
    },
  }).addTo(mainMap);
}

function showTooltip(feature, layer) {
  const z = feature.properties.modzcta;
  const rec = currentZones[z];
  const key = state.view === 'volume' ? 'count' : state.metric;
  let line;
  if (!rec || rec.count < MIN_INCIDENTS) {
    line = 'Not enough data';
  } else if (state.view === 'diff') {
    const d = rec.diff;
    line = `Evening minus morning: ${d >= 0 ? '+' : ''}${d.toFixed(1)} min`;
  } else if (key === 'share_over_10') {
    line = `${METRIC_INFO.share_over_10.label}: ${fmtShare(rec.share_over_10)}`;
  } else if (key === 'count') {
    line = `Incidents: ${fmtInt(rec.count)}`;
  } else {
    line = `${METRIC_INFO[key].label}: ${fmtMin(rec[key])}`;
  }
  layer.bindTooltip(`<b>${z}</b>, ${zoneMeta[z] || ''}<br>${line}`, { sticky: true }).openTooltip();
}

// M3: difference map, evening median minus morning median, diverging ramp used
// nowhere else. Positive means the evening is slower.
async function loadDiffAndRestyle() {
  const [evening, morning] = await Promise.all([
    fetchJSON('/api/zones?hour_band=evening&severity=all'),
    fetchJSON('/api/zones?hour_band=morning&severity=all'),
  ]);
  const diff = {};
  for (const z of evening.zones) {
    const m = morning.zones.find(x => x.zone === z.zone);
    if (m && z.count >= MIN_INCIDENTS && m.count >= MIN_INCIDENTS) {
      diff[z.zone] = { zone: z.zone, count: Math.min(z.count, m.count), diff: z.median - m.median };
    }
  }
  currentZones = diff;
  const key = 'diff';
  const values = Object.values(currentZones).map(r => r[key]);
  const breaks = quantileClasses(values);
  const diffColors = [THEME.alert, '#E7C7C4', '#F5F3EE', '#BCD0E4', THEME.primary];
  mainLayer.setStyle(f => {
    const rec = currentZones[f.properties.modzcta];
    if (!rec) return { color: '#FFFFFF', weight: 0.6, fillOpacity: 0.9, fillColor: THEME.nodata };
    let idx = breaks.findIndex(b => rec.diff <= b);
    if (idx === -1) idx = 4;
    return { color: '#FFFFFF', weight: 0.6, fillOpacity: 0.9, fillColor: diffColors[idx] };
  });
  document.getElementById('map-caption').innerHTML =
    `Evening median minus morning median by zone, all severities. Red means the evening is slower than the morning, blue means it is faster. Zones with fewer than 30 incidents in either band are grey.`;
  let legend = document.querySelector('.legend-wrap');
  if (!legend) {
    legend = document.createElement('div');
    legend.className = 'legend-wrap';
    const corner = L.control({ position: 'bottomright' });
    corner.onAdd = () => legend;
    corner.addTo(mainMap);
  }
  legend.innerHTML = `<div class="legend"><div class="ramp">${diffColors.map(c => `<span style="background:${c}"></span>`).join('')}</div>
    <div class="ticks"><span>Slower</span><span></span><span>0</span><span></span><span>Faster</span></div>
    <div class="small" style="margin-top:4px">Minutes, evening minus morning</div>
    <div class="small"><span class="nodata-swatch"></span>Not enough data</div></div>`;
  writeURL();
}

// ---------- zone selection panel ----------

async function selectZone(zone) {
  state.zone = zone;
  writeURL();
  try {
    const d = await fetchJSON(`/api/zone/${zone}`);
    document.getElementById('zone-hint').style.display = 'none';
    document.getElementById('zone-body').style.display = 'block';
    document.getElementById('zone-name').textContent = `${zone}, ${zoneMeta[zone] || d.zone}`;
    document.getElementById('zone-median').textContent = fmtMin(d.median);
    document.getElementById('zone-count').textContent = fmtInt(d.count);
    document.getElementById('zone-note').textContent =
      d.count < MIN_INCIDENTS ? `Only ${d.count} incidents, interpret with care.` : '';
    const rows = d.hourly;
    const title = chartTitleForHourly(rows);
    echarts.init(document.getElementById('zone-chart'), null, { renderer: 'canvas' }).dispose?.();
    const chart = echarts.init(document.getElementById('zone-chart'));
    chart.setOption(baseChart({
      title: { text: title, left: 0, textStyle: { fontSize: 12, color: THEME.ink } },
      xAxis: axisCommon({ type: 'category', data: rows.map(r => r.hour) }),
      yAxis: axisCommon({ type: 'value', name: 'min' }),
      series: [{
        type: 'line', data: rows.map(r => r.median),
        lineStyle: { color: THEME.primary, width: 1.5 },
        itemStyle: { color: THEME.primary },
        symbolSize: 4,
        label: { show: rows.length <= 24, fontSize: 9, color: THEME.muted, position: 'top' },
      }],
      grid: { left: 40, right: 12, top: 32, bottom: 28, containLabel: true },
      tooltip: { valueFormatter: v => `${v} min` },
    }));
    // outline the selected zone
    mainLayer.eachLayer(layer => {
      const selected = layer.feature.properties.modzcta === zone;
      layer.setStyle({ weight: selected ? 2.5 : 0.6, color: selected ? THEME.alert : '#FFFFFF' });
      if (selected) layer.bringToFront();
    });
  } catch (e) {
    document.getElementById('zone-hint').style.display = 'block';
    document.getElementById('zone-hint').textContent = e.message;
  }
}

function chartTitleForHourly(rows) {
  if (!rows.length) return 'No data for this zone';
  const slowest = rows.reduce((a, b) => (b.median > a.median ? b : a));
  return `Slowest at ${slowest.hour}:00, ${slowest.median.toFixed(1)} min median`;
}

// ---------- four band small multiples ----------

function initBandMaps() {
  for (const band of BANDS) {
    if (bandMaps[band]) continue;
    bandMaps[band] = L.map(`map-${band}`, {
      zoomControl: false, attributionControl: false, dragging: false,
      scrollWheelZoom: false, doubleClickZoom: false,
    }).setView([40.72, -73.95], 10);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', { maxZoom: 19 }).addTo(bandMaps[band]);
    bandLayers[band] = L.geoJSON(geojson, {
      style: () => ({ color: '#FFFFFF', weight: 0.5, fillOpacity: 0.9, fillColor: THEME.nodata }),
      interactive: false,
    }).addTo(bandMaps[band]);
  }
}

async function renderBandMaps() {
  initBandMaps();
  // fetch each band with the same severity filter, then one shared colour scale
  const all = await Promise.all(BANDS.map(b =>
    fetchJSON(`/api/zones?hour_band=${b}&severity=${state.severity}`)));
  const shared = {};
  for (const d of all) for (const z of d.zones) shared[z.zone] = z;
  const values = Object.values(shared).filter(r => r.count >= MIN_INCIDENTS).map(r => r.median);
  const breaks = quantileClasses(values);
  BANDS.forEach((band, i) => {
    const bandZones = {};
    for (const z of all[i].zones) bandZones[z.zone] = z;
    bandLayers[band].setStyle?.(f => {
      const rec = bandZones[f.properties.modzcta];
      const sparse = !rec || rec.count < MIN_INCIDENTS;
      return {
        color: '#FFFFFF', weight: 0.5, fillOpacity: 0.9,
        fillColor: sparse ? THEME.nodata : colourFor(rec ? rec.median : null, breaks),
      };
    });
  });
}

// ---------- ranking table with sparklines ----------

let rankZones = [];
let rankSort = { key: 'median', dir: -1 };

async function loadRanking() {
  const [zones, trend] = await Promise.all([
    fetchJSON('/api/zones?hour_band=all&severity=all'),
    fetchJSON('/api/zone_trend'),
  ]);
  const trendByZone = {};
  for (const r of trend.zone_trend) {
    (trendByZone[r.zone] = trendByZone[r.zone] || []).push(r);
  }
  rankZones = zones.zones.map(z => Object.assign({}, z, { trend: trendByZone[z.zone] || [] }));
  renderRanking();
}

function renderRanking() {
  const key = rankSort.key, dir = rankSort.dir;
  const rows = [...rankZones].filter(r => r.count >= MIN_INCIDENTS)
    .sort((a, b) => dir * (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0)).slice(0, 15);
  const body = document.getElementById('rank-body');
  body.innerHTML = rows.map(r => {
    const spark = sparkline(r.trend.map(t => t.median));
    const title = chartSentenceFor(r);
    return `<tr><td>${r.zone}</td><td>${zoneMeta[r.zone] || ''}</td>
      <td class="num">${fmtMin(r.median)}</td><td class="num">${fmtMin(r.p90)}</td>
      <td class="num">${fmtInt(r.count)}</td>
      <td><svg width="80" height="20" aria-label="${title}">${spark}</svg></td></tr>`;
  }).join('');
  body.closest('table').querySelectorAll('th[data-sort]').forEach(th => {
    th.onclick = () => {
      const k = th.dataset.sort;
      rankSort = { key: k, dir: rankSort.key === k ? -rankSort.dir : (k === 'zone' ? 1 : -1) };
      renderRanking();
    };
  });
}

function chartSentenceFor(r) {
  const t = r.trend;
  if (t.length < 2) return 'Not enough months';
  const first = t[0], last = t[t.length - 1];
  const d = last.median - first.median;
  const word = Math.abs(d) < 0.2 ? 'stayed level' : d > 0 ? 'got slower' : 'got faster';
  return `${r.zone}: from ${first.median.toFixed(1)} min in month ${first.month} to ${last.median.toFixed(1)} min in month ${last.month}, ${word}`;
}

function sparkline(values) {
  if (values.length < 2) return '';
  const w = 80, h = 20, min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) =>
    `${(i / (values.length - 1)) * w},${h - 2 - ((v - min) / span) * (h - 4)}`).join(' ');
  return `<polyline points="${pts}" fill="none" stroke="${THEME.primary}" stroke-width="1.2"/>`;
}

// ---------- view switching ----------

function setView(view) {
  state.view = view;
  for (const [id, v] of [['view-single', 'single'], ['view-bands', 'bands'],
                         ['view-diff', 'diff'], ['view-volume', 'volume']]) {
    document.getElementById(id).setAttribute('aria-pressed', String(v === view));
  }
  document.getElementById('band-maps').style.display = view === 'bands' ? 'grid' : 'none';
  document.getElementById('map').style.display = view === 'bands' ? 'none' : 'block';
  if (view === 'bands') {
    renderBandMaps();
    writeURL();
  } else if (view === 'diff') {
    loadDiffAndRestyle();
  } else {
    loadZonesAndRestyle();
  }
}

// ---------- wiring ----------

async function main() {
  readURL();
  geojson = await fetchJSON('/geo/zips.geojson');
  for (const f of geojson.features) {
    zoneMeta[f.properties.modzcta] = f.properties.borough;
    f.properties.modzcta = String(f.properties.modzcta);
  }
  initMainMap();
  await loadZonesAndRestyle();
  await loadRanking();
  if (state.zone) selectZone(state.zone);

  document.getElementById('band').value = state.band;
  document.getElementById('severity').value = state.severity;
  document.getElementById('band').onchange = e => { state.band = e.target.value; loadZonesAndRestyle(); };
  document.getElementById('severity').onchange = e => { state.severity = e.target.value; loadZonesAndRestyle(); };

  for (const [id, metric] of [['metric-median', 'median'], ['metric-p90', 'p90'], ['metric-share', 'share_over_10']]) {
    document.getElementById(id).onclick = () => {
      state.metric = metric;
      for (const [id2, m2] of [['metric-median', 'median'], ['metric-p90', 'p90'], ['metric-share', 'share_over_10']]) {
        document.getElementById(id2).setAttribute('aria-pressed', String(m2 === metric));
      }
      loadZonesAndRestyle();
    };
  }
  document.getElementById('view-single').onclick = () => setView('single');
  document.getElementById('view-bands').onclick = () => setView('bands');
  document.getElementById('view-diff').onclick = () => setView('diff');
  document.getElementById('view-volume').onclick = () => setView('volume');

  document.getElementById('export').onclick = () => {
    const url = `/api/export/zones.csv?hour_band=${state.band}&severity=${state.severity}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = 'zones.csv';
    a.click();
  };
}

main().catch(err => {
  document.getElementById('map-caption').innerHTML =
    `<span class="error-msg show" role="alert">${err.message}</span>`;
});
