/**
 * ECharts 图表工厂 — 霓虹主题
 * 统一实例创建、暗色主题、resize
 */

const Charts = {
  instances: [],

  colors: {
    ssq: { main: '#FF2D55', sub: '#1565C0', light: '#FF6B81', glow: 'rgba(255,45,85,0.35)' },
    dlt: { main: '#FF9500', sub: '#1E88E5', light: '#FFB84D', glow: 'rgba(255,149,0,0.35)' },
    kl8: { main: '#AF52DE', sub: '#AF52DE', light: '#D290F2', glow: 'rgba(175,82,222,0.35)' },
    pl5: { main: '#007AFF', sub: '#007AFF', light: '#66B0FF', glow: 'rgba(0,122,255,0.35)' },
    qxc: { main: '#00D2A0', sub: '#00D2A0', light: '#5CE6C6', glow: 'rgba(0,210,160,0.35)' },
  },

  /** 主题色常量（全局 ECharts 默认） */
  themeColors: {
    text: '#B0ACA6',
    textLight: '#E8E4DD',
    axis: '#3A3632',
    split: 'rgba(255,255,255,0.04)',
    bg: '#08080C',
  },

  init(domId) {
    this.dispose(domId);
    const dom = document.getElementById(domId);
    if (!dom) return null;
    const chart = echarts.init(dom, null, {
      backgroundColor: 'transparent',
    });
    this.instances.push(chart);
    return chart;
  },

  dispose(domId) {
    const dom = document.getElementById(domId);
    if (!dom) return;
    const idx = this.instances.findIndex(c => c.getDom() === dom);
    if (idx >= 0) { this.instances[idx].dispose(); this.instances.splice(idx, 1); }
  },

  disposeAll() { this.instances.forEach(c => c.dispose()); this.instances = []; },
  resizeAll() { this.instances.forEach(c => c.resize()); },

  getColors(type) { return this.colors[type] || this.colors.ssq; },

  /** 共享 grid */
  sharedGrid(extra = {}) {
    return { left: 52, right: 24, top: 55, bottom: extra.bottom || 65, ...extra };
  },

  /** 共享 tooltip */
  sharedTooltip() {
    return {
      trigger: 'axis',
      backgroundColor: 'rgba(20,20,30,0.96)',
      borderColor: 'rgba(255,255,255,0.1)',
      textStyle: { color: '#E8E4DD', fontSize: 12 },
    };
  },

  /** 折线图 */
  lineOption(title, data, periods, color, opts = {}) {
    return {
      title: { text: title, left: 'center', top: 6, textStyle: { color: this.themeColors.textLight, fontSize: 14, fontWeight: 700 } },
      tooltip: this.sharedTooltip(),
      grid: this.sharedGrid(),
      xAxis: {
        type: 'category', data: periods,
        axisLine: { lineStyle: { color: this.themeColors.axis } },
        axisTick: { show: false },
        axisLabel: { rotate: 45, fontSize: 10, color: this.themeColors.text, formatter: v => v.slice(-3) },
      },
      yAxis: {
        type: 'value', name: opts.yName || '',
        nameTextStyle: { color: this.themeColors.text, fontSize: 11 },
        splitLine: { lineStyle: { color: this.themeColors.split } },
        axisLabel: { color: this.themeColors.text, fontSize: 10 },
      },
      dataZoom: opts.noZoom ? undefined : [{
        type: 'slider', start: 0, end: 100, height: 18, bottom: 10,
        backgroundColor: 'rgba(20,20,30,0.8)',
        dataBackground: { lineStyle: { color: color }, areaStyle: { color: color + '20' } },
        selectedDataBackground: { lineStyle: { color: '#fff' }, areaStyle: { color: color + '40' } },
        textStyle: { color: this.themeColors.text },
      }],
      series: [{
        name: title, type: 'line', data,
        lineStyle: { color, width: 2.5, shadowBlur: 10, shadowColor: color + '60' },
        itemStyle: { color },
        symbol: 'circle', symbolSize: 4,
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: color + '50' }, { offset: 1, color: color + '02' },
        ])},
        markLine: opts.markLine ? {
          silent: true, symbol: 'none',
          lineStyle: { color: '#F5A623', type: 'dashed', width: 1.5 },
          label: { color: '#F5A623', fontSize: 11 },
          data: [{ type: 'average', name: '均值' }],
        } : undefined,
        ...(opts.seriesExtra || {}),
      }],
    };
  },

  /** 柱状图 */
  barOption(title, labels, values, color, opts = {}) {
    return {
      title: { text: title, left: 'center', top: 6, textStyle: { color: this.themeColors.textLight, fontSize: 14, fontWeight: 700 } },
      tooltip: this.sharedTooltip(),
      grid: this.sharedGrid({ bottom: 45 }),
      xAxis: {
        type: 'category', data: labels,
        axisLabel: { fontSize: opts.fontSize || 10, color: this.themeColors.text, rotate: opts.rotate || 0 },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: this.themeColors.axis } },
      },
      yAxis: {
        type: 'value', name: opts.yName || '次',
        nameTextStyle: { color: this.themeColors.text, fontSize: 11 },
        splitLine: { lineStyle: { color: this.themeColors.split } },
        axisLabel: { color: this.themeColors.text, fontSize: 10 },
      },
      series: [{
        name: title, type: 'bar', data: values,
        itemStyle: {
          borderRadius: [6, 6, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color }, { offset: 1, color: color + '88' },
          ]),
        },
        emphasis: { itemStyle: { color, shadowBlur: 16, shadowColor: color + '80' } },
        ...(opts.seriesExtra || {}),
      }],
    };
  },

  /** 堆叠柱状图 */
  stackedBarOption(title, categories, seriesData, colors, opts = {}) {
    return {
      title: { text: title, left: 'center', top: 6, textStyle: { color: this.themeColors.textLight, fontSize: 14, fontWeight: 700 } },
      tooltip: this.sharedTooltip(),
      legend: { bottom: 0, textStyle: { color: this.themeColors.text, fontSize: 11 } },
      grid: this.sharedGrid({ bottom: 55 }),
      xAxis: {
        type: 'category', data: categories,
        axisLabel: { rotate: 45, fontSize: 10, color: this.themeColors.text, formatter: v => v.slice(-3) },
        axisTick: { show: false }, axisLine: { lineStyle: { color: this.themeColors.axis } },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: this.themeColors.split } },
        axisLabel: { color: this.themeColors.text, fontSize: 10 },
      },
      dataZoom: [{
        type: 'slider', start: 0, end: 100, height: 18, bottom: 35,
        backgroundColor: 'rgba(20,20,30,0.8)',
        textStyle: { color: this.themeColors.text },
      }],
      series: seriesData.map((s, i) => ({
        name: s.name, type: 'bar', stack: 'total', data: s.data,
        itemStyle: { color: colors[i % colors.length], borderRadius: i === seriesData.length - 1 ? [6,6,0,0] : 0 },
        emphasis: { focus: 'series' },
      })),
    };
  },

  /** 热力图 */
  heatmapOption(title, data, xLabels, yLabels, rangeColors) {
    const palette = rangeColors || ['#08080C', '#FF9500', '#FF2D55'];
    return {
      title: { text: title, left: 'center', top: 6, textStyle: { color: this.themeColors.textLight, fontSize: 14, fontWeight: 700 } },
      tooltip: { position: 'top' },
      grid: { left: 60, right: 24, top: 50, bottom: 70 },
      xAxis: {
        type: 'category', data: xLabels, splitArea: { show: true },
        axisLabel: { fontSize: 9, color: this.themeColors.text },
      },
      yAxis: {
        type: 'category', data: yLabels, splitArea: { show: true },
        axisLabel: { fontSize: 10, color: this.themeColors.text },
      },
      visualMap: {
        min: 0, max: Math.max(...data.map(d => d[2]), 1),
        calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
        inRange: { color: palette },
        textStyle: { color: this.themeColors.text },
      },
      series: [{
        name: title, type: 'heatmap', data,
        label: { show: true, fontSize: 7, color: '#E8E4DD' },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.6)' } },
      }],
    };
  },

  /** 综合图（多条折线） */
  multiLineOption(title, seriesList, periods, opts = {}) {
    return {
      title: { text: title, left: 'center', top: 6, textStyle: { color: this.themeColors.textLight, fontSize: 14, fontWeight: 700 } },
      tooltip: this.sharedTooltip(),
      legend: { bottom: 0, textStyle: { color: this.themeColors.text, fontSize: 11 } },
      grid: this.sharedGrid({ bottom: 55 }),
      xAxis: {
        type: 'category', data: periods,
        axisLabel: { rotate: 45, fontSize: 10, color: this.themeColors.text, formatter: v => v.slice(-3) },
        axisTick: { show: false }, axisLine: { lineStyle: { color: this.themeColors.axis } },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: this.themeColors.split } },
        axisLabel: { color: this.themeColors.text, fontSize: 10 },
      },
      dataZoom: [{
        type: 'slider', start: 0, end: 100, height: 18, bottom: 35,
        backgroundColor: 'rgba(20,20,30,0.8)',
        textStyle: { color: this.themeColors.text },
      }],
      series: seriesList.map(s => ({
        name: s.name, type: 'line', data: s.data,
        lineStyle: { color: s.color, width: 2 },
        itemStyle: { color: s.color },
        symbol: 'circle', symbolSize: 3,
        ...(s.extra || {}),
      })),
    };
  },
};

window.addEventListener('resize', () => Charts.resizeAll());
