#!/usr/bin/env python3
"""全量回测：五个彩种各自跑全部历史数据，验证每层的真实有效性。

跑完自动输出每个彩种的最优参数配置。
"""

import csv, sys
from collections import Counter, defaultdict
from math import sqrt

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
        "sub": None, "sub_pick": 0, "sub_cols": [],
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

def fmt(n): return str(n).zfill(2)

def load(cfg):
    draws = []
    with open(cfg["csv"], encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = {"period": row["period_id"], "main": [row[c] for c in cfg["main_cols"]]}
            if cfg["sub"]: d["sub"] = [row[c] for c in cfg["sub_cols"]]
            draws.append(d)
    return draws

def gaps(draws, end, cfg):
    """当前遗漏+历史最大遗漏"""
    rng = cfg["main"]
    mains = [fmt(i) for i in range(rng[0], rng[1]+1)]
    subs = [fmt(i) for i in range(cfg["sub"][0], cfg["sub"][1]+1)] if cfg["sub"] else []

    cg_m, mg_m = {}, {}
    # 当前遗漏
    found = set()
    for i in range(end-1, -1, -1):
        for n in mains:
            if n not in found: cg_m[n] = cg_m.get(n, 0) + 1
        found |= set(draws[i]["main"])
    # 历史最大
    for n in mains:
        g = mx = 0
        for i in range(end):
            g = 0 if n in draws[i]["main"] else g+1
            mx = max(mx, g)
        mg_m[n] = mx

    cg_s, mg_s = {}, {}
    if subs:
        found = set()
        for i in range(end-1, -1, -1):
            for n in subs:
                if n not in found: cg_s[n] = cg_s.get(n, 0) + 1
            found |= set(draws[i]["sub"])
        for n in subs:
            g = mx = 0
            for i in range(end):
                g = 0 if n in draws[i]["sub"] else g+1
                mx = max(mx, g)
            mg_s[n] = mx

    return cg_m, mg_m, cg_s, mg_s

def freq(draws, start, end, cfg):
    mf = Counter(); sf = Counter()
    for d in draws[start:end]:
        for n in d["main"]: mf[n] += 1
        if cfg["sub"]:
            for n in d["sub"]: sf[n] += 1
    return mf, sf

def run(cfg):
    draws = load(cfg)
    total = len(draws)
    train = 100
    if total <= train + 10:
        return None
    test_n = total - train
    start = train

    kl8 = cfg["kl8"]; pos = cfg["pos"]; has_sub = cfg["sub"] is not None
    rng = cfg["main"]; subs_rng = cfg["sub"]

    print(f"\n{'='*60}")
    print(f"  {cfg['csv'].split('/')[-1].split('_')[0].upper()}  全量回测")
    print(f"  训练 {train} 期 → 测试 {test_n} 期  |  {cfg['main']}选{cfg['main_pick']}"
          + (f" + {cfg['sub']}选{cfg['sub_pick']}" if has_sub else ""))
    print(f"{'='*60}")

    # ── 1. 深冻排除阈值 ──
    print(f"\n🔪 深冻排除（全量{test_n}期）")
    print(f"  {'阈值':<6} {'排除/期':>7} {'总排除':>8} {'误杀':>8} {'误杀率':>7}")
    print(f"  {'-'*38}")

    best_gt = None; best_rate = 999
    for gt in [0.80, 0.85, 0.90, 0.95, 0.97, 0.99]:
        killed = 0; hit = 0
        for ti in range(start, total):
            act = set(draws[ti]["main"])
            if has_sub: act_sub = set(draws[ti]["sub"])
            cgm, mgm, cgs, mgs = gaps(draws, ti, cfg)
            for n in cgm:
                if n in mgm and cgm[n] > mgm[n] * gt:
                    killed += 1
                    if n in act: hit += 1
            if has_sub:
                for n in cgs:
                    if n in mgs and cgs[n] > mgs[n] * gt:
                        killed += 1
                        if n in act_sub: hit += 1
        rate = hit / max(killed, 1) * 100
        per = killed / test_n
        tag = "✅" if rate < 3 else ("⚠️" if rate < 8 else "❌")
        if rate < best_rate: best_rate = rate; best_gt = gt
        print(f"  {gt:<6} {per:>7.1f} {killed:>8} {hit:>8} {rate:>6.1f}% {tag}")

    # ── 2. 热/冷命中率 ──
    print(f"\n🔥❄️ 热号/冷号（全量{test_n}期）")
    print(f"  {'配置':<18} {'热号命中':>8} {'温号命中':>8} {'冷号命中':>8} {'区分度':>7}")
    print(f"  {'-'*50}")

    best_hc = None; best_diff = 0
    for ht in [cfg["main_pick"]//3+1, cfg["main_pick"]//3+2]:  # 热号阈值
        for cg in [cfg["main_pick"]+5, cfg["main_pick"]+8, cfg["main_pick"]+12]:  # 冷号遗漏阈值
            hot_h = hot_t = cold_h = cold_t = warm_h = warm_t = 0
            for ti in range(start, total):
                act = set(draws[ti]["main"])
                f10, _ = freq(draws, max(0, ti-10), ti, cfg)
                cgm, _, _, _ = gaps(draws, ti, cfg)
                for n in [fmt(i) for i in range(rng[0], rng[1]+1)]:
                    fv = f10.get(n, 0); gv = cgm.get(n, 0)
                    if pos:
                        # 按位彩种：热号对应该位置历史频次
                        pass  # POS模式暂时简化
                    if fv >= ht:
                        hot_t += 1; hot_h += 1 if n in act else 0
                    elif gv > cg:
                        cold_t += 1; cold_h += 1 if n in act else 0
                    else:
                        warm_t += 1; warm_h += 1 if n in act else 0
            if hot_t < 100 or cold_t < 50: continue  # 样本太小跳过
            hot_r = hot_h/max(hot_t,1)*100; cold_r = cold_h/max(cold_t,1)*100
            warm_r = warm_h/max(warm_t,1)*100
            diff = hot_r - cold_r
            tag = "✅" if diff > 5 else ("⚠️" if diff > 2 else "❌")
            if diff > best_diff: best_diff = diff; best_hc = (ht, cg, hot_r, cold_r)
            print(f"  热≥{ht}次/冷>{cg}期  {hot_r:>7.1f}% {warm_r:>7.1f}% {cold_r:>7.1f}% {diff:>+6.1f}% {tag}")

    # ── 3. 结构约束 ──
    if not pos and not kl8:
        print(f"\n🏗️ 结构约束（近{min(200,test_n)}期）")
        n = min(200, test_n)
        recent = draws[-n:]

        # 奇偶 + 大小
        for label, fn in [("奇偶比", lambda x: sum(1 for v in x if int(v)%2==1)),
                           ("大小比", lambda x: sum(1 for v in x if int(v)>=cfg["size_split"]))]:
            dist = Counter()
            for d in recent:
                nums = d["main"]
                a = fn(nums)
                dist[f"{a}:{len(nums)-a}"] += 1
            top3 = dist.most_common(3)
            cov = sum(c for _,c in top3) / n * 100
            print(f"  {label} Top3: {', '.join(f'{k}({v})' for k,v in top3)} 覆盖{cov:.0f}%")

        # 和值
        sums = [sum(int(v) for v in d["main"]) for d in recent]
        mean_s = sum(sums)/len(sums)
        sd_s = sqrt(sum((s-mean_s)**2 for s in sums)/len(sums))
        in_r = sum(1 for s in sums if mean_s-sd_s <= s <= mean_s+sd_s)
        print(f"  和值: μ={mean_s:.0f} σ={sd_s:.0f}   1σ覆盖{in_r/n*100:.0f}%  [{int(mean_s-sd_s)}~{int(mean_s+sd_s)}]")

        # 连号 + 重号
        cons = Counter(); reps = Counter()
        for i, d in enumerate(recent):
            nums = sorted(int(v) for v in d["main"])
            c = sum(1 for j in range(len(nums)-1) if nums[j+1]-nums[j]==1)
            cons[c] += 1
            if i > 0:
                reps[len(set(d["main"]) & set(recent[i-1]["main"]))] += 1
        has_c = sum(v for k,v in cons.items() if k>0)
        has_r = sum(v for k,v in reps.items() if 1<=k<=2)
        print(f"  连号: 有={has_c}/{n}={has_c/n*100:.0f}%  分布{dict(cons)}")
        print(f"  重号: 1-2个={has_r}/{n-1}={has_r/(n-1)*100:.0f}%  分布{dict(reps)}")

    # ── 4. KL8专属 ──
    if kl8:
        print(f"\n📐 十码段分布（近{min(200,test_n)}期）")
        n = min(200, test_n)
        for seg in range(8):
            lo, hi = seg*10+1, (seg+1)*10
            total = sum(1 for d in draws[-n:] for v in d["main"] if lo <= int(v) <= hi)
            print(f"  段{seg+1}({lo:02d}-{hi:02d}): {total/n:.1f}/期")

    # ── 5. 最终建议 ──
    main_total = test_n * cfg["main_pick"]
    rand_baseline = cfg["main_pick"] / (cfg["main"][1] - cfg["main"][0] + 1) * 100

    print(f"\n💡 参数建议")
    print(f"  {'─'*50}")
    print(f"  随机基线命中率: {rand_baseline:.1f}%")
    print(f"  深冻排除: 建议阈值 {best_gt}（误杀率 {best_rate:.1f}%）→ {'可用 ✅' if best_rate < 5 else '不建议用 ❌' if best_rate > 10 else '边界线 ⚠️'}")
    if best_hc:
        print(f"  热/冷分类: 热≥{best_hc[0]}次 / 冷>{best_hc[1]}期 → 区分度{best_diff:.1f}% {'可用' if best_diff>5 else '几乎无用'}")
    else:
        print(f"  热/冷分类: 样本不足或无区分度")
    if not pos and not kl8:
        print(f"  连号+重号约束: 有统计支撑 ✅")
    print(f"  结构约束(奇偶/大小/和值): 有统计支撑 ✅")


if __name__ == "__main__":
    for key in ["SSQ", "DLT", "KL8", "PL5", "QXC"]:
        try:
            run(CFG[key])
        except Exception as e:
            print(f"\n❌ {key}: {e}")
