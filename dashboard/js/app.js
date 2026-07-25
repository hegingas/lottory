/**
 * 彩票 Dashboard SPA — 霓虹主题版
 * 路由、导航、数据加载
 */

const App = {
  dataCache: {},
  currentType: null,
  currentChartMode: 'comprehensive',

  async init() {
    this.bindNav();
    this.bindHashChange();

    if (window.__LOTTERY_DATA__) {
      this.summary = window.__LOTTERY_DATA__.summary;
      this.dataCache = window.__LOTTERY_DATA__.detail || {};
    } else {
      try {
        const resp = await fetch('data/summary.json');
        this.summary = await resp.json();
      } catch (e) {
        console.error('加载数据失败，请运行 python dashboard/preprocess.py', e);
      }
    }
    this.route();
  },

  bindNav() {
    document.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        location.hash = link.getAttribute('href');
        // 移动端关闭菜单
        document.getElementById('nav-links')?.classList.remove('open');
      });
    });

    const toggle = document.getElementById('nav-toggle');
    const nav = document.getElementById('nav-links');
    if (toggle && nav) {
      toggle.addEventListener('click', () => nav.classList.toggle('open'));
    }
  },

  bindHashChange() { window.addEventListener('hashchange', () => this.route()); },

  async route() {
    const hash = location.hash.slice(1) || '/home';
    const parts = hash.split('/');
    const view = parts[1] || 'home';
    const sub = parts[2] || null;

    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    const activeLink = document.querySelector(`.nav-link[href="#/${view}"]`);
    if (activeLink) activeLink.classList.add('active');

    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));

    try {
      if (view === 'home') {
        this.renderHome();
      } else if (['ssq', 'dlt', 'kl8', 'pl5', 'qxc'].includes(view)) {
        await this.renderDetail(view, sub);
      } else {
        this.renderHome();
      }
    } catch (e) {
      console.error('路由渲染失败', e);
      document.getElementById('view-error').classList.add('active');
    }
  },

  /** 彩种卡片配色 */
  cardTheme(type) {
    const themes = {
      ssq: { color: '#FF2D55', color2: '#FF6B81', bg: 'rgba(255,45,85,0.12)', glow: 'rgba(255,45,85,0.15)', badgeBg: 'rgba(255,45,85,0.15)' },
      dlt: { color: '#FF9500', color2: '#FFB84D', bg: 'rgba(255,149,0,0.12)',  glow: 'rgba(255,149,0,0.15)',  badgeBg: 'rgba(255,149,0,0.15)' },
      kl8: { color: '#AF52DE', color2: '#D290F2', bg: 'rgba(175,82,222,0.12)', glow: 'rgba(175,82,222,0.15)', badgeBg: 'rgba(175,82,222,0.15)' },
      pl5: { color: '#007AFF', color2: '#66B0FF', bg: 'rgba(0,122,255,0.12)',  glow: 'rgba(0,122,255,0.15)',  badgeBg: 'rgba(0,122,255,0.15)' },
      qxc: { color: '#00D2A0', color2: '#5CE6C6', bg: 'rgba(0,210,160,0.12)', glow: 'rgba(0,210,160,0.15)', badgeBg: 'rgba(0,210,160,0.15)' },
    };
    return themes[type] || themes.ssq;
  },

  renderHome() {
    document.getElementById('view-home').classList.add('active');
    document.title = '彩票数据面板 · 霓虹大厅';

    const cards = document.getElementById('home-cards');
    if (!cards || !this.summary) return;

    const typeOrder = ['ssq', 'dlt', 'kl8', 'pl5', 'qxc'];
    const ballColors = {
      ssq: { main: [255,45,85], glow: 'rgba(255,45,85,0.45)' },
      dlt: { main: [255,149,0], glow: 'rgba(255,149,0,0.45)' },
      kl8: { main: [175,82,222], glow: 'rgba(175,82,222,0.45)' },
      pl5: { main: [0,122,255], glow: 'rgba(0,122,255,0.45)' },
      qxc: { main: [0,210,160], glow: 'rgba(0,210,160,0.45)' },
    };

    cards.innerHTML = typeOrder.map(t => {
      const info = this.summary.types[t];
      if (!info) return '';
      const theme = this.cardTheme(t);
      const bc = ballColors[t];
      const ld = info.latestDraw;

      const mainBalls = ld.main.map(n =>
        `<span class="ball ball-sm" style="--ball-color:rgb(${bc.main.join(',')});--ball-dark:rgb(${Math.round(bc.main[0]*0.4)},${Math.round(bc.main[1]*0.4)},${Math.round(bc.main[2]*0.4)});--ball-glow:${bc.glow}">${String(n).padStart(2,'0')}</span>`
      ).join('');

      const subBalls = ld.sub && ld.sub.length
        ? ' <span class="ball-plus">+</span> ' + ld.sub.map(n => `<span class="ball ball-sm ball-sub">${String(n).padStart(2,'0')}</span>`).join(' ')
        : '';

      return `
        <a href="#/${t}" class="lottery-card" style="--card-color:${theme.color};--card-color2:${theme.color2};--card-bg:${theme.bg};--card-glow:${theme.glow};--card-badge-bg:${theme.badgeBg}">
          <div class="card-header">
            <div class="card-icon" style="background:${theme.bg}">${this.getIcon(t)}</div>
            <span class="card-name">${info.name}</span>
            <span class="card-badge">${info.totalDraws} 期</span>
          </div>
          <div class="card-period">#${info.latestPeriod}</div>
          <div class="card-numbers">${mainBalls}${subBalls}</div>
          <div class="card-footer">
            <span>${info.periodRange[0]} ~ ${info.periodRange[1]}</span>
            <span>→</span>
          </div>
        </a>
      `;
    }).join('');

    const timeEl = document.getElementById('update-time');
    if (timeEl && this.summary.generatedAt) {
      timeEl.textContent = this.summary.generatedAt.slice(0, 19).replace('T', ' ');
    }
  },

  async renderDetail(type, chartMode) {
    document.getElementById('view-detail').classList.add('active');
    document.title = `${LOTTERY_META[type].name}走势图 · 彩票面板`;
    this.currentType = type;
    if (chartMode) this.currentChartMode = chartMode;

    const data = await this.loadData(type);
    if (!data) return;

    if (typeof Renderers.renderDetail === 'function') {
      Renderers.renderDetail(type, data, this.currentChartMode);
    }
  },

  async loadData(type) {
    if (this.dataCache[type]) return this.dataCache[type];
    try {
      const resp = await fetch(`data/${type}.json`);
      const json = await resp.json();
      this.dataCache[type] = json;
      return json;
    } catch (e) {
      console.error(`加载 ${type}.json 失败`, e);
      return null;
    }
  },

  switchChartMode(type, mode) {
    this.currentChartMode = mode;
    location.replace(`#/${type}/${mode}`);
  },

  getIcon(type) {
    const map = { ssq: '🔴', dlt: '🟠', kl8: '🟣', pl5: '🔵', qxc: '🟢' };
    return map[type] || '🎱';
  },
};

const LOTTERY_META = {
  ssq: { name: '双色球', mainRange: [1, 33], mainCount: 6, subRange: [1, 16], subCount: 1,
    chartModes: ['综合图', '奇偶', '大小', '质合', '012路', 'AC值', '连号', '重号', '区间', '遗漏', '频率'],
    zones: [[1, 11], [12, 22], [23, 33]], mid: 16, prime: true, positional: false },
  dlt: { name: '大乐透', mainRange: [1, 35], mainCount: 5, subRange: [1, 12], subCount: 2,
    chartModes: ['综合图', '奇偶', '大小', '质合', '012路', 'AC值', '连号', '重号', '区间', '遗漏', '频率'],
    zones: [[1, 12], [13, 24], [25, 35]], mid: 17, prime: true, positional: false },
  kl8: { name: '快乐八', mainRange: [1, 80], mainCount: 20, subRange: null, subCount: 0,
    chartModes: ['综合图', '奇偶', '大小', '和值', '跨度', '区间', '遗漏', '频率'],
    zones: [[1, 20], [21, 40], [41, 60], [61, 80]], mid: 40, prime: false, positional: false },
  pl5: { name: '排列5', mainRange: [0, 9], mainCount: 5, subRange: null, subCount: 0,
    chartModes: ['综合图', '位频', '和值', '奇偶', '跨度', '遗漏', '频率'],
    zones: null, mid: null, prime: false, positional: true },
  qxc: { name: '七星彩', mainRange: [0, 9], mainCount: 6, subRange: [0, 14], subCount: 1,
    chartModes: ['综合图', '位频', '和值', '奇偶', '跨度', '后区', '遗漏', '频率'],
    zones: null, mid: null, prime: false, positional: true },
};

document.addEventListener('DOMContentLoaded', () => App.init());
