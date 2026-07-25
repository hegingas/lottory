#!/usr/bin/env python3
"""彩票走势图数据预处理管线 — CSV → JSON 统计数据集"""

import csv
import json
import os
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_DIR = BASE_DIR / "data" / "processed"
OUT_DIR = Path(__file__).resolve().parent / "data"

LOTTERY_CONFIG = {
    "ssq": {
        "name": "双色球", "type": "ssq",
        "main_range": [1, 33], "main_count": 6,
        "sub_range": [1, 16], "sub_count": 1,
        "main_cols": ["red_1", "red_2", "red_3", "red_4", "red_5", "red_6"],
        "sub_cols": ["blue"],
        "csv": "ssq_draws.csv",
    },
    "dlt": {
        "name": "大乐透", "type": "dlt",
        "main_range": [1, 35], "main_count": 5,
        "sub_range": [1, 12], "sub_count": 2,
        "main_cols": ["front_1", "front_2", "front_3", "front_4", "front_5"],
        "sub_cols": ["back_1", "back_2"],
        "csv": "dlt_draws.csv",
    },
    "kl8": {
        "name": "快乐八", "type": "kl8",
        "main_range": [1, 80], "main_count": 20,
        "sub_range": None, "sub_count": 0,
        "main_cols": [f"n{i:02d}" for i in range(1, 21)],
        "sub_cols": [],
        "csv": "kl8_draws.csv",
    },
    "pl5": {
        "name": "排列5", "type": "pl5",
        "main_range": [0, 9], "main_count": 5,
        "sub_range": None, "sub_count": 0,
        "main_cols": ["d1", "d2", "d3", "d4", "d5"],
        "sub_cols": [],
        "csv": "pl5_draws.csv",
        "positional": True,  # 按位分析
    },
    "qxc": {
        "name": "七星彩", "type": "qxc",
        "main_range": [0, 9], "main_count": 6,
        "sub_range": [0, 14], "sub_count": 1,
        "main_cols": ["d1", "d2", "d3", "d4", "d5", "d6"],
        "sub_cols": ["special"],
        "csv": "qxc_draws.csv",
        "positional": True,
    },
}


def is_prime(n):
    if n < 2: return False
    for i in range(2, int(n**0.5)+1):
        if n % i == 0: return False
    return True


def compute_ac_value(nums):
    """AC值：所有两两差值的绝对值去重后数量 - (len-1)"""
    diffs = set()
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            diffs.add(abs(nums[i] - nums[j]))
    return len(diffs) - (len(nums) - 1)


def compute_012_route(nums):
    """返回每个号码的 012 路分类"""
    return [n % 3 for n in nums]


def read_csv(csv_path, config):
    draws = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            period = row["period_id"].strip()
            main = [int(row[c]) for c in config["main_cols"]]
            sub = [int(row[c]) for c in config["sub_cols"]] if config["sub_cols"] else []
            # 按位彩种不排序 main(保留位置信息), 非按位彩种排序
            is_pos = config.get("positional", False)
            draws.append({"period": period, "main": main if is_pos else sorted(main), "sub": sorted(sub) if sub else []})
    # 按期号数值排序(字符串排序会把"9358"排在"2026195"后面)
    draws.sort(key=lambda d: int(d["period"]))
    return draws


def compute_frequency(draws, n_range, is_sub=False):
    """计算每个号码的历史出现次数"""
    freq = defaultdict(int)
    key = "sub" if is_sub else "main"
    for d in draws:
        for n in d[key]:
            freq[n] += 1
    lo, hi = n_range
    return {str(n): freq.get(n, 0) for n in range(lo, hi + 1)}


def compute_omission(draws, n_range, is_sub=False):
    """计算每个号码的当前遗漏（距上次开出还有多少期）"""
    total = len(draws)
    lo, hi = n_range
    last_seen = {}
    for idx, d in enumerate(draws):
        key = "sub" if is_sub else "main"
        for n in d[key]:
            last_seen[n] = idx
    result = {}
    for n in range(lo, hi + 1):
        if n in last_seen:
            result[str(n)] = total - 1 - last_seen[n]
        else:
            result[str(n)] = total  # 从未出现
    return result


def compute_max_omission(draws, n_range, is_sub=False):
    """计算每个号码的历史最大遗漏"""
    lo, hi = n_range
    key = "sub" if is_sub else "main"
    prev = {n: -1 for n in range(lo, hi + 1)}
    max_gap = {n: 0 for n in range(lo, hi + 1)}
    for idx, d in enumerate(draws):
        for n in range(lo, hi + 1):
            if n in d[key]:
                gap = idx - prev[n] - 1
                if gap > max_gap[n]:
                    max_gap[n] = gap
                prev[n] = idx
    # 最后还要算到最新一期
    total = len(draws)
    for n in range(lo, hi + 1):
        gap = total - 1 - prev[n]
        if gap > max_gap[n]:
            max_gap[n] = gap
    return {str(n): v for n, v in max_gap.items()}


def compute_last_n_stats(draws, config, n=50):
    """计算最近 N 期的逐期统计"""
    recent = draws[-n:] if len(draws) >= n else draws
    lo_m, hi_m = config["main_range"]
    m_cnt = config["main_count"]
    stats = {
        "sum": [], "span": [], "odd_even": [], "big_small": [],
        "consecutive": [], "repeat": [], "periods": [],
    }

    # 额外字段
    has_sub = config["sub_range"] is not None
    is_positional = config.get("positional", False)

    if not is_positional:
        stats["zone_dist"] = []
        stats["route012"] = []
        stats["ac_value"] = []
    # KL8 只需要 zone_dist，不需要 route012 和 ac_value
    if config["type"] == "kl8":
        stats["route012"] = []
        stats["ac_value"] = []

    mid = (lo_m + hi_m) // 2
    # 区间划分 (SSQ: 1-11, 12-22, 23-33; DLT: 1-12, 13-24, 25-35)
    if config["type"] == "ssq":
        zones = [(1, 11), (12, 22), (23, 33)]
    elif config["type"] == "dlt":
        zones = [(1, 12), (13, 24), (25, 35)]
    elif config["type"] == "kl8":
        zones = [(1, 20), (21, 40), (41, 60), (61, 80)]
    else:
        zones = []

    for i, d in enumerate(recent):
        main = d["main"]
        sub = d.get("sub", [])
        stats["periods"].append(d["period"])
        stats["sum"].append(sum(main))
        stats["span"].append(max(main) - min(main))

        odd = sum(1 for x in main if x % 2 == 1)
        stats["odd_even"].append([odd, m_cnt - odd])

        if not is_positional:
            big = sum(1 for x in main if x > mid)
            stats["big_small"].append([big, m_cnt - big])

        # 连号
        cons = sum(1 for j in range(len(main)-1) if main[j+1] - main[j] == 1)
        stats["consecutive"].append(cons)

        # 重号（与上一期比较）
        if i > 0:
            prev_main = set(recent[i-1]["main"])
            rep = sum(1 for x in main if x in prev_main)
            stats["repeat"].append(rep)
        else:
            stats["repeat"].append(0)

        # 区间
        if zones:
            zc = []
            for zl, zh in zones:
                zc.append(sum(1 for x in main if zl <= x <= zh))
            stats["zone_dist"].append(zc)

        # 012路
        if not is_positional and config["type"] != "kl8":
            rts = compute_012_route(main)
            stats["route012"].append([rts.count(0), rts.count(1), rts.count(2)])
            stats["ac_value"].append(compute_ac_value(main))

    return stats


def compute_number_grid(draws, config, n=50):
    """生成号码网格数据（类似新浪走势图）：每个号码在每个期号下是"开出"还是"遗漏计数" """
    recent = draws[-n:] if len(draws) >= n else draws
    lo_m, hi_m = config["main_range"]
    has_sub = config["sub_range"] is not None

    grid = {"periods": [], "main": {}, "sub": {}}

    # 初始化遗漏计数
    main_omission = {str(x): 0 for x in range(lo_m, hi_m + 1)}
    if has_sub:
        lo_s, hi_s = config["sub_range"]
        sub_omission = {str(x): 0 for x in range(lo_s, hi_s + 1)}

    for d in recent:
        grid["periods"].append(d["period"])
        for n in range(lo_m, hi_m + 1):
            key = str(n)
            if n in d["main"]:
                grid["main"].setdefault(key, []).append({"hit": True, "omit": 0})
                main_omission[key] = 0
            else:
                main_omission[key] += 1
                grid["main"].setdefault(key, []).append({"hit": False, "omit": main_omission[key]})

        if has_sub:
            lo_s, hi_s = config["sub_range"]
            for n in range(lo_s, hi_s + 1):
                key = str(n)
                if n in d["sub"]:
                    grid["sub"].setdefault(key, []).append({"hit": True, "omit": 0})
                    sub_omission[key] = 0
                else:
                    sub_omission[key] += 1
                    grid["sub"].setdefault(key, []).append({"hit": False, "omit": sub_omission[key]})

    return grid


def compute_positional_freq(draws, config, n=50):
    """排列5/七星彩 按位频率统计"""
    recent = draws[-n:] if len(draws) >= n else draws
    m_cnt = config["main_count"]
    pos_freq = {str(i): defaultdict(int) for i in range(m_cnt)}
    for d in recent:
        for i, val in enumerate(d["main"]):
            pos_freq[str(i)][str(val)] += 1
    # 转普通 dict
    return {k: dict(v) for k, v in pos_freq.items()}


def get_hot_cold(freq_dict, top=10):
    """最热 top N 和最冷 top N"""
    items = sorted(freq_dict.items(), key=lambda x: -x[1])
    hot = [[k, v] for k, v in items[:top]]
    cold = [[k, v] for k, v in items[-top:]]
    cold.reverse()
    return hot, cold


def process_lottery(key, config):
    csv_path = CSV_DIR / config["csv"]
    if not csv_path.exists():
        print(f"  ⚠ 跳过 {config['name']}: {csv_path} 不存在")
        return None

    print(f"  读取 {csv_path.name}...")
    draws = read_csv(csv_path, config)
    print(f"    → {len(draws)} 期 ({draws[0]['period']} ~ {draws[-1]['period']})")

    # 频率
    freq_main = compute_frequency(draws, config["main_range"])
    freq_sub = {}
    if config["sub_range"]:
        freq_sub = compute_frequency(draws, config["sub_range"], is_sub=True)

    # 遗漏
    omission_main = compute_omission(draws, config["main_range"])
    omission_sub = {}
    if config["sub_range"]:
        omission_sub = compute_omission(draws, config["sub_range"], is_sub=True)

    # 最大遗漏
    max_omit_main = compute_max_omission(draws, config["main_range"])
    max_omit_sub = {}
    if config["sub_range"]:
        max_omit_sub = compute_max_omission(draws, config["sub_range"], is_sub=True)

    # 最近 50 期统计
    last50 = compute_last_n_stats(draws, config, n=50)
    last100 = compute_last_n_stats(draws, config, n=100)

    # 号码网格（最近 50 期）
    grid50 = compute_number_grid(draws, config, n=50)

    # 冷热
    hot_main, cold_main = get_hot_cold(freq_main, 10)
    hot_sub, cold_sub = [], []
    if freq_sub:
        hot_sub, cold_sub = get_hot_cold(freq_sub, 5)

    # 按位频率
    pos_freq = {}
    if config.get("positional"):
        pos_freq = compute_positional_freq(draws, config, n=100)

    # 最新一期
    latest = draws[-1]

    result = {
        "metadata": {
            "type": config["type"],
            "name": config["name"],
            "totalDraws": len(draws),
            "periodMin": draws[0]["period"],
            "periodMax": draws[-1]["period"],
            "mainRange": config["main_range"],
            "mainCount": config["main_count"],
            "subRange": config["sub_range"],
            "subCount": config["sub_count"],
            "positional": config.get("positional", False),
        },
        "latest": {
            "period": latest["period"],
            "main": latest["main"],
            "sub": latest["sub"],
        },
        "draws": draws,
        "stats": {
            "frequency": {"main": freq_main, "sub": freq_sub},
            "omission": {"main": omission_main, "sub": omission_sub},
            "maxOmission": {"main": max_omit_main, "sub": max_omit_sub},
            "last50": last50,
            "last100": last100,
            "grid50": grid50,
            "hotCold": {
                "hotMain": hot_main, "coldMain": cold_main,
                "hotSub": hot_sub, "coldSub": cold_sub,
            },
            "positionalFreq": pos_freq,
        },
    }
    return result


def main():
    print("🎰 彩票走势图数据预处理")
    print(f"   输入: {CSV_DIR}")
    print(f"   输出: {OUT_DIR}")
    print()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    summary = {"generatedAt": "", "types": {}}
    all_draws = {}

    for key, config in LOTTERY_CONFIG.items():
        print(f"[{config['name']}]")
        data = process_lottery(key, config)
        if data is None:
            continue

        all_draws[key] = data

        # 写单个文件
        out_path = OUT_DIR / f"{key}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print(f"    ✓ 已写入 {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")

        # 生成 summary
        summary["types"][key] = {
            "name": config["name"],
            "totalDraws": len(data["draws"]),
            "latestPeriod": data["latest"]["period"],
            "latestDraw": data["latest"],
            "periodRange": [data["metadata"]["periodMin"], data["metadata"]["periodMax"]],
        }

    # 时间戳
    from datetime import datetime, timezone, timedelta
    bj = timezone(timedelta(hours=8))
    summary["generatedAt"] = datetime.now(bj).isoformat()

    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  ✓ summary.json")

    # 生成 data.js — 内嵌全部数据，支持 file:// 直接打开
    js_path = OUT_DIR / "data.js"
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("// 自动生成，请勿手动编辑\n")
        f.write("// 运行 python dashboard/preprocess.py 更新\n")
        f.write("window.__LOTTERY_DATA__ = ")
        json.dump({"summary": summary, "detail": all_draws}, f, ensure_ascii=False)
        f.write(";\n")
    print(f"  ✓ data.js ({js_path.stat().st_size / 1024:.0f} KB)")

    print(f"\n✅ 全部完成！{len(all_draws)} 个彩种数据已生成")


if __name__ == "__main__":
    main()
