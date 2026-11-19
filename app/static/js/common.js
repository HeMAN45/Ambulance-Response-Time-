// C:\aimlmini\app\static\js\common.js
// Shared helpers: fetch wrapper with plain errors, chart theme built from the
// design tokens, number formatting with units.

export async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let msg = `Request failed with status ${res.status}`;
    try {
      const body = await res.json();
      if (body && body.error) msg = body.error;
    } catch (e) { /* non JSON error body */ }
    throw new Error(msg);
  }
  return res.json();
}

export function postJSON(url, data) {
  return fetchJSON(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export function fmtMin(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'No data';
  return `${Number(v).toFixed(1)} min`;
}

export function fmtShare(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'No data';
  return `${(v * 100).toFixed(0)}%`;
}

export function fmtInt(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'No data';
  return Number(v).toLocaleString('en-US');
}

// Chart theme. One hue ramp, muted ink axes, no 3D, no rainbow palettes.
export const THEME = {
  ink: '#0F1A2B',
  muted: '#5B6575',
  rule: '#D9D5CC',
  primary: '#12355B',
  alert: '#B3261E',
  ramp: ['#E6EDF5', '#BCD0E4', '#7FA3C7', '#3F6E9F', '#12355B'],
  diverging: ['#B3261E', '#f0d4d2', '#F5F3EE', '#BCD0E4', '#12355B'],
  nodata: '#E4E2DC',
  fontFamily: 'Inter, Segoe UI, sans-serif',
  fontSize: 12,
};

export function baseChart(extra = {}) {
  return Object.assign({
    textStyle: { fontFamily: THEME.fontFamily, fontSize: THEME.fontSize, color: THEME.ink },
    animationDuration: 150,
    grid: { left: 56, right: 24, top: 24, bottom: 40, containLabel: true },
    axisPointer: { lineStyle: { color: THEME.muted } },
  }, extra);
}

export function axisCommon(extra = {}) {
  return Object.assign({
    axisLine: { lineStyle: { color: THEME.rule } },
    axisLabel: { color: THEME.muted, fontSize: 11 },
    axisTick: { show: false },
  }, extra);
}

// Build an ECharts option for a bar or line chart with direct labels.
export function simpleOption({ categories, series, unit, kind = 'bar', horizontal = false }) {
  const valueAxis = axisCommon({ axisLabel: { color: THEME.muted, fontSize: 11 } });
  const catAxis = axisCommon();
  const s = series.map(x => Object.assign({
    type: kind,
    itemStyle: { color: THEME.primary, borderRadius: 2 },
    barMaxWidth: 28,
    label: { show: true, color: THEME.ink, fontSize: 11, position: 'top' },
  }, x));
  const option = baseChart({
    xAxis: horizontal ? valueAxis : catAxis,
    yAxis: horizontal ? catAxis : valueAxis,
    series: s,
  });
  if (horizontal) {
    option.series.forEach(x => { if (x.label) x.label.position = 'right'; });
    option.grid = { left: 24, right: 48, top: 24, bottom: 40, containLabel: true };
  }
  if (unit) option.tooltip = { valueFormatter: v => `${v} ${unit}` };
  return option;
}

// Render a chart and register an accessible fallback table.
export function renderChart(el, option, { title, rows, unit } = {}) {
  const chart = echarts.init(el, null, { renderer: 'canvas' });
  chart.setOption(option);
  if (title) el.setAttribute('aria-label', title);
  if (rows && title) {
    const table = document.createElement('table');
    table.className = 'data visually-hidden';
    const header = Object.keys(rows[0]).map(k => `<th scope="col">${k}</th>`).join('');
    const body = rows.map(r => `<tr>${Object.values(r).map(v => `<td>${v}</td>`).join('')}</tr>`).join('');
    table.innerHTML = `<caption>${title}</caption><thead><tr>${header}</tr></thead><tbody>${body}</tbody>`;
    el.after(table);
  }
  return chart;
}

export function showError(el, message) {
  el.textContent = message;
  el.classList.add('show');
}

export function clearError(el) {
  el.textContent = '';
  el.classList.remove('show');
}

export function emptyState(el, message) {
  el.innerHTML = `<p class="small">${message}</p>`;
}
