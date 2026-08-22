#!/usr/bin/env python3
"""全彩种官方源增量同步 —— 从 cwl.gov.cn(福彩) / sporttery.cn(体彩)
拉取最新开奖记录, 补全 data/processed/*.csv 中缺失的期号。

用法:
  python scripts/sync_all_official.py [--type ALL|SSQ|DLT|KL8|PL5|QXC]

不依赖 Playwright, 纯 urllib 实现。
"""

import argparse
import csv
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8")

BJT = timezone(timedelta(hours=8))
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.sporttery.cn/",
}

# ── 配置 ──
CWL_BASE = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
STC_BASE = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"

SOURCES = {
    "SSQ": {"api": "cwl", "name": "ssq"},
    "KL8": {"api": "cwl", "name": "kl8"},
    "DLT": {"api": "stc", "gameNo": "85"},
    "PL5": {"api": "stc", "gameNo": "350133"},
    "QXC": {"api": "stc", "gameNo": "04"},
}

CSV_PATH = {
    "SSQ": "data/processed/ssq_draws.csv",
    "DLT": "data/processed/dlt_draws.csv",
    "KL8": "data/processed/kl8_draws.csv",
    "PL5": "data/processed/pl5_draws.csv",
    "QXC": "data/processed/qxc_draws.csv",
}

FIELDNAMES = {
    "SSQ": ["lottery_type", "period_id", "red_1", "red_2", "red_3", "red_4", "red_5", "red_6", "blue"],
    "DLT": ["lottery_type", "period_id", "front_1", "front_2", "front_3", "front_4", "front_5", "back_1", "back_2"],
    "KL8": ["lottery_type", "period_id"] + [f"n{i:02d}" for i in range(1, 21)],
    "PL5": ["lottery_type", "period_id", "d1", "d2", "d3", "d4", "d5"],
    "QXC": ["lottery_type", "period_id", "d1", "d2", "d3", "d4", "d5", "d6", "special"],
}

MANIFEST_PATH = "data/processed/manifest.json"
RAW_DIR = "data/raw"


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout, context=ctx).read().decode("utf-8", errors="replace")


def fetch_cwl_latest(name, count=100):
    """福彩 API: 拉取最近 count 期, 返回 list[dict]。
    用 pageNo+pageSize 分页(与 verify_lottery_data.py 一致),
    issueCount 参数在无浏览器时可能 404。
    """
    page = 1
    page_size = min(count, 100)
    url = (f"{CWL_BASE}?name={name}&pageNo={page}&pageSize={page_size}"
           f"&systemType=PC")
    j = json.loads(fetch(url))
    if j.get("state") != 0:
        print(f"  CWL API 返回异常: {j}")
        return []
    rows = j.get("result") or []
    total = j.get("total") or 0
    # 如需更多页继续拉取
    while page * page_size < total and len(rows) < count:
        page += 1
        time.sleep(0.3)
        url = (f"{CWL_BASE}?name={name}&pageNo={page}&pageSize={page_size}"
               f"&systemType=PC")
        j2 = json.loads(fetch(url))
        rows2 = j2.get("result") or []
        if not rows2:
            break
        rows.extend(rows2)
    return rows[:count] if count < len(rows) else rows


def fetch_stc_latest(game_no, page_size=100):
    """体彩 API: 拉取第 1 页(最新100期), 返回 list[dict]。"""
    url = f"{STC_BASE}?gameNo={game_no}&provinceId=0&pageSize={page_size}&isVerify=1&pageNo=1"
    j = json.loads(fetch(url))
    value = j.get("value") or {}
    return value.get("list") or []


def load_existing(game):
    """读取本地 CSV, 返回 {period_id: row_dict}。"""
    path = CSV_PATH[game]
    existing = {}
    if not os.path.exists(path):
        return existing
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existing[row["period_id"]] = row
    return existing


def parse_ssq(draws):
    """解析福彩双色球: red(6) + blue(1)。"""
    out = []
    for d in draws:
        pid = d.get("code")
        if not pid:
            continue
        reds = [x for x in (d.get("red") or "").split(",") if x]
        blue = d.get("blue") or ""
        if len(reds) != 6 or not blue:
            continue
        reds = [f"{int(r):02d}" for r in reds]
        blue = f"{int(blue):02d}"
        out.append({
            "lottery_type": "ssq", "period_id": pid,
            "red_1": reds[0], "red_2": reds[1], "red_3": reds[2],
            "red_4": reds[3], "red_5": reds[4], "red_6": reds[5],
            "blue": blue,
        })
    return out


def parse_kl8(draws):
    """解析福彩快乐八: 20 个号码, 不补零。"""
    out = []
    for d in draws:
        pid = d.get("code")
        if not pid:
            continue
        reds = [x for x in (d.get("red") or "").split(",") if x]
        if len(reds) != 20:
            continue
        nums = sorted(int(r) for r in reds)
        row = {"lottery_type": "kl8", "period_id": pid}
        for i, n in enumerate(nums, 1):
            row[f"n{i:02d}"] = str(n)
        out.append(row)
    return out


def parse_dlt(draws):
    """解析体彩大乐透: 前5(01-35) + 后2(01-12), 补零, 升序。"""
    out = []
    for d in draws:
        num = d.get("lotteryDrawNum")
        if not num:
            continue
        pid = "20" + num  # 5位 -> 7位
        res = (d.get("lotteryDrawResult") or "").split()
        if len(res) != 7:
            continue
        fronts = sorted(f"{int(x):02d}" for x in res[:5])
        backs = sorted(f"{int(x):02d}" for x in res[5:])
        # 校验范围
        if not all(1 <= int(f) <= 35 for f in fronts):
            continue
        if not all(1 <= int(b) <= 12 for b in backs):
            continue
        out.append({
            "lottery_type": "dlt", "period_id": pid,
            "front_1": fronts[0], "front_2": fronts[1], "front_3": fronts[2],
            "front_4": fronts[3], "front_5": fronts[4],
            "back_1": backs[0], "back_2": backs[1],
        })
    return out


def parse_pl5(draws):
    """解析体彩排列5: 5 位数字(0-9), 按位, 不排序。"""
    out = []
    for d in draws:
        num = d.get("lotteryDrawNum")
        if not num:
            continue
        pid = "20" + num  # 5位 -> 7位
        res = (d.get("lotteryDrawResult") or "").split()
        if len(res) != 5:
            continue
        if not all(r.isdigit() and 0 <= int(r) <= 9 for r in res):
            continue
        out.append({
            "lottery_type": "pl5", "period_id": pid,
            "d1": res[0], "d2": res[1], "d3": res[2], "d4": res[3], "d5": res[4],
        })
    return out


def parse_qxc(draws):
    """解析体彩七星彩: 前6位(0-9) + 后区1位(0-14), 按位, 期号保持5位。"""
    out = []
    for d in draws:
        num = d.get("lotteryDrawNum")
        if not num:
            continue
        pid = num  # QXC CSV 用 5 位期号
        res = (d.get("lotteryDrawResult") or "").split()
        if len(res) != 7:
            continue
        front = res[:6]
        special = res[6]
        if not all(f.isdigit() and 0 <= int(f) <= 9 for f in front):
            continue
        if not (special.isdigit() and 0 <= int(special) <= 14):
            continue
        out.append({
            "lottery_type": "qxc", "period_id": pid,
            "d1": front[0], "d2": front[1], "d3": front[2],
            "d4": front[3], "d5": front[4], "d6": front[5],
            "special": special,
        })
    return out


PARSERS = {
    "SSQ": parse_ssq,
    "KL8": parse_kl8,
    "DLT": parse_dlt,
    "PL5": parse_pl5,
    "QXC": parse_qxc,
}


def sync_game(game):
    """同步单个彩种, 返回新增期数。"""
    print(f"\n{'='*50}")
    print(f"  {game} 同步中...")
    print(f"{'='*50}")

    src = SOURCES[game]
    # 1. 拉取官方数据
    if src["api"] == "cwl":
        raw_draws = fetch_cwl_latest(src["name"], count=100)
        print(f"  官方 API 返回: {len(raw_draws)} 条记录")
    else:
        raw_draws = fetch_stc_latest(src["gameNo"], page_size=100)
        print(f"  官方 API 返回: {len(raw_draws)} 条记录")

    if not raw_draws:
        print(f"  ⚠ 未能获取 {game} 数据, 跳过")
        return 0

    # 2. 解析
    parsed = PARSERS[game](raw_draws)
    if not parsed:
        print(f"  ⚠ 解析后无有效记录, 跳过")
        return 0
    print(f"  解析有效: {len(parsed)} 条, 最新期号: {parsed[0]['period_id']}")

    # 3. 读本地已有
    existing = load_existing(game)
    print(f"  本地 CSV: {len(existing)} 期, 最新: {max(existing.keys()) if existing else 'N/A'}")

    # 4. 筛选新增
    new_draws = [d for d in parsed if d["period_id"] not in existing]
    # 去重 (万一 API 返回重复)
    seen = set()
    new_draws_unique = []
    for d in new_draws:
        if d["period_id"] not in seen:
            seen.add(d["period_id"])
            new_draws_unique.append(d)
    new_draws = new_draws_unique
    new_draws.sort(key=lambda x: x["period_id"])

    if not new_draws:
        print(f"  ✅ 已是最新, 无需同步")
        return 0

    print(f"  缺失期数: {len(new_draws)}, 范围: {new_draws[0]['period_id']} ~ {new_draws[-1]['period_id']}")

    # 5. raw 备份
    os.makedirs(RAW_DIR, exist_ok=True)
    ts = datetime.now(BJT).strftime("%Y%m%d_%H%M%S")
    raw_file = os.path.join(RAW_DIR, f"{game.lower()}_official_sync_{ts}.json")
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump({
            "fetched_at": datetime.now(BJT).isoformat(),
            "source": "cwl.gov.cn" if src["api"] == "cwl" else "sporttery.cn",
            "draws": new_draws,
        }, f, ensure_ascii=False, indent=2)
    print(f"  raw 备份: {raw_file}")

    # 6. 合并写入 CSV
    all_rows = list(existing.values()) + new_draws
    all_rows.sort(key=lambda x: x["period_id"])
    csv_path = CSV_PATH[game]
    fields = FIELDNAMES[game]

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)

    with open(csv_path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    print(f"  CSV 写入完成, 总行数: {len(all_rows)}, SHA256: {sha[:16]}...")

    # 7. 期号单调性校验
    pids = [r["period_id"] for r in all_rows]
    ok = True
    for i in range(1, len(pids)):
        if pids[i] <= pids[i - 1]:
            print(f"  ⚠ 期号排序异常: {pids[i-1]} -> {pids[i]}")
            ok = False
            break
    if ok:
        print(f"  ✅ 期号单调递增")

    # 8. 更新 manifest
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        for block in manifest.get("outputs", []):
            if block.get("lottery_type") == game.lower():
                block["rows_out"] = len(all_rows)
                block["period_id_max"] = all_rows[-1]["period_id"] if all_rows[-1]["period_id"].isdigit() else int(all_rows[-1]["period_id"])
                if "supplement" not in block:
                    block["supplement"] = {}
                key = f"official_sync_{datetime.now(BJT).strftime('%Y%m%d')}"
                block["supplement"][key] = {
                    "rows_added": len(new_draws),
                    "period_ids": [d["period_id"] for d in new_draws],
                    "source_note": f"{'cwl.gov.cn' if src['api'] == 'cwl' else 'sporttery.cn'} 官方API自动同步 {datetime.now(BJT).strftime('%Y-%m-%d')}",
                    "official_verify": "已与官方API数据核对",
                }
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"  manifest 已更新")

    # 9. 打印新增明细
    print(f"\n  📋 新增 {len(new_draws)} 期 {game} 开奖明细:")
    for d in new_draws:
        if game == "SSQ":
            print(f"    {d['period_id']}: {d['red_1']} {d['red_2']} {d['red_3']} {d['red_4']} {d['red_5']} {d['red_6']} + {d['blue']}")
        elif game == "DLT":
            print(f"    {d['period_id']}: {d['front_1']} {d['front_2']} {d['front_3']} {d['front_4']} {d['front_5']} + {d['back_1']} {d['back_2']}")
        elif game == "KL8":
            nums = [d[f"n{i:02d}"] for i in range(1, 21)]
            print(f"    {d['period_id']}: {', '.join(nums)}")
        elif game == "PL5":
            print(f"    {d['period_id']}: {d['d1']} {d['d2']} {d['d3']} {d['d4']} {d['d5']}")
        elif game == "QXC":
            print(f"    {d['period_id']}: {d['d1']} {d['d2']} {d['d3']} {d['d4']} {d['d5']} {d['d6']} + {d['special']}")

    return len(new_draws)


def main():
    ap = argparse.ArgumentParser(description="全彩种官方源增量同步")
    ap.add_argument("--type", default="ALL", help="ALL|SSQ|DLT|KL8|PL5|QXC")
    args = ap.parse_args()

    keys = [k for k in SOURCES if args.type.upper() == "ALL" or k == args.type.upper()]
    print(f"📅 同步时间: {datetime.now(BJT).strftime('%Y-%m-%d %H:%M:%S')} BJT")
    print(f"🎯 目标彩种: {', '.join(keys)}")

    total_new = 0
    for game in keys:
        try:
            total_new += sync_game(game)
            time.sleep(0.5)  # 请求间隔
        except Exception as e:
            print(f"\n  ❌ {game} 同步失败: {e}")

    print(f"\n{'='*50}")
    print(f"  同步完成! 共新增 {total_new} 期")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
