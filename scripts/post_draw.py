#!/usr/bin/env python3
"""赛后复盘脚本 —— 开奖后自动分析：预测命中率 + 结构偏离度 + 参数自检

用法:
  python scripts/post_draw.py <彩种> [期号]
  python scripts/post_draw.py dlt            # 分析大乐透最新一期
  python scripts/post_draw.py ssq 2026084    # 分析双色球指定期号
  python scripts/post_draw.py all            # 全彩种复盘
"""

import csv, json, os, sys, math
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

BJT = timezone(timedelta(hours=8))
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 彩种配置 ────────────────────────────
CFG = {
    "dlt": {
        "csv": "data/processed/dlt_draws.csv", "lottery_type": "dlt",
        "main_cols": ["front_1","front_2","front_3","front_4","front_5"],
        "sub_cols": ["back_1","back_2"], "main_range": (1,35), "sub_range": (1,12),
        "size_split": 18, "zones": [(1,12),(13,24),(25,35)],
        "primes": {2,3,5,7,11,13,17,19,23,29,31},
        "has_blue": False,
    },
    "ssq": {
        "csv": "data/processed/ssq_draws.csv", "lottery_type": "ssq",
        "main_cols": ["red_1","red_2","red_3","red_4","red_5","red_6"],
        "sub_cols": ["blue"], "main_range": (1,33), "sub_range": (1,16),
        "size_split": 17, "zones": [(1,11),(12,22),(23,33)],
        "primes": {2,3,5,7,11,13,17,19,23,29,31},
        "has_blue": True,
    },
    "kl8": {
        "csv": "data/processed/kl8_draws.csv", "lottery_type": "kl8",
        "main_cols": [f"n{i:02d}" for i in range(1,21)],
        "sub_cols": [], "main_range": (1,80), "sub_range": None,
        "size_split": 41, "zones": [(1,10),(11,20),(21,30),(31,40),(41,50),(51,60),(61,70),(71,80)],
        "primes": {2,3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73,79},
        "has_blue": False,
    },
    "pl5": {
        "csv": "data/processed/pl5_draws.csv", "lottery_type": "pl5",
        "main_cols": ["d1","d2","d3","d4","d5"],
        "sub_cols": [], "main_range": (0,9), "sub_range": None,
        "size_split": 5, "zones": None,
        "primes": {2,3,5,7}, "has_blue": False, "pos": True,
    },
    "qxc": {
        "csv": "data/processed/qxc_draws.csv", "lottery_type": "qxc",
        "main_cols": ["d1","d2","d3","d4","d5","d6"],
        "sub_cols": ["special"], "main_range": (0,9), "sub_range": (0,14),
        "size_split": 5, "zones": None,
        "primes": {2,3,5,7}, "has_blue": False, "pos": True,
    },
}

# ── 加载数据 ────────────────────────────
def load_draws(cfg_id):
    cfg = CFG[cfg_id]
    path = os.path.join(BASE, cfg["csv"])
    draws = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = {"period": row["period_id"], "main": [row[c] for c in cfg["main_cols"]]}
            if cfg["sub_cols"]:
                d["sub"] = [row[c] for c in cfg["sub_cols"]]
            draws.append(d)
    return draws

def load_params():
    path = os.path.join(BASE, "config/funnel_params.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# 各彩种预测 CSV 的列映射：(主区列, 副区列)，None 表示该彩种无此列
PRED_CSV_COLS = {
    "dlt": [("compound_front", "compound_back"), ("s1_front", "s1_back"),
            ("s2_front", "s2_back"), ("s3_front", "s3_back")],
    "ssq": [("compound_red", "compound_blue"), ("s1_red", "s1_blue"),
            ("s2_red", "s2_blue"), ("s3_red", "s3_blue")],
    "kl8": [("compound", None), ("s1", None), ("s2", None), ("s3", None)],
    "pl5": [(None, None), ("s1", None), ("s2", None), ("s3", None)],
    "qxc": [("compound_front", "compound_back"), ("s1_front", "s1_back"),
            ("s2_front", "s2_back"), ("s3_front", "s3_back")],
}

def load_predictions(cfg_id, period):
    """尝试加载对应的预测记录（优先 JSON 存档，回退到 CSV 存档）"""
    pred_dir = os.path.join(BASE, "data/predictions")
    if not os.path.isdir(pred_dir):
        return None
    # 1) 每期 JSON 存档
    for fname in sorted(os.listdir(pred_dir), reverse=True):
        if fname.startswith(f"{cfg_id}_") and fname.endswith(".json"):
            with open(os.path.join(pred_dir, fname), encoding="utf-8") as f:
                pred = json.load(f)
            if pred.get("period") == period:
                return pred
    # 2) CSV 存档（Workflow 当前写盘格式）
    csv_path = os.path.join(pred_dir, f"{cfg_id}_predictions.csv")
    if os.path.isfile(csv_path):
        with open(csv_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("period_id") != period:
                    continue
                bets = []
                for main_col, sub_col in PRED_CSV_COLS.get(cfg_id, []):
                    main_val = (row.get(main_col) or "").strip() if main_col else ""
                    if not main_val:
                        continue
                    sub_val = (row.get(sub_col) or "").strip() if sub_col else ""
                    bets.append({"main": main_val.split(),
                                 "sub": sub_val.split() if sub_val else []})
                if bets:
                    return {"lottery_type": cfg_id, "period": period,
                            "predicted_at": row.get("pred_time", ""),
                            "bets": bets, "notes": row.get("notes", "")}
    return None

# ── 结构分析 ────────────────────────────
def analyze_draw(draw, cfg_id):
    cfg = CFG[cfg_id]
    mains = [int(x) for x in draw["main"]]
    subs = [int(x) for x in draw.get("sub", [])]
    rng = cfg["main_range"]

    result = {"period": draw["period"]}

    # 奇偶比
    odd = sum(1 for x in mains if x % 2 == 1)
    even = len(mains) - odd
    result["parity"] = f"{odd}:{even}"

    # 大小比
    big = sum(1 for x in mains if x >= cfg["size_split"])
    small = len(mains) - big
    result["size"] = f"{small}:{big}"

    # 和值
    result["sum"] = sum(mains)

    # 012路
    roads = {"0": 0, "1": 0, "2": 0}
    for x in mains:
        roads[str(x % 3)] += 1
    result["road"] = f"{roads['0']}:{roads['1']}:{roads['2']}"

    # 质数
    result["primes"] = sum(1 for x in mains if x in cfg["primes"])

    # 连号
    cons = sum(1 for i in range(len(mains)-1) if mains[i+1]-mains[i]==1)
    result["consecutive"] = cons

    # 跨度
    result["span"] = max(mains) - min(mains)

    # 区间
    if cfg["zones"]:
        zones = [sum(1 for x in mains if lo <= x <= hi) for lo, hi in cfg["zones"]]
        result["zones"] = ":".join(str(z) for z in zones)

    # 重号（需要上期数据）
    result["repeat"] = None  # 后面填

    # 同尾
    tails = Counter(x % 10 for x in mains)
    result["same_tail_groups"] = sum(1 for v in tails.values() if v >= 2)

    # 后区
    if subs:
        result["sub_parity"] = f"{sum(1 for x in subs if x%2==1)}:{sum(1 for x in subs if x%2==0)}"
        if cfg.get("size_split") and cfg["sub_range"]:
            sub_split = (cfg["sub_range"][0] + cfg["sub_range"][1]) // 2 + 1
            result["sub_size"] = f"{sum(1 for x in subs if x<sub_split)}:{sum(1 for x in subs if x>=sub_split)}"

    return result

# ── 偏离度评分 ────────────────────────────
def score_deviation(analyzed, params, cfg_id):
    """0-100 分，越低越极端"""
    score = 100
    issues = []
    p = params.get(cfg_id, {})

    # 检查是否在结构正常范围内
    struct = p.get("structure", {})
    if "sum_range" in struct:
        lo, hi = struct["sum_range"]
        if not (lo <= analyzed["sum"] <= hi):
            z = (analyzed["sum"] - struct.get("sum_mean", 0)) / max(struct.get("sum_std", 1), 1)
            issues.append(f"和值{analyzed['sum']}在[{lo},{hi}]外(z={z:+.1f}σ)")
            score -= min(30, abs(z) * 10)

    # 连号
    morph = p.get("morphology", {})
    if "consecutive_rate" in morph:
        if analyzed.get("consecutive", 0) >= 3:
            issues.append(f"三连号以上(概率<5%)")
            score -= 15

    # 质数
    pr = struct.get("prime_range", [0, 99])
    if analyzed["primes"] < pr[0]:
        issues.append(f"质数{analyzed['primes']}个<下限{pr[0]}")
        score -= 10
    if analyzed["primes"] > pr[1]:
        issues.append(f"质数{analyzed['primes']}个>上限{pr[1]}")
        score -= 10

    return max(0, score), issues

# ── 预测对比 ────────────────────────────
def compare_prediction(analyzed, prediction, cfg_id):
    """对比预测命中数"""
    if not prediction:
        return None
    cfg = CFG[cfg_id]
    actual_main = set(str(x).zfill(2) for x in [int(x) for x in analyzed.get("_raw_main", [])])
    actual_sub = set(str(x).zfill(2) for x in [int(x) for x in analyzed.get("_raw_sub", [])])

    bets = prediction.get("bets", [])
    results = []
    for i, bet in enumerate(bets):
        pred_main = set(str(x).zfill(2) for x in bet.get("main", []))
        pred_sub = set(str(x).zfill(2) for x in bet.get("sub", []))
        hit_main = len(pred_main & actual_main)
        hit_sub = len(pred_sub & actual_sub)
        results.append({"bet": i+1, "main_hit": hit_main, "sub_hit": hit_sub,
                        "main_matched": sorted(pred_main & actual_main),
                        "sub_matched": sorted(pred_sub & actual_sub)})
    return results

# ── 参数建议 ────────────────────────────
def suggest_tuning(analyzed, params, cfg_id, recent_draws):
    """检查参数是否需要调整"""
    suggestions = []
    p = params.get(cfg_id, {})

    # 检查深冻阈值是否被突破
    df = p.get("deep_freeze", {})
    if df.get("enabled") and recent_draws:
        # 简单检查：最近N期有无号码遗漏超过阈值
        pass  # 复杂逻辑后续补充

    # 检查结构覆盖是否偏离
    struct = p.get("structure", {})
    if "sum_range" in struct:
        lo, hi = struct["sum_range"]
        recent_sums = [sum(int(x) for x in d["main"]) for d in recent_draws[-20:]]
        outside = sum(1 for s in recent_sums if s < lo or s > hi)
        if outside > 6:  # 30%+ 偏离
            suggestions.append(f"⚠️ 近20期和值{outside}次出界(>30%)，考虑放宽[{lo},{hi}]")

    return suggestions

# ── 输出 ────────────────────────────
def report(cfg_id, draw, analyzed, params, pred_result, suggestions, prev_draw):
    cfg = CFG[cfg_id]
    p = params.get(cfg_id, {})

    print(f"\n{'='*60}")
    print(f"  📊 {cfg_id.upper()} 赛后复盘 —— {draw['period']}期")
    print(f"  🕐 {datetime.now(BJT).strftime('%Y-%m-%d %H:%M:%S')} 北京")
    print(f"{'='*60}")

    # 开奖号码
    print(f"\n🎰 开奖号码: {' '.join(draw['main'])}", end="")
    if draw.get("sub"):
        print(f" + {' '.join(draw['sub'])}", end="")
    print()

    # 结构快照
    print(f"\n📐 结构快照:")
    print(f"  奇偶={analyzed['parity']}  大小={analyzed['size']}  和值={analyzed['sum']}")
    print(f"  012路={analyzed['road']}  质数={analyzed['primes']}个  跨度={analyzed['span']}")
    if "zones" in analyzed:
        print(f"  区间={analyzed['zones']}  连号={analyzed['consecutive']}组  同尾={analyzed['same_tail_groups']}组")
    if "sub_parity" in analyzed:
        print(f"  后区奇偶={analyzed['sub_parity']}  后区大小={analyzed.get('sub_size','N/A')}")

    # 偏离度
    score, issues = score_deviation(analyzed, params, cfg_id)
    emoji = "🟢" if score > 80 else ("🟡" if score > 50 else "🔴")
    print(f"\n📏 结构正常度: {emoji} {score}/100")
    if issues:
        for iss in issues:
            print(f"  ⚡ {iss}")

    # 重号
    if prev_draw:
        prev_main = set(prev_draw["main"])
        curr_main = set(draw["main"])
        repeats = len(prev_main & curr_main)
        print(f"\n🔄 重号: {repeats}个 ({', '.join(sorted(prev_main & curr_main)) if repeats else '无'})")

    # 预测对比
    if pred_result:
        print(f"\n🎯 预测命中:")
        for r in pred_result:
            total_hit = r["main_hit"] + r["sub_hit"]
            star = "⭐" if total_hit >= 4 else ("✅" if total_hit >= 2 else ("➖" if total_hit >= 1 else "❌"))
            detail = ""
            if r["main_matched"]:
                detail += f"主区命中:{','.join(r['main_matched'])} "
            if r["sub_matched"]:
                detail += f"副区命中:{','.join(r['sub_matched'])}"
            print(f"  {star} 注{r['bet']}: {r['main_hit']}+{r['sub_hit']}={total_hit}中 {detail}")
    else:
        print(f"\n💤 无预测记录（需要先运行 Workflow 并保存预测）")

    # 参数建议
    if suggestions:
        print(f"\n🔧 参数建议:")
        for s in suggestions:
            print(f"  {s}")
    else:
        print(f"\n✅ 参数无需调整")

    # 下次提示
    struct_ref = p.get("structure", {})
    if "sum_range" in struct_ref:
        lo, hi = struct_ref["sum_range"]
        if analyzed["sum"] > hi:
            print(f"\n💡 下期提示: 和值偏高(z>+{1.0:.0f}σ)，建议下次预测压回{struct_ref.get('sum_mean',0)}附近")
        elif analyzed["sum"] < lo:
            print(f"\n💡 下期提示: 和值偏低，建议下次预测拉回{struct_ref.get('sum_mean',0)}附近")
    if analyzed.get("consecutive", 0) >= 3:
        print(f"💡 下期提示: 三连号是小概率事件，下期大概率无连号")
    if analyzed.get("primes", 0) == 0:
        print(f"💡 下期提示: 0质数是极端事件，下期必回补1-3个质数")

    print()

# ── 主入口 ────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/post_draw.py <彩种> [期号]")
        print("彩种: dlt/ssq/kl8/pl5/qxc/all")
        sys.exit(1)

    target = sys.argv[1].lower()
    period = sys.argv[2] if len(sys.argv) > 2 else None

    if target == "all":
        targets = list(CFG.keys())
    elif target in CFG:
        targets = [target]
    else:
        print(f"未知彩种: {target}")
        sys.exit(1)

    params = load_params()

    for cfg_id in targets:
        draws = load_draws(cfg_id)
        if not draws:
            print(f"❌ {cfg_id}: 无数据")
            continue

        # 取指定期或最新期
        if period:
            draw = next((d for d in draws if d["period"] == period), None)
            if not draw:
                print(f"❌ {cfg_id}: 找不到期号{period}")
                continue
            idx = draws.index(draw)
        else:
            draw = draws[-1]
            idx = len(draws) - 1

        prev = draws[idx-1] if idx > 0 else None
        analyzed = analyze_draw(draw, cfg_id)
        analyzed["_raw_main"] = draw["main"]
        analyzed["_raw_sub"] = draw.get("sub", [])

        prediction = load_predictions(cfg_id, draw["period"])
        pred_result = compare_prediction(analyzed, prediction, cfg_id) if prediction else None

        suggestions = suggest_tuning(analyzed, params, cfg_id, draws)

        report(cfg_id, draw, analyzed, params, pred_result, suggestions, prev)

    print("✅ 复盘完成！")

if __name__ == "__main__":
    main()
