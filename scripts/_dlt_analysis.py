#!/usr/bin/env python3
"""大乐透漏斗数据准备 — 统计近10/50期结构与形态指标，供漏斗选号使用"""
import csv, sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

PRIMES = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31}

rows = []
with open("data/processed/dlt_draws.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        front = sorted(int(r[f"front_{i}"]) for i in range(1, 6))
        back = sorted(int(r[f"back_{i}"]) for i in range(1, 3))
        rows.append({"pid": r["period_id"], "front": front, "back": back})

rows.sort(key=lambda x: x["pid"])
N = len(rows)
last = rows[-1]
print(f"总期数: {N} | 最新: {last['pid']}: {last['front']} + {last['back']}")
print(f"下一期: {int(last['pid']) + 1}")

print("\n── 近10期 ──")
for r in rows[-10:]:
    print(f"  {r['pid']}: {r['front']} + {r['back']}")

# 频率与遗漏
print("\n── 前区频率/遗漏 (近50期) ──")
gaps = {}
for n in range(1, 36):
    gap = 0
    for r in reversed(rows):
        if n in r["front"]:
            break
        gap += 1
    gaps[n] = gap
freq50 = Counter()
freq10 = Counter()
for r in rows[-50:]:
    freq50.update(r["front"])
for r in rows[-10:]:
    freq10.update(r["front"])

max_gap_hist = {}
for n in range(1, 36):
    g, mx = 0, 0
    for r in rows:
        if n in r["front"]:
            mx = max(mx, g)
            g = 0
        else:
            g += 1
    max_gap_hist[n] = mx

cold = sorted(range(1, 36), key=lambda n: -gaps[n])[:8]
hot = freq50.most_common(10)
print(f"热号(近50 Top10): {hot}")
print(f"当前遗漏最深8个: {[(n, gaps[n]) for n in sorted(cold, key=lambda n: -gaps[n])]}")
print(f"遗漏≥8且<历史最大: {[(n, gaps[n], max_gap_hist[n]) for n in range(1,36) if gaps[n] >= 8 and gaps[n] < max_gap_hist[n]]}")

print("\n── 后区频率/遗漏 (近50期) ──")
back_gaps = {}
for n in range(1, 13):
    gap = 0
    for r in reversed(rows):
        if n in r["back"]:
            break
        gap += 1
    back_gaps[n] = gap
bfreq50 = Counter()
bfreq10 = Counter()
for r in rows[-50:]:
    bfreq50.update(r["back"])
for r in rows[-10:]:
    bfreq10.update(r["back"])
print(f"热号(近50): {bfreq50.most_common(6)}")
print(f"遗漏: {[(n, back_gaps[n]) for n in range(1, 13) if back_gaps[n] >= 5]}")

# 结构 (近50期)
print("\n── 结构 (近50期) ──")
parity = Counter()
size = Counter()
sums = []
roads = Counter()
primes = Counter()
for r in rows[-50:]:
    f_ = r["front"]
    parity[f"{sum(1 for x in f_ if x % 2 == 1)}:{5 - sum(1 for x in f_ if x % 2 == 1)}"] += 1
    size[f"{sum(1 for x in f_ if x <= 17)}:{sum(1 for x in f_ if x >= 18)}"] += 1
    sums.append(sum(f_))
    rc = tuple(sorted(Counter(x % 3 for x in f_).values(), reverse=True))
    roads[str(rc)] += 1
    primes[sum(1 for x in f_ if x in PRIMES)] += 1

import statistics
mu, sd = statistics.mean(sums), statistics.stdev(sums)
print(f"奇偶比: {parity.most_common()}")
print(f"大小比: {size.most_common()}")
print(f"和值: μ={mu:.0f} σ={sd:.0f} 1σ=[{mu-sd:.0f},{mu+sd:.0f}] 近10期: {[sum(r['front']) for r in rows[-10:]]}")
print(f"012路分布(降序计数): {roads.most_common(5)}")
print(f"质数个数: {sorted(primes.items())}")

# 后区结构
bp = Counter()
bs = Counter()
for r in rows[-50:]:
    b = r["back"]
    bp[f"{sum(1 for x in b if x % 2 == 1)}:1"] += 1
    bs[f"{sum(1 for x in b if x <= 6)}:1"] += 1
print(f"后区奇偶: {bp.most_common()}")
print(f"后区大小: {bs.most_common()}")

# 形态 (近50期)
print("\n── 形态 (近50期) ──")
consec = Counter()
repeat = Counter()
tail = Counter()
span = []
zone = Counter()
boverlap = Counter()
for i in range(N - 50, N):
    r, prev = rows[i], rows[i - 1]
    f_ = r["front"]
    c = sum(1 for j in range(4) if f_[j + 1] - f_[j] == 1)
    consec[c] += 1
    rep = len(set(f_) & set(prev["front"]))
    repeat[rep] += 1
    tc = Counter(x % 10 for x in f_)
    tail[sum(1 for v in tc.values() if v >= 2)] += 1
    span.append(f_[-1] - f_[0])
    z = (sum(1 for x in f_ if 1 <= x <= 12), sum(1 for x in f_ if 13 <= x <= 24), sum(1 for x in f_ if 25 <= x <= 35))
    zone[f"{z[0]}-{z[1]}-{z[2]}"] += 1
    boverlap[len(set(r["back"]) & set(prev["back"]))] += 1

print(f"连号组数: {sorted(consec.items())}")
print(f"重号个数: {sorted(repeat.items())}")
print(f"同尾组数: {sorted(tail.items())}")
print(f"跨度: μ={statistics.mean(span):.0f} 近10期: {span[-10:]}")
print(f"三区间分布Top5: {zone.most_common(5)}")
print(f"后区与上期重叠: {sorted(boverlap.items())}")

# 连号近5期节奏
print(f"近5期连号: {[sum(1 for j in range(4) if rows[-k]['front'][j+1]-rows[-k]['front'][j]==1) for k in range(5,0,-1)]}")
print(f"近5期重号: {[len(set(rows[-k]['front']) & set(rows[-k-1]['front'])) for k in range(5,0,-1)]}")

# 前区伴随对 Top5
pair = Counter()
for r in rows[-200:]:
    f_ = r["front"]
    for i in range(5):
        for j in range(i + 1, 5):
            pair[(f_[i], f_[j])] += 1
print(f"\n伴随对Top5(近200期): {pair.most_common(5)}")

# 后区组合模式
bc = Counter()
for r in rows[-50:]:
    bc[tuple(r["back"])] += 1
print(f"后区组合Top5(近50期): {bc.most_common(5)}")
print(f"上期后区: {last['back']} (硬约束: 重叠≤1)")

# 上期前区(重号来源)
print(f"上期前区: {last['front']}")
