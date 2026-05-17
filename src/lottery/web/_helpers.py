"""Flask Web 应用 — 彩票开奖数据与预测展示的内部辅助函数。

复用现有 src/lottery 模块做数据读取，不修改现有代码。
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from ..paths import history_dir, processed_dir

# ── 彩种元数据 ──────────────────────────────────────────────────

LOTTERY_META: dict[str, dict[str, Any]] = {
    "dlt": {
        "name": "大乐透",
        "csv": "dlt_draws.csv",
        "main_cols": ["front_1", "front_2", "front_3", "front_4", "front_5"],
        "main_label": "前区",
        "main_range": (1, 35),
        "main_count": 5,
        "sub_cols": ["back_1", "back_2"],
        "sub_label": "后区",
        "sub_range": (1, 12),
        "sub_count": 2,
        "has_ac": True,
        "ac_n": 5,
        "zones": [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 35)],
        "sub_zones": [(1, 3), (4, 6), (7, 9), (10, 12)],
    },
    "ssq": {
        "name": "双色球",
        "csv": "ssq_draws.csv",
        "main_cols": ["red_1", "red_2", "red_3", "red_4", "red_5", "red_6"],
        "main_label": "红球",
        "main_range": (1, 33),
        "main_count": 6,
        "sub_cols": ["blue"],
        "sub_label": "蓝球",
        "sub_range": (1, 16),
        "sub_count": 1,
        "has_ac": True,
        "ac_n": 6,
        "zones": [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 33)],
        "sub_zones": [(1, 4), (5, 8), (9, 12), (13, 16)],
    },
    "kl8": {
        "name": "快乐八",
        "csv": "kl8_draws.csv",
        "main_cols": [f"n{i:02d}" for i in range(1, 21)],
        "main_label": "开奖20码",
        "main_range": (1, 80),
        "main_count": 20,
        "sub_cols": [],
        "sub_label": "",
        "sub_range": (0, 0),
        "sub_count": 0,
        "has_ac": True,
        "ac_n": 20,
        "zones": [(1, 10), (11, 20), (21, 30), (31, 40), (41, 50), (51, 60), (61, 70), (71, 80)],
        "sub_zones": [],
    },
    "pl5": {
        "name": "排列5",
        "csv": "pl5_draws.csv",
        "main_cols": ["d1", "d2", "d3", "d4", "d5"],
        "main_label": "5位数字",
        "main_range": (0, 9),
        "main_count": 5,
        "sub_cols": [],
        "sub_label": "",
        "sub_range": (0, 0),
        "sub_count": 0,
        "has_ac": False,
        "ac_n": 0,
        "zones": [(0, 9)],
        "sub_zones": [],
    },
    "qxc": {
        "name": "七星彩",
        "csv": "qxc_draws.csv",
        "main_cols": ["d1", "d2", "d3", "d4", "d5", "d6"],
        "main_label": "前区6位",
        "main_range": (0, 9),
        "main_count": 6,
        "sub_cols": ["special"],
        "sub_label": "后区",
        "sub_range": (0, 14),
        "sub_count": 1,
        "has_ac": False,
        "ac_n": 0,
        "zones": [(0, 9)],
        "sub_zones": [(0, 14)],
    },
}

# ── 数据加载缓存 ─────────────────────────────────────────────────

_data_cache: dict[str, pd.DataFrame] = {}


def _load_csv(lt: str) -> pd.DataFrame:
    if lt in _data_cache:
        return _data_cache[lt]
    path = processed_dir() / LOTTERY_META[lt]["csv"]
    if path.exists():
        df = pd.read_csv(path)
    else:
        df = pd.DataFrame()
    _data_cache[lt] = df
    return df


def _get_numbers(row: pd.Series, lt: str) -> list[int]:
    """从 DataFrame 行提取号码列表（主区+副区）。"""
    meta = LOTTERY_META[lt]
    nums = [int(row[c]) for c in meta["main_cols"]]
    for c in meta["sub_cols"]:
        nums.append(int(row[c]))
    return nums


def _get_main_numbers(row: pd.Series, lt: str) -> list[int]:
    meta = LOTTERY_META[lt]
    return [int(row[c]) for c in meta["main_cols"]]


# ── 走势指标计算 ─────────────────────────────────────────────────


def _compute_ac_value(nums: list[int]) -> int:
    """AC 值 = 两两差值去重个数 D − (n−1)。"""
    n = len(nums)
    if n < 3:
        return 0
    diffs: set[int] = set()
    s = sorted(nums)
    for i in range(n):
        for j in range(i + 1, n):
            diffs.add(s[j] - s[i])
    return len(diffs) - (n - 1)


def _compute_consecutive_count(nums: list[int]) -> int:
    """连号对数（相邻两号差值=1）。"""
    s = sorted(nums)
    cnt = 0
    for i in range(len(s) - 1):
        if s[i + 1] - s[i] == 1:
            cnt += 1
    return cnt


def _compute_odd_even_ratio(nums: list[int]) -> tuple[int, int]:
    odds = sum(1 for x in nums if x % 2 == 1)
    evens = len(nums) - odds
    return odds, evens


def _compute_zone_hits(nums: list[int], zones: list[tuple[int, int]]) -> list[int]:
    """各区命中计数。"""
    hits = [0] * len(zones)
    for x in nums:
        for i, (lo, hi) in enumerate(zones):
            if lo <= x <= hi:
                hits[i] += 1
                break
    return hits


def _compute_omission(df: pd.DataFrame, cols: list[str], max_val: int, window: int | None = None) -> list[int]:
    """每位号码当前遗漏期数（从最新期往前算 window 期，None=全表）。"""
    if df.empty:
        return [0] * (max_val + 1)
    sub = df.tail(window) if window else df
    latest_periods: dict[int, int] = {}
    for period_offset, (_, row) in enumerate(sub.iloc[::-1].iterrows()):
        for c in cols:
            v = int(row[c])
            if v not in latest_periods:
                latest_periods[v] = period_offset
    result = []
    for v in range(max_val + 1):
        result.append(latest_periods.get(v, len(sub)))
    return result


def build_trend_data(lt: str, window: int = 100) -> dict[str, Any]:
    """构造走势图 JSON 数据。"""
    meta = LOTTERY_META[lt]
    df = _load_csv(lt)
    if df.empty:
        return {"error": f"{meta['name']} 无数据"}

    sub = df.tail(window).copy()
    periods = sub["period_id"].astype(int).tolist()

    result: dict[str, Any] = {
        "lottery_type": lt,
        "name": meta["name"],
        "periods": periods,
        "window": window,
        "total_periods": len(df),
    }

    main_nums = sub[meta["main_cols"]].values.tolist()

    # 和值
    result["sums"] = [int(sum(r)) for r in main_nums]

    # 跨度
    if meta["main_range"][1] > 10:
        result["spans"] = [int(max(r) - min(r)) for r in main_nums]

    # AC 值
    if meta["has_ac"]:
        result["ac_values"] = [_compute_ac_value(r) for r in main_nums]

    # 连号数
    if meta["main_count"] >= 5 and meta["main_range"][1] > 10:
        result["consecutive"] = [_compute_consecutive_count(r) for r in main_nums]

    # 奇偶比
    if meta["main_range"][1] > 10:
        oe = [_compute_odd_even_ratio(r) for r in main_nums]
        result["odd_counts"] = [o for o, _ in oe]
        result["even_counts"] = [e for _, e in oe]

    # 区间热力图数据
    if len(meta["zones"]) > 1:
        zone_labels = [f"{lo}-{hi}" for lo, hi in meta["zones"]]
        result["zone_labels"] = zone_labels
        zone_data = [_compute_zone_hits(r, meta["zones"]) for r in main_nums]
        result["zone_heatmap"] = zone_data

    # 频次统计（当前窗口）
    max_val = meta["main_range"][1]
    freq = np.zeros(max_val + 1, dtype=int)
    for r in main_nums:
        for v in r:
            if 0 <= v <= max_val:
                freq[v] += 1
    result["frequency"] = freq.tolist()

    # 当前遗漏
    result["omission"] = _compute_omission(sub, meta["main_cols"], max_val)

    return result


# ── 预测 Markdown 解析 ────────────────────────────────────────────


def parse_prediction_md(lt: str) -> dict[str, Any]:
    """解析 history/*_prediction.md 为结构化数据。

    支持五彩种不同格式：DLT/SSQ 有前区/后区热冷号；
    QXC/PL5 按位摘要；KL8 有 20码/11码选十。
    """
    mapping = {
        "dlt": "daletou_prediction.md",
        "ssq": "shuangseqiu_prediction.md",
        "kl8": "kuaileba_prediction.md",
        "pl5": "pailie5_prediction.md",
        "qxc": "qixingcai_prediction.md",
    }
    path = history_dir() / mapping.get(lt, "")
    if not path.exists():
        return {"error": "预测文件不存在"}

    text = path.read_text(encoding="utf-8")
    # 统一换行符
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    result: dict[str, Any] = {"tickets": [], "best_ticket": None}

    # 提取元数据（兼容 markdown 中的 **粗体** 与 > 引用前缀）
    for pattern, key in [
        (r"\*{0,2}最后更新\*{0,2}[：:]\s*(.+?)(?:\n|$)", "last_update"),
        (r"\*{0,2}期号范围\*{0,2}[：:]\s*(.+?)(?:\n|$)", "period_range"),
        (r"\*{0,2}统计窗口\*{0,2}[：:]\s*(.+?)(?:\n|$)", "stats_window"),
    ]:
        m = re.search(pattern, text)
        if m:
            result[key] = m.group(1).strip()

    # ── 提取口径说明（含区间选择原因） ──
    method_start = re.search(r"## 口径说明", text)
    method_end = re.search(r"## 结果摘要", text)
    if method_start and method_end and method_start.end() < method_end.start():
        result["methodology"] = _strip_md(text[method_start.end() : method_end.start()].strip())

    # ── 提取结果摘要块（所有彩种通用） ──
    summary_start = re.search(r"## 结果摘要", text)
    summary_end = re.search(r"## 明确号码输出", text)
    if summary_start and summary_end:
        result["summary"] = _strip_md(text[summary_start.end() : summary_end.start()].strip())

    # ── DLT/SSQ: 热冷号（直接行匹配） ──
    if lt in ("dlt", "ssq"):
        result["hot_main"] = _extract_inline(text, r"(?:前区热号|红球热号)[：:]\s*(.+)")
        result["cold_main"] = _extract_inline(text, r"(?:前区冷号|红球冷号)[：:]\s*(.+)")
        result["hot_sub"] = _extract_inline(text, r"(?:后区热号|蓝球热号)[：:]\s*(.+)")
        result["cold_sub"] = _extract_inline(text, r"(?:后区冷号|蓝球冷号)[：:]\s*(.+)")

    # ── 提取各注号码 ──
    if lt in ("dlt", "ssq"):
        # DLT/SSQ: ### 第 N 注（单式）\n\n- **号码**：前区 ...；后区 ...
        for m in re.finditer(
            r"### 第 (\d+) 注.*?\n\n- \*\*号码\*\*[：:]\s*(.+?)\n",
            text,
        ):
            result["tickets"].append({"index": m.group(1), "numbers": _strip_md(m.group(2).strip())})
    elif lt == "pl5":
        # PL5: - 第N注：**XXXXX**（分位：...）
        for m in re.finditer(r"- 第(\d+)注[：:]\s*\*{0,2}(\d{5})\*{0,2}", text):
            result["tickets"].append({"index": m.group(1), "numbers": _strip_md(m.group(2).strip())})
    elif lt == "qxc":
        # QXC: - 第N注：前区 **...** + 后区 `N`（全码：`...`）
        for m in re.finditer(r"- 第(\d+)注[：:]\s*(.+?)(?:\n|$)", text):
            result["tickets"].append({"index": m.group(1), "numbers": _strip_md(m.group(2).strip())})
    elif lt == "kl8":
        # KL8: 参考开奖 20 码行 + 选十参考 11 码行（兼容 markdown 粗体与括号）
        for m in re.finditer(r"参考开奖\s*20\s*码[^：:\n]*[：:]\**\s*([\d,\s]+)\**", text):
            nums = ",".join(re.findall(r"\d+", m.group(1)))
            result["kl8_ref20"] = nums
            result["tickets"].append({"index": "20码", "numbers": nums})
        # 明确号码输出 中的 "选十参考 11 码"（不在单式优选节中重复匹配）
        for m in re.finditer(r"-\s*\*{0,2}选十参考\s*11\s*码[^：:\n]*[：:]\**\s*([\d,\s]+)\**", text):
            nums = ",".join(re.findall(r"\d+", m.group(1)))
            result["kl8_ref11"] = nums
            result["tickets"].append({"index": "11码", "numbers": nums})

    # ── 单式优选 ──
    # 统一策略：匹配 "## 单式优选" 到下一个 "## " 标题之间的内容
    best_section = re.search(r"## 单式优选.*?(?=\n## \S)", text, re.DOTALL)
    if not best_section:
        # fallback: 到文本末尾
        best_section = re.search(r"## 单式优选[\s\S]*", text)
    if best_section:
        section = best_section.group(0)
        # 提取号码行（兼容 DLT/SSQ "号码"、QXC/PL5 "号码（N 位）"、KL8 "11 码"）
        # 注意 [^：:\n] 防止跨行匹配
        num_match = re.search(r"(?:号码|\d+\s*码)[^：:\n]*[：:]\s*(.+?)(?:\n|$)", section)
        if not num_match:
            num_match = re.search(r"(?:参考|推荐).*?[：:]\s*(.+?)(?:\n|$)", section)
        # 提取总分（兼容 "总分"、"综合分"）
        score_match = re.search(r"(?:总分|综合分)[^：:\n]*[：:\s]\*?\*?([\d.]+)", section)
        if num_match:
            raw = num_match.group(1).strip()
            # 清理 markdown 格式
            raw = re.sub(r"\*\*|\*|`", "", raw)
            # 移除行尾括号说明
            raw = re.sub(r"[（(][^)）]*[)）]$", "", raw)
            # 移除分号后的评分说明（KL8 格式，DLT/SSQ 的；分隔前后区不能砍）
            if lt == "kl8":
                raw = re.sub(r"；.*$", "", raw)
            result["best_ticket"] = {
                "numbers": raw.strip(),
                "score": score_match.group(1).strip() if score_match else "—",
            }

    return result


def _extract_inline(text: str, pattern: str) -> str:
    """直接匹配行内模式并清洗 markdown。"""
    m = re.search(pattern, text)
    if m:
        return _strip_md(m.group(1))
    return ""


def _strip_md(raw: str) -> str:
    """清理 markdown 格式标记。"""
    if not raw:
        return ""
    raw = re.sub(r"\*\*|\*|`|>", "", raw)
    # 去掉行首的 ：:
    raw = re.sub(r"^[：:\s]+", "", raw)
    return raw.strip()


def _extract_section_between(text: str, start_pat: str, end_pat: str) -> str:
    """提取两个标题模式之间的内容（含列表项）。"""
    s = re.search(start_pat, text)
    e = re.search(end_pat, text)
    if s and e and s.end() < e.start():
        return text[s.end() : e.start()].strip()
    if s:
        rest = text[s.end() :]
        lines = rest.strip().split("\n")
        out = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("-") or stripped.startswith("`"):
                out.append(stripped)
            elif stripped == "":
                continue
            else:
                break
        return "\n".join(out)
    return ""


# ── 走势表格数据 ─────────────────────────────────────────────────

ZONE_COLORS = [
    "#faf6f0", "#f0f4fa", "#f4faf0", "#faf0f4",
    "#f0faf6", "#f6f0fa", "#faf8f0", "#f0f6fa",
]


def _build_zone_list(zones: list[tuple[int, int]]) -> list[dict]:
    """构建分区列表（含颜色索引）。"""
    result = []
    for i, (lo, hi) in enumerate(zones):
        result.append({"lo": lo, "hi": hi, "color": ZONE_COLORS[i % len(ZONE_COLORS)]})
    return result


def _detect_patterns(draws: list[set[int]], lo: int, hi: int) -> dict:
    """检测连线模式：连号、斜连号、连续多期开出。"""
    n = len(draws)

    # 1) 同注连号 (consecutive in same draw)
    consecutive_in_draw: list[dict] = []
    for pi, d in enumerate(draws):
        s = sorted(d)
        for i in range(len(s) - 1):
            if s[i + 1] - s[i] == 1:
                consecutive_in_draw.append({
                    "period_idx": pi,
                    "num1": s[i],
                    "num2": s[i + 1],
                })

    # 2) 斜连号 (num N in period P, N+1 or N-1 in period P+1)
    diagonal_pairs: list[dict] = []
    for pi in range(n - 1):
        d1 = draws[pi]
        d2 = draws[pi + 1]
        for v in d1:
            if (v + 1) in d2:
                diagonal_pairs.append({
                    "period_idx1": pi,
                    "num1": v,
                    "period_idx2": pi + 1,
                    "num2": v + 1,
                })
            if (v - 1) in d2 and v - 1 >= lo:
                diagonal_pairs.append({
                    "period_idx1": pi,
                    "num1": v,
                    "period_idx2": pi + 1,
                    "num2": v - 1,
                })

    # 3) 连续多期开出 (streak >= 2)
    streaks: list[dict] = []
    for v in range(lo, hi + 1):
        start = None
        for pi, d in enumerate(draws):
            if v in d:
                if start is None:
                    start = pi
            else:
                if start is not None and pi - start >= 2:
                    streaks.append({"num": v, "start": start, "end": pi - 1})
                start = None
        if start is not None and n - start >= 2:
            streaks.append({"num": v, "start": start, "end": n - 1})

    return {
        "consecutive_in_draw": consecutive_in_draw,
        "diagonal_pairs": diagonal_pairs,
        "streaks": streaks,
    }


def _detect_position_patterns(
    sub: pd.DataFrame, meta: dict, df: pd.DataFrame
) -> dict:
    """位式型连线模式检测：斜连号 + 连续多期。"""
    n = len(sub)
    all_cols = meta["main_cols"] + meta["sub_cols"]

    diagonal_pairs = []
    streaks = []

    for pi, col in enumerate(all_cols):
        vals = [int(row[col]) for _, row in sub.iterrows()]
        lo = 0
        hi = meta["sub_range"][1] if pi >= len(meta["main_cols"]) else meta["main_range"][1]

        # 斜连号
        for i in range(n - 1):
            v1, v2 = vals[i], vals[i + 1]
            if abs(v2 - v1) == 1:
                diagonal_pairs.append({
                    "pos": pi, "period_idx1": i, "digit1": v1,
                    "period_idx2": i + 1, "digit2": v2,
                })

        # 连续多期
        for d in range(lo, hi + 1):
            start = None
            for i, v in enumerate(vals):
                if v == d:
                    if start is None:
                        start = i
                else:
                    if start is not None and i - start >= 2:
                        streaks.append({"pos": pi, "digit": d, "start": start, "end": i - 1})
                    start = None
            if start is not None and n - start >= 2:
                streaks.append({"pos": pi, "digit": d, "start": start, "end": n - 1})

    return {
        "consecutive_in_draw": [],
        "diagonal_pairs": diagonal_pairs,
        "streaks": streaks,
    }


def _calc_stats(
    draws: list[set[int]], lo: int, hi: int, meta: dict, df: pd.DataFrame
) -> dict:
    """统计计算（原 _build_trend_table 内嵌函数，提取为独立函数）。"""
    freq_win = [0] * (hi + 1)
    for d in draws:
        for v in d:
            if lo <= v <= hi:
                freq_win[v] += 1

    # 全表频次
    freq_total = [0] * (hi + 1)
    for _, row in df.iterrows():
        cols = meta["main_cols"] if lo == meta["main_range"][0] else meta["sub_cols"]
        for c in cols:
            v = int(row[c])
            if lo <= v <= hi:
                freq_total[v] += 1

    # 当前遗漏
    omission_cur = [0] * (hi + 1)
    max_omission = [0] * (hi + 1)
    for v in range(lo, hi + 1):
        # 当前遗漏: 从最新期往前找
        cur_om = 0
        for d in reversed(draws):
            if v in d:
                break
            cur_om += 1
        omission_cur[v] = cur_om

        # 历史最大遗漏: 扫描全表
        max_om = 0
        run = 0
        for _, row in df.iterrows():
            cols2 = meta["main_cols"] if lo == meta["main_range"][0] else meta["sub_cols"]
            found = any(int(row[c]) == v for c in cols2)
            if found:
                max_om = max(max_om, run)
                run = 0
            else:
                run += 1
        max_om = max(max_om, run)
        max_omission[v] = max_om

    return {
        "lo": lo,
        "hi": hi,
        "freq_window": freq_win,
        "freq_total": freq_total,
        "omission_current": omission_cur,
        "omission_max": max_omission,
    }


def _build_trend_table(lt: str, window: int = 100) -> dict[str, Any]:
    """构造传统表格型走势图数据。"""
    meta = LOTTERY_META[lt]
    df = _load_csv(lt)
    if df.empty:
        return {"error": f"{meta['name']} 无数据"}

    window = min(window, len(df))
    sub = df.tail(window)
    periods = sub["period_id"].astype(int).tolist()

    result: dict[str, Any] = {
        "lottery_type": lt,
        "name": meta["name"],
        "periods": periods,
        "window": window,
        "total_periods": len(df),
    }

    # ── 数池型 (DLT/SSQ/KL8) ──
    if lt in ("dlt", "ssq", "kl8"):
        m_lo, m_hi = meta["main_range"]

        # 主区每期号码集合
        main_draws: list[set[int]] = []
        for _, row in sub.iterrows():
            main_draws.append({int(row[c]) for c in meta["main_cols"]})

        # 副区
        sub_draws: list[set[int]] = []
        has_sub = bool(meta["sub_cols"])
        if has_sub:
            s_lo, s_hi = meta["sub_range"]
            for _, row in sub.iterrows():
                sub_draws.append({int(row[c]) for c in meta["sub_cols"]})

        # ── 遗漏值矩阵（每期每个号码的遗漏期数） ──
        omission_grid = []
        for pi in range(len(main_draws)):
            row_om = {}
            for v in range(m_lo, m_hi + 1):
                om = 0
                for pj in range(pi, -1, -1):
                    if v in main_draws[pj]:
                        break
                    om += 1
                row_om[v] = om
            omission_grid.append(row_om)

        sub_omission_grid = None
        if has_sub:
            s_lo, s_hi = meta["sub_range"]
            sub_omission_grid = []
            for pi in range(len(sub_draws)):
                row_om = {}
                for v in range(s_lo, s_hi + 1):
                    om = 0
                    for pj in range(pi, -1, -1):
                        if v in sub_draws[pj]:
                            break
                        om += 1
                    row_om[v] = om
                sub_omission_grid.append(row_om)

        # ── 衍生指标 ──
        derived_cols = []
        for pi in range(len(main_draws)):
            s = sorted(main_draws[pi])
            col = {
                "sum": sum(s),
                "span": max(s) - min(s) if s else 0,
                "zone_ratio": ":".join(str(c) for c in _compute_zone_hits(s, meta["zones"])),
                "oe_ratio": f"{sum(1 for x in s if x % 2 == 1)}:{sum(1 for x in s if x % 2 == 0)}",
            }
            if meta["has_ac"]:
                col["ac"] = _compute_ac_value(s)
            derived_cols.append(col)

        # ── 重号检测 ──
        repeat_hits = []
        for pi in range(len(main_draws)):
            if pi == 0:
                repeat_hits.append([])
            else:
                repeat_hits.append(sorted(main_draws[pi] & main_draws[pi - 1]))

        sub_repeat_hits = None
        if has_sub:
            sub_repeat_hits = []
            for pi in range(len(sub_draws)):
                if pi == 0:
                    sub_repeat_hits.append([])
                else:
                    sub_repeat_hits.append(sorted(sub_draws[pi] & sub_draws[pi - 1]))

        result["main_zone"] = {
            "label": meta["main_label"],
            "draws": [sorted(d) for d in main_draws],
            "stats": _calc_stats(main_draws, m_lo, m_hi, meta, df),
        }

        if has_sub:
            result["sub_zone"] = {
                "label": meta["sub_label"],
                "draws": [sorted(d) for d in sub_draws],
                "stats": _calc_stats(sub_draws, s_lo, s_hi, meta, df),
            }
        else:
            result["sub_zone"] = None

        # ── 分区定义 ──
        result["zones"] = _build_zone_list(meta["zones"])
        if has_sub and meta["sub_zones"]:
            result["sub_zones"] = _build_zone_list(meta["sub_zones"])

        # KL8: 额外十码段分组
        if lt == "kl8":
            zones_kl8 = [(1, 10), (11, 20), (21, 30), (31, 40), (41, 50), (51, 60), (61, 70), (71, 80)]
            result["decadic_zones"] = [
                {"label": f"{lo}-{hi}", "lo": lo, "hi": hi} for lo, hi in zones_kl8
            ]

        # ── 连线模式检测 ──
        result["patterns"] = _detect_patterns(main_draws, m_lo, m_hi)
        if has_sub:
            result["sub_patterns"] = _detect_patterns(sub_draws, s_lo, s_hi)
        else:
            result["sub_patterns"] = None

        # ── 新增字段 ──
        result["omission_grid"] = omission_grid
        result["sub_omission_grid"] = sub_omission_grid
        result["derived_cols"] = derived_cols
        result["repeat_hits"] = repeat_hits
        result["sub_repeat_hits"] = sub_repeat_hits

    # ── 位式型 (PL5/QXC) ──
    else:
        positions: list[dict] = []
        # 主区位
        for pi, col in enumerate(meta["main_cols"]):
            pos_draws = []
            for _, row in sub.iterrows():
                pos_draws.append(int(row[col]))
            pos_label = f"第{pi+1}位" if lt == "pl5" else f"前区第{pi+1}位"
            lo = meta["main_range"][0]
            hi = meta["main_range"][1]
            positions.append(_pos_stats(pos_label, pos_draws, lo, hi, df, col))

        # 副区位
        if meta["sub_cols"]:
            col = meta["sub_cols"][0]
            pos_draws = []
            for _, row in sub.iterrows():
                pos_draws.append(int(row[col]))
            positions.append(_pos_stats("后区", pos_draws, meta["sub_range"][0], meta["sub_range"][1], df, col))

        result["positions"] = positions
        # 位式型分区: 每位一个 zone + QXC 后区分两段
        if lt == "qxc":
            result["pos_zones"] = [
                {"lo": 0, "hi": 9} for _ in range(6)
            ] + [
                {"lo": 0, "hi": 7}, {"lo": 8, "hi": 14}
            ]
        else:
            result["pos_zones"] = [{"lo": 0, "hi": 9} for _ in range(len(positions))]

        # 位式型模式检测
        result["patterns"] = _detect_position_patterns(sub, meta, df)

        # ── 衍生指标（位式型） ──
        pos_derived_cols = []
        all_pos_cols = meta["main_cols"] + meta["sub_cols"]
        for _, row in sub.iterrows():
            vals = [int(row[c]) for c in all_pos_cols]
            col = {
                "sum": sum(vals),
                "oe_ratio": f"{sum(1 for x in vals if x % 2 == 1)}:{sum(1 for x in vals if x % 2 == 0)}",
            }
            pos_derived_cols.append(col)
        result["derived_cols"] = pos_derived_cols

        # ── 重号检测（位式型：每位数字与上期相同） ──
        pos_repeat_hits = []
        for pi_idx in range(len(positions)):
            pos_repeats = []
            draws_list = positions[pi_idx]["draws"]
            for i, v in enumerate(draws_list):
                if i == 0:
                    continue
                if v == draws_list[i - 1]:
                    pos_repeats.append({"period_idx": i, "digit": v})
            if pos_repeats:
                pos_repeat_hits.append({"pos": pi_idx, "repeats": pos_repeats})
        result["pos_repeat_hits"] = pos_repeat_hits

    return result


def _pos_stats(label: str, window_draws: list[int], lo: int, hi: int, df: pd.DataFrame, col: str) -> dict:
    """计算单一位的统计数据。"""
    freq_win = [0] * (hi + 1)
    for v in window_draws:
        if lo <= v <= hi:
            freq_win[v] += 1

    freq_total = [0] * (hi + 1)
    for _, row in df.iterrows():
        v = int(row[col])
        if lo <= v <= hi:
            freq_total[v] += 1

    omission_cur = [0] * (hi + 1)
    max_omission = [0] * (hi + 1)
    for d in range(lo, hi + 1):
        cur_om = 0
        for v in reversed(window_draws):
            if v == d:
                break
            cur_om += 1
        omission_cur[d] = cur_om

        max_om = 0
        run = 0
        for _, row in df.iterrows():
            if int(row[col]) == d:
                max_om = max(max_om, run)
                run = 0
            else:
                run += 1
        max_om = max(max_om, run)
        max_omission[d] = max_om

    return {
        "label": label,
        "lo": lo,
        "hi": hi,
        "draws": window_draws,
        "freq_window": freq_win,
        "freq_total": freq_total,
        "omission_current": omission_cur,
        "omission_max": max_omission,
    }


# ── 号码解析（预测文本 → 结构化） ────────────────────────────────


def _parse_dlt_ssq_numbers(raw: str, lt: str) -> dict | None:
    """解析 DLT/SSQ 预测号码文本。

    期望格式： "前区 01 02 03 04 05；后区 06 07" 或 "红球 01 ...；蓝球 ..."
    """
    text = raw.replace("；", ";").replace("，", ",").replace("：", ":")
    # 分离主区/副区
    main_part = ""
    sub_part = ""
    if ";" in text:
        parts = text.split(";")
        main_part = parts[0]
        sub_part = parts[1] if len(parts) > 1 else ""
    elif "后区" in text or "蓝球" in text:
        # "前区 ... 后区 ..." or "红球 ... 蓝球 ..."
        for sep in ["后区", "蓝球"]:
            if sep in text:
                idx = text.index(sep)
                main_part = text[:idx]
                sub_part = text[idx:]
                break
    else:
        main_part = text

    # 提取数字
    main_str = re.sub(r"前区|红球|主区|号码", "", main_part)
    sub_str = re.sub(r"后区|蓝球|副区", "", sub_part)
    main_nums = [int(m) for m in re.findall(r"\d+", main_str)]
    sub_nums = [int(m) for m in re.findall(r"\d+", sub_str)]

    meta = LOTTERY_META[lt]
    if len(main_nums) < meta["main_count"]:
        return None
    main_nums = main_nums[: meta["main_count"]]
    if meta["sub_count"] > 0 and len(sub_nums) < meta["sub_count"]:
        return None
    sub_nums = sub_nums[: meta["sub_count"]] if meta["sub_count"] > 0 else []

    return {"main": sorted(main_nums), "sub": sorted(sub_nums)}


def _parse_kl8_numbers(raw: str) -> dict | None:
    """解析 KL8 11 码文本。"""
    nums = [int(m) for m in re.findall(r"\d+", raw)]
    # 取前 11 或 20 个（去重排序）
    nums = sorted(set(nums))
    if len(nums) < 5:
        return None
    return {"candidates": nums}


def _parse_pl5_numbers(raw: str) -> dict | None:
    """解析排列5 5 位数字文本。"""
    digits_str = re.sub(r"\D", "", raw)
    if len(digits_str) < 5:
        return None
    return {"digits": [int(d) for d in digits_str[:5]]}


def _parse_qxc_numbers(raw: str) -> dict | None:
    """解析七星彩前6+后1 文本。"""
    # 提取全部数字
    nums = [int(m) for m in re.findall(r"\d+", raw)]
    if len(nums) < 7:
        return None
    return {"front": nums[:6], "special": nums[6]}


# ── 回测聚合 ────────────────────────────────────────────────────


def _aggregate_backtest_api(lt: str, entries: list[dict]) -> dict | None:
    if not entries:
        return None
    from collections import Counter
    info: dict = {"count": len(entries)}
    if lt in ("dlt",):
        info["avg_front"] = round(sum(e.get("front_matches", 0) for e in entries) / len(entries), 2)
        info["avg_back"] = round(sum(e.get("back_matches", 0) for e in entries) / len(entries), 2)
        info["prize_dist"] = dict(Counter(e.get("prize_level", "未中奖") for e in entries).most_common())
    elif lt == "ssq":
        info["avg_red"] = round(sum(e.get("red_matches", 0) for e in entries) / len(entries), 2)
        info["avg_blue"] = round(sum(e.get("blue_match", 0) for e in entries) / len(entries), 2)
        info["prize_dist"] = dict(Counter(e.get("prize_level", "未中奖") for e in entries).most_common())
    elif lt == "kl8":
        info["avg_overlap"] = round(sum(e.get("overlap_count", 0) for e in entries) / len(entries), 2)
    elif lt == "pl5":
        info["avg_pos"] = round(sum(e.get("position_matches", 0) for e in entries) / len(entries), 2)
        info["all_matched"] = sum(1 for e in entries if e.get("all_matched"))
    elif lt == "qxc":
        info["avg_front"] = round(sum(e.get("front_matches", 0) for e in entries) / len(entries), 2)
        info["avg_special"] = round(sum(e.get("special_match", 0) for e in entries) / len(entries), 2)
    return info
