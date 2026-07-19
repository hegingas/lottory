/**
 * 彩票 Dashboard 工具函数库
 * 统计计算、格式化、DOM 工具
 */

const Utils = {
  // ─── 数组工具 ───
  sum(arr) {
    return arr.reduce((a, b) => a + b, 0);
  },

  avg(arr) {
    return arr.length ? this.sum(arr) / arr.length : 0;
  },

  max(arr) {
    return Math.max(...arr);
  },

  min(arr) {
    return Math.min(...arr);
  },

  // ─── 彩票专用 ───
  /** 计算一组号码的 AC 值 */
  acValue(nums) {
    const diffs = new Set();
    for (let i = 0; i < nums.length; i++) {
      for (let j = i + 1; j < nums.length; j++) {
        diffs.add(Math.abs(nums[i] - nums[j]));
      }
    }
    return diffs.size - (nums.length - 1);
  },

  /** 奇偶比 */
  oddEvenRatio(nums) {
    const odd = nums.filter(n => n % 2 === 1).length;
    return [odd, nums.length - odd];
  },

  /** 大小比 (mid = (min+max)//2) */
  bigSmallRatio(nums, mid) {
    const big = nums.filter(n => n > mid).length;
    return [big, nums.length - big];
  },

  /** 质数判断 */
  isPrime(n) {
    if (n < 2) return false;
    for (let i = 2; i <= Math.sqrt(n); i++) {
      if (n % i === 0) return false;
    }
    return true;
  },

  /** 连号数 */
  consecutiveCount(nums) {
    let count = 0;
    for (let i = 1; i < nums.length; i++) {
      if (nums[i] - nums[i - 1] === 1) count++;
    }
    return count;
  },

  /** 重号数 */
  repeatCount(curr, prev) {
    if (!prev || !prev.length) return 0;
    const set = new Set(prev);
    return curr.filter(n => set.has(n)).length;
  },

  /** 生成号码 CSS class */
  ballClass(n, type, colorKey) {
    // 双色球: 红球 1-33, 蓝球 1-16
    // 大乐透: 前区 1-35, 后区 1-12
    return `ball ${colorKey}`;
  },

  // ─── 格式化 ───
  fmtNum(n, pad = 2) {
    return String(n).padStart(pad, '0');
  },

  /** 彩种名简称 */
  shortName(type) {
    const map = { ssq: 'SSQ', dlt: 'DLT', kl8: 'KL8', pl5: 'PL5', qxc: 'QXC' };
    return map[type] || type.toUpperCase();
  },

  /** 号码数组格式化显示 */
  fmtBalls(main, sub, sep = ' ') {
    const m = main.map(n => this.fmtNum(n)).join(sep);
    if (!sub || !sub.length) return m;
    const s = sub.map(n => this.fmtNum(n)).join(sep);
    return `${m} + ${s}`;
  },

  // ─── DOM 工具 ───
  $(id) {
    return document.getElementById(id);
  },

  $$(sel, parent) {
    return (parent || document).querySelectorAll(sel);
  },

  create(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'className') el.className = v;
      else if (k === 'innerHTML') el.innerHTML = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
      else el.setAttribute(k, v);
    });
    children.forEach(c => {
      if (typeof c === 'string') el.appendChild(document.createTextNode(c));
      else if (c) el.appendChild(c);
    });
    return el;
  },

  /** 防抖 */
  debounce(fn, ms = 300) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  },
};
