/**
 * 彩票 Dashboard SPA — 路由、导航、数据加载
 */

const App = {
  // 缓存已加载的彩种数据
  dataCache: {},

  // 当前激活的彩种类型
  currentType: null,

  // 当前选中的图表模式
  currentChartMode: 'comprehensive',

  /** 初始化 */
  async init() {
    this.bindNav();
    this.bindHashChange();

    // 优先从内嵌数据加载（支持 file://），fallback 到 fetch（HTTP 服务器模式）
    if (window.__LOTTERY_DATA__) {
      this.summary = window.__LOTTERY_DATA__.summary;
      this.dataCache = window.__LOTTERY_DATA__.detail || {};
      console.log('✅ 使用内嵌数据（offline 模式）');
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

  /** 绑定导航点击 */
  bindNav() {
    document.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const hash = link.getAttribute('href');
        location.hash = hash;
      });
    });

    // 移动端汉堡菜单
    const toggle = document.getElementById('nav-toggle');
    const nav = document.getElementById('nav-links');
    if (toggle && nav) {
      toggle.addEventListener('click', () => {
        nav.classList.toggle('open');
      });
    }
  },

  /** 监听 hash 变化 */
  bindHashChange() {
    window.addEventListener('hashchange', () => this.route());
  },

  /** 路由分发 */
  async route() {
    const hash = location.hash.slice(1) || '/home';
    const parts = hash.split('/');
    const view = parts[1] || 'home';
    const sub = parts[2] || null;

    // 高亮导航
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    const activeLink = document.querySelector(`.nav-link[href="#/${view}"]`);
    if (activeLink) activeLink.classList.add('active');

    // 隐藏所有视图
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

  /** 渲染主页 */
  renderHome() {
    document.getElementById('view-home').classList.add('active');
    document.title = '彩票数据分析面板';

    const cards = document.getElementById('home-cards');
    if (!cards || !this.summary) return;

    const typeOrder = ['ssq', 'dlt', 'kl8', 'pl5', 'qxc'];

    cards.innerHTML = typeOrder.map(t => {
      const info = this.summary.types[t];
      if (!info) return '';
      const color = Charts.colors[t].main;
      const ld = info.latestDraw;
      const balls = ld.main.map(n => `<span class="ball-sm" style="background:${color}">${Utils.fmtNum(n)}</span>`).join(' ');
      const subBalls = ld.sub && ld.sub.length
        ? ld.sub.map(n => `<span class="ball-sm ball-sm-sub">${Utils.fmtNum(n)}</span>`).join(' ')
        : '';

      return `
        <a href="#/${t}" class="home-card" style="--card-accent:${color}">
          <div class="home-card-header">
            <span class="home-card-icon">${this.getIcon(t)}</span>
            <span class="home-card-name">${info.name}</span>
            <span class="home-card-badge" style="background:${color}20;color:${color}">${info.totalDraws}期</span>
          </div>
          <div class="home-card-period">最新 ${info.latestPeriod}</div>
          <div class="home-card-balls">${balls}${subBalls ? ' <span class="ball-plus">+</span> ' + subBalls : ''}</div>
          <div class="home-card-range">${info.periodRange[0]} ~ ${info.periodRange[1]}</div>
        </a>
      `;
    }).join('');

    // 更新页脚时间
    const timeEl = document.getElementById('update-time');
    if (timeEl && this.summary.generatedAt) {
      timeEl.textContent = this.summary.generatedAt.slice(0, 19).replace('T', ' ');
    }
  },

  /** 渲染彩种详情页 */
  async renderDetail(type, chartMode) {
    document.getElementById('view-detail').classList.add('active');
    document.title = `${LOTTERY_META[type].name}走势图 · 彩票面板`;
    this.currentType = type;

    if (chartMode) this.currentChartMode = chartMode;

    // 加载数据
    const data = await this.loadData(type);
    if (!data) return;

    // 渲染
    if (typeof Renderers.renderDetail === 'function') {
      Renderers.renderDetail(type, data, this.currentChartMode);
    }
  },

  /** 按需加载 JSON 数据（优先从内嵌缓存） */
  async loadData(type) {
    if (this.dataCache[type]) return this.dataCache[type];
    // fallback: HTTP 服务器模式下 fetch
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

  /** 切换图表模式（renderers 调用） */
  switchChartMode(type, mode) {
    this.currentChartMode = mode;
    location.replace(`#/${type}/${mode}`);
  },

  /** 图标映射 */
  getIcon(type) {
    const map = { ssq: '🔴', dlt: '🟠', kl8: '🟣', pl5: '🔵', qxc: '🟢' };
    return map[type] || '🎱';
  },
};

/** 彩种元数据（避免重复 fetch） */
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

// DOM ready 后启动
document.addEventListener('DOMContentLoaded', () => App.init());
