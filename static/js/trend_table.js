/**
 * 传统表格型走势图 — 多行模拟选号 + 分区着色 + CSS 标记连线/重号
 */

// ── 全局状态 ──
let simRows = [{ name: '模拟选行1', main: '', sub: '', pos: {} }];
let currentTrendData = null;

// ── 主入口 ──
async function loadTrendTable() {
  const w = document.getElementById('trend-window').value;
  const resp = await fetch(`/api/${LT}/trend-table?window=${w}`);
  const data = await resp.json();
  if (data.error) {
    document.getElementById('trend-table-container').innerHTML =
      `<p class="text-danger text-center py-3">${data.error}</p>`;
    return;
  }
  currentTrendData = data;
  document.getElementById('trend-table-container').innerHTML = buildTrendHTML(data);
  document.getElementById('sim-panel').style.display = '';
  document.getElementById('line-legend-panel').style.display = '';
  renderSimPanel();
  // 走势连线（位式型 or 数池型副区）
  if (data.positions || data.sub_zone) {
    _bindLineDrawEvents();
    setTimeout(drawPositionLines, 100);
  }
}

// ═══════════════════════════════════════════════════
// HTML 构建
// ═══════════════════════════════════════════════════

function buildTrendHTML(data) {
  if (data.positions) return buildPositionTrendHTML(data);
  return buildNumberPoolTrendHTML(data);
}

// ── 数池型 ──
function buildNumberPoolTrendHTML(data) {
  const main = data.main_zone, sub = data.sub_zone;
  const periods = data.periods;
  const mStats = main.stats, sStats = sub ? sub.stats : null;
  const mR = rangeArr(mStats.lo, mStats.hi);
  const zones = data.zones || [];
  const subZones = data.sub_zones || [];
  const omissionGrid = data.omission_grid || [];
  const subOmissionGrid = data.sub_omission_grid || null;
  const derivedCols = data.derived_cols || [];
  const repeatHits = data.repeat_hits || [];
  const subRepeatHits = data.sub_repeat_hits || null;

  // 确定衍生列标题
  const derivedHeaders = [];
  if (derivedCols.length > 0) {
    const s0 = derivedCols[0];
    derivedHeaders.push({ key: 'sum', label: '和值' });
    if ('span' in s0) derivedHeaders.push({ key: 'span', label: '跨度' });
    if ('zone_ratio' in s0) derivedHeaders.push({ key: 'zone_ratio', label: '区间比' });
    derivedHeaders.push({ key: 'oe_ratio', label: '奇偶比' });
    if ('ac' in s0) derivedHeaders.push({ key: 'ac', label: 'AC值' });
  }

  // 预计算每列的 zone 索引
  const mainZoneMap = buildZoneMap(zones, mStats.lo, mStats.hi);
  const subZoneMap = sub ? buildZoneMap(subZones, sStats.lo, sStats.hi) : {};

  // ── 连线模式查找表（key: "period_idx:num"） ──
  const patterns = data.patterns || {};
  const consecMap = {};
  (patterns.consecutive_in_draw || []).forEach(p => {
    consecMap[`${p.period_idx}:${p.num1}`] = true;
  });
  const diagonalMap = {};
  (patterns.diagonal_pairs || []).forEach(p => {
    diagonalMap[`${p.period_idx1}:${p.num1}`] = true;
    diagonalMap[`${p.period_idx2}:${p.num2}`] = true;
  });
  const streakMap = {};
  (patterns.streaks || []).forEach(s => {
    for (let pi = s.start; pi <= s.end; pi++) {
      streakMap[`${pi}:${s.num}`] = true;
    }
  });

  let html = '<div class="trend-scroll" id="trend-scroll"><table class="trend-table ' + data.lottery_type + '">';

  // 表头
  html += '<thead><tr><th class="period-col">期号</th>';
  mR.forEach((v, i) => {
    const zc = zoneClass(mainZoneMap, v, mR, i);
    html += `<th class="${zc}">${pad(v)}</th>`;
  });
  if (sub) {
    html += '<th class="spacer-col"></th>';
    const sR = rangeArr(sStats.lo, sStats.hi);
    sR.forEach((v, i) => {
      const zc = zoneClass(subZoneMap, v, sR, i);
      html += `<th class="sub-header ${zc}">${pad(v)}</th>`;
    });
  }
  // 衍生列标题
  derivedHeaders.forEach((dh) => {
    const extraCls = dh.key === 'zone_ratio' ? ' derived-col-zone' : '';
    html += `<th class="derived-col${extraCls}">${dh.label}</th>`;
  });
  html += '</tr></thead><tbody>';

  // 数据行（期号递增）
  for (let i = 0; i < periods.length; i++) {
    const isLatest = (i === periods.length - 1);
    html += `<tr${isLatest ? ' class="latest-row"' : ''}>`;
    html += `<td class="period-col">${periods[i]}</td>`;

    const mainSet = new Set(main.draws[i]);
    const omRow = omissionGrid[i] || {};
    const rptSet = new Set(repeatHits[i] || []);
    mR.forEach((v, j) => {
      const zc = zoneClass(mainZoneMap, v, mR, j);
      const pKey = `${i}:${v}`;
      const patCls = [
        consecMap[pKey] ? 'consec-connector' : '',
        diagonalMap[pKey] ? 'diagonal-cell' : '',
        streakMap[pKey] ? 'streak-cell' : ''
      ].filter(Boolean).join(' ');
      if (mainSet.has(v)) {
        const rptCls = rptSet.has(v) ? ' repeat-hit' : '';
        html += `<td class="data-cell ${zc}${rptCls} ${patCls}" data-zone="M" data-num="${v}" data-row="${i}"><span class="num-mark">${pad(v)}</span></td>`;
      } else {
        const om = omRow[v] || 0;
        const ocls = omissionClass(om);
        html += `<td class="data-cell ${zc} ${patCls}" data-zone="M" data-num="${v}" data-row="${i}"><span class="om-val ${ocls}">${om}</span></td>`;
      }
    });

    if (sub) {
      html += '<td class="spacer-col"></td>';
      const subSet = new Set(sub.draws[i]);
      const sR = rangeArr(sStats.lo, sStats.hi);
      const subOmRow = subOmissionGrid ? (subOmissionGrid[i] || {}) : {};
      const subRptSet = new Set(subRepeatHits ? (subRepeatHits[i] || []) : []);
      sR.forEach((v, j) => {
        const zc = zoneClass(subZoneMap, v, sR, j);
        if (subSet.has(v)) {
          const rptCls = subRptSet.has(v) ? ' repeat-hit' : '';
          html += `<td class="data-cell sub-cell ${zc}${rptCls}" data-zone="S" data-num="${v}" data-row="${i}"><span class="num-mark">${pad(v)}</span></td>`;
        } else {
          const om = subOmRow[v] || 0;
          const ocls = omissionClass(om);
          html += `<td class="data-cell sub-cell ${zc}" data-zone="S" data-num="${v}" data-row="${i}"><span class="om-val ${ocls}">${om}</span></td>`;
        }
      });
    }
    // 衍生列
    const dc = derivedCols[i] || {};
    derivedHeaders.forEach((dh) => {
      const extraCls = dh.key === 'zone_ratio' ? ' derived-col-zone' : '';
      html += `<td class="derived-col${extraCls}">${dc[dh.key] != null ? dc[dh.key] : ''}</td>`;
    });
    html += '</tr>';
  }
  html += '</tbody>';

  // 统计行 — 窗口统计
  html += '<tfoot>';
  const winStatRows = [
    { label: '窗口频次', key: 'freq_window', fmt: v => v || '' },
    { label: '当前遗漏', key: 'omission_current', fmt: v => v > 0 ? v : '0' },
  ];
  winStatRows.forEach(sr => {
    html += '<tr><td class="stat-label">' + sr.label + '</td>';
    mR.forEach((v, j) => {
      html += `<td class="${zoneClass(mainZoneMap, v, mR, j)}">${sr.fmt(mStats[sr.key][v])}</td>`;
    });
    if (sub) {
      html += '<td class="spacer-col"></td>';
      const sR2 = rangeArr(sStats.lo, sStats.hi);
      sR2.forEach((v, j) => {
        html += `<td class="${zoneClass(subZoneMap, v, sR2, j)}">${sr.fmt(sStats[sr.key][v])}</td>`;
      });
    }
    derivedHeaders.forEach(() => { html += '<td class="derived-col"></td>'; });
    html += '</tr>';
  });
  // 分隔行
  html += '<tr class="stat-sep"><td class="stat-label">— 历史 —</td>';
  mR.forEach(() => { html += '<td></td>'; });
  if (sub) {
    html += '<td class="spacer-col"></td>';
    rangeArr(sStats.lo, sStats.hi).forEach(() => { html += '<td></td>'; });
  }
  derivedHeaders.forEach(() => { html += '<td class="derived-col"></td>'; });
  html += '</tr>';
  // 历史统计
  const histStatRows = [
    { label: '历史总次', key: 'freq_total', fmt: v => v || '' },
    { label: '最大遗漏', key: 'omission_max', fmt: v => v || '' },
  ];
  histStatRows.forEach(sr => {
    html += '<tr><td class="stat-label">' + sr.label + '</td>';
    mR.forEach((v, j) => {
      html += `<td class="${zoneClass(mainZoneMap, v, mR, j)}">${sr.fmt(mStats[sr.key][v])}</td>`;
    });
    if (sub) {
      html += '<td class="spacer-col"></td>';
      const sR2 = rangeArr(sStats.lo, sStats.hi);
      sR2.forEach((v, j) => {
        html += `<td class="${zoneClass(subZoneMap, v, sR2, j)}">${sr.fmt(sStats[sr.key][v])}</td>`;
      });
    }
    derivedHeaders.forEach(() => { html += '<td class="derived-col"></td>'; });
    html += '</tr>';
  });
  html += '</tfoot></table>';
  html += '<canvas id="trend-line-canvas" style="position:absolute;top:0;left:0;pointer-events:none;z-index:0"></canvas>';
  html += '</div>';
  return html;
}

// ── 位式型 ──
function buildPositionTrendHTML(data) {
  const periods = data.periods;
  const positions = data.positions;
  const posZones = data.pos_zones || [];
  const derivedCols = data.derived_cols || [];

  const posDerivedHeaders = [{ key: 'sum', label: '和值' }, { key: 'oe_ratio', label: '奇偶比' }];

  // 重号查找表: key="pos:period_idx"
  const posRepeatMap = {};
  (data.pos_repeat_hits || []).forEach(pr => {
    pr.repeats.forEach(r => {
      posRepeatMap[`${pr.pos}:${r.period_idx}`] = r.digit;
    });
  });

  // 连线模式查找表 key: "period_idx:pos:digit"
  const patterns = data.patterns || {};
  const diagonalMap = {};
  (patterns.diagonal_pairs || []).forEach(p => {
    diagonalMap[`${p.period_idx1}:${p.pos}:${p.digit1}`] = true;
    diagonalMap[`${p.period_idx2}:${p.pos}:${p.digit2}`] = true;
  });
  const streakMap = {};
  (patterns.streaks || []).forEach(s => {
    for (let pi = s.start; pi <= s.end; pi++) {
      streakMap[`${pi}:${s.pos}:${s.digit}`] = true;
    }
  });

  let html = '<div class="trend-scroll" id="trend-scroll"><table class="trend-table ' + data.lottery_type + '">';
  html += '<thead><tr><th class="period-col">期号</th>';
  positions.forEach((p, pi) => {
    html += `<th colspan="${p.hi - p.lo + 1}" class="zone-label">${p.label} (${p.lo}–${p.hi})</th>`;
  });
  html += '</tr><tr><th class="period-col"></th>';
  positions.forEach((p, pi) => {
    const z = posZones[pi] || { lo: p.lo, hi: p.hi };
    for (let d = p.lo; d <= p.hi; d++) {
      const zi = getPosZoneIdx(pi, d, posZones);
      html += `<th class="zone-${zi % 8}">${d}</th>`;
    }
  });
  // 衍生列标题
  posDerivedHeaders.forEach((dh) => {
    html += `<th class="derived-col">${dh.label}</th>`;
  });
  html += '</tr></thead><tbody>';

  for (let i = 0; i < periods.length; i++) {
    const isLatest = (i === periods.length - 1);
    html += `<tr${isLatest ? ' class="latest-row"' : ''}>`;
    html += `<td class="period-col">${periods[i]}</td>`;
    positions.forEach((p, pi) => {
      const z = posZones[pi] || { lo: p.lo, hi: p.hi };
      const hitVal = p.draws[i];
      // QXC 前区=main-pos, 后区=sub-pos; PL5 全部 main-pos
      const isSub = data.lottery_type === 'qxc' && pi === positions.length - 1;
      const posCls = isSub ? 'sub-pos' : 'main-pos';
      for (let d = p.lo; d <= p.hi; d++) {
        const zi = getPosZoneIdx(pi, d, posZones);
        let cls = `data-cell zone-${zi % 8} ${posCls}`;
        // 重号检测
        const rptDigit = posRepeatMap[`${pi}:${i}`];
        if (rptDigit !== undefined && d === rptDigit) {
          cls += ' repeat-hit';
        }
        if (d === hitVal) {
          const pKey = `${i}:${pi}:${d}`;
          const patCls = [
            diagonalMap[pKey] ? 'diagonal-cell' : '',
            streakMap[pKey] ? 'streak-cell' : ''
          ].filter(Boolean).join(' ');
          html += `<td class="${cls} ${patCls}" data-zone="P${pi}" data-num="${d}" data-row="${i}"><span class="num-mark">${d}</span></td>`;
        } else {
          html += `<td class="${cls}" data-zone="P${pi}" data-num="${d}" data-row="${i}"></td>`;
        }
      }
    });
    // 衍生列
    const dc = derivedCols[i] || {};
    posDerivedHeaders.forEach((dh) => {
      const extraCls = dh.key === 'zone_ratio' ? ' derived-col-zone' : '';
      html += `<td class="derived-col${extraCls}">${dc[dh.key] != null ? dc[dh.key] : ''}</td>`;
    });
    html += '</tr>';
  }
  html += '</tbody>';

  // 统计行 — 窗口统计
  html += '<tfoot>';
  const posWinKeys = [
    { label: '窗口频次', key: 'freq_window' },
    { label: '当前遗漏', key: 'omission_current' },
  ];
  posWinKeys.forEach(sr => {
    html += '<tr><td class="stat-label">' + sr.label + '</td>';
    positions.forEach((p, pi) => {
      const z = posZones[pi] || { lo: p.lo, hi: p.hi };
      for (let d = p.lo; d <= p.hi; d++) {
        const zi = getPosZoneIdx(pi, d, posZones);
        let val = p[sr.key][d];
        if (sr.key === 'omission_current' && val === 0) val = '0';
        html += `<td class="zone-${zi % 8}">${val || ''}</td>`;
      }
    });
    posDerivedHeaders.forEach(() => { html += '<td class="derived-col"></td>'; });
    html += '</tr>';
  });
  // 分隔行
  html += '<tr class="stat-sep"><td class="stat-label">— 历史 —</td>';
  positions.forEach((p) => {
    for (let d = p.lo; d <= p.hi; d++) { html += '<td></td>'; }
  });
  posDerivedHeaders.forEach(() => { html += '<td class="derived-col"></td>'; });
  html += '</tr>';
  // 历史统计
  const posHistKeys = [
    { label: '历史总次', key: 'freq_total' },
    { label: '最大遗漏', key: 'omission_max' },
  ];
  posHistKeys.forEach(sr => {
    html += '<tr><td class="stat-label">' + sr.label + '</td>';
    positions.forEach((p, pi) => {
      const z = posZones[pi] || { lo: p.lo, hi: p.hi };
      for (let d = p.lo; d <= p.hi; d++) {
        const zi = getPosZoneIdx(pi, d, posZones);
        html += `<td class="zone-${zi % 8}">${p[sr.key][d] || ''}</td>`;
      }
    });
    posDerivedHeaders.forEach(() => { html += '<td class="derived-col"></td>'; });
    html += '</tr>';
  });
  html += '</tfoot></table>';
  html += '<canvas id="trend-line-canvas" style="position:absolute;top:0;left:0;pointer-events:none;z-index:0"></canvas>';
  html += '</div>';
  return html;
}

// ═══════════════════════════════════════════════════
// 分区辅助
// ═══════════════════════════════════════════════════

function buildZoneMap(zones, lo, hi) {
  const map = {};
  zones.forEach((z, zi) => {
    for (let v = z.lo; v <= z.hi; v++) {
      map[v] = { idx: zi, boundary: false };
    }
  });
  // 标记分区边界（每个zone最后一个号码）
  zones.forEach(z => { if (map[z.hi]) map[z.hi].boundary = true; });
  return map;
}

function zoneClass(zoneMap, v, range, idx) {
  const zm = zoneMap[v];
  if (!zm) return '';
  let cls = 'zone-' + (zm.idx % 8);
  if (zm.boundary) cls += ' zone-boundary';
  return cls;
}

function getPosZoneIdx(pi, d, posZones) {
  // 简单的：每位一个zone
  let base = pi;
  if (posZones.length > 0 && posZones[pi]) {
    // 如果有分段的（QXC后区），d在哪个段就用哪个
    if (posZones.length > pi + 1 && d > posZones[pi].hi) {
      return pi + 1;
    }
  }
  return base;
}

// ═══════════════════════════════════════════════════
// 位式走势连线 (Canvas 叠加层)
// ═══════════════════════════════════════════════════

let _lineDrawPending = false;

function drawPositionLines() {
  const container = document.getElementById('trend-scroll');
  if (!container) return;
  const canvas = document.getElementById('trend-line-canvas');
  if (!canvas) return;

  canvas.width = container.scrollWidth;
  canvas.height = container.scrollHeight;
  canvas.style.width = container.scrollWidth + 'px';
  canvas.style.height = container.scrollHeight + 'px';

  const ctx = canvas.getContext('2d');
  const cRect = container.getBoundingClientRect();
  const sl = container.scrollLeft;
  const st = container.scrollTop;
  const colors = ['#e74c3c', '#3498db', '#27ae60', '#f39c12', '#8e44ad', '#1abc9c', '#e67e22'];

  function getCenter(span) {
    const r = span.getBoundingClientRect();
    return {
      x: r.left + r.width / 2 - cRect.left + sl,
      y: r.top + r.height / 2 - cRect.top + st,
    };
  }

  // ── 位式型连线 (PL5/QXC) ──
  const posSpans = container.querySelectorAll('td[data-zone^="P"] .num-mark');
  if (posSpans.length > 0) {
    const posGroups = {};
    posSpans.forEach(span => {
      const td = span.parentElement;
      const zone = td.getAttribute('data-zone');
      const row = parseInt(td.getAttribute('data-row'));
      if (isNaN(row)) return;
      if (!posGroups[zone]) posGroups[zone] = [];
      posGroups[zone].push({ row, span });
    });

    Object.entries(posGroups).forEach(([zone, cells]) => {
      const gi = parseInt((zone || 'P0').replace('P', '')) || 0;
      cells.sort((a, b) => a.row - b.row);

      ctx.strokeStyle = colors[gi % colors.length];
      ctx.lineWidth = 2.2;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();

      for (let i = 0; i < cells.length - 1; i++) {
        const a = cells[i];
        const b = cells[i + 1];
        if (b.row !== a.row + 1) continue;
        const p1 = getCenter(a.span);
        const p2 = getCenter(b.span);
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
      }
      ctx.stroke();
    });
  }

  // ── 数池型副区连线 ──
  // SSQ: 蓝球每期1球，直接向下串联
  // DLT: 后区每期2球，Z字形折线（同行左→右，行末→下行首）
  const subSpans = container.querySelectorAll('td.sub-cell[data-zone="S"] .num-mark');
  if (subSpans.length > 0) {
    // 按行号分组，行内按 x 坐标排序（左→右）
    const rowGroups = {};
    subSpans.forEach(span => {
      const row = parseInt(span.parentElement.getAttribute('data-row'));
      if (isNaN(row)) return;
      if (!rowGroups[row]) rowGroups[row] = [];
      rowGroups[row].push(span);
    });

    // 每行内按 x 坐标排序
    Object.values(rowGroups).forEach(spans => {
      spans.sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
    });

    const rows = Object.keys(rowGroups).map(Number).sort((a, b) => a - b);

    // 拼接全部有序点：行内左→右，行尾接下行首
    const ordered = [];
    for (let ri = 0; ri < rows.length; ri++) {
      const r = rows[ri];
      if (ri > 0 && rows[ri] !== rows[ri - 1] + 1) continue;  // 跳过不连续行
      ordered.push(...rowGroups[r]);
    }

    ctx.strokeStyle = 'rgba(52, 152, 219, 0.7)';
    ctx.lineWidth = 1.8;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();

    for (let i = 0; i < ordered.length - 1; i++) {
      const r1 = parseInt(ordered[i].parentElement.getAttribute('data-row'));
      const r2 = parseInt(ordered[i + 1].parentElement.getAttribute('data-row'));
      if (r2 > r1 + 1) continue;  // 只连相邻行

      const p1 = getCenter(ordered[i]);
      const p2 = getCenter(ordered[i + 1]);
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
    }
    ctx.stroke();
  }
}

function _scheduleLineDraw() {
  if (_lineDrawPending) return;
  _lineDrawPending = true;
  requestAnimationFrame(() => {
    _lineDrawPending = false;
    drawPositionLines();
  });
}

function _bindLineDrawEvents() {
  const container = document.getElementById('trend-scroll');
  if (!container || container._lineDrawBound) return;
  container._lineDrawBound = true;
  container.addEventListener('scroll', _scheduleLineDraw);
  window.addEventListener('resize', _scheduleLineDraw);
}

// ═══════════════════════════════════════════════════
// 模拟选号 — 输入框多行
// ═══════════════════════════════════════════════════

function _parseNums(raw, lo, hi) {
  if (!raw || !raw.trim()) return [];
  const nums = [];
  const parts = raw.split(/[,\s]+/);
  parts.forEach(p => {
    const v = parseInt(p);
    if (!isNaN(v) && v >= lo && v <= hi) nums.push(v);
  });
  return [...new Set(nums)].sort((a, b) => a - b);
}

function _fmtNums(nums) {
  return nums.length ? nums.map(pad).join(' ') : '—';
}

function _ballHTML(nums, cls) {
  return nums.map(n => `<span class="ball ball-sm ${cls}">${pad(n)}</span>`).join(' ');
}

function _onSimInput(idx, field, value) {
  simRows[idx][field] = value;
}

function _onSimPosInput(idx, pKey, value) {
  if (!simRows[idx].pos) simRows[idx].pos = {};
  simRows[idx].pos[pKey] = value;
}

function renderSimPanel() {
  const c = document.getElementById('sim-rows-container');
  const isPos = META.main_range[1] <= 10 && META.main_range[0] >= 0;

  let h = '<div class="table-responsive"><table class="sim-table"><thead><tr><th>行</th>';
  if (isPos) {
    const mainN = META.main_cols ? META.main_cols.length : 5;
    for (let i = 0; i < mainN; i++) h += `<th>第${i+1}位</th>`;
    if (META.sub_cols && META.sub_cols.length) h += '<th>后区</th>';
  } else {
    h += '<th>' + (META.main_label || '主区') + '</th>';
    if (META.sub_cols && META.sub_cols.length) h += '<th>' + (META.sub_label || '副区') + '</th>';
  }
  h += '<th>操作</th></tr></thead><tbody>';

  simRows.forEach((row, idx) => {
    h += '<tr>';
    h += `<td class="sim-name">${row.name}</td>`;

    if (isPos) {
      const mainN = META.main_cols ? META.main_cols.length : 5;
      for (let pi = 0; pi < mainN; pi++) {
        const key = 'p' + pi;
        const val = (row.pos && row.pos[key]) ? row.pos[key] : '';
        const nums = _parseNums(val, META.main_range[0], META.main_range[1]);
        h += `<td><input class="sim-input" value="${val}" placeholder="0-9" oninput="_onSimPosInput(${idx},'${key}',this.value);renderSimPanel()"><div class="sim-balls">${_ballHTML(nums, 'ball-' + LT + '-main')}</div></td>`;
      }
      if (META.sub_cols && META.sub_cols.length) {
        const val = row.sub || '';
        const sLo = META.sub_range ? META.sub_range[0] : 0;
        const sHi = META.sub_range ? META.sub_range[1] : 14;
        const nums = _parseNums(val, sLo, sHi);
        h += `<td><input class="sim-input" value="${val}" placeholder="${sLo}-${sHi}" oninput="_onSimInput(${idx},'sub',this.value);renderSimPanel()"><div class="sim-balls">${_ballHTML(nums, 'ball-' + LT + '-sub')}</div></td>`;
      }
    } else {
      const mVal = row.main || '';
      const mLo = META.main_range[0], mHi = META.main_range[1];
      const mNums = _parseNums(mVal, mLo, mHi);
      h += `<td><input class="sim-input" value="${mVal}" placeholder="如: 01 05 12 23 30" oninput="_onSimInput(${idx},'main',this.value);renderSimPanel()"><div class="sim-balls">${_ballHTML(mNums, 'ball-' + LT + '-main')}</div></td>`;

      if (META.sub_cols && META.sub_cols.length) {
        const sVal = row.sub || '';
        const sLo = META.sub_range[0], sHi = META.sub_range[1];
        const sNums = _parseNums(sVal, sLo, sHi);
        h += `<td><input class="sim-input" value="${sVal}" placeholder="如: 03 08" oninput="_onSimInput(${idx},'sub',this.value);renderSimPanel()"><div class="sim-balls">${_ballHTML(sNums, 'ball-' + LT + '-sub')}</div></td>`;
      }
    }

    h += `<td>${simRows.length > 1 ? `<button class="btn btn-sm btn-outline-danger" onclick="removeSimRow(${idx})">×</button>` : ''}</td>`;
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  c.innerHTML = h;
}

function addSimRow() {
  simRows.push({ name: '模拟选行' + (simRows.length + 1), main: '', sub: '', pos: {} });
  renderSimPanel();
}

function removeSimRow(idx) {
  if (simRows.length <= 1) return;
  simRows.splice(idx, 1);
  renderSimPanel();
}

function clearAllSimRows() {
  simRows = [{ name: '模拟选行1', main: '', sub: '', pos: {} }];
  renderSimPanel();
}

function refreshTable() {
  if (!currentTrendData) return;
  document.getElementById('trend-table-container').innerHTML = buildTrendHTML(currentTrendData);
  renderSimPanel();
}

// ═══════════════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════════════
function pad(n) { return String(n).padStart(2, '0'); }
function rangeArr(lo, hi) { const a = []; for (let i = lo; i <= hi; i++) a.push(i); return a; }

function omissionClass(om) {
  if (om === 0) return '';
  if (om <= 5) return 'om-1';
  if (om <= 10) return 'om-2';
  if (om <= 20) return 'om-3';
  return 'om-4';
}
