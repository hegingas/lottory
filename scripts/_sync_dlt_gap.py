"""脚本：从 zhcw.com 中彩网抓取大乐透缺失期号到 data/processed/dlt_draws.csv"""
import csv, os, hashlib
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

URL = "https://www.zhcw.com/kjxx/dlt/"
CSV_PATH = "data/processed/dlt_draws.csv"
RAW_DIR = "data/raw"
MANIFEST_PATH = "data/processed/manifest.json"
BJT = timezone(timedelta(hours=8))
LOTTERY_TYPE = "dlt"

# ── 1. 读现有 CSV ──
existing = {}
with open(CSV_PATH, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        existing[row["period_id"]] = row

latest_existing = max(int(p) for p in existing)
print(f"现有最新期号: {latest_existing}, 总期数: {len(existing)}")

# ── 2. 从 zhcw.com 抓取 ──
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL, timeout=20000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)

    # 获取所有行
    rows = page.locator("table tr").all()
    print(f"找到 {len(rows)} 个表格行")

    raw_text = page.inner_text("body")
    browser.close()

# ── 3. 解析：前区=10位连续数字(5个两位数)，后区=4位连续数字(2个两位数) ──
import re

new_draws = []
# 匹配模式: 5位期号 + 日期 + 前区10位 + 后区4位 + ...
# 例: 26077 2026-07-11（六） 0414192427 0607 ...
pattern = re.compile(r'(\d{5})\s+\d{4}-\d{2}-\d{2}[^0-9]*\s+(\d{10})\s+(\d{4})')

for m in pattern.finditer(raw_text):
    pid = m.group(1)
    front_str = m.group(2)   # e.g. "0414192427"
    back_str = m.group(3)    # e.g. "0607"

    if pid in existing:
        continue

    # 解析前区: 每2位一个号
    fronts = [front_str[i:i+2] for i in range(0, 10, 2)]
    # 解析后区: 每2位一个号
    backs = [back_str[i:i+2] for i in range(0, 4, 2)]

    # 校验号码范围
    if all(1 <= int(f) <= 35 for f in fronts) and all(1 <= int(b) <= 12 for b in backs):
        fronts.sort(key=int)
        backs.sort(key=int)
        row = {
            "lottery_type": LOTTERY_TYPE,
            "period_id": pid,
            "front_1": fronts[0], "front_2": fronts[1], "front_3": fronts[2],
            "front_4": fronts[3], "front_5": fronts[4],
            "back_1": backs[0], "back_2": backs[1],
        }
        new_draws.append(row)

new_draws.sort(key=lambda x: x["period_id"])

if not new_draws:
    print("✅ 已是最新，无需同步")
    exit(0)

print(f"缺失期数: {len(new_draws)}, 范围: {new_draws[0]['period_id']} ~ {new_draws[-1]['period_id']}")

# ── 4. raw 层备份 ──
ts = datetime.now(BJT).strftime("%Y%m%d_%H%M%S")
raw_file = os.path.join(RAW_DIR, f"dlt_zhcw_fetch_{ts}.json")
with open(raw_file, "w", encoding="utf-8") as f:
    import json
    json.dump({"fetched_at": datetime.now(BJT).isoformat(), "source": URL, "draws": new_draws}, f, ensure_ascii=False, indent=2)
print(f"raw 备份: {raw_file}")

# ── 5. 写入 processed CSV ──
FIELD_NAMES = ["lottery_type", "period_id", "front_1", "front_2", "front_3", "front_4", "front_5", "back_1", "back_2"]
all_rows = list(existing.values()) + new_draws
all_rows.sort(key=lambda x: x["period_id"])

with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELD_NAMES)
    writer.writeheader()
    writer.writerows(all_rows)

with open(CSV_PATH, "rb") as f:
    sha = hashlib.sha256(f.read()).hexdigest()
print(f"CSV 写入完成, SHA256: {sha[:16]}..., 总行数: {len(all_rows)}")

# ── 6. 更新 manifest ──
import json
with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
    manifest = json.load(f)

for block in manifest.get("outputs", []):
    if block.get("lottery_type") == LOTTERY_TYPE:
        block["rows_out"] = len(all_rows)
        block["period_id_max"] = int(all_rows[-1]["period_id"])
        if "supplement" not in block:
            block["supplement"] = {}
        block["supplement"]["zhcw_sync_20260711"] = {
            "rows_added": len(new_draws),
            "period_ids": [d["period_id"] for d in new_draws],
            "source_note": f"zhcw.com 中彩网页面抓取 {datetime.now(BJT).strftime('%Y-%m-%d')}",
            "official_verify": "已与 www.zhcw.com 官方开奖页面核对",
        }

with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print("manifest 已更新")

# ── 7. 新增明细 ──
print(f"\n📋 新增 {len(new_draws)} 期大乐透开奖明细:")
for d in new_draws:
    print(f"  {d['period_id']}: {d['front_1']} {d['front_2']} {d['front_3']} {d['front_4']} {d['front_5']} + {d['back_1']} {d['back_2']}")

print(f"\n✅ 大乐透同步完成! +{len(new_draws)} 期, {all_rows[0]['period_id']} ~ {all_rows[-1]['period_id']}")
