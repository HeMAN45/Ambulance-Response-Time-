// C:\aimlmini\app\static\js\method.js
// Method page: model card, calibration charts C10 to C12, limitations.
import { fetchJSON, fmtMin, THEME, baseChart, axisCommon } from './common.js';

function renderCard(card) {
  const rows = [
    ['Task', card.task],
    ['Data source', card.data_source],
    ['Training period', `${card.training_period[0].slice(0, 10)} to ${card.training_period[1].slice(0, 10)}`],
    ['Test period', `${card.test_period[0].slice(0, 10)} to ${card.test_period[1].slice(0, 10)}`],
    ['Rows after valid flag', card.row_counts.after_valid_flag],
    ['Rows after 60 minute cut', card.row_counts.after_60min_cut],
    ['Train rows', card.row_counts.train_rows],
    ['Test rows', card.row_counts.test_rows],
    ['Best model', `${card.best_model}, beats baseline: ${card.beats_baseline ? 'yes' : 'no'}`],
    ['Range coverage', `${(card.range_coverage * 100).toFixed(1)}% of test cases inside the 10 to 90 range`],
    ['Weather features', card.weather
      ? `${card.weather.decision}: test MAE ${card.weather.with_mae} min with weather and ${card.weather.without_mae} min without`
      : 'Not evaluated'],
    ['Intended use', card.intended_use],
    ['Known weaknesses', card.known_weaknesses.join(' ')],
    ['Limitations', card.limitations.join(' ')],
  ];
  document.getElementById('card-body').innerHTML = rows.map(([k, v]) =>
    `<tr><th scope="row" style="width:200px;color:var(--muted);font-size:12px;text-transform:uppercase">${k}</th><td>${v}</td></tr>`).join('');
  document.getElementById('limitations').innerHTML =
    card.limitations.map(l => `<li>${l}</li>`).join('');
}

function renderCalibration(data) {
  const bins = data.pred_vs_actual;
  const all = bins.flatMap(b => [b.predicted, b.actual]);
  const lo = Math.min(...all), hi = Math.max(...all);
  const worstBin = bins.reduce((a, b) => (Math.abs(b.actual - b.predicted) > Math.abs(a.actual - a.predicted) ? b : a));
  document.getElementById('c10-title').textContent =
    `Calibration: the worst bin is off by ${Math.abs(worstBin.actual - worstBin.predicted).toFixed(1)} min (${worstBin.bin + 1} of 10)`;
  echarts.init(document.getElementById('chart-c10')).setOption(baseChart({
    xAxis: axisCommon({ type: 'value', name: 'predicted min', min: Math.floor(lo), max: Math.ceil(hi) }),
    yAxis: axisCommon({ type: 'value', name: 'actual min', min: Math.floor(lo), max: Math.ceil(hi) }),
    series: [
      {
        type: 'line', silent: true, data: [[lo, lo], [hi, hi]], symbol: 'none',
        lineStyle: { color: THEME.muted, type: 'dashed', width: 1 },
      },
      {
        type: 'scatter', symbolSize: 8,
        data: bins.map(b => [b.predicted, b.actual]),
        itemStyle: { color: THEME.primary },
        label: { show: false },
        tooltip: { valueFormatter: v => `${v} min` },
      },
    ],
  }));
  document.getElementById('chart-c10').setAttribute('aria-label',
    `Predicted versus actual. Worst bin off by ${Math.abs(worstBin.actual - worstBin.predicted).toFixed(1)} minutes.`);

  const boroughs = Object.keys(data.range_coverage_by_borough);
  const cover = data.range_coverage_by_borough;
  document.getElementById('c11-title').textContent =
    `Range coverage ranges from ${(Math.min(...Object.values(cover)) * 100).toFixed(0)}% to ${(Math.max(...Object.values(cover)) * 100).toFixed(0)}% across boroughs`;
  echarts.init(document.getElementById('chart-c11')).setOption(baseChart({
    xAxis: axisCommon({ type: 'category', data: boroughs }),
    yAxis: axisCommon({ type: 'value', name: 'covered', min: 0.5, max: 1,
      axisLabel: { formatter: v => `${(v * 100).toFixed(0)}%` } }),
    series: [
      {
        type: 'bar', barWidth: 30, data: boroughs.map(b => cover[b]),
        itemStyle: { color: THEME.ramp[3], borderRadius: 2 },
        label: { show: true, position: 'top', fontSize: 10, color: THEME.ink,
          formatter: p => `${(p.value * 100).toFixed(0)}%` },
      },
      {
        type: 'line', silent: true, data: boroughs.map(() => 0.8), symbol: 'none',
        lineStyle: { color: THEME.alert, width: 1.5, type: 'dashed' },
      },
    ],
  }));

  const hours = Object.keys(data.error_by_hour).map(Number).sort((a, b) => a - b);
  const worstHour = hours.reduce((a, b) => (data.error_by_hour[b] > data.error_by_hour[a] ? b : a));
  document.getElementById('c12-title').textContent =
    `Error is highest at ${worstHour}:00, at ${data.error_by_hour[worstHour].toFixed(1)} min mean absolute error`;
  echarts.init(document.getElementById('chart-c12')).setOption(baseChart({
    xAxis: axisCommon({ type: 'category', data: hours.map(h => `${h}`) }),
    yAxis: axisCommon({ type: 'value', name: 'MAE min' }),
    series: [{
      type: 'bar', barWidth: '80%', data: hours.map(h => data.error_by_hour[h]),
      itemStyle: { color: THEME.ramp[2], borderRadius: 2 },
      label: { show: false },
    }],
    tooltip: { valueFormatter: v => `${v} min` },
  }));
}

async function main() {
  const [card, calibration] = await Promise.all([
    fetchJSON('/api/modelcard'),
    fetchJSON('/api/calibration'),
  ]);
  renderCard(card);
  renderCalibration(calibration);
}

main().catch(err => {
  const el = document.createElement('p');
  el.className = 'error-msg show';
  el.textContent = `The Method page could not load: ${err.message}`;
  document.querySelector('main').prepend(el);
});
