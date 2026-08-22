# -*- coding: utf-8 -*-
"""一次性修复: pl5_draws.csv 期号格式统一 + 去重 + 排序。

背景:
- 历史数据期号有三种写法: 4位 "4001"(2004年), 5位 "26124"(2026年124期), 7位 "2026127"
- 2026-08-22 同步时按字符串排序/去重, 导致期号乱序 + 14 期双格式重复
- 本脚本全部规范为 7 位 YYYYDDD, 冲突时保留 7 位官方源记录(已核对号码一致)
"""
import csv
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CSV_PATH = "data/processed/pl5_draws.csv"
FIELDS = ["lottery_type", "period_id", "d1", "d2", "d3", "d4", "d5"]


def normalize_pid(pid: str) -> str:
    """规范为 7 位 YYYYDDD。

    4位  "4001"  -> "2004001"  (2004年, 原始为 04001 去掉了前导零)
    5位  "10001" -> "2010001"  (2010年)
    5位  "26124" -> "2026124"  (2026年)
    7位  "2026124" -> 原样
    """
    if not pid.isdigit():
        return pid
    n = len(pid)
    if n == 7:
        return pid
    if n == 4:
        return "20" + pid.zfill(5)  # "4001" -> "04001" -> "2004001"
    if n == 5:
        return "20" + pid  # "26124" -> "2026124"
    return pid


def main():
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"修复前: {len(rows)} 行")

    merged = {}
    conflicts = []
    for r in rows:
        pid = normalize_pid(r["period_id"])
        r = dict(r, period_id=pid)
        if pid in merged:
            old = merged[pid]
            same = all(old[c] == r[c] for c in FIELDS[2:])
            conflicts.append((pid, "号码一致" if same else "号码不一致"))
            if not same:
                # 号码冲突时保留后读入的行(7位官方源在文件后部)
                merged[pid] = r
        else:
            merged[pid] = r

    if conflicts:
        print(f"双格式重复: {len(conflicts)} 期")
        for pid, status in conflicts:
            print(f"  {pid}: {status}")

    all_rows = sorted(merged.values(), key=lambda x: int(x["period_id"]))
    print(f"修复后: {len(all_rows)} 行, {all_rows[0]['period_id']} ~ {all_rows[-1]['period_id']}")

    # 单调性校验
    pids = [int(r["period_id"]) for r in all_rows]
    for i in range(1, len(pids)):
        assert pids[i] > pids[i - 1], f"排序异常: {pids[i-1]} -> {pids[i]}"
    # 格式校验: 全部 7 位
    assert all(len(r["period_id"]) == 7 for r in all_rows), "存在非7位期号"
    print("校验通过: 全部 7 位期号, 严格递增")

    # 备份原文件
    bak = CSV_PATH + ".bak_20260822"
    if not os.path.exists(bak):
        import shutil
        shutil.copy2(CSV_PATH, bak)
        print(f"原文件备份: {bak}")

    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(all_rows)
    print(f"已写入 {CSV_PATH}")

    # 更新 manifest 中 pl5 的行数与最新期号
    manifest_path = "data/processed/manifest.json"
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        for block in manifest.get("outputs", []):
            if block.get("lottery_type") == "pl5":
                block["rows_out"] = len(all_rows)
                block["period_id_max"] = int(all_rows[-1]["period_id"])
                block.setdefault("fixes", {})["fix_period_format_20260822"] = (
                    f"期号统一为7位YYYYDDD, 去重{len(conflicts)}期双格式重复, "
                    f"{len(rows)}行 -> {len(all_rows)}行"
                )
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print("manifest 已更新")


if __name__ == "__main__":
    main()
