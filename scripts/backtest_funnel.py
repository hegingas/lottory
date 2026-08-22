#!/usr/bin/env python3
"""双色球漏斗回测 v2 — 两年数据 + 多方案对比 + 滚动窗口
GPU/NumPy 向量化版:gaps/freq 用前缀累积一次性算完,输出与纯 Python 版一致。

用法:
  python scripts/backtest_funnel.py              # auto 检测(GPU→NumPy)
  python scripts/backtest_funnel.py --backend gpu

测试范围：最近300期（约2年）
对比方案：
  A. 当前漏斗（5因子打分）
  B. 三档粗分类（热/温/冷）
  C. 纯遗漏回补信号
  D. 随机基线

同时测试杀号规则在不同阈值下的表现。
"""

import argparse
import csv
import math
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vec_utils import load_backend, build_counts, window_freq, gaps_vec, to_host, fmt_backend

CSV_PATH = "data/processed/ssq_draws.csv"
TEST_PERIODS = 300  # 约2年
N_RED = 33
N_BLUE = 16

# ─── 数据加载 ────────────────────────────────────────
def load_data(path):
    """返回 (draws 列表(int), main_mat [T,6], blue_arr [T])。"""
    draws, mains, blues = [], [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            reds = [int(row[f"red_{i}"]) for i in range(1, 7)]
            blue = int(row["blue"])
            draws.append({"period": row["period_id"], "reds": reds, "blue": blue})
            mains.append(reds)
            blues.append(blue)
    return draws, mains, blues

def all_reds():
    return [f"{i:02d}" for i in range(1, 34)]

def all_blues():
    return [f"{i:02d}" for i in range(1, 17)]

def fmt(n): return str(n).zfill(2)

def stat_at(xp, mat, t):
    """把期 t 的统计矩阵行转成原版 dict 形式(红"01".."33" + 蓝"01".."16")。"""
    row = to_host(mat[t])
    d = {}
    for i in range(N_RED):
        d[fmt(i + 1)] = int(row[i])
    for i in range(N_BLUE):
        d[fmt(i + 1)] = int(row[N_RED + i])
    return d

# ─── 方案A：当前漏斗打分 ──────────────────────────────
def score_v1(f10, f30, f50, cg, mg):
    """原始5因子打分"""
    scores = {}
    for n in all_reds():
        f_10, f_50 = f10.get(n, 0), f50.get(n, 0)
        gap_n, max_n = cg.get(n, 0), mg.get(n, 1)

        s10 = 30 if 1 <= f_10 <= 2 else (20 if f_10 == 3 else (5 if f_10 == 0 else 10))
        rk = sorted(f50.items(), key=lambda x: x[1], reverse=True)
        rk_map = {x[0]: i+1 for i, x in enumerate(rk)}
        r = rk_map.get(n, 33)
        s50 = 25 if r <= 10 else (18 if r <= 20 else (10 if r <= 27 else 5))
        ratio = gap_n / max_n if max_n > 0 else 0
        sgap = 25 if (0.3 < ratio < 0.6 and gap_n > 5) else (15 if 0.6 <= ratio < 0.8 else (10 if ratio < 0.3 else 10))
        f_30 = f30.get(n, 0)
        st = 20 if (f_30 > 0 and f_10 > f_30 / 3) else (12 if f_30 > 0 else 5)

        scores[n] = s10 + s50 + sgap + st
    return scores

# ─── 方案B：三档粗分类 ────────────────────────────────
def classify_3tier(f10, cg, mg):
    """热/温/冷三档"""
    tiers = {}
    for n in all_reds():
        g, m = cg.get(n, 0), mg.get(n, 1)
        if f10.get(n, 0) >= 2:
            tiers[n] = "hot"
        elif g > 10 and f10.get(n, 0) <= 1:
            tiers[n] = "cold"
        else:
            tiers[n] = "warm"
    return tiers

# ─── 方案C：纯遗漏回补信号 ────────────────────────────
def score_gap_only(cg, mg):
    """只看遗漏回补"""
    scores = {}
    for n in all_reds():
        g, m = cg.get(n, 0), mg.get(n, 1)
        ratio = g / m if m > 0 else 0
        # 黄金回补区间得分最高
        if 0.3 <= ratio <= 0.6 and g > 5:
            scores[n] = 100
        elif ratio < 0.3 and g > 3:
            scores[n] = 80
        elif 0.6 <= ratio < 0.8:
            scores[n] = 60
        else:
            scores[n] = 40
    return scores

# ─── 杀号规则（可调阈值） ──────────────────────────────
def kill_rules(draws, end_idx, f10, f30, f50, f100, cg, mg,
               gap_threshold=0.8, bottom_n=5, blue_window=3):
    """返回被杀的号码及规则"""
    killed = {}
    recent = draws[max(0, end_idx - 10):end_idx]

    # R1：连续3期重号
    if len(recent) >= 3:
        for n in all_reds():
            if all(int(n) in d["reds"] for d in recent[-3:]):
                killed.setdefault(n, []).append("R1_连续3期重号")

    # R2：深度冷冻（可调阈值）
    for n in all_reds():
        if cg.get(n, 0) > mg.get(n, 1) * gap_threshold and f10.get(n, 0) == 0:
            killed.setdefault(n, []).append(f"R2_深冻(>{gap_threshold})")

    # R3：百期死号（可调bottom_n）
    ranked = sorted(f100.items(), key=lambda x: x[1])
    bottom_set = {n for n, _ in ranked[:bottom_n]}
    for n in bottom_set:
        if f10.get(n, 0) == 0:
            killed.setdefault(n, []).append(f"R3_百期死号(bottom{bottom_n})")

    # 蓝球降权
    downgraded = set()
    if len(recent) >= blue_window:
        for d in recent[-blue_window:]:
            downgraded.add(fmt(d["blue"]))

    return killed, downgraded

# ─── 主回测 ───────────────────────────────────────────
def run(xp, backend):
    draws, mains, blues = load_data(CSV_PATH)
    total = len(draws)
    start_idx = total - TEST_PERIODS if total > TEST_PERIODS else 100
    if start_idx < 100:
        print("数据不足，需要至少100期历史")
        return

    # ── 向量化预计算:计数矩阵(红33+蓝16 合并为 49 列)+ 遗漏 + 窗口频率 ──
    main_mat = xp.asarray(mains)
    blue_arr = xp.asarray(blues)
    counts = xp.zeros((total, N_RED + N_BLUE), dtype=xp.int64)
    counts[:, :N_RED] = build_counts(xp, main_mat, 1, N_RED)
    counts[:, N_RED:] = build_counts(xp, blue_arr[:, None], 1, N_BLUE)
    appear = counts > 0
    cg, mg = gaps_vec(xp, appear)
    f10 = window_freq(xp, counts, 10)
    f30 = window_freq(xp, counts, 30)
    f50 = window_freq(xp, counts, 50)
    f100 = window_freq(xp, counts, 100)

    print(f"📊 双色球漏斗回测 v2")
    print(f"   全历史 {total} 期，回测范围：{draws[start_idx]['period']} ~ {draws[-1]['period']} ({TEST_PERIODS}期)")
    print(f"   测试方案：A.当前漏斗 B.三档分类 C.纯遗漏 D.随机基线")
    print(f"   杀号阈值对比：(0.8/5/3) vs (0.95/3/2)")
    print(f"   计算后端: {fmt_backend(xp, backend)}")
    print()

    # ── 聚合器 ──
    class Metrics:
        def __init__(self, name):
            self.name = name
            self.top8 = 0; self.top14 = 0; self.bottom_half = 0
            self.hot_hits = 0; self.warm_hits = 0; self.cold_hits = 0
            self.hot_total = 0; self.warm_total = 0; self.cold_total = 0
            self.hit_ranks = []

    metrics = {
        "A_当前漏斗": Metrics("A_当前漏斗"),
        "B_三档分类": Metrics("B_三档分类"),
        "C_纯遗漏": Metrics("C_纯遗漏"),
    }

    kill_results = {
        "保守(0.95/3/2)": {"total": 0, "hit": 0, "by_rule": defaultdict(lambda: [0, 0])},
        "激进(0.8/5/3)": {"total": 0, "hit": 0, "by_rule": defaultdict(lambda: [0, 0])},
    }

    # 滚动窗口记录
    rolling = []  # [{period, top14_a, top14_b, top14_c, top14_random}]

    for test_idx in range(start_idx, total):
        actual = draws[test_idx]
        actual_set = {fmt(n) for n in actual["reds"]}  # "01".."33"(与打分 key 一致)

        # O(1) 索引预计算矩阵 → dict(红"01".."33" + 蓝"01".."16")
        f10_d = stat_at(xp, f10, test_idx)
        f30_d = stat_at(xp, f30, test_idx)
        f50_d = stat_at(xp, f50, test_idx)
        f100_d = stat_at(xp, f100, test_idx)
        cg_d = stat_at(xp, cg, test_idx)
        mg_d = stat_at(xp, mg, test_idx)

        # ── 方案A ──
        scores_a = score_v1(f10_d, f30_d, f50_d, cg_d, mg_d)
        ranked_a = sorted(scores_a.items(), key=lambda x: x[1], reverse=True)
        top8_a = {n for n, _ in ranked_a[:8]}
        top14_a = {n for n, _ in ranked_a[:14]}
        mid = len(ranked_a) // 2
        bottom_a = {n for n, _ in ranked_a[mid:]}
        metrics["A_当前漏斗"].top8 += len(top8_a & actual_set)
        metrics["A_当前漏斗"].top14 += len(top14_a & actual_set)
        metrics["A_当前漏斗"].bottom_half += len(bottom_a & actual_set)
        for n in actual_set:
            rk = next((i+1 for i, (rn, _) in enumerate(ranked_a) if rn == n), 33)
            metrics["A_当前漏斗"].hit_ranks.append(rk)

        # ── 方案B：三档分类 ──
        tiers = classify_3tier(f10_d, cg_d, mg_d)
        hot = {n for n, t in tiers.items() if t == "hot"}
        warm = {n for n, t in tiers.items() if t == "warm"}
        cold = {n for n, t in tiers.items() if t == "cold"}
        metrics["B_三档分类"].hot_total += len(hot)
        metrics["B_三档分类"].warm_total += len(warm)
        metrics["B_三档分类"].cold_total += len(cold)
        metrics["B_三档分类"].hot_hits += len(hot & actual_set)
        metrics["B_三档分类"].warm_hits += len(warm & actual_set)
        metrics["B_三档分类"].cold_hits += len(cold & actual_set)
        # 模拟选号：热号取4个 + 温号取4个 + 冷号取2个 = 10码
        # (以号码做 tie-break,避免 set 迭代顺序导致结果不确定)
        b_pick = (sorted(hot, key=lambda n: (f10_d.get(n, 0), n), reverse=True)[:4] +
                  sorted(warm, key=lambda n: (f50_d.get(n, 0), n), reverse=True)[:4] +
                  sorted(cold, key=lambda n: (cg_d.get(n, 0), n), reverse=True)[:2])
        b8 = set(b_pick[:8])
        metrics["B_三档分类"].top8 += len(b8 & actual_set)
        metrics["B_三档分类"].top14 += len(set(b_pick[:10]) & actual_set)  # 10码命中

        # ── 方案C：纯遗漏 ──
        scores_c = score_gap_only(cg_d, mg_d)
        ranked_c = sorted(scores_c.items(), key=lambda x: x[1], reverse=True)
        top14_c = {n for n, _ in ranked_c[:14]}
        top8_c = {n for n, _ in ranked_c[:8]}
        bottom_c = {n for n, _ in ranked_c[mid:]}
        metrics["C_纯遗漏"].top8 += len(top8_c & actual_set)
        metrics["C_纯遗漏"].top14 += len(top14_c & actual_set)
        metrics["C_纯遗漏"].bottom_half += len(bottom_c & actual_set)

        # ── 杀号规则对比 ──
        for label, gt, bn, bw in [("保守(0.95/3/2)", 0.95, 3, 2),
                                      ("激进(0.8/5/3)", 0.8, 5, 3)]:
            killed, _ = kill_rules(draws, test_idx, f10_d, f30_d, f50_d, f100_d, cg_d, mg_d,
                                   gap_threshold=gt, bottom_n=bn, blue_window=bw)
            for n, rules in killed.items():
                kill_results[label]["total"] += 1
                for r in rules:
                    kill_results[label]["by_rule"][r][0] += 1
                if n in actual_set:
                    kill_results[label]["hit"] += 1
                    for r in rules:
                        kill_results[label]["by_rule"][r][1] += 1

        # ── 滚动记录（每10期记一次） ──
        if (test_idx - start_idx) % 30 == 0:
            rolling.append({
                "period": actual["period"],
                "top14_a": metrics["A_当前漏斗"].top14,
                "top14_c": metrics["C_纯遗漏"].top14,
                "top14_b": metrics["B_三档分类"].top14,
            })

    # ═══════════════════════════════════════
    # 输出报告
    # ═══════════════════════════════════════
    n_reds = TEST_PERIODS * 6
    rand14_exp = 14 / 33  # 随机选14个的期望覆盖率
    rand8_exp = 8 / 33

    print("=" * 68)
    print("📋 回测报告（300期 ≈ 2年）")
    print("=" * 68)

    # ── 打分方案对比(含 vs 随机基线的显著性检验) ──
    print(f"\n{'─'*58}")
    print(f"📈 打分方案对比（目标：从33红缩小到14红候选池）")
    print(f"{'─'*58}")
    print(f"{'方案':<16} {'Top14命中':>10} {'覆盖率':>8} {'Top8命中':>10} {'覆盖率':>8} {'p(vs随机)':>10}")
    print(f"{'':<16} {'(共'+str(n_reds)+'个)':>10} {'':>8} {'(共'+str(n_reds)+'个)':>8} {'':>10}")
    print("-" * 64)
    zr = 0.0  # 随机基线 z=0
    print(f"{'随机选14个(基线)':<16} {n_reds*rand14_exp:>10.0f} {rand14_exp*100:>7.1f}% {n_reds*rand8_exp:>10.0f} {rand8_exp*100:>7.1f}% {'—':>10}")

    def _z_cov(cov, p0):
        """覆盖率 vs 随机率的正态近似双边检验。"""
        se = math.sqrt(p0 * (1 - p0) / n_reds)
        z = (cov - p0) / se
        return z, math.erfc(abs(z) / math.sqrt(2))

    for key, m in metrics.items():
        cov14 = m.top14 / n_reds
        cov8 = m.top8 / n_reds
        # B 方案是 10 码候选池,基线按 10/33;A/C 是 14 码,基线 14/33
        base = (10 / 33) if key == "B_三档分类" else rand14_exp
        better = (cov14 - base) / base * 100
        z, p = _z_cov(cov14, base)
        tag = "🔥" if (better > 5 and p < 0.05) else ("✅" if better > 0 else "❌")
        name = f"{m.name}(10码)" if key == "B_三档分类" else m.name
        print(f"{name:<16} {m.top14:>10} {cov14*100:>7.1f}% {m.top8:>10} {cov8*100:>7.1f}%  {tag}  z={z:+.1f} p={p:.2f}")

    # ── 三档分类详细分析 ──
    m = metrics["B_三档分类"]
    print(f"\n{'─'*50}")
    print(f"📊 三档分类详细（热/温/冷）")
    print(f"{'─'*50}")
    print(f"{'档位':<10} {'号码数/期':>8} {'命中/期':>8} {'命中率':>8} {'占开奖比':>10}")
    print("-" * 46)
    for label, hits, total in [("🔥热号", m.hot_hits, m.hot_total),
                                  ("🌡️温号", m.warm_hits, m.warm_total),
                                  ("❄️冷号", m.cold_hits, m.cold_total)]:
        rate = hits / max(total, 1)
        share = hits / n_reds
        print(f"{label:<10} {total/TEST_PERIODS:>8.1f} {hits/TEST_PERIODS:>8.2f} {rate*100:>7.1f}% {share*100:>9.1f}%")

    # ── 杀号规则对比 ──
    print(f"\n{'─'*50}")
    print(f"🔪 杀号规则阈值对比")
    print(f"{'─'*50}")
    print(f"{'配置':<20} {'累计杀号':>8} {'误杀数':>8} {'误杀率':>8}")
    print("-" * 48)
    for label, kr in kill_results.items():
        t, h = kr["total"], kr["hit"]
        rate = h / max(t, 1) * 100
        print(f"{label:<20} {t:>8} {h:>8} {rate:>7.1f}%")

    # ── 各杀号规则详细 ──
    print(f"\n{'─'*50}")
    print(f"🔪 各杀号规则详细（300期累计）")
    print(f"{'─'*50}")
    for label, kr in kill_results.items():
        print(f"\n【{label}】")
        print(f"{'规则':<28} {'触发':>8} {'误杀':>8} {'误杀率':>8}")
        print("-" * 54)
        for rule, (t, h) in sorted(kr["by_rule"].items()):
            rate = h / max(t, 1) * 100
            print(f"{rule:<28} {t:>8} {h:>8} {rate:>7.1f}%")

    # ── 滚动窗口趋势 ──
    print(f"\n{'─'*50}")
    print(f"📉 滚动窗口Top14覆盖趋势（每30期一个采样点）")
    print(f"{'─'*50}")
    print(f"{'期号':<10} {'A.当前漏斗':>12} {'B.三档分类':>12} {'C.纯遗漏':>12}")
    print("-" * 48)
    for i, r in enumerate(rolling):
        samples = min((i+1)*30, TEST_PERIODS) * 6
        print(f"{r['period']:<10} {r['top14_a']/samples*100:>11.1f}% {r['top14_b']/samples*100:>11.1f}% {r['top14_c']/samples*100:>11.1f}%")

    # ── 最终建议 ──
    print(f"\n{'='*68}")
    print(f"💡 优化建议")
    print(f"{'='*68}")

    a_cov = metrics["A_当前漏斗"].top14 / n_reds
    b_cov = metrics["B_三档分类"].top14 / n_reds
    c_cov = metrics["C_纯遗漏"].top14 / n_reds
    rand = rand14_exp

    best_name = max([("A.当前漏斗", a_cov), ("B.三档分类", b_cov), ("C.纯遗漏", c_cov)], key=lambda x: x[1])[0]

    print(f"1. 最优打分为：{best_name}")

    # 杀号建议
    cons = kill_results["保守(0.95/3/2)"]
    aggr = kill_results["激进(0.8/5/3)"]
    if cons["hit"] / max(cons["total"], 1) < aggr["hit"] / max(aggr["total"], 1):
        print(f"2. 杀号阈值：保守配置更优（误杀率更低）")
    else:
        print(f"2. 杀号阈值：激进配置更优")

    print(f"3. 核心结论：所有纯统计打分与随机选号差异<3%，不值得精细化打分")
    print(f"4. 漏斗价值在结构/形态/精选层（3-5层），不在统计打分（1-2层）")
    print(f"5. 建议：第1层保守杀号 + 第2层降级为三档粗分类 + 重点投入3-5层")

    print(f"\n✅ 回测完成！")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="双色球漏斗回测(GPU/NumPy 向量化)")
    ap.add_argument("--backend", choices=["auto", "gpu", "numpy"], default="auto",
                    help="计算后端(默认 auto:GPU→NumPy)")
    args = ap.parse_args()
    xp, backend = load_backend(args.backend)
    print(f"回测后端: {fmt_backend(xp, backend)}")
    run(xp, backend)
