// C:\aimlmini\app\static\js\predict.js
// Predict page: form, range result, explanation waterfall, two case compare,
// and a small map that shades the selected zone.
import { fetchJSON, postJSON, fmtMin, fmtInt, THEME, baseChart, axisCommon, showError, clearError } from './common.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
let zipsData = {};  // borough -> [zip]
let staticAnalytics = null;
let geoLayer = null;
let miniMap = null;
let lastZone = null;

function fillZips(selectEl, borough) {
  selectEl.innerHTML = '<option value="">Select a zip code</option>';
  for (const z of zipsData[borough] || []) {
    const opt = document.createElement('option');
    opt.value = z;
    opt.textContent = z;
    selectEl.appendChild(opt);
  }
  selectEl.disabled = false;
}

function caseFrom(prefix) {
  return {
    borough: document.getElementById(`${prefix}-borough`).value,
    zipcode: document.getElementById(`${prefix}-zip`).value,
    hour: Number(document.getElementById(`${prefix}-hour`).value),
    day_of_week: Number(document.getElementById(`${prefix}-dow`).value),
    severity: document.getElementById(`${prefix}-sev`).value,
    call_type: document.getElementById(`${prefix}-call`).value,
  };
}

async function loadZips() {
  // The route renders the borough options. Fetch the zip lists from the
  // rendered markup is unreliable, so use the schema endpoint fallback:
  // the zip lists were embedded as a JSON script block by the template.
  const el = document.getElementById('zips-data');
  if (el) zipsData = JSON.parse(el.textContent);
}

function zoneStyle(zone) {
  return f => ({
    color: '#FFFFFF', weight: 0.5, fillOpacity: 0.85,
    fillColor: zone && String(f.properties.modzcta) === zone ? THEME.primary : THEME.nodata,
  });
}

function initMiniMap() {
  if (miniMap || !window.__zipsGeo) return;
  miniMap = L.map('mini-map', { zoomControl: false, attributionControl: false, dragging: false,
    scrollWheelZoom: false, doubleClickZoom: false }).setView([40.72, -73.95], 10);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', { maxZoom: 19 }).addTo(miniMap);
  geoLayer = L.geoJSON(window.__zipsGeo, {
    style: zoneStyle(lastZone),
    interactive: false,
  }).addTo(miniMap);
  miniMap.fitBounds(geoLayer.getBounds(), { padding: [8, 8] });
}

function highlightZone(zone) {
  lastZone = zone;
  initMiniMap();
  if (!geoLayer) return;
  geoLayer.setStyle(zoneStyle(zone));
  let selected = null;
  geoLayer.eachLayer(l => {
    if (String(l.feature.properties.modzcta) === zone) selected = l;
  });
  if (selected) {
    miniMap.invalidateSize();
    miniMap.fitBounds(selected.getBounds(), { padding: [20, 20] });
  }
  const note = document.getElementById('mini-note');
  if (note) {
    note.textContent = 'The zone is shaded, not marked with a pin, because exact locations are not in the data.';
  }
}

function waterfall(explain, targetEl) {
  const items = explain.contributions.filter(c => Math.abs(c.contribution) >= 0.05).slice(0, 10);
  const labels = ['Average case', ...items.map(c => c.plain_name), 'Estimate'];
  const values = [explain.base_value, ...items.map(c => c.contribution), explain.p50];
  // running totals for a waterfall: each bar floats between cumulative values
  let running = explain.base_value;
  const bars = [];
  bars.push({ value: explain.base_value, start: 0, color: THEME.muted });
  for (const c of items) {
    bars.push({ value: c.contribution, start: c.contribution >= 0 ? running : running + c.contribution,
                color: c.contribution >= 0 ? THEME.alert : THEME.primary });
    running += c.contribution;
  }
  bars.push({ value: explain.p50, start: 0, color: THEME.ink });
  echarts.getInstanceByDom(targetEl)?.dispose();
  const chart = echarts.init(targetEl);
  chart.setOption(baseChart({
    xAxis: axisCommon({ type: 'category', data: labels,
      axisLabel: { color: THEME.muted, fontSize: 11, rotate: 28 } }),
    yAxis: axisCommon({ type: 'value', name: 'min' }),
    series: [{
      type: 'bar', barWidth: 26,
      data: bars.map(b => ({ value: b.value, itemStyle: { color: b.color } })),
      label: { show: true, fontSize: 10, color: THEME.ink,
        position: 'top', formatter: p => p.value.toFixed(1) },
      tooltip: { valueFormatter: v => `${v} min` },
    }],
    grid: { left: 40, right: 12, top: 24, bottom: 60, containLabel: true },
  }));
  targetEl.setAttribute('aria-label', `Estimate ${explain.p50} minutes. Base value ${explain.base_value} minutes. Top contributions from ${items.map(c => c.plain_name).join(', ')}.`);
}

function compareChart(a, b, diff, targetEl) {
  const labels = ['Case A', 'Case B'];
  echarts.getInstanceByDom(targetEl)?.dispose();
  const chart = echarts.init(targetEl);
  chart.setOption(baseChart({
    yAxis: axisCommon({ type: 'category', data: labels }),
    xAxis: axisCommon({ type: 'value', name: 'min', min: 0 }),
    series: [
      {
        name: 'p10', type: 'bar', stack: 'r', silent: true, barWidth: 20,
        data: [a.p10, b.p10], itemStyle: { color: 'transparent' },
      },
      {
        name: 'range', type: 'bar', stack: 'r', barWidth: 20,
        data: [a.p90 - a.p10, b.p90 - b.p10],
        itemStyle: { color: THEME.ramp[2], borderRadius: 2 },
        label: { show: true, position: 'inside', fontSize: 10, color: THEME.ink,
          formatter: p => `${[a.p10, b.p10][p.dataIndex]} to ${[a.p90, b.p90][p.dataIndex]}` },
      },
      {
        name: 'p50 marker', type: 'scatter', symbol: 'rect', symbolSize: [3, 26],
        data: [a.p50, b.p50],
        itemStyle: { color: THEME.ink },
        label: { show: true, position: 'top', fontSize: 11, color: THEME.ink,
          formatter: p => `${p.value.toFixed(1)} min` },
      },
    ],
    grid: { left: 24, right: 48, top: 24, bottom: 40, containLabel: true },
  }));
  const word = diff >= 0 ? 'slower' : 'faster';
  document.getElementById('compare-note').textContent =
    `Case B is ${Math.abs(diff).toFixed(1)} minutes ${word} than case A at the median.`;
}

function padHour(h) {
  return String(h).padStart(2, '0');
}

function initChart(id) {
  const el = document.getElementById(id);
  echarts.getInstanceByDom(el)?.dispose();
  return echarts.init(el);
}

function getStaticAnalytics() {
  if (!staticAnalytics) {
    staticAnalytics = Promise.all([
      fetchJSON('/api/zone_trend'),
      fetchJSON('/api/breakdown?by=borough'),
      fetchJSON('/api/zones?hour_band=all&severity=all'),
    ]).then(([trend, breakdown, zones]) => ({ trend, breakdown, zones }))
      .catch(err => { staticAnalytics = null; throw err; });
  }
  return staticAnalytics;
}

function renderZoneHour(zone, hour) {
  const rows = zone.hourly || [];
  if (!rows.length) return;
  const selected = rows.find(r => r.hour === Number(hour));
  const slowest = rows.reduce((a, b) => (b.median > a.median ? b : a), rows[0]);
  document.getElementById('zone-hour-title').textContent = `Zone ${zone.zone} by hour`;
  const note = document.getElementById('zone-hour-note');
  note.textContent = `Slowest at ${padHour(slowest.hour)}:00, ${slowest.median.toFixed(1)} minutes.` +
    (selected ? ` The selected hour is ${padHour(selected.hour)}:00 at ${selected.median.toFixed(1)} minutes.` : '');

  const chart = initChart('chart-zone-hour');
  chart.setOption(baseChart({
    tooltip: { trigger: 'axis', valueFormatter: v => `${Number(v).toFixed(1)} min` },
    grid: { left: 40, right: 16, top: 24, bottom: 28, containLabel: true },
    xAxis: axisCommon({ type: 'category', data: rows.map(r => String(r.hour)),
      axisLabel: { color: THEME.muted, fontSize: 11, interval: 2 } }),
    yAxis: axisCommon({ type: 'value', name: 'min', min: 0 }),
    series: [{
      type: 'line', data: rows.map(r => r.median), symbolSize: 4,
      lineStyle: { color: THEME.primary, width: 1.6 }, itemStyle: { color: THEME.primary },
      areaStyle: { color: 'rgba(18, 53, 91, 0.08)' },
      markLine: {
        silent: true, symbol: 'none',
        lineStyle: { color: THEME.alert, type: 'dashed', width: 1 },
        label: { formatter: `${padHour(hour)}:00`, color: THEME.alert, fontSize: 10 },
        data: [{ xAxis: String(hour) }],
      },
      markPoint: selected ? {
        symbol: 'circle', symbolSize: 8, itemStyle: { color: THEME.alert },
        label: { show: false },
        data: [{ coord: [String(selected.hour), selected.median] }],
      } : undefined,
    }],
  }));
  document.getElementById('chart-zone-hour').setAttribute('aria-label',
    `Median response time by hour for zone ${zone.zone}. ${note.textContent}`);
}

function renderZoneMonth(zone, trend) {
  const rows = (trend.zone_trend || [])
    .filter(r => r.zone === zone)
    .sort((a, b) => a.month - b.month);
  if (rows.length < 2) return;
  const low = rows.reduce((a, b) => (b.median < a.median ? b : a), rows[0]);
  const high = rows.reduce((a, b) => (b.median > a.median ? b : a), rows[0]);
  document.getElementById('zone-month-title').textContent = `Zone ${zone} across 2023`;
  const note = document.getElementById('zone-month-note');
  note.textContent = `Lowest in ${MONTHS[low.month - 1]} at ${low.median.toFixed(1)} minutes, ` +
    `highest in ${MONTHS[high.month - 1]} at ${high.median.toFixed(1)} minutes.`;

  const chart = initChart('chart-zone-month');
  chart.setOption(baseChart({
    tooltip: { trigger: 'axis', valueFormatter: v => `${Number(v).toFixed(1)} min` },
    grid: { left: 40, right: 16, top: 24, bottom: 28, containLabel: true },
    xAxis: axisCommon({ type: 'category', data: rows.map(r => MONTHS[r.month - 1]) }),
    yAxis: axisCommon({ type: 'value', name: 'min', scale: true }),
    series: [{
      type: 'line', data: rows.map(r => r.median), symbolSize: 5,
      lineStyle: { color: THEME.primary, width: 1.6 }, itemStyle: { color: THEME.primary },
    }],
  }));
  document.getElementById('chart-zone-month').setAttribute('aria-label',
    `Monthly median response time for zone ${zone} in 2023. ${note.textContent}`);
}

function renderContext(res, caseData, breakdown, zones) {
  const bLabel = caseData.borough === 'Staten Island' ? 'Richmond / Staten Island' : caseData.borough;
  const borough = (breakdown.records || []).find(r => r.value === bLabel);
  const city = zones.summary?.median;
  const items = [
    { label: 'This case', value: res.p50, color: THEME.primary },
    { label: 'Zone median', value: res.zone_median, color: THEME.ramp[3] },
    { label: `${caseData.borough} median`, value: borough?.median, color: THEME.ramp[2] },
    { label: 'City median', value: city, color: THEME.muted },
  ].filter(i => Number.isFinite(i.value));
  if (items.length < 2) return;

  let text = `This case is ${Math.abs(res.p50 - res.zone_median).toFixed(1)} minutes ` +
    `${res.p50 >= res.zone_median ? 'slower' : 'faster'} than the zone median`;
  if (Number.isFinite(borough?.median)) {
    const d = res.p50 - borough.median;
    text += ` and ${Math.abs(d).toFixed(1)} minutes ${d >= 0 ? 'slower' : 'faster'} than the ${caseData.borough} median`;
  }
  document.getElementById('context-note').textContent = `${text}.`;

  const chart = initChart('chart-context');
  chart.setOption(baseChart({
    tooltip: { trigger: 'item', formatter: p => `${p.name}: ${p.value.toFixed(1)} min` },
    grid: { left: 8, right: 56, top: 16, bottom: 24, containLabel: true },
    xAxis: axisCommon({ type: 'value', name: 'min', min: 0 }),
    yAxis: axisCommon({ type: 'category', inverse: true, data: items.map(i => i.label) }),
    series: [{
      type: 'bar', barMaxWidth: 22,
      data: items.map(i => ({ value: i.value, itemStyle: { color: i.color } })),
      label: { show: true, position: 'right', fontSize: 11, color: THEME.ink,
        formatter: p => `${p.value.toFixed(1)}` },
    }],
  }));
  document.getElementById('chart-context').setAttribute('aria-label',
    `How this estimate compares. ${document.getElementById('context-note').textContent}`);
}

async function renderAnalytics(res, caseData) {
  try {
    const [zone, statics] = await Promise.all([
      fetchJSON(`/api/zone/${encodeURIComponent(res.zone)}`),
      getStaticAnalytics(),
    ]);
    document.getElementById('analytics').style.display = 'grid';
    renderZoneHour(zone, caseData.hour);
    renderZoneMonth(String(res.zone), statics.trend);
    renderContext(res, caseData, statics.breakdown, statics.zones);
  } catch (e) {
    document.getElementById('analytics').style.display = 'none';
  }
}

async function submitForm(prefix) {
  const errEl = document.getElementById(`err-${prefix}`);
  clearError(errEl);
  const data = caseFrom(prefix);
  if (!data.borough || !data.zipcode) {
    showError(errEl, 'Choose a borough and a zip code first.');
    return;
  }
  try {
    const res = await postJSON('/api/predict', data);
    const explain = await postJSON('/api/explain', data);
    document.getElementById('result-panel').style.display = 'block';
    document.getElementById('res-p50').textContent = `${res.p50.toFixed(1)} min`;
    document.getElementById('res-range').textContent =
      `Likely range: ${res.p10.toFixed(1)} to ${res.p90.toFixed(1)} minutes, 10th to 90th percentile.`;
    const diffP = res.p50 - res.zone_median;
    document.getElementById('res-compare').textContent =
      `Zone ${res.zone} median is ${fmtMin(res.zone_median)} across all hours, so this case is ` +
      `${Math.abs(diffP).toFixed(1)} minutes ${diffP >= 0 ? 'slower' : 'faster'} than the zone median.`;
    const sparse = res.zone_count < 30;
    document.getElementById('res-sparse').textContent = sparse
      ? `This zone has only ${fmtInt(res.zone_count)} incidents in the data, so treat the range with care.`
      : '';
    waterfall(explain, document.getElementById('waterfall'));
    highlightZone(String(res.zone));
    renderAnalytics(res, data);
    document.getElementById('result-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (e) {
    showError(errEl, e.message);
  }
}

async function submitCompare() {
  const a = caseFrom('a'), b = caseFrom('b');
  const errEl = document.getElementById('err-b');
  clearError(errEl);
  if (!b.borough || !b.zipcode) {
    showError(errEl, 'Fill in case B to compare.');
    return;
  }
  try {
    const res = await postJSON('/api/compare', { case_a: a, case_b: b });
    document.getElementById('compare-panel').style.display = 'block';
    compareChart(res.case_a, res.case_b, res.difference_p50, document.getElementById('compare-chart'));
    document.getElementById('compare-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (e) {
    showError(errEl, e.message);
  }
}

async function main() {
  await loadZips();
  for (const p of ['a', 'b']) {
    document.getElementById(`${p}-borough`).addEventListener('change', e => {
      fillZips(document.getElementById(`${p}-zip`), e.target.value);
    });
  }
  document.getElementById('form-a').addEventListener('submit', e => { e.preventDefault(); submitForm('a'); });
  document.getElementById('form-b').addEventListener('submit', e => { e.preventDefault(); submitCompare(); });
  document.getElementById('show-compare').onclick = () => {
    document.getElementById('panel-b-wrap').style.display = 'block';
    document.getElementById('show-compare').disabled = true;
  };
  // boundaries for the highlight map, fetched once
  try {
    window.__zipsGeo = await fetchJSON('/geo/zips.geojson');
  } catch (e) {
    window.__zipsGeo = null;
  }
  initMiniMap();
}

main();
