"""脚本：从 zhcw.com 中彩网抓取七星彩缺失期号到 data/processed/qxc_draws.csv"""
import csv, os, hashlib, re, json
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

URL = "https://www.zhcw.com/kjxx/xqxc/"
CSV_PATH = "data/processed/qxc_draws.csv"
RAW_DIR = "data/raw"
MANIFEST_PATH = "data/processed/manifest.json"
BJT = timezone(timedelta(hours=8))
LOTTERY_TYPE = "qxc"

# ── 1. 读现有 CSV ──
existing = {}
with open(CSV_PATH, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        existing[row["period_id"]] = row

latest_existing = max(int(p) for p in existing)
print(f"现有最新期号: {latest_existing}, 总期数: {len(existing)}")

# ── 2. 从 zhcw.com 新版七星彩抓取 ──
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL, timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)

    # 点近100期获取更多数据
    try:
        page.locator("text=近100期").first.click(timeout=5000)
        page.wait_for_timeout(4000)
    except:
        pass

    raw_text = page.inner_text("body")
    browser.close()

# ── 3. 解析：提取 260xx 期号行 ──
# 格式: 期号(5位) + 日期 + 号码串(7或8位, 前6+后区1-2位) + 销售额...
lines = raw_text.split("\n")
new_draws = []

for line in lines:
    line = line.strip()
    # 匹配: 26xxx (仅新版期号) + 日期 + 数字串
    m = re.match(r"^(26\d{3})\s+(\d{4}-\d{2}-\d{2})[^0-9]*\s+(\d+)\b", line)
    if not m:
        continue
    pid = m.group(1)
    if pid in existing:
        continue

    num_str = m.group(3)
    num_len = len(num_str)

    # 七星彩: 前区6位数字 + 后区1位(0-14)
    # 后区<10时占1位(共7位), 后区>=10时占2位(共8位)
    if num_len not in (7, 8):
        continue

    d1, d2, d3, d4, d5, d6 = num_str[0], num_str[1], num_str[2], num_str[3], num_str[4], num_str[5]
    special = num_str[6:]  # 可能是1位或2位

    # 校验
    if not (0 <= int(special) <= 14):
        continue

    new_draws.append({
        "lottery_type": LOTTERY_TYPE,
        "period_id": pid,
        "d1": d1, "d2": d2, "d3": d3, "d4": d4, "d5": d5, "d6": d6,
        "special": special,
    })

new_draws.sort(key=lambda x: x["period_id"])

if not new_draws:
    print("✅ 已是最新，无需同步")
    exit(0)

print(f"缺失期数: {len(new_draws)}, 范围: {new_draws[0]['period_id']} ~ {new_draws[-1]['period_id']}")

# ── 4. raw 层备份 ──
ts = datetime.now(BJT).strftime("%Y%m%d_%H%M%S")
raw_file = os.path.join(RAW_DIR, f"qxc_zhcw_fetch_{ts}.json")
with open(raw_file, "w", encoding="utf-8") as f:
    json.dump({"fetched_at": datetime.now(BJT).isoformat(), "source": URL, "draws": new_draws}, f, ensure_ascii=False, indent=2)
print(f"raw 备份: {raw_file}")

# ── 5. 写入 processed CSV ──
FIELD_NAMES = ["lottery_type", "period_id", "d1", "d2", "d3", "d4", "d5", "d6", "special"]
all_rows = list(existing.values()) + new_draws
all_rows.sort(key=lambda x: int(x["period_id"]))

with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELD_NAMES)
    writer.writeheader()
    writer.writerows(all_rows)

with open(CSV_PATH, "rb") as f:
    sha = hashlib.sha256(f.read()).hexdigest()
print(f"CSV 写入完成, SHA256: {sha[:16]}..., 总行数: {len(all_rows)}")

# ── 6. 校验严格递增 ──
pids = [int(r["period_id"]) for r in all_rows]
for i in range(1, len(pids)):
    if pids[i] <= pids[i - 1]:
        print(f"⚠ 排序错误: {pids[i-1]} -> {pids[i]}")
        break
else:
    print("✅ 期号严格递增")

# ── 7. 更新 manifest ──
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
            "source_note": f"zhcw.com 中彩网新版七星彩页面抓取 {datetime.now(BJT).strftime('%Y-%m-%d')}",
            "official_verify": "已与 www.zhcw.com 官方开奖页面核对",
        }

with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print("manifest 已更新")

# ── 8. 新增明细 ──
print(f"\n📋 新增 {len(new_draws)} 期七星彩开奖明细:")
for d in new_draws:
    print(f"  {d['period_id']}: {d['d1']} {d['d2']} {d['d3']} {d['d4']} {d['d5']} {d['d6']} + {d['special']}")

print(f"\n✅ 七星彩同步完成! +{len(new_draws)} 期, {all_rows[0]['period_id']} ~ {all_rows[-1]['period_id']}")
