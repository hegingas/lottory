/**
 * ECharts 走势图渲染
 * 根据彩票类型和 API 数据自适应渲染图表
 */

// ── 通用主题色 ──
const COLORS = {
  sum: '#e74c3c',
  span: '#3498db',
  ac: '#27ae60',
  consecutive: '#e67e22',
  odd: '#9b59b6',
  even: '#2ecc71',
  freq: '#3498db',
  omission: '#e74c3c',
};

// ── 初始化所有图表 ──
function renderAllCharts(data) {
  renderSumChart(data);
  if (data.spans) renderSpanChart(data);
  if (data.ac_values) renderAcChart(data);
  if (data.consecutive) renderConsecutiveChart(data);
  if (data.odd_counts) renderOEChart(data);
  renderFreqChart(data);
  renderOmissionChart(data);
  if (data.zone_heatmap && data.zone_heatmap.length > 0) renderHeatmap(data);
}

function initChart(domId) {
  const dom = document.getElementById(domId);
  if (!dom) return null;
  let chart = echarts.getInstanceByDom(dom);
  if (!chart) chart = echarts.init(dom);
  else chart.clear();
  return chart;
}

// ── 和值走势 ──
function renderSumChart(data) {
  const chart = initChart('chart-sum');
  if (!chart) return;
  const avg = data.sums.reduce((a, b) => a + b, 0) / data.sums.length;
  chart.setOption({
    title: { text: '和值走势', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    xAxis: { data: data.periods, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { name: '和值' },
    series: [
      { name: '和值', type: 'line', data: data.sums, lineStyle: { color: COLORS.sum }, itemStyle: { color: COLORS.sum }, symbol: 'none' },
      { name: '均值', type: 'line', data: Array(data.sums.length).fill(avg.toFixed(1)), lineStyle: { color: '#999', type: 'dashed' }, itemStyle: { color: '#999' }, symbol: 'none' },
    ],
    grid: { left: 55, right: 20, top: 40, bottom: 60 },
    legend: { bottom: 0 },
  });
  window.addEventListener('resize', () => chart.resize());
}

// ── 跨度走势 ──
function renderSpanChart(data) {
  const chart = initChart('chart-span');
  if (!chart || !data.spans) return;
  const avg = (data.spans.reduce((a, b) => a + b, 0) / data.spans.length).toFixed(1);
  chart.setOption({
    title: { text: '跨度走势', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    xAxis: { data: data.periods, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { name: '跨度' },
    series: [
      { name: '跨度', type: 'line', data: data.spans, lineStyle: { color: COLORS.span }, itemStyle: { color: COLORS.span }, symbol: 'none', areaStyle: { color: 'rgba(52,152,219,0.1)' } },
      { name: '均值 ' + avg, type: 'line', data: Array(data.spans.length).fill(avg), lineStyle: { color: '#999', type: 'dashed' }, itemStyle: { color: '#999' }, symbol: 'none' },
    ],
    grid: { left: 55, right: 20, top: 40, bottom: 60 },
    legend: { bottom: 0 },
  });
  window.addEventListener('resize', () => chart.resize());
}

// ── AC值走势 ──
function renderAcChart(data) {
  const chart = initChart('chart-ac');
  if (!chart || !data.ac_values) return;
  chart.setOption({
    title: { text: 'AC值走势', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    xAxis: { data: data.periods, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { name: 'AC值', minInterval: 1 },
    series: [
      { name: 'AC值', type: 'line', data: data.ac_values, lineStyle: { color: COLORS.ac }, itemStyle: { color: COLORS.ac }, symbol: 'circle', symbolSize: 4 },
    ],
    grid: { left: 55, right: 20, top: 40, bottom: 60 },
  });
  window.addEventListener('resize', () => chart.resize());
}

// ── 连号统计 ──
function renderConsecutiveChart(data) {
  const chart = initChart('chart-consecutive');
  if (!chart || !data.consecutive) return;
  const maxC = Math.max(...data.consecutive, 1);
  chart.setOption({
    title: { text: '连号对数', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    xAxis: { data: data.periods, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { name: '连号对数', minInterval: 1, max: maxC + 1 },
    series: [
      { name: '连号数', type: 'bar', data: data.consecutive, itemStyle: { color: COLORS.consecutive } },
    ],
    grid: { left: 55, right: 20, top: 40, bottom: 60 },
  });
  window.addEventListener('resize', () => chart.resize());
}

// ── 奇偶比 ──
function renderOEChart(data) {
  const chart = initChart('chart-oe');
  if (!chart || !data.odd_counts) return;
  chart.setOption({
    title: { text: '奇偶分布', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    legend: { data: ['奇数', '偶数'], bottom: 0 },
    xAxis: { data: data.periods, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { name: '个数' },
    series: [
      { name: '奇数', type: 'bar', stack: 'total', data: data.odd_counts, itemStyle: { color: COLORS.odd } },
      { name: '偶数', type: 'bar', stack: 'total', data: data.even_counts, itemStyle: { color: COLORS.even } },
    ],
    grid: { left: 55, right: 20, top: 40, bottom: 60 },
  });
  window.addEventListener('resize', () => chart.resize());
}

// ── 频次柱状图 ──
function renderFreqChart(data) {
  const chart = initChart('chart-freq');
  if (!chart) return;
  const freq = data.frequency || [];
  const labels = [];
  const values = [];
  for (let i = 0; i < freq.length; i++) {
    if (freq[i] > 0 || i === 0) {
      labels.push(String(i).padStart(2, '0'));
      values.push(freq[i]);
    }
  }
  // 跳过 index 0（通常为0）
  const start = labels[0] === '00' ? 1 : 0;
  chart.setOption({
    title: { text: '号码频次', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { data: labels.slice(start), axisLabel: { rotate: 90, fontSize: 9 } },
    yAxis: { name: '出现次数' },
    series: [
      { name: '频次', type: 'bar', data: values.slice(start), itemStyle: { color: COLORS.freq } },
    ],
    grid: { left: 50, right: 20, top: 40, bottom: 50 },
  });
  window.addEventListener('resize', () => chart.resize());
}

// ── 遗漏图 ──
function renderOmissionChart(data) {
  const chart = initChart('chart-omission');
  if (!chart) return;
  const omission = data.omission || [];
  const labels = [];
  const values = [];
  for (let i = 0; i < omission.length; i++) {
    if (omission[i] >= 0 || i === 0) {
      labels.push(String(i).padStart(2, '0'));
      values.push(omission[i]);
    }
  }
  const start = labels[0] === '00' ? 1 : 0;
  chart.setOption({
    title: { text: '当前遗漏', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { data: labels.slice(start), axisLabel: { rotate: 90, fontSize: 9 } },
    yAxis: { name: '遗漏期数' },
    series: [
      { name: '遗漏', type: 'bar', data: values.slice(start),
        itemStyle: {
          color: function(p) { return p.value > 10 ? COLORS.omission : '#95a5a6'; }
        }
      },
    ],
    grid: { left: 55, right: 20, top: 40, bottom: 50 },
  });
  window.addEventListener('resize', () => chart.resize());
}

// ── 区间热力图 ──
function renderHeatmap(data) {
  const chart = initChart('chart-heatmap');
  if (!chart) return;
  const zoneLabels = data.zone_labels || [];
  const heatData = [];
  for (let i = 0; i < data.periods.length; i++) {
    const hits = data.zone_heatmap[i] || [];
    for (let j = 0; j < hits.length; j++) {
      heatData.push([j, i, hits[j]]);
    }
  }

  // 只显示部分期号标签以避免拥挤
  const step = Math.max(1, Math.floor(data.periods.length / 15));
  const yLabels = {};
  data.periods.forEach((p, i) => {
    if (i % step === 0 || i === data.periods.length - 1) {
      yLabels[i] = String(p);
    }
  });

  chart.setOption({
    title: { text: '区间命中热力图', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: {
      formatter: function(p) {
        return `期号: ${data.periods[p.value[1]]}<br/>区间: ${zoneLabels[p.value[0]]}<br/>命中: ${p.value[2]}`;
      }
    },
    grid: { left: 80, right: 40, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: zoneLabels,
      splitArea: { show: true },
    },
    yAxis: {
      type: 'category',
      data: data.periods.map(String),
      axisLabel: {
        formatter: function(v, i) { return yLabels[i] || ''; },
        fontSize: 10,
      },
      inverse: true,
    },
    visualMap: {
      min: 0,
      max: Math.max(...heatData.map(d => d[2]), 1),
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: { color: ['#f0f9e8', '#b8e186', '#7bcb4d', '#4d9221'] },
    },
    series: [{
      name: '命中数',
      type: 'heatmap',
      data: heatData,
      label: { show: true, fontSize: 10 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,.5)' } },
    }],
  });
  window.addEventListener('resize', () => chart.resize());
}
