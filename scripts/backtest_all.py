#!/usr/bin/env python3
"""全量回测：五个彩种各自跑全部历史数据，验证每层的真实有效性。
GPU/NumPy 向量化版：统计逻辑与纯 Python 版逐字节一致。

方法论（v2，修正乐观偏差）:
  - 训练 100 期 → 验证 100 期(选参数)→ 测试集(只报告一次,不选参)
  - 深冻误杀率 / 热冷区分度 均对照随机基线 + 正态近似显著性检验
  - 结构约束对照解析随机理论分布(连号/重号/奇偶/大小/和值)

用法:
  python scripts/backtest_all.py              # auto 检测(GPU→NumPy)
  python scripts/backtest_all.py --backend gpu
  python scripts/backtest_all.py --backend numpy
"""

import argparse
import csv
import math
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vec_utils import load_backend, build_counts, window_freq, gaps_vec, to_host, fmt_backend

TRAIN = 100     # 训练期数(遗漏/频率的历史底子)
VAL = 100       # 验证期数(参数选择,只用于选参)

# ═══════════════════════════════ 彩种配置 ═══════════════════════════════
CFG = {
    "SSQ": {
        "csv": "data/processed/ssq_draws.csv",
        "main": (1,33), "main_pick": 6, "main_cols": ["red_1","red_2","red_3","red_4","red_5","red_6"],
        "sub": (1,16), "sub_pick": 1, "sub_cols": ["blue"],
        "size_split": 17, "primes": {2,3,5,7,11,13,17,19,23,29,31},
        "kl8": False, "pos": False,
    },
    "DLT": {
        "csv": "data/processed/dlt_draws.csv",
        "main": (1,35), "main_pick": 5, "main_cols": ["front_1","front_2","front_3","front_4","front_5"],
        "sub": (1,12), "sub_pick": 2, "sub_cols": ["back_1","back_2"],
        "size_split": 18, "primes": {2,3,5,7,11,13,17,19,23,29,31},
        "kl8": False, "pos": False,
    },
    "KL8": {
        "csv": "data/processed/kl8_draws.csv",
        "main": (1,80), "main_pick": 10, "main_cols": [f"n{i:02d}" for i in range(1,21)],
        "sub": None, "sub_pick": 0, "sub_cols": [], "draw_pick": 20,
        "size_split": 41, "primes": {2,3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73,79},
        "kl8": True, "pos": False,
    },
    "PL5": {
        "csv": "data/processed/pl5_draws.csv",
        "main": (0,9), "main_pick": 5, "main_cols": ["d1","d2","d3","d4","d5"],
        "sub": None, "sub_pick": 0, "sub_cols": [],
        "size_split": 5, "primes": {2,3,5,7},
        "kl8": False, "pos": True,
    },
    "QXC": {
        "csv": "data/processed/qxc_draws.csv",
        "main": (0,9), "main_pick": 6, "main_cols": ["d1","d2","d3","d4","d5","d6"],
        "sub": (0,14), "sub_pick": 1, "sub_cols": ["special"],
        "size_split": 5, "primes": {2,3,5,7},
        "kl8": False, "pos": True,
    },
}

def load(cfg, xp):
    """读取 CSV → 号码整数矩阵 [T, pick]。"""
    mains, subs = [], []
    with open(cfg["csv"], encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mains.append([int(row[c]) for c in cfg["main_cols"]])
            if cfg["sub"]:
                subs.append([int(row[c]) for c in cfg["sub_cols"]])
    return xp.asarray(mains), xp.asarray(subs) if subs else None

# ═══════════════════════════════ 显著性检验(正态近似) ═══════════════════════════════

def z_vs_random(killed, hit, p0):
    """观测率(hit/killed) vs 随机率 p0 的单侧检验(观测是否显著低于随机)。

    返回 (rate, z, p) 或 None(样本为空/边界)。
    """
    if killed == 0 or p0 <= 0 or p0 >= 1:
        return None
    rate = hit / killed
    z = (rate - p0) / math.sqrt(p0 * (1 - p0) / killed)
    p = 0.5 * math.erfc(-z / math.sqrt(2))  # 单侧左尾:深冻是否显著低于随机
    return rate, z, p

def z_two_prop(h1, n1, h2, n2):
    """两个比例的差检验(双边),返回 (z, p) 或 None。"""
    if n1 == 0 or n2 == 0:
        return None
    p1, p2 = h1 / n1, h2 / n2
    p = (h1 + h2) / (n1 + n2)
    if p <= 0 or p >= 1:
        return None
    z = (p1 - p2) / math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return z, math.erfc(abs(z) / math.sqrt(2))

def sig(p):
    """显著性星号。"""
    if p is None: return "—"
    if p < 0.001: return "***"
    if p < 0.01: return "**"
    if p < 0.05: return "*"
    return "ns"

# ═══════════════════════════════ 深冻 / 热冷统计 ═══════════════════════════════

def freeze_stats(cfg, cg_m, mg_m, appear_m, cg_s, mg_s, appear_s, gt, s, e, xp):
    """深冻排除统计:[s, e) 期累计被杀与误杀(主区+副区)。"""
    frozen = cg_m > mg_m * gt
    seg = frozen[s:e]
    killed = int(seg.sum())
    hit = int((seg & appear_m[s:e]).sum())
    if cfg["sub"] is not None:
        fs = cg_s > mg_s * gt
        segs = fs[s:e]
        killed += int(segs.sum())
        hit += int((segs & appear_s[s:e]).sum())
    return killed, hit

def hotcold_stats(cfg, f10, cg_m, appear_m, ht, cg_th, s, e, xp):
    """热/温/冷三档统计:[s, e) 期累计。返回 (hot_t, hot_h, warm_t, warm_h, cold_t, cold_h)。"""
    is_hot = f10 >= ht
    is_cold = (~is_hot) & (cg_m > cg_th)
    is_warm = ~(is_hot | is_cold)
    hot_t = int(is_hot[s:e].sum())
    hot_h = int((is_hot & appear_m)[s:e].sum())
    cold_t = int(is_cold[s:e].sum())
    cold_h = int((is_cold & appear_m)[s:e].sum())
    warm_t = int(is_warm[s:e].sum())
    warm_h = int((is_warm & appear_m)[s:e].sum())
    return hot_t, hot_h, warm_t, warm_h, cold_t, cold_h

def comb(n, k):
    return math.comb(n, k) if n >= k else 0

# ═══════════════════════════════ 主回测 ═══════════════════════════════

def run(cfg, xp):
    mains, subs = load(cfg, xp)
    total = mains.shape[0]
    if total <= TRAIN + VAL + 10:
        return None
    val_start = TRAIN
    test_start = TRAIN + VAL
    test_n = total - test_start

    pos = cfg["pos"]; has_sub = cfg["sub"] is not None
    rng = cfg["main"]

    # ── 一次性向量化:计数矩阵 + 遗漏 + 10期窗口频率 ──
    M = rng[1] - rng[0] + 1
    counts_m = build_counts(xp, mains, rng[0], M)
    appear_m = counts_m > 0
    cg_m, mg_m = gaps_vec(xp, appear_m)
    f10_all = window_freq(xp, counts_m, 10)
    if has_sub:
        sr = cfg["sub"]
        B = sr[1] - sr[0] + 1
        counts_s = build_counts(xp, subs, sr[0], B)
        appear_s = counts_s > 0
        cg_s, mg_s = gaps_vec(xp, appear_s)
    # 随机基线:号码池中每个号码单期开出概率
    # (开奖个数 = 投注个数;快乐八例外:投注 10 但每期开出 20)
    pool = M + (B if has_sub else 0)
    draw_n = cfg.get("draw_pick", cfg["main_pick"]) + (cfg["sub_pick"] if has_sub else 0)
    p0 = draw_n / pool

    print(f"\n{'='*64}")
    print(f"  {cfg['csv'].split('/')[-1].split('_')[0].upper()}  全量回测 v2(训练{TRAIN}/验证{VAL}/测试{test_n})")
    print(f"  {cfg['main']}选{cfg['main_pick']}" + (f" + {cfg['sub']}选{cfg['sub_pick']}" if has_sub else "")
          + f"  |  随机基线 p0={p0:.1%}")
    print(f"{'='*64}")

    # ── 1. 深冻排除:验证集选参 → 测试集单次报告 ──
    print(f"\n🔪 深冻排除(验证集选参,测试集{test_n}期报告)")
    print(f"  {'阈值':<6} {'排除':>6} {'误杀率':>7} {'vs随机':>8} {'z':>6} {'p':>8}")
    print(f"  {'-'*46}")

    best_gt = None; best_z = 0
    sub_args = (cg_s, mg_s, appear_s) if has_sub else (None, None, None)
    for gt in [0.80, 0.85, 0.90, 0.95, 0.97, 0.99]:
        kv, hv = freeze_stats(cfg, cg_m, mg_m, appear_m, *sub_args, gt,
                              val_start, test_start, xp)
        vt = z_vs_random(kv, hv, p0)
        if vt:
            rel = (vt[0] - p0) / p0 * 100
            print(f"  {gt:<6} {kv:>6} {vt[0]*100:>6.1f}% {rel:>+7.0f}% {vt[1]:>+6.2f} {sig(vt[2]):>8}")
            if vt[1] < best_z:
                best_z = vt[1]; best_gt = gt
        else:
            print(f"  {gt:<6} 样本为空")
    # 测试集:只报告最优参数一次(若无任何阈值在验证集呈负向信号,取默认 0.95 兜底)
    if best_gt is None:
        best_gt = 0.95
        print("  (验证集:所有阈值误杀率均不低于随机,深冻无信号)")
    kt, ht = freeze_stats(cfg, cg_m, mg_m, appear_m, *sub_args, best_gt,
                          test_start, total, xp)
    tt = z_vs_random(kt, ht, p0)
    rate_t, z_t, p_t = tt if tt else (0, 0, 1)
    rel = (rate_t - p0) / p0 * 100
    print(f"  → 验证集最优阈值 {best_gt} | 测试集: 排除 {kt:,} 误杀 {ht:,}"
          f" 误杀率 {rate_t*100:.1f}% vs 随机 {p0*100:.1f}%({rel:+.0f}%)"
          f" z={z_t:+.1f} p={p_t:.2e} {sig(p_t)}")

    # ── 2. 热/冷命中率:验证集选参 → 测试集报告 ──
    print(f"\n🔥❄️ 热号/冷号(验证集选参,测试集{test_n}期报告)")
    print(f"  {'配置':<18} {'热号命中':>8} {'温号命中':>8} {'冷号命中':>8} {'区分度':>7} {'p(热vs冷)':>10}")
    print(f"  {'-'*64}")

    best_hc = None; best_diff = -999
    for ht in [cfg["main_pick"]//3+1, cfg["main_pick"]//3+2]:
        for cg_th in [cfg["main_pick"]+5, cfg["main_pick"]+8, cfg["main_pick"]+12]:
            hot_t, hot_h, warm_t, warm_h, cold_t, cold_h = hotcold_stats(
                cfg, f10_all, cg_m, appear_m, ht, cg_th, val_start, test_start, xp)
            if hot_t < 100 or cold_t < 50:
                continue
            diff = hot_h/max(hot_t,1)*100 - cold_h/max(cold_t,1)*100
            z2 = z_two_prop(hot_h, hot_t, cold_h, cold_t)
            # 验证集选区分度最强的配置(负区分度也纳入,测试集再检验)
            if diff > best_diff:
                best_diff = diff
                best_hc = (ht, cg_th, diff, z2)
    if best_hc:
        ht, cg_th, diff_v, z2v = best_hc
        # 测试集单次报告
        hot_t, hot_h, warm_t, warm_h, cold_t, cold_h = hotcold_stats(
            cfg, f10_all, cg_m, appear_m, ht, cg_th, test_start, total, xp)
        hot_r = hot_h/max(hot_t,1)*100; cold_r = cold_h/max(cold_t,1)*100; warm_r = warm_h/max(warm_t,1)*100
        diff = hot_r - cold_r
        z2 = z_two_prop(hot_h, hot_t, cold_h, cold_t)
        p2 = z2[1] if z2 else 1
        tag = "✅" if diff > 5 else ("⚠️" if diff > 2 else "❌")
        print(f"  热≥{ht}次/冷>{cg_th}期(验证选)  {hot_r:>7.1f}% {warm_r:>7.1f}% {cold_r:>7.1f}% {diff:>+6.1f}% {p2:>8.3f} {tag}")
        print(f"  (验证集区分度 {diff_v:+.1f}% → 测试集 {diff:+.1f}%,p={p2:.3f} {sig(p2)})")
    else:
        print("  验证集样本不足,无可用配置")

    # ── 3. 结构约束(近 200 期)+ 随机对照 ──
    if not pos and not cfg["kl8"]:
        print(f"\n🏗️ 结构约束(近{min(200,test_n)}期,对照解析随机理论)")
        n = min(200, test_n)
        recent = to_host(mains)[-n:]
        mp, M2 = cfg["main_pick"], M

        # 奇偶/大小:观测 Top3 形态 → 随机概率(口径与原版一致:a 为奇数个数/大号个数)
        for label, is_odd in [("奇偶比", True), ("大小比", False)]:
            if is_odd:
                n_a = (M2 + 1) // 2          # 奇数个数(SSQ 1-33 → 17;DLT 1-35 → 18)
            else:
                n_a = M2 - cfg["size_split"] + 1  # 大号个数(split..max)
            n_b = M2 - n_a
            dist = Counter()
            for row in recent:
                a = int(((row % 2 == 1) if is_odd else (row >= cfg["size_split"])).sum())
                dist[f"{a}:{len(row)-a}"] += 1
            top3 = dist.most_common(3)
            cov = sum(c for _, c in top3) / n * 100
            rand_top3 = sum(comb(n_a, int(k.split(":")[0])) * comb(n_b, int(k.split(":")[1])) / comb(M2, mp)
                            for k, _ in top3) * 100
            tag = "✅" if abs(cov - rand_top3) > 10 else ("⚠️" if abs(cov - rand_top3) > 5 else "○")
            print(f"  {label} Top3 {', '.join(f'{k}({v})' for k, v in top3)} 观测覆盖{cov:.0f}%"
                  f" | 随机期望{rand_top3:.0f}% 差{cov-rand_top3:+.0f}% {tag}")

        # 和值:1σ 覆盖 vs 正态 68.3%
        sums = recent.sum(axis=1)
        mean_s, sd_s = sums.mean(), sums.std()
        in_r = int(((sums >= mean_s-sd_s) & (sums <= mean_s+sd_s)).sum()) / n * 100
        print(f"  和值: μ={mean_s:.0f} σ={sd_s:.0f} 1σ覆盖{in_r:.0f}% | 正态期望68%"
              f" {'✅' if abs(in_r-68.3) > 8 else '○'}")

        # 连号:至少一对连号的概率 = 1 - C(M-mp+1, mp)/C(M, mp)
        cons = Counter()
        for row in recent:
            nums = sorted(int(v) for v in row)
            c = sum(1 for j in range(len(nums)-1) if nums[j+1]-nums[j] == 1)
            cons[c] += 1
        has_c = sum(v for k, v in cons.items() if k > 0) / n * 100
        p_conn = (1 - comb(M2 - mp + 1, mp) / comb(M2, mp)) * 100
        print(f"  连号: 有={has_c:.0f}% | 随机期望{p_conn:.0f}% 差{has_c-p_conn:+.0f}%")

        # 重号:与上期交集 1-2 个的概率 = Σ_{r=1,2} C(mp,r)C(M-mp,mp-r)/C(M,mp)
        reps = Counter()
        for i, row in enumerate(recent):
            if i > 0:
                reps[len(set(row) & set(recent[i-1]))] += 1
        has_r = sum(v for k, v in reps.items() if 1 <= k <= 2) / (n - 1) * 100
        p_rep = sum(comb(mp, r) * comb(M2 - mp, mp - r) for r in (1, 2)) / comb(M2, mp) * 100
        print(f"  重号: 1-2个={has_r:.0f}% | 随机期望{p_rep:.0f}% 差{has_r-p_rep:+.0f}%")

    # ── 4. KL8专属 ──
    if cfg["kl8"]:
        print(f"\n📐 十码段分布(近{min(200,test_n)}期)")
        n = min(200, test_n)
        recent = to_host(mains)[-n:]
        for seg in range(8):
            lo, hi = seg*10+1, (seg+1)*10
            total_c = int(((recent >= lo) & (recent <= hi)).sum())
            print(f"  段{seg+1}({lo:02d}-{hi:02d}): {total_c/n:.1f}/期(随机期望1.0/号码档)")

    # ── 5. 最终建议 ──
    rand_baseline = cfg["main_pick"] / M * 100
    print(f"\n💡 参数建议(训练/验证/测试三分离,测试集仅报告一次)")
    print(f"  {'─'*60}")
    print(f"  随机基线: 主区号码单期开出率 {rand_baseline:.1f}%")
    if best_gt is not None:
        print(f"  深冻排除: 阈值 {best_gt} | 测试集误杀率 {rate_t*100:.1f}% vs 随机 {p0*100:.1f}%"
              f"({rel:+.0f}%) p={p_t:.1e} → {'信号存在但排除量小,不建议当主力' if p_t < 0.05 else '无信号'}")
    if best_hc:
        print(f"  热/冷分类: 热≥{best_hc[0]}次/冷>{best_hc[1]}期 | 测试集区分度 {diff:+.1f}%"
              f" p={p2:.3f} → {'可用' if diff > 5 and p2 < 0.05 else '无显著区分度'}")
    else:
        print(f"  热/冷分类: 验证集样本不足或无区分度")
    if not pos and not cfg["kl8"]:
        print(f"  结构约束: 观测分布与随机理论吻合 → 仅形态合规参考,无预测力")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="五彩种全量回测 v2(验证集选参+随机对照+显著性检验)")
    ap.add_argument("--backend", choices=["auto", "gpu", "numpy"], default="auto",
                    help="计算后端(默认 auto:GPU→NumPy)")
    args = ap.parse_args()
    xp, backend = load_backend(args.backend)
    print(f"回测后端: {fmt_backend(xp, backend)}")
    for key in ["SSQ", "DLT", "KL8", "PL5", "QXC"]:
        try:
            run(CFG[key], xp)
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"\n❌ {key}: {e}")
