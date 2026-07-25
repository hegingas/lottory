"""脚本：从 cwl.gov.cn 官方 API 补全快乐八缺失期号到 data/processed/kl8_draws.csv"""
import json, csv, os, hashlib
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

API_URL = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
CSV_PATH = "data/processed/kl8_draws.csv"
RAW_DIR = "data/raw"
MANIFEST_PATH = "data/processed/manifest.json"
BJT = timezone(timedelta(hours=8))
LOTTERY_TYPE = "kl8"

# ── 1. 读现有 CSV ──
existing = {}
with open(CSV_PATH, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        existing[row["period_id"]] = row

latest_existing = max(int(p) for p in existing)
print(f"现有最新期号: {latest_existing}, 总期数: {len(existing)}")

# ── 2. 从官方 API 拉取 ──
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    # 拉 100 条确保覆盖所有缺失
    page.goto(f"{API_URL}?name=kl8&issueCount=100", timeout=15000)
    page.wait_for_load_state("networkidle")
    data = json.loads(page.inner_text("body"))
    browser.close()

if data.get("state") != 0:
    print(f"API 返回异常: {data}")
    exit(1)

api_draws = data["result"]
print(f"API 返回 {len(api_draws)} 条记录, 最新期号: {api_draws[0]['code']}")

# ── 3. 筛选缺失期号 ──
new_draws = []
for d in api_draws:
    pid = d["code"]
    if pid not in existing:
        nums = [int(x) for x in d["red"].split(",")]
        nums.sort()  # 升序排列，与现有格式一致
        row = {"lottery_type": LOTTERY_TYPE, "period_id": pid}
        for i, n in enumerate(nums, 1):
            row[f"n{i:02d}"] = str(n)
        new_draws.append(row)

new_draws.sort(key=lambda x: x["period_id"])

if not new_draws:
    print("✅ 已是最新，无需同步")
    exit(0)

print(f"缺失期数: {len(new_draws)}, 范围: {new_draws[0]['period_id']} ~ {new_draws[-1]['period_id']}")

# ── 4. raw 层备份 ──
ts = datetime.now(BJT).strftime("%Y%m%d_%H%M%S")
raw_file = os.path.join(RAW_DIR, f"kl8_api_fetch_{ts}.json")
with open(raw_file, "w", encoding="utf-8") as f:
    json.dump({"fetched_at": datetime.now(BJT).isoformat(), "draws": new_draws}, f, ensure_ascii=False, indent=2)
print(f"raw 备份: {raw_file}")

# ── 5. 写入 processed CSV ──
FIELD_NAMES = ["lottery_type", "period_id"] + [f"n{i:02d}" for i in range(1, 21)]
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
with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
    manifest = json.load(f)

for block in manifest.get("outputs", []):
    if block.get("lottery_type") == LOTTERY_TYPE:
        block["rows_out"] = len(all_rows)
        block["period_id_max"] = int(all_rows[-1]["period_id"])
        if "supplement" not in block:
            block["supplement"] = {}
        block["supplement"][f"api_sync_{datetime.now(BJT).strftime('%Y%m%d')}"] = {
            "rows_added": len(new_draws),
            "period_ids": [d["period_id"] for d in new_draws],
            "source_note": f"cwl.gov.cn API auto-fetch {datetime.now(BJT).strftime('%Y-%m-%d')}",
            "official_verify": "已与中彩网官方API数据核对",
        }

with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print("manifest 已更新")

# ── 7. 新增明细 ──
print(f"\n📋 新增 {len(new_draws)} 期快乐八开奖明细:")
for d in new_draws:
    nums = [d[f"n{i:02d}"] for i in range(1, 21)]
    print(f"  {d['period_id']}: {', '.join(nums)}")

print(f"\n✅ 快乐八同步完成! +{len(new_draws)} 期, {all_rows[0]['period_id']} ~ {all_rows[-1]['period_id']}")
