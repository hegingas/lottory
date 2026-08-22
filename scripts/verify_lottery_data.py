#!/usr/bin/env python3
"""全彩种历史数据交叉验证 —— 官方源(福彩 cwl.gov.cn / 体彩 sporttery.cn)拉全量
开奖记录,与本地 data/processed/*.csv 逐期对比,输出不一致清单。

用法:
  python scripts/verify_lottery_data.py [--type ALL|SSQ|DLT|KL8|PL5|QXC]
"""

import argparse
import csv
import json
import os
import re
import ssl
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://www.sporttery.cn/"}

# ── 官方源定义 ──
SOURCES = {
    "SSQ": {"api": "cwl", "name": "ssq"},
    "KL8": {"api": "cwl", "name": "kl8"},
    "DLT": {"api": "stc", "gameNo": "85"},
    "PL5": {"api": "stc", "gameNo": "350133"},
    "QXC": {"api": "stc", "gameNo": "04"},
}
LOCAL_CSV = {
    "SSQ": "data/processed/ssq_draws.csv",
    "DLT": "data/processed/dlt_draws.csv",
    "KL8": "data/processed/kl8_draws.csv",
    "PL5": "data/processed/pl5_draws.csv",
    "QXC": "data/processed/qxc_draws.csv",
}

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout, context=ctx).read().decode("utf-8", errors="replace")

def fetch_cwl(name):
    """福彩分页拉全量:返回 {period: [号码...]}。"""
    out, page = {}, 1
    while True:
        url = (f"https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice?"
               f"name={name}&pageNo={page}&pageSize=100&systemType=PC")
        j = json.loads(fetch(url))
        rows = j.get("result") or []
        if not rows:
            break
        for r in rows:
            code = r.get("code")
            reds = [x for x in (r.get("red") or "").split(",") if x]
            blue = r.get("blue") or ""
            if blue:  # 双色球:red(6) + blue(1)
                reds = reds + [blue]
            out[code] = reds
        total = j.get("total") or 0
        if page * 100 >= total:
            break
        page += 1
        time.sleep(0.3)
    return out

def fetch_stc(game_no):
    """体彩分页拉全量:返回 {period(7位): [号码...]}。"""
    out, page = {}, 1
    while True:
        url = (f"https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?"
               f"gameNo={game_no}&provinceId=0&pageSize=100&isVerify=1&pageNo={page}")
        j = json.loads(fetch(url))
        value = j.get("value") or {}
        rows = value.get("list") or []
        if not rows:
            break
        for r in rows:
            num = r.get("lotteryDrawNum")
            res = (r.get("lotteryDrawResult") or "").split()
            if num and res:
                out["20" + num] = res  # 5位期号 → 7位
        total = value.get("total") or 0
        if page * 100 >= total:
            break
        page += 1
        time.sleep(0.3)
    return out

def norm_pid(game, pid):
    """本地期号 → 官方 7 位口径。
    PL5: 4001→2004001, 10001→2010001, 7位直通
    QXC: 本地 5 位(=官方 5 位)→ 7 位
    其余: 直通(7 位)
    """
    if game == "PL5":
        if len(pid) == 4:
            return "200" + pid[0] + pid[1:]
        if len(pid) == 5:
            return "20" + pid
        return pid
    if game == "QXC":
        return "20" + pid if len(pid) == 5 else pid
    return pid

def norm_nums(game, nums):
    """号码归一化:组合型补前导零(本地 '5' vs 官方 '05');按位型不补。"""
    if game in ("PL5", "QXC"):
        return list(nums)
    return [f"{int(n):02d}" for n in nums]

def load_local(path):
    """本地 CSV → {period(7位): {front: [...], back: [...]}}。"""
    game = os.path.basename(path).split("_")[0].upper()
    cfg = {
        "SSQ": (["red_1","red_2","red_3","red_4","red_5","red_6"], ["blue"]),
        "DLT": (["front_1","front_2","front_3","front_4","front_5"], ["back_1","back_2"]),
        "KL8": ([f"n{i:02d}" for i in range(1, 21)], []),
        "PL5": (["d1","d2","d3","d4","d5"], []),
        "QXC": (["d1","d2","d3","d4","d5","d6"], ["special"]),
    }[game]
    out = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[norm_pid(game, row["period_id"])] = (
                norm_nums(game, [row[c] for c in cfg[0]]),
                norm_nums(game, [row[c] for c in cfg[1]]))
    return out

def compare(game, local, remote):
    """逐期对比,返回不一致清单 [(period, 本地, 官方)]。"""
    diffs = []
    pos = game in ("PL5", "QXC")  # 按位型:顺序敏感
    for pid, (lfront, lback) in local.items():
        if pid not in remote:
            continue
        rf = remote[pid]
        if game == "SSQ":
            rfront, rback = rf[:6], rf[6:]
        elif game == "KL8":
            rfront, rback = rf[:20], []
        elif game == "DLT":
            rfront, rback = rf[:5], rf[5:]
        elif game == "PL5":
            rfront, rback = rf[:5], []
        else:  # QXC
            rfront, rback = rf[:6], rf[6:]
        if pos:
            lf, lb = lfront, lback
            rf2, rb2 = rfront, rback
        else:
            lf = sorted(lfront, key=int); lb = sorted(lback, key=int)
            rf2 = sorted(rfront, key=int); rb2 = sorted(rback, key=int)
        if lf != rf2 or lb != rb2:
            diffs.append((pid, lfront + lback, rfront + rback))
    return diffs

def main():
    ap = argparse.ArgumentParser(description="全彩种历史数据官方源交叉验证")
    ap.add_argument("--type", default="ALL")
    args = ap.parse_args()
    keys = [k for k in SOURCES if args.type.upper() == "ALL" or k == args.type.upper()]

    for game in keys:
        src = SOURCES[game]
        print(f"\n═══ {game} ═══")
        remote = fetch_cwl(src["name"]) if src["api"] == "cwl" else fetch_stc(src["gameNo"])
        print(f"官方源拉取: {len(remote)} 期")
        local = load_local(LOCAL_CSV[game])
        print(f"本地 CSV: {len(local)} 期")
        diffs = compare(game, local, remote)
        print(f"覆盖对比: {len([p for p in local if p in remote])} 期 | 不一致: {len(diffs)} 期")
        for pid, l, r in diffs[:15]:
            print(f"  {pid}: 本地 {l} vs 官方 {r}")
        if len(diffs) > 15:
            print(f"  ... 共 {len(diffs)} 期")
        # 本地缺失期(官方有本地没有)
        missing = sorted(set(remote) - set(local))
        if missing:
            print(f"本地缺失(官方有): {len(missing)} 期, 范围 {missing[0]}~{missing[-1]}")
        # 保存官方数据
        os.makedirs("data/raw", exist_ok=True)
        out = f"data/raw/{game.lower()}_official_verify.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"source": "official", "draws": remote}, f, ensure_ascii=False)
        print(f"官方数据已存: {out}")

if __name__ == "__main__":
    main()
