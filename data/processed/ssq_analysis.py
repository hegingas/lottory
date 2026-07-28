import csv
import math
from collections import Counter, defaultdict

rows = []
with open("data/processed/ssq_draws.csv", "r") as f:
    reader = csv.DictReader(f)
    for r in reader:
        reds = tuple(sorted([int(r[f"red_{i}"]) for i in range(1,7)]))
        blue = int(r["blue"])
        rows.append({"period": r["period_id"], "reds": reds, "blue": blue})

total = len(rows)
print(f"总期数: {total}")
print(f"最新期: {rows[-1]['period']}  开奖: {' '.join(f'{n:02d}' for n in rows[-1]['reds'])} + {rows[-1]['blue']:02d}")
print(f"上上期: {rows[-2]['period']}  开奖: {' '.join(f'{n:02d}' for n in rows[-2]['reds'])} + {rows[-2]['blue']:02d}")
print()

# ========= 1. 近10期 =========
print("=" * 70)
print("【1. 近10期开奖明细】")
print("=" * 70)
for r in rows[-10:]:
    print(f"{r['period']}  {' '.join(f'{n:02d}' for n in r['reds'])} + {r['blue']:02d}")
print()

# ========= 2. 频率遗漏 =========
print("=" * 70)
print("【2. 频率 & 遗漏分析】")
print("=" * 70)
recent10 = rows[-10:]
recent50 = rows[-50:]

red_hit_10 = Counter()
red_hit_50 = Counter()
blue_hit_10 = Counter()
blue_hit_50 = Counter()
for r in recent10:
    for n in r["reds"]:
        red_hit_10[n] += 1
    blue_hit_10[r["blue"]] += 1
for r in recent50:
    for n in r["reds"]:
        red_hit_50[n] += 1
    blue_hit_50[r["blue"]] += 1

red_last_seen = {}
for i, r in enumerate(rows):
    for n in r["reds"]:
        red_last_seen[n] = i
blue_last_seen = {}
for i, r in enumerate(rows):
    blue_last_seen[r["blue"]] = i

cur_idx = total - 1
red_miss = {n: cur_idx - red_last_seen[n] for n in range(1,34)}
blue_miss = {n: cur_idx - blue_last_seen[n] for n in range(1,17)}

def max_misses(nums_range, extract_func):
    max_m = {}
    for n in nums_range:
        positions = [i for i, r in enumerate(rows) if n in extract_func(r)]
        if not positions:
            max_m[n] = cur_idx + 1
        else:
            gaps = []
            prev = -1
            for p in positions:
                gaps.append(p - prev - 1)
                prev = p
            gaps.append(cur_idx - prev)
            max_m[n] = max(gaps)
    return max_m

red_max_miss = max_misses(range(1,34), lambda r: r["reds"])
blue_max_miss = max_misses(range(1,17), lambda r: {r["blue"]})

print("\n--- 红球频率遗漏 (01-33) ---")
print(f"{'号':>3} {'近10':>4} {'近50':>4} {'当前遗漏':>6} {'历史最大':>6} {'标注':>10}")
for n in range(1, 34):
    h10 = red_hit_10.get(n, 0)
    h50 = red_hit_50.get(n, 0)
    cm = red_miss[n]
    hm = red_max_miss[n]
    tag = ""
    if cm >= hm * 0.99 and hm > 5:
        tag = "深冻"
    elif h10 >= 4:
        tag = "热号"
    elif cm > 18:
        tag = "冷号"
    print(f"{n:02d}  {h10:>4} {h50:>4} {cm:>6} {hm:>6} {tag:>10}")

print("\n--- 蓝球频率遗漏 (01-16) ---")
print(f"{'号':>3} {'近10':>4} {'近50':>4} {'当前遗漏':>6} {'历史最大':>6} {'标注':>10}")
for n in range(1, 17):
    h10 = blue_hit_10.get(n, 0)
    h50 = blue_hit_50.get(n, 0)
    cm = blue_miss[n]
    hm = blue_max_miss[n]
    tag = ""
    if cm >= hm * 0.99 and hm > 5:
        tag = "深冻"
    elif h10 >= 4:
        tag = "热号"
    elif cm > 18:
        tag = "冷号"
    print(f"{n:02d}  {h10:>4} {h50:>4} {cm:>6} {hm:>6} {tag:>10}")

print()

# ========= 3. 结构分析（近50期）=========
print("=" * 70)
print("【3. 结构分析（近50期）】")
print("=" * 70)

def is_prime(n):
    if n < 2: return False
    for i in range(2, int(n**0.5)+1):
        if n % i == 0: return False
    return True

odd_even_counts = Counter()
size_counts = Counter()
sums = []
road_counts = Counter()
prime_counts = Counter()
consec_counts = Counter()
repeat_counts = Counter()
same_tail_counts = Counter()
spans = []
zone_counts = Counter()

for idx in range(total - 50, total):
    r = rows[idx]
    reds = r["reds"]
    odd = sum(1 for n in reds if n % 2 == 1)
    even = 6 - odd
    odd_even_counts[f"{odd}:{even}"] += 1
    big = sum(1 for n in reds if n >= 17)
    small = 6 - big
    size_counts[f"{small}:{big}"] += 1
    s = sum(reds)
    sums.append(s)
    r0 = sum(1 for n in reds if n % 3 == 0)
    r1 = sum(1 for n in reds if n % 3 == 1)
    r2 = sum(1 for n in reds if n % 3 == 2)
    road_counts[f"{r0}:{r1}:{r2}"] += 1
    pc = sum(1 for n in reds if is_prime(n))
    prime_counts[pc] += 1
    consec = 0
    i = 0
    while i < 5:
        if reds[i+1] - reds[i] == 1:
            consec += 1
            i += 2
        else:
            i += 1
    consec_counts[consec] += 1
    if idx > 0:
        prev_reds = rows[idx-1]["reds"]
        repeat = len(set(reds) & set(prev_reds))
        repeat_counts[repeat] += 1
    tails = [n % 10 for n in reds]
    tail_groups = [v for v in Counter(tails).values() if v >= 2]
    same_tail_counts[len(tail_groups)] += 1
    spans.append(max(reds) - min(reds))
    z1 = sum(1 for n in reds if 1 <= n <= 11)
    z2 = sum(1 for n in reds if 12 <= n <= 22)
    z3 = sum(1 for n in reds if 23 <= n <= 33)
    zone_counts[f"{z1}:{z2}:{z3}"] += 1

print(f"\n奇偶比分布（奇:偶）:")
for k in sorted(odd_even_counts, key=lambda x: -odd_even_counts[x]):
    print(f"  {k} -> {odd_even_counts[k]}次 ({odd_even_counts[k]/50*100:.0f}%)")

print(f"\n大小比分布（小:大）:")
for k in sorted(size_counts, key=lambda x: -size_counts[x]):
    print(f"  {k} -> {size_counts[k]}次 ({size_counts[k]/50*100:.0f}%)")

avg_sum = sum(sums) / len(sums)
std_sum = (sum((s-avg_sum)**2 for s in sums) / len(sums))**0.5
print(f"\n和值: 均值 {avg_sum:.1f} +- 1σ [{avg_sum-std_sum:.1f}, {avg_sum+std_sum:.1f}]")
print(f"  近10期和值: {' '.join(str(s) for s in sums[-10:])}")

print(f"\n012路比分布（0:1:2）:")
for k in sorted(road_counts, key=lambda x: -road_counts[x]):
    print(f"  {k} -> {road_counts[k]}次 ({road_counts[k]/50*100:.0f}%)")

print(f"\n质数个数分布:")
for k in sorted(prime_counts):
    print(f"  {k}个 -> {prime_counts[k]}次 ({prime_counts[k]/50*100:.0f}%)")

print()

# ========= 4. 形态分析（近50期）=========
print("=" * 70)
print("【4. 形态分析（近50期）】")
print("=" * 70)

print(f"\n连号组数分布:")
for k in sorted(consec_counts):
    print(f"  {k}组 -> {consec_counts[k]}次 ({consec_counts[k]/50*100:.0f}%)")

print(f"\n重号个数分布（相对上期）:")
for k in sorted(repeat_counts):
    print(f"  {k}个 -> {repeat_counts[k]}次 ({repeat_counts[k]/50*100:.0f}%)")

print(f"\n同尾组数分布:")
for k in sorted(same_tail_counts):
    print(f"  {k}组 -> {same_tail_counts[k]}次 ({same_tail_counts[k]/50*100:.0f}%)")

avg_span = sum(spans) / len(spans)
print(f"\n跨度范围: min={min(spans)} max={max(spans)} 均值={avg_span:.1f}")
print(f"  近10期跨度: {' '.join(str(s) for s in spans[-10:])}")

print(f"\n三区间分布（1-11 : 12-22 : 23-33）:")
for k in sorted(zone_counts, key=lambda x: -zone_counts[x]):
    print(f"  [{k}] -> {zone_counts[k]}次 ({zone_counts[k]/50*100:.0f}%)")

print()

# ========= 5. 伴随对 + 蓝球跟随 =========
print("=" * 70)
print("【5. 伴随对 & 蓝球跟随】")
print("=" * 70)

pair_cnt = defaultdict(int)
for r in rows:
    reds = r["reds"]
    for i in range(5):
        for j in range(i+1, 6):
            a, b = reds[i], reds[j]
            pair_cnt[(a,b)] += 1

top5_pairs = sorted(pair_cnt.items(), key=lambda x: -x[1])[:5]
print("\n红球伴随对 Top5（全历史）:")
for (a,b), cnt in top5_pairs:
    print(f"  {a:02d}-{b:02d}  {cnt}次")

recent100 = rows[-100:]
blue_seq = [r["blue"] for r in recent100]

repeat_b = sum(1 for i in range(len(blue_seq)-1) if blue_seq[i] == blue_seq[i+1])
total_blue_samples = len(blue_seq) - 1
print(f"\n蓝球重复率（近100期）: {repeat_b}/{total_blue_samples} = {repeat_b/total_blue_samples*100:.1f}%")

adj_b = sum(1 for i in range(len(blue_seq)-1) if abs(blue_seq[i] - blue_seq[i+1]) == 1)
print(f"蓝球邻号率(+-1): {adj_b}/{total_blue_samples} = {adj_b/total_blue_samples*100:.1f}%")

jump_b = sum(1 for i in range(len(blue_seq)-1) if abs(blue_seq[i] - blue_seq[i+1]) == 2)
print(f"蓝球跳号率(+-2): {jump_b}/{total_blue_samples} = {jump_b/total_blue_samples*100:.1f}%")

same_parity = sum(1 for i in range(len(blue_seq)-1) if blue_seq[i] % 2 == blue_seq[i+1] % 2)
print(f"蓝球同奇偶率: {same_parity}/{total_blue_samples} = {same_parity/total_blue_samples*100:.1f}%")

same_road_b = sum(1 for i in range(len(blue_seq)-1) if blue_seq[i] % 3 == blue_seq[i+1] % 3)
print(f"蓝球同012路率: {same_road_b}/{total_blue_samples} = {same_road_b/total_blue_samples*100:.1f}%")

print(f"\n近50期蓝球走势:")
last50_b = [r["blue"] for r in recent50]
for i in range(0, 50, 10):
    chunk = last50_b[i:i+10]
    print(f"  {' '.join(f'{n:02d}' for n in chunk)}")

print("\n近50期每个蓝球伴随最多的红球（top3）:")
blue_red_counter = defaultdict(Counter)
for r in recent50:
    br = r["blue"]
    for n in r["reds"]:
        blue_red_counter[br][n] += 1
for b in sorted(blue_red_counter):
    top3 = blue_red_counter[b].most_common(3)
    print(f"  蓝{b:02d}: {' '.join(f'{n:02d}({c}次)' for n,c in top3)}")

print("\n\n======= 以上就是全部数据，主打一个真实 =======")
