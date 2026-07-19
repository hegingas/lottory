/**
 * ECharts 图表工厂
 * 统一管理实例创建、主题、resize
 */

const Charts = {
  // 当前活跃的 chart 实例
  instances: [],

  // 彩种强调色映射
  colors: {
    ssq: { main: '#E53935', sub: '#1565C0', light: '#EF9A9A' },
    dlt: { main: '#FB8C00', sub: '#1E88E5', light: '#FFCC80' },
    kl8: { main: '#8E24AA', sub: '#8E24AA', light: '#CE93D8' },
    pl5: { main: '#1E88E5', sub: '#1E88E5', light: '#90CAF9' },
    qxc: { main: '#00897B', sub: '#00897B', light: '#80CBC4' },
  },

  /** 初始化 ECharts 实例 */
  init(domId) {
    this.dispose(domId); // 先销毁同 ID 旧实例
    const dom = document.getElementById(domId);
    if (!dom) return null;
    const chart = echarts.init(dom, 'dark', {
      backgroundColor: '#1a1a2e',
    });
    this.instances.push(chart);
    return chart;
  },

  /** 销毁指定实例 */
  dispose(domId) {
    const dom = document.getElementById(domId);
    if (!dom) return;
    const idx = this.instances.findIndex(c => c.getDom() === dom);
    if (idx >= 0) {
      this.instances[idx].dispose();
      this.instances.splice(idx, 1);
    }
  },

  /** 销毁全部实例 */
  disposeAll() {
    this.instances.forEach(c => c.dispose());
    this.instances = [];
  },

  /** 全局 resize */
  resizeAll() {
    this.instances.forEach(c => c.resize());
  },

  /** 获取彩种色板 */
  getColors(type) {
    return this.colors[type] || this.colors.ssq;
  },

  // ─── 共享图表 options ───

  /** 折线图：和值/跨度/AC值 走势 */
  lineOption(title, data, periods, color, opts = {}) {
    return {
      title: { text: title, left: 'center', textStyle: { color: '#e0e0e0', fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 30, top: 50, bottom: 60 },
      xAxis: {
        type: 'category',
        data: periods,
        axisLabel: { rotate: 45, fontSize: 10, color: '#999',
          formatter: v => v.slice(-3) },
      },
      yAxis: { type: 'value', name: opts.yName || '' },
      dataZoom: [{ type: 'slider', start: 0, end: 100, height: 20, bottom: 10 }],
      series: [{
        name: title, type: 'line', data,
        lineStyle: { color, width: 2 },
        itemStyle: { color },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: color + '40' },
          { offset: 1, color: color + '05' },
        ])},
        markLine: opts.markLine ? { data: [{ type: 'average', name: '平均' }] } : undefined,
        ...(opts.seriesExtra || {}),
      }],
    };
  },

  /** 柱状图：频率/遗漏/冷热 */
  barOption(title, labels, values, color, opts = {}) {
    return {
      title: { text: title, left: 'center', textStyle: { color: '#e0e0e0', fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 20, top: 50, bottom: 40 },
      xAxis: {
        type: 'category', data: labels,
        axisLabel: { fontSize: opts.fontSize || 10, color: '#999', rotate: opts.rotate || 0 },
      },
      yAxis: { type: 'value', name: opts.yName || '次' },
      series: [{
        name: title, type: 'bar', data: values,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color },
            { offset: 1, color: color + '80' },
          ]),
          borderRadius: [4, 4, 0, 0],
        },
        ...(opts.seriesExtra || {}),
      }],
    };
  },

  /** 堆叠柱状图：区间/奇偶/大小/012路分布 */
  stackedBarOption(title, categories, seriesData, colors, opts = {}) {
    return {
      title: { text: title, left: 'center', textStyle: { color: '#e0e0e0', fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, textStyle: { color: '#999' } },
      grid: { left: 40, right: 20, top: 50, bottom: 50 },
      xAxis: {
        type: 'category', data: categories,
        axisLabel: { rotate: 45, fontSize: 10, color: '#999', formatter: v => v.slice(-3) },
      },
      yAxis: { type: 'value' },
      dataZoom: [{ type: 'slider', start: 0, end: 100, height: 20, bottom: 35 }],
      series: seriesData.map((s, i) => ({
        name: s.name, type: 'bar', stack: 'total', data: s.data,
        itemStyle: { color: colors[i % colors.length] },
        emphasis: { focus: 'series' },
      })),
    };
  },

  /** 热力图 */
  heatmapOption(title, data, xLabels, yLabels, colors) {
    return {
      title: { text: title, left: 'center', textStyle: { color: '#e0e0e0', fontSize: 14 } },
      tooltip: { position: 'top' },
      grid: { left: 60, right: 20, top: 50, bottom: 60 },
      xAxis: {
        type: 'category', data: xLabels, splitArea: { show: true },
        axisLabel: { fontSize: 9, color: '#999' },
      },
      yAxis: {
        type: 'category', data: yLabels, splitArea: { show: true },
        axisLabel: { fontSize: 10, color: '#999' },
      },
      visualMap: {
        min: 0, max: Math.max(...data.map(d => d[2])),
        calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
        inRange: { color: colors || ['#1a1a2e', '#4fc3f7', '#E53935'] },
      },
      series: [{
        name: title, type: 'heatmap', data,
        label: { show: true, fontSize: 8 },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
      }],
    };
  },
};

// 全局 resize 监听
window.addEventListener('resize', Utils.debounce(() => Charts.resizeAll(), 200));
