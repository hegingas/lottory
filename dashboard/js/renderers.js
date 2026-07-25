/**
 * 页面渲染引擎 — 5 彩种详情页 + 图表模式切换
 */

const Renderers = {
  _preSelectionRows: [new Set(), new Set(), new Set()],
  _currentPeriodSize: 50,
  _currentAnnotations: {},

  renderDetail(type, data, chartMode) {
    const meta = LOTTERY_META[type];
    const color = Charts.colors[type];
    const container = document.getElementById('view-detail');
    if (!container || !data) return;

    Charts.disposeAll();

    const mainClr = color.main.match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})/i);
    const rgbMain = mainClr ? `${parseInt(mainClr[1],16)},${parseInt(mainClr[2],16)},${parseInt(mainClr[3],16)}` : '255,45,85';
    const subClr = (color.sub||'#1565C0').match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})/i);
    const rgbSub = subClr ? `${parseInt(subClr[1],16)},${parseInt(subClr[2],16)},${parseInt(subClr[3],16)}` : '26,86,219';

    container.innerHTML = `
      <div class="detail-topbar">
        <a href="#/home" class="back-btn">← 返回</a>
        <h2 class="detail-title">${this.getIcon(type)} ${meta.name} 走势图</h2>
        <span class="detail-period-tag">${data.metadata.periodMin} ~ ${data.metadata.periodMax} · ${data.metadata.totalDraws}期</span>
      </div>

      <div class="latest-bar" style="border-left: 3px solid ${color.main}">
        <span class="latest-label">最新开奖 · ${data.latest.period}</span>
        <span class="latest-balls">
          ${data.latest.main.map(n => `<span class="ball" style="--ball-color:rgb(${rgbMain});--ball-dark:rgb(${Math.round(parseInt(rgbMain.split(',')[0])*0.35)},${Math.round(parseInt(rgbMain.split(',')[1])*0.35)},${Math.round(parseInt(rgbMain.split(',')[2])*0.35)});--ball-glow:rgba(${rgbMain},0.45)">${Utils.fmtNum(n)}</span>`).join('')}
          ${data.latest.sub && data.latest.sub.length
            ? `<span class="ball-plus">+</span>${data.latest.sub.map(n => `<span class="ball ball-sub">${Utils.fmtNum(n)}</span>`).join('')}`
            : ''}
        </span>
        <span class="latest-meta">和值: ${data.latest.main.reduce((a,b)=>a+parseInt(b),0)}</span>
      </div>

      <div class="stat-row" id="stat-cards"></div>

      <div class="chart-tabs" id="chart-tabs"></div>
      <div class="chart-area" id="chart-area"></div>

      <div class="grid-section" id="number-grid-section"></div>

      <div class="table-section" id="data-table-section"></div>
    `;

    this.renderStatCards(type, data, color);
    this.renderChartTabs(type, meta, color);
    this.renderChart(type, data, chartMode || '综合图', meta, color);
    this.renderNumberGrid(type, data, meta, color);
    this.renderDataTable(type, data, color);
  },

  // ─── 统计卡片 ───
  renderStatCards(type, data, color) {
    const el = document.getElementById('stat-cards');
    if (!el) return;
    const stats = data.stats;
    const hotMain = stats.hotCold.hotMain.slice(0, 3).map(h => h[0]).join(' ');
    const coldMain = stats.hotCold.coldMain.slice(0, 3).map(h => h[0]).join(' ');

    const cards = [
      { label: '总期数', value: data.metadata.totalDraws },
      { label: '热号 Top3', value: hotMain, cls: 'hot' },
      { label: '冷号 Top3', value: coldMain, cls: 'cold' },
    ];
    if (stats.hotCold.hotSub.length) {
      cards.push({ label: '后区热号', value: stats.hotCold.hotSub.slice(0, 2).map(h => h[0]).join(' ') });
    }

    el.innerHTML = cards.map(c => `
      <div class="stat-card">
        <div class="stat-label">${c.label}</div>
        <div class="stat-value ${c.cls || ''}" style="color:${c.cls === 'hot' ? color.main : c.cls === 'cold' ? '#78909C' : '#e0e0e0'}">${c.value}</div>
      </div>
    `).join('');
  },

  // ─── 图表模式标签 ───
  renderChartTabs(type, meta, color) {
    const el = document.getElementById('chart-tabs');
    if (!el) return;
    const currentMode = App.currentChartMode || '综合图';

    el.innerHTML = meta.chartModes.map(m => `
      <button class="chart-tab ${m === currentMode ? 'active' : ''}"
              style="${m === currentMode ? '--tab-color:' + color.main + ';border-bottom:2px solid ' + color.main : ''}"
              data-mode="${m}">${m}</button>
    `).join('');

    el.querySelectorAll('.chart-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        // 只更新状态+重绘图表，不触发路由重载
        App.currentChartMode = btn.dataset.mode;
        this.renderChart(type, App.dataCache[type], btn.dataset.mode, meta, color);
        // 重新高亮 tab
        el.querySelectorAll('.chart-tab').forEach(b => {
          b.classList.remove('active');
          b.style.borderBottom = 'none';
          b.style.setProperty('--tab-color', '');
          b.style.setProperty('--tab-glow', '');
        });
        btn.classList.add('active');
        btn.style.setProperty('--tab-color', color.main);
        btn.style.setProperty('--tab-glow', color.glow);
      });
    });
  },

  // ─── 主图表区 ───
  renderChart(type, data, mode, meta, color) {
    const el = document.getElementById('chart-area');
    if (!el) return;

    // 新浪式表格视图不走 ECharts
    const tableModes = ['奇偶', '大小', '质合', '012路', '重号', '连号', '区间'];
    if (tableModes.includes(mode)) {
      this._attrTableView(type, data, meta, color, mode);
      return;
    }

    const stats = data.stats;
    const periods = stats.last50.periods;
    const N = periods.length;
    const chartId = `chart-main-${type}`;
    el.innerHTML = `<div id="${chartId}" style="width:100%;height:420px;"></div>`;
    const chart = Charts.init(chartId);
    if (!chart) return;

    let option = {};

    switch (mode) {
      case '综合图':
        option = this._comprehensiveChart(data, meta, color);
        break;
      case 'AC值':
        option = Charts.lineOption('AC值走势', stats.last50.ac_value, periods, color.main);
        break;
      case '遗漏':
        option = this._omissionHeatmap(data, meta, color);
        break;
      case '频率':
        option = this._frequencyChart(data, meta, color);
        break;
      case '和值':
        option = Charts.lineOption('和值走势', stats.last50.sum, periods, color.main, { markLine: true });
        break;
      case '跨度':
        option = Charts.lineOption('跨度走势', stats.last50.span, periods, color.main, { markLine: true, yName: '跨度' });
        break;
      case '位频':
        option = this._positionalChart(data, meta, color);
        break;
      case '后区':
        option = this._subChart(data, meta, color);
        break;
      default:
        option = this._comprehensiveChart(data, meta, color);
    }

    chart.setOption(option, true);
  },

  // ─── 各图表模式实现 ───

  _comprehensiveChart(data, meta, color) {
    // 综合图：和值 + 跨度 + 区间比 三联图
    const stats = data.stats;
    const periods = stats.last50.periods;
    return {
      title: { text: '综合走势 · 近50期', left: 'center', textStyle: { color: '#e0e0e0', fontSize: 14 } },
      grid: [
        { left: 50, right: 30, top: 50, height: 100 },
        { left: 50, right: 30, top: '50%', height: 100 },
        { left: 50, right: 30, top: '70%', height: 100, bottom: 30 },
      ],
      xAxis: [
        { type: 'category', data: periods, gridIndex: 0, axisLabel: { show: false } },
        { type: 'category', data: periods, gridIndex: 1, axisLabel: { show: false } },
        { type: 'category', data: periods, gridIndex: 2, axisLabel: { rotate: 45, fontSize: 9, color: '#999', formatter: v => v.slice(-3) } },
      ],
      yAxis: [
        { type: 'value', gridIndex: 0, name: '和值' },
        { type: 'value', gridIndex: 1, name: '跨度' },
        { type: 'value', gridIndex: 2, name: '连号' },
      ],
      series: [
        { name: '和值', type: 'line', data: stats.last50.sum, xAxisIndex: 0, yAxisIndex: 0, lineStyle: { color: color.main, width: 2 }, itemStyle: { color: color.main } },
        { name: '跨度', type: 'line', data: stats.last50.span, xAxisIndex: 1, yAxisIndex: 1, lineStyle: { color: color.sub, width: 2 }, itemStyle: { color: color.sub } },
        { name: '连号', type: 'bar', data: stats.last50.consecutive, xAxisIndex: 2, yAxisIndex: 2, itemStyle: { color: color.light } },
      ],
    };
  },

  _oddEvenChart(periods, stats, color) {
    const oddData = stats.last50.odd_even.map(r => r[0]);
    const evenData = stats.last50.odd_even.map(r => r[1]);
    const oddRatio = oddData.map((v, i) => parseFloat(((v / (v + evenData[i])) * 100).toFixed(1)));

    return {
      title: { text: '奇偶走势 (近50期)', left: 'center', textStyle: { color: '#e0e0e0', fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, textStyle: { color: '#999' } },
      grid: { left: 50, right: 50, top: 50, bottom: 50 },
      xAxis: { type: 'category', data: periods, axisLabel: { rotate: 45, fontSize: 10, color: '#999', formatter: v => v.slice(-3) } },
      yAxis: [
        { type: 'value', name: '个数' },
        { type: 'value', name: '占比 %', min: 0, max: 100 },
      ],
      dataZoom: [{ type: 'slider', start: 0, end: 100, height: 20, bottom: 35 }],
      series: [
        { name: '奇数', type: 'bar', data: oddData, itemStyle: { color: color.main } },
        { name: '偶数', type: 'bar', data: evenData, itemStyle: { color: '#78909C' } },
        { name: '奇数占比', type: 'line', yAxisIndex: 1, data: oddRatio, lineStyle: { color: '#FFD54F', width: 2, type: 'dashed' }, itemStyle: { color: '#FFD54F' } },
      ],
    };
  },

  _primeChart(periods, stats, meta, color, data) {
    const primeSet = meta.prime ? new Set([2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31]) : new Set();
    const primeData = [];
    const compData = [];

    // 从 draws 数据中按 periods 顺序计算每期质数个数
    if (data && data.draws) {
      const drawMap = {};
      data.draws.forEach(d => { drawMap[d.period] = d.main.map(Number); });
      periods.forEach(p => {
        const nums = drawMap[p] || [];
        const pc = nums.filter(n => primeSet.has(n)).length;
        primeData.push(pc);
        compData.push(nums.length - pc);
      });
    } else {
      // fallback: 如果没数据，填 0
      periods.forEach(() => { primeData.push(0); compData.push(meta.mainCount); });
    }

    // 对于按位彩种（PL5/QXC），质合不适用
    if (meta.positional) {
      return Charts.barOption('质合不适用于按位彩种', [], [], color.main);
    }

    return Charts.stackedBarOption('质合分布 (近50期)', periods,
      [{ name: '质数', data: primeData }, { name: '合数', data: compData }],
      [color.main, '#546E7A']);
  },

  // ─── 新浪式属性表格（大小/奇偶/质合/012路/重号/连号/区间） ───
  _attrTableView(type, data, meta, color, mode) {
    const el = document.getElementById('chart-area');
    if (!el) return;
    const grid = data.stats.grid50;
    const stats = data.stats;
    const [lo, hi] = meta.mainRange;
    const periods = grid.periods.slice(-50);
    const P = periods.length;
    const mid = meta.mid || 17;

    const mainClr = color.main.match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})/i);
    const rgbM = mainClr ? `${parseInt(mainClr[1],16)},${parseInt(mainClr[2],16)},${parseInt(mainClr[3],16)}` : '255,45,85';

    // 每格显示的属性标签
    const getLabel = (n, periodIdx) => {
      const key = String(n);
      const cell = grid.main[key] ? grid.main[key][periodIdx] : null;
      if (mode === '奇偶') return String(n % 2 === 1 ? '奇' : '偶');
      if (mode === '大小') return n >= mid ? '大' : '小';
      if (mode === '质合') {
        const primes = new Set([2,3,5,7,11,13,17,19,23,29,31]);
        return primes.has(n) ? '质' : '合';
      }
      if (mode === '012路') return String(n % 3) + '路';
      return '';
    };
    const getLabelColor = (label) => {
      if (label === '奇' || label === '大' || label === '质') return 'color:#FF6B6B';
      if (label === '偶' || label === '小' || label === '合') return 'color:#6B9BD2';
      if (label === '0路') return 'color:#E53935';
      if (label === '1路') return 'color:#1E88E5';
      if (label === '2路') return 'color:#43A047';
      return 'color:#807C78';
    };

    let html = `<div style="padding:8px;font-weight:700;font-size:14px">📋 ${mode}走势图 · 新浪式表格 (近50期·旧→新)</div>`;
    html += '<div class="grid-scroll"><table class="num-grid"><thead><tr>';
    html += '<th class="grid-period-th">期号</th>';
    for (let n = lo; n <= hi; n++) html += `<th class="grid-num-th">${Utils.fmtNum(n)}</th>`;
    html += '</tr></thead><tbody>';

    for (let i = 0; i < P; i++) {
      const period = periods[i];
      const periodIdx = grid.periods.indexOf(period);
      html += '<tr>';
      html += `<td class="grid-period">${period}</td>`;
      for (let n = lo; n <= hi; n++) {
        const key = String(n);
        const cell = grid.main[key] ? grid.main[key][periodIdx] : null;
        if (cell && cell.hit) {
          html += `<td class="grid-cell"><span class="ball" style="--ball-color:rgb(${rgbM});--ball-dark:rgb(${Math.round(parseInt(rgbM.split(',')[0])*0.3)},${Math.round(parseInt(rgbM.split(',')[1])*0.3)},${Math.round(parseInt(rgbM.split(',')[2])*0.3)});--ball-glow:rgba(${rgbM},0.4);width:22px;height:22px;font-size:10px">${Utils.fmtNum(n)}</span></td>`;
        } else {
          const label = getLabel(n, periodIdx);
          html += `<td class="grid-cell" style="${getLabelColor(label)};font-size:11px;font-weight:600;text-align:center">${label}</td>`;
        }
      }
      html += '</tr>';
    }
    html += '</tbody></table></div>';
    el.innerHTML = html;
  },

  _zoneChart(periods, stats, meta, color) {
    if (!meta.zones) return {};
    const zoneNames = meta.zones.map((z, i) => `${z[0]}-${z[1]}`);
    const seriesData = meta.zones.map((_, zi) => ({
      name: zoneNames[zi],
      data: stats.last50.zone_dist.map(r => r[zi] || 0),
    }));
    const palette = [color.main, '#1E88E5', '#43A047', '#FB8C00'];
    return Charts.stackedBarOption('区间分布 (近50期)', periods, seriesData, palette);
  },

  _omissionHeatmap(data, meta, color) {
    const grid = data.stats.grid50;
    const periods = grid.periods.slice(-30); // 最近30期
    const [lo, hi] = meta.mainRange;
    const xLabels = periods.map(p => p.slice(-3));
    const yLabels = [];
    const heatData = [];

    for (let n = lo; n <= hi; n++) {
      const key = String(n);
      yLabels.push(Utils.fmtNum(n));
      const vals = grid.main[key] || [];
      const recent = vals.slice(-30);
      recent.forEach((v, i) => {
        heatData.push([i, n - lo, v.hit ? -1 : v.omit]); // -1 for hit
      });
    }

    return {
      title: { text: '遗漏热力图 (最近30期)', left: 'center', textStyle: { color: '#e0e0e0', fontSize: 14 } },
      tooltip: {
        formatter: params => {
          const n = params.data[1] + lo;
          const v = params.data[2];
          return `期号${periods[params.data[0]].slice(-3)} 号码${Utils.fmtNum(n)}: ${v === -1 ? '✓ 开出' : '遗漏' + v + '期'}`;
        },
      },
      grid: { left: 50, right: 30, top: 50, bottom: 60 },
      xAxis: { type: 'category', data: xLabels, axisLabel: { fontSize: 9, color: '#999' } },
      yAxis: { type: 'category', data: yLabels, axisLabel: { fontSize: 10, color: '#999' } },
      visualMap: {
        pieces: [
          { value: -1, color: color.main, label: '开出' },
          { min: 0, max: 3, color: '#4CAF50', label: '遗漏0-3' },
          { min: 4, max: 8, color: '#FFC107', label: '遗漏4-8' },
          { min: 9, max: 15, color: '#FF9800', label: '遗漏9-15' },
          { min: 16, max: 99, color: '#E53935', label: '遗漏>15' },
        ],
        orient: 'horizontal', left: 'center', bottom: 0,
      },
      series: [{ type: 'heatmap', data: heatData, label: { show: false }, emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } } }],
    };
  },

  _frequencyChart(data, meta, color) {
    const [lo, hi] = meta.mainRange;
    const freq = data.stats.frequency.main;
    const labels = [];
    const values = [];
    for (let n = lo; n <= hi; n++) {
      labels.push(Utils.fmtNum(n));
      values.push(freq[String(n)] || 0);
    }
    const avg = Utils.avg(values);
    return {
      ...Charts.barOption('号码频率统计 (全部历史)', labels, values, color.main, { yName: '次' }),
      series: [{
        name: '频率', type: 'bar', data: values,
        itemStyle: {
          color: params => params.value > avg ? color.main : '#546E7A',
        },
        markLine: { data: [{ yAxis: avg, name: '均值', label: { formatter: `均值: ${avg.toFixed(0)}` } }], lineStyle: { color: '#FFD54F' } },
      }],
    };
  },

  _positionalChart(data, meta, color) {
    const pf = data.stats.positionalFreq;
    if (!pf) return {};
    const posKeys = Object.keys(pf).sort();
    const digits = Array.from({ length: 10 }, (_, i) => String(i));
    const seriesData = posKeys.map((pos, i) => ({
      name: `第${Number(pos) + 1}位`,
      data: digits.map(d => pf[pos][d] || 0),
    }));
    return Charts.stackedBarOption('按位数字频率 (近100期)', digits, seriesData,
      [color.main, '#1E88E5', '#43A047', '#FB8C00', '#E53935', '#00897B', '#8E24AA']);
  },

  _subChart(data, meta, color) {
    // 后区走势图
    if (!meta.subRange) return {};
    const [lo, hi] = meta.subRange;
    const freq = data.stats.frequency.sub;
    const labels = [];
    const values = [];
    for (let n = lo; n <= hi; n++) {
      labels.push(Utils.fmtNum(n));
      values.push(freq[String(n)] || 0);
    }
    return Charts.barOption('后区号码频率', labels, values, color.sub, { yName: '次' });
  },

  // ─── 号码网格 (对标新浪走势图·完整版) ───
  renderNumberGrid(type, data, meta, color, periodCount, annotations) {
    const el = document.getElementById('number-grid-section');
    if (!el) return;

    // 按位彩种（排列5/七星彩）走新浪式按位分块表格
    if (meta.positional) {
      this._renderPositionalGrid(type, data, meta, color, periodCount, annotations);
      return;
    }

    const grid = data.stats.grid50;
    const stats = data.stats;
    const [lo, hi] = meta.mainRange;
    const N = periodCount || 50;
    const periods = grid.periods.slice(-N);
    const P = periods.length;
    const ann = annotations || { repeat: false, consecutive: false, neighbor: false };

    const mainClr = color.main.match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})/i);
    const rgbM = mainClr ? `${parseInt(mainClr[1],16)},${parseInt(mainClr[2],16)},${parseInt(mainClr[3],16)}` : '255,45,85';
    const subClr = (color.sub||'#1565C0').match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})/i);
    const rgbS = subClr ? `${parseInt(subClr[1],16)},${parseInt(subClr[2],16)},${parseInt(subClr[3],16)}` : '26,86,219';

    // 新浪式遗漏分层（深色主题适配版）
    // 低于均值=偏热(暗红底) 高于均值=偏冷(暗蓝底) 接近均值=无底色
    const avgOmits = {};
    for (let n = lo; n <= hi; n++) {
      const key = String(n);
      const vals = grid.main[key] || [];
      const omits = vals.filter(v => v && !v.hit).map(v => v.omit);
      avgOmits[key] = omits.length > 0 ? omits.reduce((a,b)=>a+b,0) / omits.length : 5;
    }
    const omitBg = (v, key) => {
      const avg = avgOmits[key] || 5;
      if (v < avg * 0.7) return 'background:rgba(255,107,107,0.18)';    // 偏热 → 暗红底
      if (v > avg * 1.3) return 'background:rgba(107,155,210,0.18)';    // 偏冷 → 暗蓝底
      return '';
    };
    const omitFg = (v, key) => {
      const avg = avgOmits[key] || 5;
      if (v < avg * 0.7) return 'color:#FF6B6B;font-weight:600';        // 偏热 → 亮红字
      if (v > avg * 1.3) return 'color:#6B9BD2;font-weight:600';        // 偏冷 → 亮蓝字
      return 'color:#807C78';                                             // 正常 → 暗灰字
    };

    // ── 工具栏 ──
    const sizes = [20, 50, 80, 120].filter(s => s <= grid.periods.length);
    let toolbar = `<div class="grid-toolbar">
      <div class="grid-toolbar-left">
        <span style="font-weight:700;font-size:14px">📋 号码走势网格</span>
        <div class="period-selector">${sizes.map(s => `<button class="period-opt${s === N ? ' active' : ''}" data-size="${s}">${s}期</button>`).join('')}</div>
      </div>
      <div class="grid-toolbar-right">
        <div class="annotation-toggles">
          <label class="anno-toggle${ann.repeat?' active':''}" data-anno="repeat"><span>🔄 重号</span></label>
          <label class="anno-toggle${ann.consecutive?' active':''}" data-anno="consecutive"><span>🔗 连号</span></label>
          <label class="anno-toggle${ann.neighbor?' active':''}" data-anno="neighbor"><span>↔️ 边号</span></label>
          <label class="anno-toggle${ann.omitData !== false ? ' active' : ''}" data-anno="omitData"><span>📊 遗漏数据</span></label>
          <label class="anno-toggle${ann.omitLayer !== false ? ' active' : ''}" data-anno="omitLayer"><span>🎨 遗漏分层</span></label>
        </div>
      </div>
    </div>`;

    // ── 表格 ──
    let html = toolbar + '<div class="grid-scroll"><table class="num-grid"><thead><tr>';
    html += '<th class="grid-period-th">期号</th>';

    // 分区标签行
    if (meta.zones) {
      for (let zi = 0; zi < meta.zones.length; zi++) {
        const [zLo, zHi] = meta.zones[zi];
        const span = zHi - zLo + 1;
        const zoneColors = ['rgba(255,107,107,0.12)','rgba(107,155,210,0.12)','rgba(255,167,38,0.12)','rgba(0,210,160,0.12)'];
        html += `<th colspan="${span}" style="background:${zoneColors[zi]||'rgba(255,255,255,0.03)'};font-size:11px;color:var(--text-dim);font-weight:700;border-bottom:2px solid ${['#FF6B6B','#6B9BD2','#FFA726','#00D2A0'][zi]||'rgba(255,255,255,0.2)'}">${['一区','二区','三区','四区'][zi]||('区'+(zi+1))} ${zLo}-${zHi}</th>`;
      }
    } else {
      html += `<th colspan="${hi - lo + 1}" style="background:rgba(255,255,255,0.03);font-size:10px;color:var(--text-dim)">主区号码</th>`;
    }
    html += '</tr><tr>';
    html += '<th class="grid-period-th">期号</th>';

    // 主区号码头（分区隔线）
    const zoneEndsH = meta.zones ? new Set(meta.zones.map(z => z[1])) : new Set();
    for (let n = lo; n <= hi; n++) {
      const isZoneEnd = zoneEndsH.has(n);
      html += `<th class="grid-num-th" style="${isZoneEnd ? 'border-right:3px solid rgba(255,255,255,0.35)' : ''}">${Utils.fmtNum(n)}</th>`;
    }

    // 后区
    if (meta.subRange) {
      html += '<th class="grid-gap"></th>';
      html += `<th colspan="${meta.subRange[1] - meta.subRange[0] + 1}" style="background:rgba(21,101,192,0.1);font-size:10px;color:#1565C0">后区</th></tr><tr>`;
      html += '<th class="grid-period-th"></th>';
      for (let n = lo; n <= hi; n++) {
        const isLast = String(n) === String(hi);
        html += `<th class="grid-num-th" style="${isLast && meta.zones ? 'border-right:2px solid rgba(255,255,255,0.1)' : ''}"></th>`;
      }
      html += '<th class="grid-gap"></th>';
      for (let n = meta.subRange[0]; n <= meta.subRange[1]; n++) {
        html += `<th class="grid-num-th grid-sub-th">${Utils.fmtNum(n)}</th>`;
      }
    }

    // 统计列
    html += '<th class="grid-gap"></th><th>和值</th><th>跨度</th>';
    if (meta.zones) html += '<th>区间比</th>';
    html += '<th>奇偶</th>';
    if (!meta.positional) html += '<th>连号</th>';
    html += '</tr></thead><tbody>';

    // 预计算所有行的命中集合（用于每行的重号/边号标注）
    const allRowHits = [];
    for (let i = 0; i < P; i++) {
      const periodIdx = grid.periods.indexOf(periods[i]);
      const hits = new Set();
      if (periodIdx >= 0) {
        for (let n = lo; n <= hi; n++) {
          const key = String(n);
          const cell = grid.main[key] ? grid.main[key][periodIdx] : null;
          if (cell && cell.hit) hits.add(key);
        }
      }
      allRowHits.push(hits);
    }

    // 数据行 — 旧→新
    for (let i = 0; i < P; i++) {
      const period = periods[i];
      const periodIdx = grid.periods.indexOf(period);
      const curHits = allRowHits[i];
      const prevRowHits = i > 0 ? allRowHits[i-1] : new Set();

      html += '<tr>';
      html += `<td class="grid-period">${period}</td>`;

      // 主区
      // 计算各区边界（用于分区隔线）
      const zoneEnds = meta.zones ? new Set(meta.zones.map(z => z[1])) : new Set();
      for (let n = lo; n <= hi; n++) {
        const key = String(n);
        const cell = grid.main[key] ? grid.main[key][grid.main[key].length - P + i] : null;
        const isZoneEnd = zoneEnds.has(n);
        const zoneBorder = isZoneEnd ? 'border-right:3px solid rgba(255,255,255,0.25)' : '';

        // 标注 class
        let cellClass = '';
        // 重号：号码在上期(prevRowHits)开了，本期也开了 → 真正的重号
        if (ann.repeat && prevRowHits.has(key) && curHits.has(key)) cellClass += ' grid-anno-repeat';
        // 连号：当期命中，且相邻号码也命中
        if (ann.consecutive && curHits.has(key)) {
          const prevKey = String(n - 1);
          const nextKey = String(n + 1);
          if (curHits.has(prevKey) || curHits.has(nextKey)) cellClass += ' grid-anno-consec';
        }
        // 边号：上期开出过相邻号(±1)但本期未开本号 → 邻号候选
        if (ann.neighbor && (prevRowHits.has(String(n - 1)) || prevRowHits.has(String(n + 1))) && !prevRowHits.has(key)) {
          cellClass += ' grid-anno-neighbor';
        }

        if (cell && cell.hit) {
          // 根据标注选小球颜色：重号=金色, 连号=青色, 默认=彩种色
          const isRepeat = cellClass.includes('grid-anno-repeat');
          const isConsec = cellClass.includes('grid-anno-consec');
          let ballClr, ballDark, ballGlow;
          if (isRepeat && isConsec) {
            ballClr = '255,105,180'; ballDark = '180,50,120'; ballGlow = 'rgba(255,105,180,0.5)';  // 重号+连号=粉色
          } else if (isRepeat) {
            ballClr = '255,215,0'; ballDark = '184,134,11'; ballGlow = 'rgba(255,215,0,0.5)';      // 重号=金色
          } else if (isConsec) {
            ballClr = '0,229,255'; ballDark = '0,131,143'; ballGlow = 'rgba(0,229,255,0.5)';       // 连号=青色
          } else {
            ballClr = rgbM; ballDark = `${Math.round(parseInt(rgbM.split(',')[0])*0.3)},${Math.round(parseInt(rgbM.split(',')[1])*0.3)},${Math.round(parseInt(rgbM.split(',')[2])*0.3)}`; ballGlow = `rgba(${rgbM},0.4)`;
          }
          html += `<td class="grid-cell${cellClass}" style="${zoneBorder}"><span class="ball" style="--ball-color:rgb(${ballClr});--ball-dark:rgb(${ballDark});--ball-glow:${ballGlow};width:22px;height:22px;font-size:10px">${Utils.fmtNum(n)}</span></td>`;
        } else {
          const omit = cell ? cell.omit : '?';
          const showBg = ann.omitLayer !== false;
          const showNum = ann.omitData !== false;
          const style = [
            showBg ? omitBg(omit, key) : '',
            showNum ? omitFg(omit, key) : 'color:transparent',
            zoneBorder,
            'font-size:11px;font-weight:600;text-align:center'
          ].filter(Boolean).join(';');
          const display = showNum ? omit : '';
          html += `<td class="grid-cell${cellClass}" style="${style}">${display}</td>`;
        }
      }

      // 后区
      if (meta.subRange && grid.sub) {
        html += '<td class="grid-gap"></td>';
        for (let n = meta.subRange[0]; n <= meta.subRange[1]; n++) {
          const key = String(n);
          const cell = grid.sub[key] ? grid.sub[key][grid.sub[key].length - P + i] : null;
          if (cell && cell.hit) {
            html += `<td class="grid-cell"><span class="ball ball-sub" style="--ball-color:rgb(${rgbS});--ball-dark:rgb(${Math.round(parseInt(rgbS.split(',')[0])*0.3)},${Math.round(parseInt(rgbS.split(',')[1])*0.3)},${Math.round(parseInt(rgbS.split(',')[2])*0.3)});--ball-glow:rgba(${rgbS},0.4);width:22px;height:22px;font-size:10px">${Utils.fmtNum(n)}</span></td>`;
          } else {
            const omit = cell ? cell.omit : '?';
            const showBg = ann.omitLayer !== false;
            const showNum = ann.omitData !== false;
            const style = [
              showBg ? omitBg(omit, key) : '',
              showNum ? omitFg(omit, key) : 'color:transparent',
              'font-size:10px;font-weight:600;text-align:center'
            ].filter(Boolean).join(';');
            html += `<td class="grid-cell" style="${style}">${showNum ? omit : ''}</td>`;
          }
        }
      }

      // 统计
      const idx = stats.last50.periods.indexOf(period);
      if (idx >= 0) {
        html += '<td class="grid-gap"></td>';
        html += `<td style="font-weight:600">${stats.last50.sum[idx]}</td>`;
        html += `<td>${stats.last50.span[idx]}</td>`;
        if (meta.zones && stats.last50.zone_dist[idx]) html += `<td>${stats.last50.zone_dist[idx].join(':')}</td>`;
        html += `<td>${(stats.last50.odd_even[idx] || []).join(':')}</td>`;
        if (!meta.positional) html += `<td>${stats.last50.consecutive[idx]}</td>`;
      }

      html += '</tr>';
    }

    // ── 预选行 (开奖数据下方) ──
    {
      const preRows = this._preSelectionRows;
      for (let ri = 0; ri < preRows.length; ri++) {
        html += `<tr style="background:rgba(245,166,35,0.06)"><td style="font-size:10px;color:var(--gold);font-weight:700;white-space:nowrap">预选${ri+1} <span style="color:#E53935;cursor:pointer;margin-left:4px;font-size:12px" class="presel-action" data-action="del" data-row="${ri}">✕</span></td>`;
        for (let n = lo; n <= hi; n++) {
          const isLast = String(n) === String(hi);
          const zoneBorder = isLast && meta.zones ? 'border-right:3px solid rgba(255,255,255,0.25)' : '';
          const checked = preRows[ri].has(String(n));
          html += `<td class="grid-cell" style="${zoneBorder};cursor:pointer" data-presel-row="${ri}" data-presel-num="${n}">${checked ? `<span class="ball" style="--ball-color:rgb(${rgbM});--ball-dark:rgb(${Math.round(parseInt(rgbM.split(',')[0])*0.3)},${Math.round(parseInt(rgbM.split(',')[1])*0.3)},${Math.round(parseInt(rgbM.split(',')[2])*0.3)});--ball-glow:rgba(${rgbM},0.3);width:20px;height:20px;font-size:9px">${Utils.fmtNum(n)}</span>` : `<span style="color:var(--text-muted);font-size:10px">${Utils.fmtNum(n)}</span>`}</td>`;
        }
        if (meta.subRange) {
          html += '<td class="grid-gap"></td>';
          for (let n = meta.subRange[0]; n <= meta.subRange[1]; n++) {
            const checked = preRows[ri].has('s'+String(n));
            html += `<td class="grid-cell" style="cursor:pointer" data-presel-row="${ri}" data-presel-num="s${n}">${checked ? `<span class="ball ball-sub" style="width:20px;height:20px;font-size:9px">${Utils.fmtNum(n)}</span>` : `<span style="color:var(--text-muted);font-size:10px">${Utils.fmtNum(n)}</span>`}</td>`;
          }
        }
        html += '<td class="grid-gap"></td><td></td><td></td>';
        if (meta.zones) html += '<td></td>';
        html += '<td></td>';
        if (!meta.positional) html += '<td></td>';
        html += '</tr>';
      }
      // 预选工具栏
      html += `<tr style="background:rgba(245,166,35,0.03)"><td colspan="${(hi-lo+1)+(meta.subRange?meta.subRange[1]-meta.subRange[0]+1+1:0)+5}" style="padding:4px 8px;font-size:10px">
        <span style="color:var(--gold);cursor:pointer;margin-right:12px" class="presel-action" data-action="add">➕ 添加</span>
        <span style="color:var(--text-dim);cursor:pointer;margin-right:12px" class="presel-action" data-action="copy">📋 复制</span>
        <span style="color:#E53935;cursor:pointer" class="presel-action" data-action="clear">🗑️ 清除</span>
      </td></tr>`;
    }

    // ── 统计行 (对标新浪: 出现总次数/平均遗漏/最大遗漏/最大连出) ──
    const statRows = [
      { label: '出现总次数', key: 'totalHits', fmt: v => v },
      { label: '平均遗漏值', key: 'avgOmit', fmt: v => v.toFixed(1) },
      { label: '最大遗漏值', key: 'maxOmit', fmt: v => v },
      { label: '最大连出数', key: 'maxConsec', fmt: v => v },
    ];

    // 计算统计数据
    const gridStats = {};
    const fullLen = grid.periods.length;
    for (let n = lo; n <= hi; n++) {
      const key = String(n);
      const vals = grid.main[key] || [];
      const omits = [];
      let maxOmit = 0, hitCount = 0, maxConsec = 0, curConsec = 0;
      for (let j = 0; j < fullLen; j++) {
        if (vals[j] && vals[j].hit) { hitCount++; curConsec++; maxConsec = Math.max(maxConsec, curConsec); }
        else { curConsec = 0; }
        if (vals[j]) omits.push(vals[j].omit);
        maxOmit = Math.max(maxOmit, vals[j] ? vals[j].omit : 0);
      }
      gridStats[key] = {
        totalHits: hitCount,
        avgOmit: omits.length > 0 ? omits.reduce((a,b)=>a+b,0) / omits.length : 0,
        maxOmit,
        maxConsec,
      };
    }
    // 后区统计
    if (meta.subRange && grid.sub) {
      for (let n = meta.subRange[0]; n <= meta.subRange[1]; n++) {
        const key = String(n);
        const vals = grid.sub[key] || [];
        const omits = [];
        let maxOmit = 0, hitCount = 0, maxConsec = 0, curConsec = 0;
        for (let j = 0; j < fullLen; j++) {
          if (vals[j] && vals[j].hit) { hitCount++; curConsec++; maxConsec = Math.max(maxConsec, curConsec); }
          else { curConsec = 0; }
          if (vals[j]) omits.push(vals[j].omit);
          maxOmit = Math.max(maxOmit, vals[j] ? vals[j].omit : 0);
        }
        gridStats['s'+key] = {
          totalHits: hitCount,
          avgOmit: omits.length > 0 ? omits.reduce((a,b)=>a+b,0) / omits.length : 0,
          maxOmit,
          maxConsec,
        };
      }
    }

    for (const sr of statRows) {
      html += `<tr style="background:rgba(255,255,255,0.02)"><td style="font-size:10px;color:var(--text-dim);font-weight:600">${sr.label}</td>`;
      for (let n = lo; n <= hi; n++) {
        const key = String(n);
        const isLast = String(n) === String(hi);
        const zoneBorder = isLast && meta.zones ? 'border-right:3px solid rgba(255,255,255,0.25)' : '';
        const val = gridStats[key] ? gridStats[key][sr.key] : '';
        html += `<td class="grid-cell" style="${zoneBorder};font-size:10px;color:var(--text-dim)">${sr.fmt(val)}</td>`;
      }
      if (meta.subRange) {
        html += '<td class="grid-gap"></td>';
        for (let n = meta.subRange[0]; n <= meta.subRange[1]; n++) {
          const key = 's'+String(n);
          const val = gridStats[key] ? gridStats[key][sr.key] : '';
          html += `<td class="grid-cell" style="font-size:10px;color:var(--text-dim)">${sr.fmt(val)}</td>`;
        }
      }
      html += '<td class="grid-gap"></td><td></td><td></td>';
      if (meta.zones) html += '<td></td>';
      html += '<td></td>';
      if (!meta.positional) html += '<td></td>';
      html += '</tr>';
    }

    html += '</tbody></table></div>';
    el.innerHTML = html;

    // 绑定事件
    this._bindGridEvents(el, type, data, meta, color);
  },

  // ─── 新浪式按位分块走势图（排列5/七星彩） ───
  _renderPositionalGrid(type, data, meta, color, periodCount, annotations) {
    const el = document.getElementById('number-grid-section');
    if (!el) return;
    const draws = data.draws;
    const N = Math.min(periodCount || 50, draws.length);
    const recent = draws.slice(-N);
    const P = recent.length;
    const ann = annotations || {};

    const mainClr = color.main.match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})/i);
    const rgbM = mainClr ? `${parseInt(mainClr[1],16)},${parseInt(mainClr[2],16)},${parseInt(mainClr[3],16)}` : '255,45,85';
    const subClr = (color.sub||'#1565C0').match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})/i);
    const rgbS = subClr ? `${parseInt(subClr[1],16)},${parseInt(subClr[2],16)},${parseInt(subClr[3],16)}` : '26,86,219';

    // 位置定义
    const isQXC = type === 'qxc';
    const posNames = isQXC ? ['d1','d2','d3','d4','d5','d6'] : ['万位','千位','百位','十位','个位'];
    // 数据列 d1=万位 d2=千位 d3=百位 d4=十位 d5=个位
    const posCount = posNames.length;
    const hasSpecial = isQXC && meta.subRange;
    const digitRange = [0, 9];

    // 为每个位置 × 每个数字计算遗漏
    const posOmits = [];  // posOmits[p][periodIdx][digit] = omission
    for (let p = 0; p < posCount; p++) {
      const digitOmits = {};
      for (let d = 0; d <= 9; d++) digitOmits[d] = 0;
      const byPeriod = [];
      for (let i = 0; i < P; i++) {
        const drawnDigit = parseInt(recent[i].main[p]);
        const row = {};
        for (let d = 0; d <= 9; d++) {
          row[d] = { hit: d === drawnDigit, omit: d === drawnDigit ? 0 : digitOmits[d] };
          if (d === drawnDigit) digitOmits[d] = 0;
          else digitOmits[d]++;
        }
        byPeriod.push(row);
      }
      posOmits.push(byPeriod);
    }

    // 后区遗漏（七星彩）
    let specialOmits = null;
    if (hasSpecial) {
      specialOmits = [];
      const digitOmits = {};
      for (let d = 0; d <= 14; d++) digitOmits[d] = 0;
      for (let i = 0; i < P; i++) {
        const drawnDigit = parseInt(recent[i].sub[0]);
        const row = {};
        for (let d = 0; d <= 14; d++) {
          row[d] = { hit: d === drawnDigit, omit: d === drawnDigit ? 0 : digitOmits[d] };
          if (d === drawnDigit) digitOmits[d] = 0;
          else digitOmits[d]++;
        }
        specialOmits.push(row);
      }
    }

    // 构建工具栏
    const sizes = [20, 50, 80, 120].filter(s => s <= draws.length);
    let html = `<div class="grid-toolbar">
      <div class="grid-toolbar-left">
        <span style="font-weight:700;font-size:14px">📋 ${isQXC?'七星彩':'排列5'} 按位走势 (新浪式·旧→新)</span>
        <div class="period-selector">${sizes.map(s => `<button class="period-opt${s === N ? ' active' : ''}" data-size="${s}">${s}期</button>`).join('')}</div>
      </div>
      <div class="grid-toolbar-right">
        <div class="annotation-toggles">
          <label class="anno-toggle${ann.repeat?' active':''}" data-anno="repeat"><span>🔄 重号</span></label>
          <label class="anno-toggle${ann.consecutive?' active':''}" data-anno="consecutive"><span>🔗 连号</span></label>
          <label class="anno-toggle${ann.omitData !== false ? ' active' : ''}" data-anno="omitData"><span>📊 遗漏数据</span></label>
        </div>
      </div>
    </div>`;

    html += '<div class="grid-scroll"><table class="num-grid"><thead>';

    // 表头行1: 位置名
    html += '<tr><th class="grid-period-th">期号</th>';
    for (let p = 0; p < posCount; p++) {
      html += `<th colspan="10" style="background:rgba(255,255,255,0.03);font-size:11px;color:var(--text-dim);font-weight:700">${posNames[p]}</th>`;
      if (p < posCount - 1) html += '<th class="grid-gap"></th>';
    }
    if (hasSpecial) {
      html += '<th class="grid-gap"></th>';
      html += '<th colspan="15" style="background:rgba(21,101,192,0.1);font-size:11px;color:#1565C0;font-weight:700">后区 special</th>';
    }
    html += '<th class="grid-gap"></th><th>和值</th><th>奇偶</th></tr>';

    // 表头行2: 数字0-9
    html += '<tr><th class="grid-period-th"></th>';
    for (let p = 0; p < posCount; p++) {
      for (let d = 0; d <= 9; d++) {
        html += `<th class="grid-num-th">${d}</th>`;
      }
      if (p < posCount - 1) html += '<th class="grid-gap"></th>';
    }
    if (hasSpecial) {
      html += '<th class="grid-gap"></th>';
      for (let d = 0; d <= 14; d++) html += `<th class="grid-num-th grid-sub-th">${Utils.fmtNum(d)}</th>`;
    }
    html += '<th class="grid-gap"></th><th></th><th></th></tr>';
    html += '</thead><tbody>';

    // 预选行
    const preRows = this._preSelectionRows;
    for (let ri = 0; ri < preRows.length; ri++) {
      html += `<tr style="background:rgba(245,166,35,0.06)"><td style="font-size:10px;color:var(--gold);font-weight:700">预选${ri+1} <span style="color:#E53935;cursor:pointer;margin-left:4px;font-size:12px" class="presel-action" data-action="del" data-row="${ri}">✕</span></td>`;
      for (let p = 0; p < posCount; p++) {
        for (let d = 0; d <= 9; d++) {
          const key = `${p}_${d}`;
          const checked = preRows[ri].has(key);
          html += `<td class="grid-cell" style="cursor:pointer" data-presel-row="${ri}" data-presel-num="${key}">${checked ? `<span class="ball" style="--ball-color:rgb(${rgbM});--ball-dark:rgb(${Math.round(parseInt(rgbM.split(',')[0])*0.3)},${Math.round(parseInt(rgbM.split(',')[1])*0.3)},${Math.round(parseInt(rgbM.split(',')[2])*0.3)});--ball-glow:rgba(${rgbM},0.3);width:20px;height:20px;font-size:9px">${d}</span>` : `<span style="color:var(--text-muted);font-size:10px">${d}</span>`}</td>`;
        }
        if (p < posCount - 1) html += '<td class="grid-gap"></td>';
      }
      html += '<td class="grid-gap"></td><td></td><td></td></tr>';
    }
    // 预选工具栏
    html += `<tr style="background:rgba(245,166,35,0.03)"><td colspan="${posCount*10+(posCount-1)+(hasSpecial?16:0)+4}" style="padding:4px 8px;font-size:10px">
      <span style="color:var(--gold);cursor:pointer;margin-right:12px" class="presel-action" data-action="add">➕ 添加</span>
      <span style="color:var(--text-dim);cursor:pointer;margin-right:12px" class="presel-action" data-action="copy">📋 复制</span>
      <span style="color:#E53935;cursor:pointer" class="presel-action" data-action="clear">🗑️ 清除</span>
    </td></tr>`;

    // d1=万位 d2=千位 d3=百位 d4=十位 d5=个位
    for (let i = 0; i < P; i++) {
      const period = recent[i].period;
      html += '<tr>';
      html += `<td class="grid-period">${period}</td>`;

      for (let p = 0; p < posCount; p++) {
        for (let d = 0; d <= 9; d++) {
          const cell = posOmits[p][i][d];
          if (cell.hit) {
            html += `<td class="grid-cell"><span class="ball" style="--ball-color:rgb(${rgbM});--ball-dark:rgb(${Math.round(parseInt(rgbM.split(',')[0])*0.3)},${Math.round(parseInt(rgbM.split(',')[1])*0.3)},${Math.round(parseInt(rgbM.split(',')[2])*0.3)});--ball-glow:rgba(${rgbM},0.4);width:20px;height:20px;font-size:9px">${d}</span></td>`;
          } else {
            const showBg = ann.omitLayer !== false;
            const showNum = ann.omitData !== false;
            const bgStyle = showBg ? (cell.omit > 5 ? 'background:rgba(107,155,210,0.15)' : cell.omit > 2 ? '' : 'background:rgba(255,107,107,0.12)') : '';
            html += `<td class="grid-cell" style="${bgStyle};font-size:10px;text-align:center;${showNum ? 'color:'+(cell.omit>5?'#6B9BD2':cell.omit>2?'#807C78':'#FF6B6B') : 'color:transparent'}">${showNum ? cell.omit : ''}</td>`;
          }
        }
        if (p < posCount - 1) html += '<td class="grid-gap"></td>';
      }

      // 后区 special
      if (hasSpecial && specialOmits) {
        html += '<td class="grid-gap"></td>';
        for (let d = 0; d <= 14; d++) {
          const cell = specialOmits[i][d];
          if (cell.hit) {
            html += `<td class="grid-cell"><span class="ball ball-sub" style="--ball-color:rgb(${rgbS});--ball-dark:rgb(${Math.round(parseInt(rgbS.split(',')[0])*0.3)},${Math.round(parseInt(rgbS.split(',')[1])*0.3)},${Math.round(parseInt(rgbS.split(',')[2])*0.3)});--ball-glow:rgba(${rgbS},0.4);width:20px;height:20px;font-size:9px">${Utils.fmtNum(d)}</span></td>`;
          } else {
            const showBg = ann.omitLayer !== false;
            const showNum = ann.omitData !== false;
            const bgStyle = showBg ? (cell.omit > 5 ? 'background:rgba(107,155,210,0.15)' : cell.omit > 2 ? '' : 'background:rgba(255,107,107,0.12)') : '';
            html += `<td class="grid-cell" style="${bgStyle};font-size:10px;text-align:center;${showNum ? 'color:'+(cell.omit>5?'#6B9BD2':cell.omit>2?'#807C78':'#FF6B6B') : 'color:transparent'}">${showNum ? cell.omit : ''}</td>`;
          }
        }
      }

      html += '<td class="grid-gap"></td>';
      // 统计列
      html += `<td style="font-weight:600">${recent[i].main.reduce((a,b)=>a+parseInt(b),0)}</td>`;
      const odd = recent[i].main.filter(x => parseInt(x) % 2 === 1).length;
      html += `<td>${odd}:${recent[i].main.length-odd}</td>`;
      html += '</tr>';
    }

    // 统计行
    html += '</tbody></table></div>';
    el.innerHTML = html;
    this._bindGridEvents(el, type, data, meta, color);
  },

  _bindGridEvents(el, type, data, meta, color) {
    const self = this;
    // 期数切换
    el.querySelectorAll('.period-opt').forEach(btn => {
      btn.addEventListener('click', () => {
        const size = parseInt(btn.dataset.size);
        this._currentPeriodSize = size;
        this.renderNumberGrid(type, data, meta, color, size, this._currentAnnotations || {});
      });
    });

    // 标注开关
    const ann = this._currentAnnotations || { repeat: false, consecutive: false, neighbor: false, omitData: true, omitLayer: true };
    el.querySelectorAll('.anno-toggle').forEach(toggle => {
      toggle.addEventListener('click', () => {
        const key = toggle.dataset.anno;
        ann[key] = !ann[key];
        this._currentAnnotations = ann;
        this.renderNumberGrid(type, data, meta, color, this._currentPeriodSize || 50, ann);
      });
    });

    // 预选行操作
    el.querySelectorAll('.presel-action').forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        if (action === 'del') {
          const rowIdx = parseInt(btn.dataset.row);
          self._preSelectionRows.splice(rowIdx, 1);
          if (self._preSelectionRows.length === 0) self._preSelectionRows = [new Set(), new Set(), new Set()];
        } else if (action === 'add') {
          self._preSelectionRows.push(new Set());
        } else if (action === 'copy') {
          if (self._preSelectionRows.length > 0) {
            self._preSelectionRows.push(new Set(self._preSelectionRows[self._preSelectionRows.length - 1]));
          }
        } else if (action === 'clear') {
          self._preSelectionRows = [new Set(), new Set(), new Set()];
        }
        this.renderNumberGrid(type, data, meta, color, this._currentPeriodSize || 50, this._currentAnnotations || {});
      });
    });

    // 预选格点击切换
    el.querySelectorAll('.grid-cell[data-presel-row]').forEach(cell => {
      cell.addEventListener('click', () => {
        const row = parseInt(cell.dataset.preselRow);
        const num = cell.dataset.preselNum;
        if (!self._preSelectionRows[row]) self._preSelectionRows[row] = new Set();
        if (self._preSelectionRows[row].has(num)) {
          self._preSelectionRows[row].delete(num);
        } else {
          self._preSelectionRows[row].add(num);
        }
        this.renderNumberGrid(type, data, meta, color, this._currentPeriodSize || 50, this._currentAnnotations || {});
      });
    });

    this._currentPeriodSize = this._currentPeriodSize || 50;
  },

  // ─── 历史数据表格 ───
  renderDataTable(type, data, color) {
    const el = document.getElementById('data-table-section');
    if (!el) return;

    const mainClr = color.main.match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})/i);
    const rgbM = mainClr ? `${parseInt(mainClr[1],16)},${parseInt(mainClr[2],16)},${parseInt(mainClr[3],16)}` : '255,45,85';

    const draws = data.draws;
    const pageSize = 30;
    let currentPage = 0;
    const totalPages = Math.ceil(draws.length / pageSize);

    const render = (page) => {
      const start = Math.max(0, draws.length - (page + 1) * pageSize);
      const end = draws.length - page * pageSize;
      const slice = draws.slice(start, end);

      let html = '<div class="table-header">📊 历史开奖数据</div>';
      html += `<div class="table-pagination">
        <button class="page-btn" ${page === 0 ? 'disabled' : ''} data-page="${page - 1}">上一页</button>
        <span>第 ${page + 1} / ${totalPages} 页 (共 ${draws.length} 期)</span>
        <button class="page-btn" ${page >= totalPages - 1 ? 'disabled' : ''} data-page="${page + 1}">下一页</button>
      </div>`;
      html += '<div class="table-scroll"><table class="data-table"><thead><tr>';
      html += '<th>期号</th>';
      for (let i = 1; i <= data.metadata.mainCount; i++) {
        html += `<th>${i <= 9 ? '0' + i : i}</th>`;
      }
      if (data.metadata.subCount > 0) {
        html += '<th class="table-sub-header">后区</th>';
      }
      html += '</tr></thead><tbody>';

      // 从旧到新排列
      slice.forEach(d => {
        html += '<tr>';
        html += `<td style="font-family:var(--font-mono);font-weight:600">${d.period}</td>`;
        d.main.forEach(n => {
          html += `<td><span class="ball" style="--ball-color:rgb(${rgbM});--ball-dark:rgb(${Math.round(parseInt(rgbM.split(',')[0])*0.3)},${Math.round(parseInt(rgbM.split(',')[1])*0.3)},${Math.round(parseInt(rgbM.split(',')[2])*0.3)});--ball-glow:rgba(${rgbM},0.35);width:26px;height:26px;font-size:11px">${Utils.fmtNum(n)}</span></td>`;
        });
        if (d.sub && d.sub.length) {
          html += `<td class="table-sub-cell">${d.sub.map(n => `<span class="ball ball-sub" style="width:26px;height:26px;font-size:11px">${Utils.fmtNum(n)}</span>`).join(' ')}</td>`;
        }
        html += '</tr>';
      });

      html += '</tbody></table></div>';
      el.innerHTML = html;

      // 绑定分页按钮
      el.querySelectorAll('.page-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          if (btn.disabled) return;
          render(parseInt(btn.dataset.page));
        });
      });
    };

    render(currentPage);
  },

  getIcon(type) {
    const map = { ssq: '🔴', dlt: '🟠', kl8: '🟣', pl5: '🔵', qxc: '🟢' };
    return map[type] || '🎱';
  },
};
