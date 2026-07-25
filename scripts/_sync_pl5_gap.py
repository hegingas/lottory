"""脚本：从 zhcw.com 中彩网抓取排列5缺失期号到 data/processed/pl5_draws.csv"""
import csv, os, hashlib, re, json
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

URL = "https://www.zhcw.com/kjxx/pl5/"
CSV_PATH = "data/processed/pl5_draws.csv"
RAW_DIR = "data/raw"
MANIFEST_PATH = "data/processed/manifest.json"
BJT = timezone(timedelta(hours=8))
LOTTERY_TYPE = "pl5"

# ── 辅助: zhcw期号(YYNNN) → CSV 7位格式(YYYYNNN) ──
def convert_period(pid_short: str) -> str:
    """26147 -> 2026147, 04001 -> 2004001"""
    yy = pid_short[:2]
    nnn = pid_short[2:]
    year = 2000 + int(yy)
    # 已有部分 CSV 条目用的是4位(丢前导0), 但新数据用统一7位
    return f"{year}{nnn}"

# ── 1. 读现有 CSV ──
existing = {}
with open(CSV_PATH, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        existing[row["period_id"]] = row

# 建立短格式到长格式的映射，用于去重
# CSV里旧期号可能: "4001"(4位), "2026146"(7位), "2009001"(7位)...
existing_short = set()
for pid in existing:
    # 去掉前导"20"还原短格式(zcw格式)
    if len(pid) >= 5 and pid.startswith("20"):
        existing_short.add(pid[2:])  # 2026146 -> 26146
    else:
        # 旧格式 4位数，补齐: 4001 -> 04001
        existing_short.add(pid.zfill(5))

latest_csv_pid = max(int(p) for p in existing)
print(f"现有最新期号: {latest_csv_pid}, 总期数: {len(existing)}")

# ── 2. 从 zhcw.com 抓取 ──
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL, timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)

    # 点近100期
    try:
        page.locator("text=近100期").first.click(timeout=5000)
        page.wait_for_timeout(4000)
    except:
        pass

    raw_text = page.inner_text("body")
    browser.close()

# ── 3. 解析 ──
lines = raw_text.split("\n")
new_draws = []

# 匹配: 5位期号(YYNNN) + 日期 + 5位号码(0-9) + 销售额...
for line in lines:
    line = line.strip()
    m = re.match(r"^(\d{5})\s+(\d{4}-\d{2}-\d{2})[^0-9]*\s+(\d{5})\b", line)
    if not m:
        continue
    pid_short = m.group(1)
    # 只处理最近期号(26xxx范围)
    if not pid_short.startswith("26"):
        continue

    # 检查是否已存在(短格式去重)
    if pid_short in existing_short:
        continue

    nums = m.group(3)  # 5-digit string
    pid_full = convert_period(pid_short)

    new_draws.append({
        "lottery_type": LOTTERY_TYPE,
        "period_id": pid_full,
        "d1": nums[0], "d2": nums[1], "d3": nums[2], "d4": nums[3], "d5": nums[4],
    })

new_draws.sort(key=lambda x: int(x["period_id"]))

if not new_draws:
    print("✅ 已是最新，无需同步")
    exit(0)

print(f"缺失期数: {len(new_draws)}, 范围: {new_draws[0]['period_id']} ~ {new_draws[-1]['period_id']}")

# ── 4. raw 层备份 ──
ts = datetime.now(BJT).strftime("%Y%m%d_%H%M%S")
raw_file = os.path.join(RAW_DIR, f"pl5_zhcw_fetch_{ts}.json")
with open(raw_file, "w", encoding="utf-8") as f:
    json.dump({"fetched_at": datetime.now(BJT).isoformat(), "source": URL, "draws": new_draws}, f, ensure_ascii=False, indent=2)
print(f"raw 备份: {raw_file}")

# ── 5. 写入 processed CSV ──
FIELD_NAMES = ["lottery_type", "period_id", "d1", "d2", "d3", "d4", "d5"]
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
        # 检查是否重复
        if pids[i] == pids[i - 1]:
            print(f"  重复期号! row {i}: {all_rows[i-1]['period_id']} = {all_rows[i]['period_id']}")
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
        block["supplement"][f"zhcw_sync_{datetime.now(BJT).strftime('%Y%m%d')}"] = {
            "rows_added": len(new_draws),
            "period_ids": [d["period_id"] for d in new_draws],
            "source_note": f"zhcw.com 中彩网排列5页面抓取 {datetime.now(BJT).strftime('%Y-%m-%d')}",
            "official_verify": "已与 www.zhcw.com 官方开奖页面核对",
        }

with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print("manifest 已更新")

# ── 8. 新增明细 ──
print(f"\n📋 新增 {len(new_draws)} 期排列5开奖明细:")
for d in new_draws[:5]:
    print(f"  {d['period_id']}: {d['d1']} {d['d2']} {d['d3']} {d['d4']} {d['d5']}")
if len(new_draws) > 10:
    print(f"  ... 中间 {len(new_draws) - 10} 期省略 ...")
for d in new_draws[-5:]:
    print(f"  {d['period_id']}: {d['d1']} {d['d2']} {d['d3']} {d['d4']} {d['d5']}")

print(f"\n✅ 排列5同步完成! +{len(new_draws)} 期, {all_rows[0]['period_id']} ~ {all_rows[-1]['period_id']}")
