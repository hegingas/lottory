#!/usr/bin/env python3
"""全量技术指标回测 —— 五彩种 × 15 期滚动窗口 × 全部分组命中率对照随机基线。

指标清单:
  号码级(预测下期开出率,基线 = 号码随机开出率):
    近15期频率 / 当前遗漏 / 遗漏比(当前/历史最大) / 历史最大遗漏 / 平均遗漏 /
    上期重号 / 上期邻号 / 奇偶 / 大小 / 质合 / 012路 / 区间
  期级(上期形态 → 下期形态的自相关,基线 = 无条件类别频率):
    和值高 / 跨度高 / 最频奇偶形态 / 最频大小形态 / 有连号 / 有重号

方法:训练 100 期起步,测试期逐期用开奖前 15 期窗口计算指标分组,
统计各组号码在下期的实际开出率,对照随机基线做正态近似 z 检验。

用法:
  python scripts/backtest_indicators.py            # auto(GPU→NumPy)
  python scripts/backtest_indicators.py --backend gpu
  python scripts/backtest_indicators.py --type SSQ
"""

import argparse
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vec_utils import load_backend, build_counts, window_freq, gaps_vec, to_host, fmt_backend

TRAIN = 100   # 训练期数
WIN = 15      # 滚动窗口期数

# ═══════════════════════════════ 彩种配置 ═══════════════════════════════
CFG = {
    "SSQ": {
        "csv": "data/processed/ssq_draws.csv",
        "main": (1, 33), "main_pick": 6, "main_cols": [f"red_{i}" for i in range(1, 7)],
        "sub": (1, 16), "sub_pick": 1, "sub_cols": ["blue"],
        "size_split": 17, "primes": {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31},
        "pos": False,
    },
    "DLT": {
        "csv": "data/processed/dlt_draws.csv",
        "main": (1, 35), "main_pick": 5, "main_cols": [f"front_{i}" for i in range(1, 6)],
        "sub": (1, 12), "sub_pick": 2, "sub_cols": [f"back_{i}" for i in range(1, 3)],
        "size_split": 18, "primes": {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31},
        "pos": False,
    },
    "KL8": {
        "csv": "data/processed/kl8_draws.csv",
        "main": (1, 80), "main_pick": 10, "main_cols": [f"n{i:02d}" for i in range(1, 21)],
        "sub": None, "sub_pick": 0, "sub_cols": [],
        "size_split": 41, "draw_pick": 20,
        "primes": {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79},
        "pos": False,
    },
    "PL5": {
        "csv": "data/processed/pl5_draws.csv",
        "main": (0, 9), "main_pick": 5, "main_cols": [f"d{i}" for i in range(1, 6)],
        "sub": None, "sub_pick": 0, "sub_cols": [],
        "size_split": 5, "primes": {2, 3, 5, 7},
        "pos": True,
    },
    "QXC": {
        "csv": "data/processed/qxc_draws.csv",
        "main": (0, 9), "main_pick": 6, "main_cols": [f"d{i}" for i in range(1, 7)],
        "sub": (0, 14), "sub_pick": 1, "sub_cols": ["special"],
        "size_split": 5, "primes": {2, 3, 5, 7},
        "pos": True,
    },
}

def load(cfg, xp):
    mains, subs = [], []
    with open(cfg["csv"], encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mains.append([int(row[c]) for c in cfg["main_cols"]])
            if cfg["sub"]:
                subs.append([int(row[c]) for c in cfg["sub_cols"]])
    return xp.asarray(mains), xp.asarray(subs) if subs else None

# ═══════════════════════════════ 统计工具 ═══════════════════════════════

def z_one_prop(hit, n, p0):
    """命中率 vs 随机基线的双边检验。"""
    if n == 0 or p0 <= 0 or p0 >= 1:
        return None
    rate = hit / n
    z = (rate - p0) / math.sqrt(p0 * (1 - p0) / n)
    return rate, z, math.erfc(abs(z) / math.sqrt(2))

def z_two_prop(h1, n1, h2, n2):
    if n1 == 0 or n2 == 0:
        return None
    p1, p2 = h1 / n1, h2 / n2
    p = (h1 + h2) / (n1 + n2)
    if p <= 0 or p >= 1:
        return None
    z = (p1 - p2) / math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return z, math.erfc(abs(z) / math.sqrt(2))

def sig(p):
    if p is None: return "—"
    if p < 0.001: return "***"
    if p < 0.01: return "**"
    if p < 0.05: return "*"
    return "ns"

def cut_groups(mat, edges, labels):
    """把指标矩阵切分成组:[T, M] → [T, M] 组号;返回 (groups, labels)。"""
    import numpy as np
    groups = np.full(mat.shape, -1, dtype=np.int64)
    for i, (lo, hi) in enumerate(edges):
        if hi is None:
            groups[(mat >= lo)] = i
        else:
            groups[(mat >= lo) & (mat < hi)] = i
    return groups, labels

def aggregate(groups, appear_next, start, end, n_groups):
    """逐组累计:候选数 / 下期命中数。返回 (n_cand, n_hit) 数组。"""
    import numpy as np
    g = groups[start:end]
    a = appear_next.get() if hasattr(appear_next, "get") else np.asarray(appear_next)
    a = a[start:end]
    valid = g >= 0
    n_cand = np.bincount(g[valid], minlength=n_groups)
    n_hit = np.bincount(g[valid & a], minlength=n_groups)
    return n_cand, n_hit

# ═══════════════════════════════ 号码级指标构建 ═══════════════════════════════

def build_number_indicators(cfg, appear, cg, mg, f15):
    """返回 [(指标名, 组标签, groups[T,M]), ...](host numpy)。"""
    import numpy as np
    T, M = appear.shape
    lo = cfg["main"][0]
    nums = np.arange(lo, lo + M)

    # 平均遗漏(前缀、无未来泄漏):见下方 cg/app 定义之后计算

    # 静态属性
    is_odd = (nums % 2 == 1)
    is_big = nums >= cfg["size_split"]
    is_prime = np.array([n in cfg["primes"] for n in nums])
    mod3 = nums % 3
    seg = (nums - lo) // (M // 3)
    seg = np.clip(seg, 0, 2)

    cg_np = to_host(cg)
    mg_np = to_host(mg)
    f15_np = to_host(f15)
    app_np = to_host(appear)
    ratio = np.divide(cg_np, mg_np, out=np.zeros_like(cg_np, dtype=float),
                      where=mg_np > 0)
    # 平均遗漏(前缀、无泄漏):截至期 t,间隔均值 = 最近出现位置 / 出现次数
    cnt = np.cumsum(app_np, axis=0)
    cnt_excl = np.vstack([np.zeros(M), cnt[:-1]])   # 截至 t 之前
    t_idx = np.arange(T)[:, None]
    last_excl = t_idx - cg_np                       # cg = t - last_excl(未出现时 cg=t → last=0)
    avg_mat = np.where(cnt_excl > 0,
                       last_excl / np.maximum(cnt_excl, 1),
                       t_idx.astype(float))

    # 上期重号 / 邻号(期 t 的"上期" = 期 t-1 开出;首行无上期 → -1)
    prev = np.vstack([np.zeros(M, dtype=bool), app_np[:-1]])
    adj = np.zeros_like(prev)
    for n in range(M):
        v = nums[n]
        if prev[:, n].any():
            adj[:, n] = prev[:, max(0, n - 1)] | prev[:, min(M - 1, n + 1)]
    adj = adj & ~prev  # 邻号不含重号本身

    inds = []
    inds.append(("近15期频率", ["0次", "1次", "2次", "3次", "4+次"],
                 cut_groups(f15_np, [(0, 1), (1, 2), (2, 3), (3, 4), (4, None)],
                            None)[0]))
    inds.append(("当前遗漏", ["0-2期", "3-6期", "7-12期", "13-20期", "21+期"],
                 cut_groups(cg_np, [(0, 3), (3, 7), (7, 13), (13, 21), (21, None)],
                            None)[0]))
    inds.append(("遗漏比(当前/最大)", ["<0.3", "0.3-0.6", "0.6-0.8", "≥0.8"],
                 cut_groups(ratio, [(0, 0.3), (0.3, 0.6), (0.6, 0.8), (0.8, None)],
                            None)[0]))
    inds.append(("历史最大遗漏", ["≤10", "11-20", "21+"],
                 cut_groups(mg_np, [(0, 11), (11, 21), (21, None)], None)[0]))
    inds.append(("平均遗漏", ["≤5", "6-10", "11+"],
                 cut_groups(avg_mat, [(0, 6), (6, 11), (11, None)], None)[0]))
    inds.append(("上期重号", ["否", "是"],
                 cut_groups(prev.astype(np.int64), [(0, 1), (1, None)], None)[0]))
    inds.append(("上期邻号", ["否", "是"],
                 cut_groups(adj.astype(np.int64), [(0, 1), (1, None)], None)[0]))
    inds.append(("奇偶", ["偶", "奇"],
                 np.broadcast_to(is_odd.astype(np.int64), (T, M)), ))
    inds.append(("大小", ["小", "大"],
                 np.broadcast_to(is_big.astype(np.int64), (T, M)), ))
    inds.append(("质合", ["合", "质"],
                 np.broadcast_to(is_prime.astype(np.int64), (T, M)), ))
    inds.append(("012路", ["0路", "1路", "2路"],
                 np.broadcast_to(mod3, (T, M)), ))
    inds.append(("区间", ["区1", "区2", "区3"],
                 np.broadcast_to(seg, (T, M)), ))
    return inds

# ═══════════════════════════════ 期级指标构建 ═══════════════════════════════

def build_period_indicators(cfg, mains_np):
    """返回 [(指标名, 类别数, seq[T] int)],seq 为 0/1 二分类形态序列。"""
    import numpy as np
    T, pick = mains_np.shape
    lo = cfg["main"][0]
    M = cfg["main"][1] - lo + 1

    sums = mains_np.sum(axis=1).astype(float)
    span = (mains_np.max(axis=1) - mains_np.min(axis=1)).astype(float)
    # 15 期滚动均值(不含当期)
    def roll_mean(x, w=WIN):
        c = np.concatenate([np.zeros(1), np.cumsum(x)[:-1]])
        out = np.empty_like(x)
        for t in range(T):
            s = max(0, t - w)
            out[t] = (c[t] - (c[s] if s > 0 else 0)) / (t - s)
        return out
    sum_hi = (sums > roll_mean(sums)).astype(int)
    span_hi = (span > roll_mean(span)).astype(int)

    n_odd = ((mains_np % 2 == 1).sum(axis=1))
    # 最频奇偶形态 = 中位数形态(组合型);按位型用"奇数多"
    odd_mode = pick // 2
    odd_ratio = (n_odd > odd_mode).astype(int)

    n_big = (mains_np >= cfg["size_split"]).sum(axis=1)
    size_ratio = (n_big > pick // 2).astype(int)

    rows_sorted = np.sort(mains_np, axis=1)
    conn = (np.diff(rows_sorted, axis=1) == 1).any(axis=1).astype(int)
    rep = np.zeros(T, dtype=int)
    if T > 1:
        rep[1:] = np.array([len(set(rows_sorted[i]) & set(rows_sorted[i - 1])) > 0
                            for i in range(1, T)]).astype(int)

    return [("和值高", sum_hi), ("跨度高", span_hi), ("奇数多", odd_ratio),
            ("大号多", size_ratio), ("有连号", conn), ("有重号", rep)]

# ═══════════════════════════════ 主回测 ═══════════════════════════════

def run(cfg, xp):
    mains, subs = load(cfg, xp)
    total = mains.shape[0]
    if total <= TRAIN + WIN + 10:
        return
    M = cfg["main"][1] - cfg["main"][0] + 1
    test_start = TRAIN
    test_end = total - 1  # 需要下期开奖作标签

    counts = build_counts(xp, mains, cfg["main"][0], M)
    appear = counts > 0
    cg, mg = gaps_vec(xp, appear)
    f15 = window_freq(xp, counts, WIN)
    appear_next = appear[1:]
    cg_t = cg[:-1]; mg_t = mg[:-1]; f15_t = f15[:-1]

    # 随机基线:号码单期开出概率
    if cfg["pos"]:
        p0 = 1 - (1 - 1 / 10) ** cfg["main_pick"]
    else:
        p0 = cfg.get("draw_pick", cfg["main_pick"]) / M

    name = cfg["csv"].split("/")[-1].split("_")[0].upper()
    n_test = test_end - test_start
    print(f"\n{'═' * 74}")
    print(f"  {name} 全量指标回测(窗口 {WIN} 期,测试 {n_test} 期,基线 号码开出率 {p0:.1%})")
    print(f"{'═' * 74}")

    # ── 号码级指标 ──
    inds = build_number_indicators(cfg, appear, cg, mg, f15)
    print(f"\n📊 号码级指标(组内号码下期开出率 vs 随机)")
    strong = []  # (指标名, 组名, groups, 组号) p<1e-4 的强显著项
    for iname, labels, groups in inds:
        ng = len(labels)
        n_cand, n_hit = aggregate(groups[:-1], appear_next, test_start, test_end, ng)
        rows = []
        for i, lab in enumerate(labels):
            vt = z_one_prop(int(n_hit[i]), int(n_cand[i]), p0)
            rows.append((lab, int(n_cand[i]), int(n_hit[i]), vt))
            if vt and vt[2] < 1e-4:
                strong.append((iname, lab, groups, i))
        # 最高 vs 最低组差异
        good = [(lab, c, h, vt) for lab, c, h, vt in rows if c > 0 and vt]
        spread = None
        if len(good) >= 2:
            hi = max(good, key=lambda r: r[3][0]); lo = min(good, key=lambda r: r[3][0])
            spread = z_two_prop(hi[2], hi[1], lo[2], lo[1])
        print(f"\n  ▸ {iname}")
        for lab, c, h, vt in rows:
            if vt:
                rel = (vt[0] - p0) / p0 * 100
                tag = "🔥高" if rel > 2 and vt[2] < 0.05 else ("❄️低" if rel < -2 and vt[2] < 0.05 else "ns")
                print(f"    {lab:<10} 候选 {c:>8,} 命中 {h:>7,}  {vt[0]*100:>6.2f}%  vs {p0*100:>5.1f}%({rel:>+5.0f}%)  z={vt[1]:>+6.2f} p={vt[2]:<6.2g} {tag}")
            else:
                print(f"    {lab:<10} 样本为空")
        if spread:
            print(f"    ── 最高组-最低组: 差 {spread[0]:+.2f}σ p={spread[1]:.2g} {sig(spread[1])}")

    # ── 强显著项时间稳定性:测试期前半/后半分开重验 ──
    if strong:
        half = (test_end - test_start) // 2
        print(f"\n▸ 强显著项(p<1e-4)时间稳定性(测试期前半/后半):")
        for iname, lab, groups, gi in strong:
            ng = int(groups.max()) + 1
            parts = []
            for pname, s, e in [("前半", test_start, test_start + half),
                                ("后半", test_start + half, test_end)]:
                nc, nh = aggregate(groups[:-1], appear_next, s, e, ng)
                vt = z_one_prop(int(nh[gi]), int(nc[gi]), p0)
                parts.append((pname, int(nc[gi]), int(nh[gi]), vt))
            ok = all(pt[3] and pt[3][2] < 0.05 for pt in parts)
            desc = "两半均显著 ✅" if ok else "仅半段/均不显著 ⚠️"
            for pname, c, h, vt in parts:
                rel = (vt[0] - p0) / p0 * 100 if vt else 0
                print(f"    {iname}/{lab:<8} {pname}: 候选 {c:>6,} 命中 {h:>5,} "
                      f"{vt[0]*100:>6.2f}% ({rel:>+4.0f}%) p={vt[2]:.2g}" if vt else f"    {iname}/{lab} {pname}: 空")
            print(f"    → {desc}")

    # ── 号码频率均匀性(测试期,卡方) ──
    freq_h = to_host(counts[test_start:test_end + 1]).sum(axis=0)
    expect = freq_h.sum() / M
    chi2 = float(((freq_h - expect) ** 2 / expect).sum())
    df = M - 1
    z_c = (chi2 - df) / math.sqrt(2 * df)
    p_c = math.erfc(abs(z_c) / math.sqrt(2))
    print(f"\n▸ 号码频率均匀性(测试期 {n_test} 期): χ²={chi2:.1f} df={df} z={z_c:+.1f} p={p_c:.2g}"
          f" {'⚠️ 频率显著不均匀' if p_c < 0.01 else '均匀 ✓'}")

    # ── 期级指标 ──
    mains_np = to_host(mains)
    print(f"\n📈 期级指标(上期形态 → 下期形态自相关,基线 = 无条件频率)")
    for pname, seq in build_period_indicators(cfg, mains_np):
        s = seq[test_start:test_end]; s_next = seq[test_start + 1:test_end + 1]
        n11 = int(((s == 1) & (s_next == 1)).sum())
        n10 = int(((s == 1) & (s_next == 0)).sum())
        n01 = int(((s == 0) & (s_next == 1)).sum())
        n00 = int(((s == 0) & (s_next == 0)).sum())
        base = (n11 + n01) / (n11 + n10 + n01 + n00)
        vt = z_two_prop(n11, n11 + n10, n01, n01 + n00)
        if vt:
            rel = (vt[0] - base) / base * 100
            tag = "🔥正自相关" if rel > 5 and vt[1] < 0.05 else ("❄️负自相关" if rel < -5 and vt[1] < 0.05 else "ns")
            print(f"  ▸ {pname:<8} P(下期1|上期1)={n11/(n11+n10)*100:5.1f}% vs P(1|上期0)={n01/(n01+n00)*100:5.1f}%"
                  f" (无条件 {base*100:.1f}%) z={vt[0]:>+6.2f} p={vt[1]:.2g} {tag}")
        else:
            print(f"  ▸ {pname:<8} 样本为空")

    print(f"  说明: 指标仅统计关联性,彩票为独立随机事件,历史指标无预测力;仅供参考娱乐。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="全量技术指标回测(15期窗口,GPU 默认)")
    ap.add_argument("--backend", choices=["auto", "gpu", "numpy"], default="auto",
                    help="计算后端(默认 auto:GPU→NumPy)")
    ap.add_argument("--type", default="ALL", help="彩种: SSQ/DLT/KL8/PL5/QXC 或 ALL")
    args = ap.parse_args()
    xp, backend = load_backend(args.backend)
    print(f"回测后端: {fmt_backend(xp, backend)}")
    keys = [k for k in CFG if args.type.upper() == "ALL" or k == args.type.upper()]
    for key in keys:
        try:
            run(CFG[key], xp)
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"\n❌ {key}: {e}")
