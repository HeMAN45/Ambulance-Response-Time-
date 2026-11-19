// C:\aimlmini\app\static\js\insights.js
// Insights page: H1 to H3 heatmaps and C1 to C9, grouped When, Where, What, Model.
// Every chart title is generated from the data so it cannot drift from the numbers.
import { fetchJSON, fmtMin, fmtShare, THEME, baseChart, axisCommon } from './common.js';

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

function setTitle(id, text) {
  document.getElementById(id).textContent = text;
}

function init(el) {
  const chart = echarts.init(el);
  return chart;
}

// ---------- heatmaps ----------

function renderHourWeekday(records) {
  const by = {};
  for (const r of records) by[`${r.weekday}|${r.hour}`] = r.median;
  const data = [];
  let slowest = null, fastest = null;
  DAYS.forEach((d, di) => HOURS.forEach(h => {
    const v = by[`${d}|${h}`];
    data.push([h, di, v]);
    if (v !== undefined) {
      if (!slowest || v > slowest.v) slowest = { v, d, h };
      if (!fastest || v < fastest.v) fastest = { v, d, h };
    }
  }));
  const values = data.filter(d => d[2] !== undefined).map(d => d[2]);
  const min = Math.min(...values), max = Math.max(...values);
  setTitle('h1-title',
    `Response is slowest on ${slowest.d} around ${slowest.h}:00, at ${slowest.v.toFixed(1)} min, and fastest on ${fastest.d} around ${fastest.h}:00, at ${fastest.v.toFixed(1)} min`);
  document.getElementById('chart-h1').setAttribute('aria-label', document.getElementById('h1-title').textContent);
  init(document.getElementById('chart-h1')).setOption(baseChart({
    tooltip: { formatter: p => `${DAYS[p.value[1]]} ${p.value[0]}:00, ${p.value[2] == null ? 'No data' : p.value[2].toFixed(1) + ' min'}` },
    grid: { left: 80, right: 24, top: 16, bottom: 60, containLabel: true },
    xAxis: axisCommon({ type: 'category', data: HOURS.map(h => `${h}`) }),
    yAxis: axisCommon({ type: 'category', data: DAYS }),
    visualMap: {
      min, max, calculable: false, orient: 'horizontal', left: 8, bottom: 0,
      inRange: { color: THEME.ramp }, text: ['min', ''], textStyle: { color: THEME.muted, fontSize: 11 },
    },
    series: [{
      type: 'heatmap', data,
      label: { show: false },
    }],
  }));
}

function renderBoroughHour(records) {
  const boroughs = [...new Set(records.map(r => r.borough))].filter(b => b !== 'Unknown');
  const by = {};
  for (const r of records) by[`${r.borough}|${r.hour}`] = r.median;
  const data = [];
  boroughs.forEach((b, bi) => HOURS.forEach(h => {
    const v = by[`${b}|${h}`];
    if (v !== undefined) data.push([h, bi, v]);
  }));
  const values = data.map(d => d[2]);
  const worst = data.reduce((a, b) => (b[2] > a[2] ? b : a));
  setTitle('h2-title', `${boroughs[worst[1]]} at ${worst[0]}:00 has the slowest median, ${worst[2].toFixed(1)} min`);
  init(document.getElementById('chart-h2')).setOption(baseChart({
    tooltip: { formatter: p => `${boroughs[p.value[1]]} ${p.value[0]}:00, ${p.value[2].toFixed(1)} min` },
    grid: { left: 90, right: 24, top: 16, bottom: 60, containLabel: true },
    xAxis: axisCommon({ type: 'category', data: HOURS.map(h => `${h}`) }),
    yAxis: axisCommon({ type: 'category', data: boroughs }),
    visualMap: {
      min: Math.min(...values), max: Math.max(...values), calculable: false,
      orient: 'horizontal', left: 8, bottom: 0,
      inRange: { color: THEME.ramp }, text: ['min', ''], textStyle: { color: THEME.muted, fontSize: 11 },
    },
    series: [{ type: 'heatmap', data }],
  }));
}

function renderSeverityBand(records) {
  const bands = ['overnight', 'morning', 'midday', 'evening'];
  const sevs = [...new Set(records.map(r => r.severity))].sort();
  const by = {};
  for (const r of records) by[`${r.severity}|${r.hour_band}`] = r.share_over_10;
  const data = [];
  sevs.forEach((s, si) => bands.forEach((b, bi) => {
    const v = by[`${s}|${b}`];
    if (v !== undefined) data.push([bi, si, v]);
  }));
  const worst = data.reduce((a, b2) => (b2[2] > a[2] ? b2 : a));
  setTitle('h3-title', `Severity ${sevs[worst[1]]} in the ${bands[worst[0]]} band has the largest share over 10 minutes, ${(worst[2] * 100).toFixed(0)}%`);
  init(document.getElementById('chart-h3')).setOption(baseChart({
    tooltip: { formatter: p => `Severity ${sevs[p.value[1]]}, ${bands[p.value[0]]}, ${(p.value[2] * 100).toFixed(0)}% over 10 min` },
    grid: { left: 90, right: 24, top: 16, bottom: 60, containLabel: true },
    xAxis: axisCommon({ type: 'category', data: bands.map(b => b[0].toUpperCase() + b.slice(1)) }),
    yAxis: axisCommon({ type: 'category', data: sevs.map(s => `Level ${s}`) }),
    visualMap: {
      min: 0, max: Math.max(...data.map(d => d[2])), calculable: false,
      orient: 'horizontal', left: 8, bottom: 0,
      inRange: { color: THEME.ramp }, text: ['share', ''], textStyle: { color: THEME.muted, fontSize: 11 },
    },
    series: [{ type: 'heatmap', data,
      label: { show: true, fontSize: 10, color: THEME.ink, formatter: p => `${(p.value[2] * 100).toFixed(0)}%` } }],
  }));
}

// ---------- line and band charts ----------

function renderHourlyBand(records) {
  const boroughs = [...new Set(records.map(r => r.borough))].filter(b => b !== 'all');
  const by = {};
  for (const r of records) by[`${r.borough}|${r.hour}`] = r;
  const series = boroughs.map((b, i) => {
    const hrs = HOURS.filter(h => by[`${b}|${h}`]);
    return {
      name: b, type: 'line', symbolSize: 4,
      data: hrs.map(h => [h, by[`${b}|${h}`].median]),
      lineStyle: { width: 1.5 }, itemStyle: { color: THEME.ramp[i % 5] },
      markPoint: undefined,
    };
  });
  const overall = HOURS.map(h => by[`all|${h}`]).filter(Boolean);
  const slowest = overall.reduce((a, b) => (b.median > a.median ? b : a));
  setTitle('c1-title', `Citywide response peaks at ${slowest.hour}:00 with a median of ${slowest.median.toFixed(1)} min`);
  init(document.getElementById('chart-c1')).setOption(baseChart({
    legend: { top: 0, textStyle: { color: THEME.muted, fontSize: 11 } },
    xAxis: axisCommon({ type: 'category', data: HOURS.map(String) }),
    yAxis: axisCommon({ type: 'value', name: 'min' }),
    series,
    tooltip: { valueFormatter: v => `${v} min` },
  }));
}

function renderTrend(records) {
  const months = Array.from({ length: 12 }, (_, i) => i + 1);
  const all = months.map(m => records.find(r => r.borough === 'all' && r.month === m)).filter(Boolean);
  const slowest = all.reduce((a, b) => (b.median > a.median ? b : a));
  setTitle('c2-title', `${MONTH_NAMES[slowest.month - 1]} was the slowest month, ${slowest.median.toFixed(1)} min median`);
  init(document.getElementById('chart-c2')).setOption(baseChart({
    xAxis: axisCommon({ type: 'category', data: months.map(m => MONTH_NAMES[m - 1].slice(0, 3)) }),
    yAxis: axisCommon({ type: 'value', name: 'min' }),
    series: [
      { name: 'Median', type: 'line', data: all.map(r => r.median), lineStyle: { color: THEME.primary, width: 2 }, itemStyle: { color: THEME.primary }, symbolSize: 5 },
      { name: '90th percentile', type: 'line', data: all.map(r => r.p90), lineStyle: { color: THEME.muted, width: 1.5, type: 'dashed' }, itemStyle: { color: THEME.muted }, symbolSize: 4 },
    ],
    legend: { top: 0, textStyle: { color: THEME.muted, fontSize: 11 } },
    tooltip: { valueFormatter: v => `${v} min` },
  }));
}

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];

function renderBoroughDot(records) {
  const rows = records.filter(r => r.value !== 'Unknown' && r.count > 1000)
    .sort((a, b) => b.median - a.median);
  setTitle('c5-title', `${rows[0].value} has the slowest median at ${rows[0].median.toFixed(1)} min, ${rows[rows.length - 1].value} the fastest at ${rows[rows.length - 1].median.toFixed(1)} min`);
  const chart = echarts.init(document.getElementById('chart-c5'));
  chart.setOption(baseChart({
    yAxis: axisCommon({ type: 'category', data: rows.map(r => r.value), inverse: true }),
    xAxis: axisCommon({ type: 'value', name: 'min', min: 0 }),
    series: [
      {
        type: 'bar', barWidth: 14, data: rows.map(r => ({
          value: r.median,
          itemStyle: { color: THEME.ramp[3], borderRadius: 2 },
        })),
        label: { show: true, position: 'right', fontSize: 11, color: THEME.ink,
          formatter: p => `${p.value.toFixed(1)} min` },
      },
      {
        type: 'custom', silent: true, data: rows.map(r => [r.p90, r.value]),
        renderItem: (params, api) => {
          const idx = params.dataIndex;
          const median = rows[idx].median;
          const xMedian = api.coord([median, idx]);
          const xP90 = api.coord([api.value(0), idx]);
          return {
            type: 'line', shape: { x1: xMedian[0], y1: xMedian[1] - 5, x2: xP90[0], y2: xMedian[1] - 5 },
            style: { stroke: THEME.muted, lineWidth: 1 },
          };
        },
        encode: { x: [0], y: [1] },
      },
    ],
    grid: { left: 24, right: 80, top: 24, bottom: 40, containLabel: true },
  }));
}

function renderDistribution(dist) {
  const bins = dist.bins;
  let cumulative = 0;
  const medBin = bins.findIndex(b => b.lo + 2 > dist.median);
  setTitle('c4-title', `Half of incidents are answered within ${dist.median.toFixed(1)} min, 9 in 10 within ${dist.p90.toFixed(1)} min`);
  init(document.getElementById('chart-c4')).setOption(baseChart({
    xAxis: axisCommon({ type: 'category', data: bins.map(b => `${b.lo}`),
      axisLabel: { color: THEME.muted, fontSize: 10, interval: 1 } }),
    yAxis: axisCommon({ type: 'value', name: 'incidents' }),
    series: [{
      type: 'bar', barWidth: '100%', barCategoryGap: '0%',
      data: bins.map((b, i) => ({
        value: b.count,
        itemStyle: { color: i === medBin ? THEME.alert : THEME.ramp[3] },
      })),
      markLine: {
        silent: true, symbol: 'none',
        data: [
          { xAxis: medBin, label: { formatter: `Median ${dist.median.toFixed(1)} min`, fontSize: 10, color: THEME.ink }, lineStyle: { color: THEME.alert, width: 1.5 } },
        ],
      },
    }],
    tooltip: { valueFormatter: v => `${v} incidents` },
  }));
}

function renderCallTypes(records) {
  const rows = records.filter(r => r.count > 1000).sort((a, b) => b.median - a.median).slice(0, 12);
  setTitle('c3-title', `${rows[0].value} is the slowest call type at ${rows[0].median.toFixed(1)} min median`);
  init(document.getElementById('chart-c3')).setOption(baseChart({
    yAxis: axisCommon({ type: 'category', data: rows.map(r => r.value), inverse: true }),
    xAxis: axisCommon({ type: 'value', name: 'min' }),
    series: [
      { type: 'bar', barWidth: 12, data: rows.map(r => r.median),
        itemStyle: { color: THEME.ramp[4], borderRadius: 2 },
        label: { show: true, position: 'right', fontSize: 10, color: THEME.ink, formatter: p => `${p.value.toFixed(1)}` } },
      { type: 'bar', barWidth: 12, data: rows.map(r => r.p90),
        itemStyle: { color: THEME.ramp[1], borderRadius: 2 } },
    ],
    legend: { top: 0, textStyle: { color: THEME.muted, fontSize: 11 }, data: ['Median', '90th pct'] },
    grid: { left: 24, right: 60, top: 24, bottom: 40, containLabel: true },
  }));
}

function renderSeverityBars(records) {
  const rows = records.filter(r => r.value !== 'Unknown').sort((a, b) => Number(a.value) - Number(b.value));
  setTitle('c6-title', `Median response rises from level ${rows[0].value} at ${rows[0].median.toFixed(1)} min to level ${rows[rows.length - 1].value} at ${rows[rows.length - 1].median.toFixed(1)} min`);
  init(document.getElementById('chart-c6')).setOption(baseChart({
    xAxis: axisCommon({ type: 'category', data: rows.map(r => `Level ${r.value}`) }),
    yAxis: axisCommon({ type: 'value', name: 'min' }),
    series: [{
      type: 'bar', barWidth: 30, data: rows.map(r => r.median),
      itemStyle: { color: THEME.ramp[3], borderRadius: 2 },
      label: { show: true, position: 'top', fontSize: 10, color: THEME.ink, formatter: p => `${p.value.toFixed(1)} min` },
    }],
    tooltip: { valueFormatter: v => `${v} min` },
  }));
}

function renderWeatherEffect(data) {
  const precip = data.precipitation || [];
  const find = (band, hol) => precip.find(r => r.precipitation_band === band && r.holiday === hol);
  const rows = [];
  const dry = find('dry', 0);
  if (dry) rows.push({ label: 'Dry', ...dry });
  const light = find('light rain', 0);
  if (light) rows.push({ label: 'Light rain', ...light });
  const moderate = find('moderate rain', 0);
  if (moderate) rows.push({ label: 'Moderate rain', ...moderate });
  const heavy = find('heavy rain', 0);
  if (heavy) rows.push({ label: 'Heavy rain', ...heavy });
  const snow = (data.snow || []).find(r => r.snow === 1);
  if (snow) rows.push({ label: 'Snow', ...snow });
  const holiday = find('dry', 1);
  if (holiday) rows.push({ label: 'Holiday', ...holiday });

  const worst = rows.reduce((a, b) => (b.median > a.median ? b : a));
  const best = rows.reduce((a, b) => (b.median < a.median ? b : a));
  setTitle('c7-title',
    `${worst.label} has the slowest median at ${worst.median.toFixed(1)} min, ${best.label} the fastest at ${best.median.toFixed(1)} min`);
  init(document.getElementById('chart-c7')).setOption(baseChart({
    xAxis: axisCommon({ type: 'category', data: rows.map(r => r.label) }),
    yAxis: axisCommon({ type: 'value', name: 'min' }),
    series: [{
      type: 'bar', barWidth: 30, data: rows.map(r => r.median),
      itemStyle: { color: THEME.ramp[3], borderRadius: 2 },
      label: { show: true, position: 'top', fontSize: 10, color: THEME.ink, formatter: p => `${p.value.toFixed(1)} min` },
    }],
    tooltip: { formatter: p => `${p.name}, ${rows[p.dataIndex].median.toFixed(1)} min median, ${rows[p.dataIndex].count.toLocaleString('en-US')} incidents` },
  }));
}

// ---------- model ----------

function renderModelComparison(models) {
  const named = models.filter(m => !m.name.startsWith('p10') && !m.name.startsWith('p50') && !m.name.startsWith('p90'));
  const best = named.reduce((a, b) => (b.mae < a.mae ? b : a));
  setTitle('c8-title', `${best.name} has the lowest MAE at ${best.mae.toFixed(2)} min`);
  init(document.getElementById('chart-c8')).setOption(baseChart({
    yAxis: axisCommon({ type: 'category', data: named.map(m => m.name), inverse: true }),
    xAxis: axisCommon({ type: 'value', name: 'MAE min' }),
    series: [{
      type: 'bar', barWidth: 16, data: named.map(m => m.mae),
      itemStyle: { color: THEME.ramp[3], borderRadius: 2 },
      label: { show: true, position: 'right', fontSize: 11, color: THEME.ink, formatter: p => p.value.toFixed(2) },
    }],
    grid: { left: 24, right: 60, top: 24, bottom: 40, containLabel: true },
  }));
  const body = document.getElementById('model-body');
  body.innerHTML = named.map(m =>
    `<tr><td>${m.name}</td><td class="num">${m.mae.toFixed(2)}</td><td class="num">${m.rmse.toFixed(2)}</td>
     <td class="num">${m.r2.toFixed(2)}</td><td class="num">${(m.within_2min_share * 100).toFixed(0)}%</td></tr>`).join('');
}

function renderImportance(top) {
  const rows = top.slice(0, 12).reverse();
  setTitle('c9-title', `${top[0].plain_name} matters most, moving typical predictions by about ${top[0].mean_abs_contribution_min.toFixed(1)} min`);
  init(document.getElementById('chart-c9')).setOption(baseChart({
    yAxis: axisCommon({ type: 'category', data: rows.map(r => r.plain_name) }),
    xAxis: axisCommon({ type: 'value', name: 'mean abs contribution, min' }),
    series: [{
      type: 'bar', barWidth: 16, data: rows.map(r => r.mean_abs_contribution_min),
      itemStyle: { color: THEME.ramp[2], borderRadius: 2 },
      label: { show: true, position: 'right', fontSize: 11, color: THEME.ink, formatter: p => p.value.toFixed(1) },
    }],
    grid: { left: 24, right: 60, top: 24, bottom: 40, containLabel: true },
  }));
  document.getElementById('shap-note').textContent =
    `Mean absolute contribution per feature from the 50th percentile model's own contribution output, on ${top.length ? 'a 5,000 row test sample' : 'no data'}. The top drivers: ${top.slice(0, 5).map(t => t.plain_name).join(', ')}.`;
}

async function main() {
  const [h1, h2, h3, hourly, trend, dist, breakdown, metrics, weather] = await Promise.all([
    fetchJSON('/api/heatmap?type=hour_weekday'),
    fetchJSON('/api/heatmap?type=borough_hour'),
    fetchJSON('/api/heatmap?type=severity_band'),
    fetchJSON('/api/hourly?borough=all'),
    fetchJSON('/api/trend?borough=all'),
    fetchJSON('/api/distribution?borough=all'),
    Promise.all([
      fetchJSON('/api/breakdown?by=call_type'),
      fetchJSON('/api/breakdown?by=borough'),
      fetchJSON('/api/breakdown?by=severity'),
    ]),
    fetchJSON('/api/metrics'),
    fetchJSON('/api/weather_effect'),
  ]);

  renderHourWeekday(h1.records);
  renderBoroughHour(h2.records);
  renderSeverityBand(h3.records);
  renderHourlyBand(hourly.records);
  renderTrend(trend.records);
  renderDistribution(dist);
  renderCallTypes(breakdown[0].records);
  renderBoroughDot(breakdown[1].records);
  renderSeverityBars(breakdown[2].records);
  renderWeatherEffect(weather);
  renderModelComparison(metrics.models);
  renderImportance(metrics.shap_top_features);
}

main().catch(err => {
  const el = document.createElement('p');
  el.className = 'error-msg show';
  el.textContent = `Some charts could not load: ${err.message}`;
  document.querySelector('main').prepend(el);
});
