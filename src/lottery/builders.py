"""分析/预测 Markdown 构建器：大乐透、双色球、快乐八的分析与预测归档生成。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .config import (
    DEFAULT_STATS_WINDOW,
    DLT_FRONT_ZONES_CAP,
    DLT_FRONT_MAX_PER_ZONE,
    DLT_BACK_ZONES_CAP,
    DLT_BACK_MAX_PER_ZONE,
    SSQ_RED_ZONES_CAP,
    SSQ_RED_MAX_PER_ZONE,
    SSQ_BLUE_ZONES_CAP,
    SSQ_BLUE_MAX_PER_ZONE,
    PREDICTION_SINGLE_LINES,
    PATTERN_RECENT_K,
    PATTERN_W_MARKOV,
    KL8_MIN_PER_PICK_ZONE,
    KL8_MAX_PER_PICK_ZONE,
    _ACTIVE_RANDOM_SEED,
)
from .scoring import (
    ac_value,
    freq_miss_from_draws,
    topk,
    _minmax01_ball,
    _markov_next_probabilities,
    _recency_counts,
    _dlt_front_scores,
    _dlt_back_scores,
    _ssq_red_scores,
    _ssq_blue_scores,
)
from .selection import (
    _dlt_collect_five_unique_tickets,
    _ssq_collect_five_unique_tickets,
    _kl8_twenty_from_patterns,
    _kl8_eleven_random_from_twenty,
    _assert_kl8_zone_bounds,
)
from .markdown_utils import (
    _fmt2,
    now_cn_iso,
    _pattern_weight_md_line,
    _build_dlt_five_numbers_md,
    _build_ssq_five_numbers_md,
    _dlt_appendix_five_singles_line,
    _ssq_appendix_five_singles_line,
    _prediction_md_appendix_budget_rules,
    _prediction_md_appendix_kl8_bet,
)

# ── 通用辅助 ──────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[2]
PROC = REPO / "data" / "processed"
HIST = REPO / "history"
MANIFEST = PROC / "manifest.json"


def _norm_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).lstrip("﻿").strip() for c in df.columns]
    return df


def _qstats(a: np.ndarray) -> str:
    qs = np.nanpercentile(a, [25, 50, 75])
    return f"均值 {a.mean():.2f}，中位数 {qs[1]:.0f}，Q1–Q3 约 {qs[0]:.0f}–{qs[2]:.0f}"


def format_ac_top(acs: np.ndarray) -> str:
    vals, counts = np.unique(acs.astype(int), return_counts=True)
    order = np.argsort(-counts)
    parts = []
    for i in order[:5]:
        parts.append(f"AC={int(vals[i])}（{int(counts[i])}期）")
    return "，".join(parts)


def _kl8_draw_rows(df: pd.DataFrame) -> tuple[list[list[int]], list]:
    ncols = [f"n{i:02d}" for i in range(1, 21)]
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    df = df.sort_values("period_id").reset_index(drop=True)
    draws: list[list[int]] = []
    for _, row in df.iterrows():
        draws.append([int(row[c]) for c in ncols])
    return draws, df["period_id"].tolist()


# ── 兼容旧接口 ────────────────────────────────────────────────

def dlt_explicit_from_patterns(
    f_draws: list[list[int]],
    b_draws: list[list[int]],
    fq: np.ndarray,
    fcur: np.ndarray,
    bq: np.ndarray,
    bcur: np.ndarray,
) -> tuple[str, str]:
    f_mk = _markov_next_probabilities(f_draws, 35)
    b_mk = _markov_next_probabilities(b_draws, 12)
    fs = _dlt_front_scores(f_draws, fq, fcur, f_mk)
    bs = _dlt_back_scores(b_draws, bq, bcur, b_mk)
    f0, b0 = _dlt_collect_five_unique_tickets(fs, bs)[0]
    return ",".join(_fmt2(x) for x in f0), ",".join(_fmt2(x) for x in b0)


def ssq_explicit_from_patterns(
    r_draws: list[list[int]],
    blues: list[int],
    rq: np.ndarray,
    rcur: np.ndarray,
    bq: np.ndarray,
    bcur: np.ndarray,
) -> tuple[str, str]:
    r_mk = _markov_next_probabilities(r_draws, 33)
    b_mk = _markov_next_probabilities([[int(x)] for x in blues], 16)
    rs = _ssq_red_scores(r_draws, rq, rcur, r_mk)
    bs = _ssq_blue_scores(blues, bq, bcur, b_mk)
    r0, b0 = _ssq_collect_five_unique_tickets(rs, bs)[0]
    return ",".join(_fmt2(x) for x in r0), _fmt2(b0)


# ── 大乐透分析 ────────────────────────────────────────────────

def build_dlt_analysis(
    df: pd.DataFrame,
    manifest_excluded: list[dict],
    analysis_window: int = DEFAULT_STATS_WINDOW,
) -> str:
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    df = df.sort_values("period_id").reset_index(drop=True)
    full_n = len(df)
    pid_full_min, pid_full_max = int(df["period_id"].iloc[0]), int(df["period_id"].iloc[-1])
    win = df.tail(min(analysis_window, full_n)).reset_index(drop=True)
    n = len(win)

    fronts = win[["front_1", "front_2", "front_3", "front_4", "front_5"]].astype(int).values.tolist()
    backs = win[["back_1", "back_2"]].astype(int).values.tolist()

    f_draws = [list(map(int, row)) for row in fronts]
    b_draws = [list(map(int, row)) for row in backs]
    fq, fcur, favg = freq_miss_from_draws(f_draws, win["period_id"].tolist(), 35)
    bq, bcur, bavg = freq_miss_from_draws(b_draws, win["period_id"].tolist(), 12)

    sums = np.array([sum(x) for x in f_draws])
    spans = np.array([max(x) - min(x) for x in f_draws])
    acs = np.array([ac_value(x) for x in f_draws], dtype=float)

    odd_rat = []
    consec_cnt = 0
    for row in f_draws:
        srow = sorted(row)
        odds = sum(1 for x in row if x % 2 == 1)
        odd_rat.append(odds)
        if any(srow[i + 1] - srow[i] == 1 for i in range(len(srow) - 1)):
            consec_cnt += 1

    odd_ctr = Counter(odd_rat)
    top_odd = odd_ctr.most_common(3)

    pid_min, pid_max = int(win["period_id"].min()), int(win["period_id"].max())
    excl_note = ""
    if manifest_excluded:
        excl_note = "\n".join(
            f"- Manifest 剔除记录：期号 `{e.get('period_id')}`，原因：{e.get('reason')}" for e in manifest_excluded
        )

    topf = topk(fq, 5, high=True)
    lowf = topk(fq, 5, high=False)
    topb = topk(bq, 5, high=True)
    lowb = topk(bq, 5, high=False)
    topf_miss = sorted([(i, int(fcur[i])) for i in range(1, 36)], key=lambda t: t[1], reverse=True)[:5]
    topb_miss = sorted([(i, int(bcur[i])) for i in range(1, 13)], key=lambda t: t[1], reverse=True)[:5]

    return f"""# 大乐透 — 历史数据分析归档

> **最后更新**：{now_cn_iso()}
> **统计窗口（默认）**：近 **{n}** 期，期号 **`{pid_min}`–`{pid_max}`**（期末尾连续段，至多 **{analysis_window}** 期）。
> **全表收录**：`data/processed/dlt_draws.csv` 共 **{full_n}** 期，期号 **`{pid_full_min}`–`{pid_full_max}`**（溯源见 `data/processed/manifest.json`）

---

## 摘要（数据范围与异常处理）

本次基于 **processed 主数据** `data/processed/dlt_draws.csv` 对大乐透历史开奖做质量检查与描述性统计。**本表不含开奖日期列**；**频率、遗漏与结构类指标**仅针对上述 **近 {n} 期** 默认窗口，全表范围见元数据。**以下结论仅基于期号 + 号码**。

质量检查结果：

- 期号：已按数值排序；`manifest.json` 中记录的剔除行 **未包含**在本 CSV（已在构建阶段剔除）。
- 号码区间：前区 01–35、后区 01–12（构建脚本已校验）。
{excl_note if excl_note else "- 剔除记录：见 manifest.json（与 processed 对照）。"}

**可执行结论**：

1. 后续分析与预测 **优先** 使用本 processed 文件；更新开奖数据请编辑 `data/processed/*.csv` 与 `manifest.json`，或使用 `lottery-draw-dlt-ssq` / `lottery-draw-sync` 后再重跑本脚本。
2. 若需修正异常期号，请走官方源核对后修正 processed 或走上述同步流程。

---

## 大乐透结果（数据质量检查与描述性统计）

以下频率、遗漏与结构统计均基于 **近 {n} 期** 默认窗口（非必为全表）。

### 1) 频次与遗漏

前区频次（Top5）：

- { "、".join([f"`{a}（{b}）`" for a, b in topf]) }

前区频次（Low5）：

- { "、".join([f"`{a}（{b}）`" for a, b in lowf]) }

后区频次（Top5）：

- { "、".join([f"`{a}（{b}）`" for a, b in topb]) }

后区频次（Low5）：

- { "、".join([f"`{a}（{b}）`" for a, b in lowb]) }

前区当前遗漏（Top5）：

- { "、".join([f"`{a}（{b}期）`" for a, b in topf_miss]) }

后区当前遗漏（Top5）：

- { "、".join([f"`{a}（{b}期）`" for a, b in topb_miss]) }

### 2) 和值 / 跨度 / AC（前区）

- 和值：{_qstats(sums)}
- 跨度：{_qstats(spans)}
- AC（算术复杂度，AC = D−(n−1)，n=5）：主要取值分布（Top5）：{format_ac_top(acs)}

### 3) 连号与奇偶结构

- 含至少一对连号占比：{consec_cnt / n * 100:.2f}%
- 前区奇数个数的常见取值（Top3）：{", ".join([f"`{k}奇:{n-k}偶`（{v}期）" for k,v in top_odd])}

### 4) 局限

历史分布仅为描述性统计，不构成预测或投资建议。

"""


# ── 双色球分析 ────────────────────────────────────────────────

def build_ssq_analysis(df: pd.DataFrame, analysis_window: int = DEFAULT_STATS_WINDOW) -> str:
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    df = df.sort_values("period_id").reset_index(drop=True)
    full_n = len(df)
    pid_full_min, pid_full_max = int(df["period_id"].iloc[0]), int(df["period_id"].iloc[-1])
    win = df.tail(min(analysis_window, full_n)).reset_index(drop=True)
    n = len(win)

    reds = win[[f"red_{i}" for i in range(1, 7)]].astype(int).values.tolist()
    blues = win["blue"].astype(int).tolist()
    r_draws = [list(map(int, row)) for row in reds]
    rq, rcur, _ = freq_miss_from_draws(r_draws, win["period_id"].tolist(), 33)
    bq, bcur, _ = freq_miss_from_draws([[b] for b in blues], win["period_id"].tolist(), 16)

    sums = np.array([sum(x) for x in r_draws])
    spans = np.array([max(x) - min(x) for x in r_draws])
    acs = np.array([ac_value(x) for x in r_draws], dtype=float)

    odd_rat = [sum(1 for x in row if x % 2 == 1) for row in r_draws]
    odd_ctr = Counter(odd_rat)
    top_odd = odd_ctr.most_common(3)

    consec_cnt = 0
    for row in r_draws:
        srow = sorted(row)
        if any(srow[i + 1] - srow[i] == 1 for i in range(len(srow) - 1)):
            consec_cnt += 1

    pid_min, pid_max = int(win["period_id"].min()), int(win["period_id"].max())
    topr = topk(rq, 5, high=True)
    lowr = topk(rq, 5, high=False)
    topb = topk(bq, 5, high=True)
    lowb = topk(bq, 5, high=False)
    top_miss_r = sorted([(i, int(rcur[i])) for i in range(1, 34)], key=lambda t: t[1], reverse=True)[:5]
    top_miss_b = sorted([(i, int(bcur[i])) for i in range(1, 17)], key=lambda t: t[1], reverse=True)[:5]

    return f"""# 双色球 — 历史数据分析归档

> **最后更新**：{now_cn_iso()}
> **统计窗口（默认）**：近 **{n}** 期，期号 **`{pid_min}`–`{pid_max}`**（期末尾连续段，至多 **{analysis_window}** 期）。
> **全表收录**：`data/processed/ssq_draws.csv` 共 **{full_n}** 期，期号 **`{pid_full_min}`–`{pid_full_max}`**（溯源见 `data/processed/manifest.json`）

---

## 摘要（数据范围与异常处理）

本次基于 **processed 主数据** `data/processed/ssq_draws.csv` 做质量检查与描述性统计。**本表不含开奖日期列**；**频率、遗漏与结构类指标**仅针对上述 **近 {n} 期** 默认窗口。**以下结论仅基于期号 + 号码**。

质量检查要点：

- 期号已按数值排序；行内红球去重、区间 01–33，蓝球 01–16（构建脚本已校验）。

---

## 双色球结果（描述性统计）

以下频率、遗漏与结构统计均基于 **近 {n} 期** 默认窗口（非必为全表）。

### 1) 频次与遗漏

红球频次（Top5）：

- { "、".join([f"`{a}（{b}）`" for a, b in topr]) }

红球频次（Low5）：

- { "、".join([f"`{a}（{b}）`" for a, b in lowr]) }

蓝球频次（Top5）：

- { "、".join([f"`{a}（{b}）`" for a, b in topb]) }

蓝球频次（Low5）：

- { "、".join([f"`{a}（{b}）`" for a, b in lowb]) }

红球当前遗漏（Top5）：

- { "、".join([f"`{a}（{b}期）`" for a, b in top_miss_r]) }

蓝球当前遗漏（Top5）：

- { "、".join([f"`{a}（{b}期）`" for a, b in top_miss_b]) }

### 2) 和值 / 跨度 / AC（红球）

- 和值：{_qstats(sums)}
- 跨度：{_qstats(spans)}
- AC（n=6，AC=D−5）：{format_ac_top(acs)}

### 3) 连号与奇偶

- 含至少一对连号占比：{consec_cnt / n * 100:.2f}%
- 红球奇数个数 Top3：{", ".join([f"`{k}奇`（{v}期）" for k,v in top_odd])}

### 4) 局限

历史分布仅为描述性统计，不构成预测或投资建议。

"""


# ── 快乐八分析 ────────────────────────────────────────────────

def build_kl8_analysis(df: pd.DataFrame, analysis_window: int = DEFAULT_STATS_WINDOW) -> str:
    df = _norm_df(df)
    draws_all, pids_all = _kl8_draw_rows(df)
    full_n = len(draws_all)
    if full_n == 0:
        return "# 快乐八 — 历史数据分析归档\n\n（无数据行）\n"
    pid_full_min, pid_full_max = int(min(pids_all)), int(max(pids_all))
    cap = min(analysis_window, full_n)
    draws = draws_all[-cap:]
    pids = pids_all[-cap:]
    n = len(draws)
    fq, fcur, _ = freq_miss_from_draws(draws, pids, 80)
    pid_min, pid_max = int(min(pids)), int(max(pids))
    last_pid = int(pids[-1])

    man_src = ""
    man_note = ""
    if MANIFEST.exists():
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for block in m.get("outputs", []):
            if block.get("lottery_type") == "kl8":
                man_src = str(block.get("source", "") or "").strip()
                man_note = str(block.get("note", "") or "").strip()
                break

    hot5 = topk(fq, 5, high=True)
    low5 = topk(fq, 5, high=False)
    top_miss = sorted([(i, int(fcur[i])) for i in range(1, 81)], key=lambda t: -t[1])[:5]
    hot_txt = "、".join([f"`{a}（{b}）`" for a, b in hot5])
    low_txt = "、".join([f"`{a}（{b}）`" for a, b in low5])
    miss_txt = "、".join([f"`{a}（{b}期）`" for a, b in top_miss])

    sums = np.array([sum(d) for d in draws], dtype=float)
    spans = np.array([max(d) - min(d) for d in draws], dtype=float)

    odds_n = [sum(1 for x in d if x % 2 == 1) for d in draws]
    odd_ctr = Counter(odds_n).most_common(3)
    odd_line = ", ".join([f"`{k}奇/{20 - k}偶`（{v}期）" for k, v in odd_ctr])

    rows_md = "\n".join([f"| {_fmt2(i)} | {int(fq[i])} | {int(fcur[i])} |" for i in range(1, 81)])
    verify = n * 20
    man_extra = ""
    if man_src:
        man_extra += f"\n> **manifest.source**：`{man_src}`"
    if man_note:
        man_extra += f"\n> **manifest.note**：{man_note}"

    return f"""# 快乐八 — 历史数据分析归档

> **最后更新**：{now_cn_iso()}
> **统计窗口（默认）**：近 **{n}** 期，期号 **`{pid_min}`–`{pid_max}`**（期末尾连续段，至多 **{analysis_window}** 期）。
> **全表收录**：`data/processed/kl8_draws.csv` 共 **{full_n}** 行，期号 **`{pid_full_min}`–`{pid_full_max}`**（溯源见 `data/processed/manifest.json`）
> **所用数据路径**：`data/processed/kl8_draws.csv`
> **最后一期（窗口内）**：`{last_pid}`{man_extra}

---

## 摘要（数据范围与统计视角）

本次基于 **processed** `kl8_draws.csv` 做质量检查与描述性统计。**频率、遗漏与结构类指标**仅针对上述 **近 {n} 期** 默认窗口（与大乐透/双色球 `regenerate-history` 一致）；全表行数见元数据。

- **结构**：每期一行，`period_id` + `n01`–`n20` 共 **20** 个开奖号码；取值 **01–80**。
- **数据质量（脚本自检）**：窗口内每期恰为 **20** 个互异号码、升序存储、无越界（与 `lottery.py validate` 规则一致方可入库）。
- **统计视角**：下文「频次 / 当前遗漏」均针对 **每期开出的 20 个开奖号码**；**不等同**于「选十」玩法下购彩者选 10 个号后的中奖分析。

---

## 「开奖 20 码」与「选十玩法」视角区分

| 视角 | 含义 | 本报告 |
|------|------|--------|
| **开奖 20 码** | 每期从 01–80 中开出 **20** 个不重复号码 | 频次、遗漏均基于窗口内这 20 码的出现 |
| **选十玩法** | 购彩者从 80 个号中选 **10** 个投注并按规则计奖 | **未**模拟选十注单；选十视角须另定义口径 |

---

## 快乐八结果（数据质量检查与描述性统计）

以下频率、遗漏与结构统计均基于 **近 {n} 期** 默认窗口（非必为全表）。

### 1) 频次与遗漏（01–80）

开奖号码出现次数（Top5）：

- {hot_txt}

出现次数（Low5）：

- {low_txt}

当前遗漏（Top5，截至窗口末 `{last_pid}`）：

- {miss_txt}

### 2) 每期 20 码和值与跨度（窗口内）

- 20 码和值：{_qstats(sums)}
- 20 码跨度（max−min）：{_qstats(spans)}

### 3) 每期 20 码中「奇数个数」主结构（Top3）

- {odd_line}

### 4) 全号码表（出现次数 / 当前遗漏，窗口内）

| 号码 | 出现次数 | 当前遗漏(期) |
|------|----------|----------------|
{rows_md}

*验算：{n} 期 × 20 码/期 = **{verify}** 次球号计入（窗口内）。*

### 5) 局限

- 开奖具有随机性，历史频次与遗漏**不构成**对未来开奖的可验证预测；本报告仅为描述性统计。
- 若 `manifest.json` 标注第三方来源，用途涉及合规或资金决策时请与**官方渠道**核对。
- 本分析**不包含**任何保证性结论；**禁止**「必出」「稳赚」类解读。

---

> **脚本提示**：本文件由 `python src/scripts/lottery.py regenerate-history`（`--only all` 且存在 `kl8_draws.csv` 时）或 `regenerate-history --only kl8` **按相同默认窗口**自动重写；亦可由 `lottery-history-analysis` 增补深度解读（须在元数据中保持口径一致）。
"""


# ── 大乐透预测 ────────────────────────────────────────────────

def prediction_block_dlt(df: pd.DataFrame, n_last: int = DEFAULT_STATS_WINDOW) -> str:
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    full = df.sort_values("period_id").reset_index(drop=True)
    tail = full.tail(n_last)
    pmin, pmax = int(tail["period_id"].min()), int(tail["period_id"].max())
    fronts = tail[["front_1", "front_2", "front_3", "front_4", "front_5"]].astype(int).values.tolist()
    backs = tail[["back_1", "back_2"]].astype(int).values.tolist()
    f_draws = [list(map(int, r)) for r in fronts]
    b_draws = [list(map(int, r)) for r in backs]
    f_draws_all = full[["front_1", "front_2", "front_3", "front_4", "front_5"]].astype(int).values.tolist()
    b_draws_all = full[["back_1", "back_2"]].astype(int).values.tolist()
    fq, fcur, _ = freq_miss_from_draws(f_draws, [], 35)
    bq, bcur, _ = freq_miss_from_draws(b_draws, [], 12)
    hotf = topk(fq, 5, high=True)
    lowf = topk(fq, 5, high=False)
    hotb = topk(bq, 5, high=True)
    lowb = topk(bq, 5, high=False)

    odd_pairs: dict[str, int] = {}
    size_pairs: dict[str, int] = {}
    sums = []
    spans = []
    for row in fronts:
        row = list(map(int, row))
        odds = sum(1 for x in row if x % 2)
        odd_pairs[f"{odds}:{5-odds}"] = odd_pairs.get(f"{odds}:{5-odds}", 0) + 1
        big = sum(1 for x in row if x >= 18)
        size_pairs[f"{big}:{5-big}"] = size_pairs.get(f"{big}:{5-big}", 0) + 1
        sums.append(sum(row))
        spans.append(max(row) - min(row))
    top_odd = sorted(odd_pairs.items(), key=lambda t: -t[1])[:2]
    top_sz = sorted(size_pairs.items(), key=lambda t: -t[1])[:2]
    s = np.array(sums, dtype=float)
    sp = np.array(spans, dtype=float)
    qs = np.percentile(s, [25, 50, 75])
    qsp = np.percentile(sp, [25, 50, 75])
    pred_ts = now_cn_iso()
    n_win = len(tail)
    f_mk = _markov_next_probabilities([list(map(int, r)) for r in f_draws_all], 35)
    b_mk = _markov_next_probabilities([list(map(int, r)) for r in b_draws_all], 12)
    f_mk_n = _minmax01_ball(f_mk, 35)
    b_mk_n = _minmax01_ball(b_mk, 12)
    fs = _dlt_front_scores(f_draws, fq, fcur, f_mk)
    bs = _dlt_back_scores(b_draws, bq, bcur, b_mk)
    five = _dlt_collect_five_unique_tickets(fs, bs)
    numbers_md = _build_dlt_five_numbers_md(
        five, fs, bs, fq, fcur, bq, bcur, f_mk, f_mk_n, b_mk, b_mk_n, n_win, pred_ts,
    )

    return f"""# 大乐透 — 统计型预测参考归档

> **最后更新**：{pred_ts}
> **统计窗口**：近 **{n_win}** 期（至多 **{n_last}** 期，期末尾连续段）
> **期号范围**：`{pmin}`–`{pmax}`
> **所用数据路径**：`data/processed/dlt_draws.csv`
> **引用分析归档**（可选）：`history/daletou_analysis.md`

---

## 口径说明

- 彩种：大乐透
- 窗口：近 **{n_win}** 期（至多 **{n_last}** 期）
- 指标：热/冷号 = 窗口内出现次数；前区奇偶比、大小比（18–35 为大）；前区 5 码和值与跨度
- **{PREDICTION_SINGLE_LINES} 注单式（机械）**：每注前区 5 + 后区 2；各号多因子原始分 **min-max 归一** 后按权重合成综合分，再按下述小区上限贪心取号（**同分随机**）。**前区**：**7** 段、每段连续 **5** 个号（**01–05 / 06–10 / 11–15 / 16–20 / 21–25 / 26–30 / 31–35**），每段至多 **{DLT_FRONT_MAX_PER_ZONE}** 个；**后区**：**3** 段、每段连续 **4** 个号（**01–04 / 05–08 / 09–12**），每段至多 **{DLT_BACK_MAX_PER_ZONE}** 个。**{PREDICTION_SINGLE_LINES} 注**之间对**已出现过的号码**在下一轮综合分上施加**递减惩罚**，以拉开互异组合；仍不足则换随机种子补全互异注。**权重**：**{_pattern_weight_md_line()}**；因子含 **近 {PATTERN_RECENT_K} 期密度、奇偶结构、大小（前≥18 / 后≥7）、和值带、区段划分**（区间热度与取号分区一致），并新增 **马尔可夫链转移因子**：基于**全历史**（非仅窗口）按相邻期重算二状态转移矩阵，取**最新一期状态**对应的下一期出现条件概率。

## 结果摘要

- 前区热号：{ "、".join([f"`{a}（{b}）`" for a,b in hotf]) }
- 前区冷号：{ "、".join([f"`{a}（{b}）`" for a,b in lowf]) }
- 后区热号：{ "、".join([f"`{a}（{b}）`" for a,b in hotb]) }
- 后区冷号：{ "、".join([f"`{a}（{b}）`" for a,b in lowb]) }
- 奇偶主结构：{ "；".join([f"`{k}`（{v}期）" for k,v in top_odd]) }
- 大小主结构：{ "；".join([f"`{k}`（{v}期）" for k,v in top_sz]) }
- 和值：中位数约 `{qs[1]:.0f}`，Q1–Q3 约 `{qs[0]:.0f}`–`{qs[2]:.0f}`，均值 `{s.mean():.2f}`
- 跨度：中位数约 `{qsp[1]:.0f}`，Q1–Q3 约 `{qsp[0]:.0f}`–`{qsp[2]:.0f}`

## 明确号码输出（强制，统计参考）

{numbers_md}

## 使用说明

以上仅为近 **{n_win}** 期历史统计参考，用于娱乐与信息整理；下一期开奖仍为独立随机事件，不构成中奖承诺或投资建议。
{_prediction_md_appendix_budget_rules("大乐透", _dlt_appendix_five_singles_line())}
"""


# ── 双色球预测 ────────────────────────────────────────────────

def prediction_block_ssq(df: pd.DataFrame, n_last: int = DEFAULT_STATS_WINDOW) -> str:
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    full = df.sort_values("period_id").reset_index(drop=True)
    tail = full.tail(n_last)
    pmin, pmax = int(tail["period_id"].min()), int(tail["period_id"].max())
    reds = tail[[f"red_{i}" for i in range(1, 7)]].astype(int).values.tolist()
    blues = tail["blue"].astype(int).tolist()
    r_draws = [list(map(int, r)) for r in reds]
    blues_list = [int(b) for b in blues]
    reds_all = full[[f"red_{i}" for i in range(1, 7)]].astype(int).values.tolist()
    blues_all = full["blue"].astype(int).tolist()
    rq, rcur, _ = freq_miss_from_draws(r_draws, [], 33)
    bq, bcur, _ = freq_miss_from_draws([[b] for b in blues_list], [], 16)
    hotr = topk(rq, 5, high=True)
    lowr = topk(rq, 5, high=False)
    hotb = topk(bq, 5, high=True)
    lowb = topk(bq, 5, high=False)

    odd_pairs: dict[str, int] = {}
    size_pairs: dict[str, int] = {}
    sums = []
    spans = []
    for row in reds:
        row = list(map(int, row))
        odds = sum(1 for x in row if x % 2)
        odd_pairs[f"{odds}:{6-odds}"] = odd_pairs.get(f"{odds}:{6-odds}", 0) + 1
        big = sum(1 for x in row if x >= 17)
        size_pairs[f"{big}:{6-big}"] = size_pairs.get(f"{big}:{6-big}", 0) + 1
        sums.append(sum(row))
        spans.append(max(row) - min(row))
    top_odd = sorted(odd_pairs.items(), key=lambda t: -t[1])[:2]
    top_sz = sorted(size_pairs.items(), key=lambda t: -t[1])[:2]
    s = np.array(sums, dtype=float)
    sp = np.array(spans, dtype=float)
    qs = np.percentile(s, [25, 50, 75])
    qsp = np.percentile(sp, [25, 50, 75])
    pred_ts = now_cn_iso()
    n_win = len(tail)
    r_mk = _markov_next_probabilities([list(map(int, r)) for r in reds_all], 33)
    b_mk = _markov_next_probabilities([[int(x)] for x in blues_all], 16)
    r_mk_n = _minmax01_ball(r_mk, 33)
    b_mk_n = _minmax01_ball(b_mk, 16)
    rs = _ssq_red_scores(r_draws, rq, rcur, r_mk)
    bs_sc = _ssq_blue_scores(blues_list, bq, bcur, b_mk)
    five = _ssq_collect_five_unique_tickets(rs, bs_sc)
    numbers_md = _build_ssq_five_numbers_md(
        five, rs, bs_sc, rq, rcur, bq, bcur, r_mk, r_mk_n, b_mk, b_mk_n, n_win, pred_ts,
    )

    return f"""# 双色球 — 统计型预测参考归档

> **最后更新**：{pred_ts}
> **统计窗口**：近 **{n_win}** 期（至多 **{n_last}** 期，期末尾连续段）
> **期号范围**：`{pmin}`–`{pmax}`
> **所用数据路径**：`data/processed/ssq_draws.csv`
> **引用分析归档**（可选）：`history/shuangseqiu_analysis.md`

---

## 口径说明

- 彩种：双色球
- 窗口：近 **{n_win}** 期（至多 **{n_last}** 期）
- 指标：红球热/冷、蓝球热/冷；红球奇偶比；大小比（17–33 为大）；红球和值与跨度
- **{PREDICTION_SINGLE_LINES} 注单式（机械）**：每注红球 6 + 蓝球 1；多因子 **min-max 归一** 后加权合成，再按下述小区上限贪心取号（**同分随机**）。**红球**：**7** 段、每段连续 **5** 个号（末段 **31–33** 仅 3 个号：**01–05 / 06–10 / 11–15 / 16–20 / 21–25 / 26–30 / 31–33**），每段至多 **{SSQ_RED_MAX_PER_ZONE}** 个；**蓝球**：**4** 段、每段连续 **4** 个号（**01–04 / 05–08 / 09–12 / 13–16**），每段至多 **{SSQ_BLUE_MAX_PER_ZONE}** 个（单码取蓝时自然满足）。**{PREDICTION_SINGLE_LINES} 注**间对**已出现过的号码**在下一轮综合分上施加**递减惩罚**以拉开互异组合；仍不足则换随机种子补全。**权重**：**{_pattern_weight_md_line()}**；红球另有 **近 {PATTERN_RECENT_K} 期密度、奇偶/大小（≥17）、和值带、五码段划分**；蓝球另有 **近 {PATTERN_RECENT_K} 期密度、奇偶、中位蓝贴近、大号占比（≥9）**，并新增 **马尔可夫链转移因子**：每次预测都基于**全历史**重算转移矩阵，按**最新一期状态**取下一期条件概率入权重。

## 结果摘要

- 红球热号：{ "、".join([f"`{a}（{b}）`" for a,b in hotr]) }
- 红球冷号：{ "、".join([f"`{a}（{b}）`" for a,b in lowr]) }
- 蓝球热号：{ "、".join([f"`{a}（{b}）`" for a,b in hotb]) }
- 蓝球冷号：{ "、".join([f"`{a}（{b}）`" for a,b in lowb]) }
- 奇偶主结构：{ "；".join([f"`{k}`（{v}期）" for k,v in top_odd]) }
- 大小主结构：{ "；".join([f"`{k}`（{v}期）" for k,v in top_sz]) }
- 和值：中位数约 `{qs[1]:.0f}`，Q1–Q3 约 `{qs[0]:.0f}`–`{qs[2]:.0f}`，均值 `{s.mean():.2f}`
- 跨度：中位数约 `{qsp[1]:.0f}`，Q1–Q3 约 `{qsp[0]:.0f}`–`{qsp[2]:.0f}`

## 明确号码输出（强制，统计参考）

{numbers_md}

## 使用说明

以上仅为近 **{n_win}** 期历史统计参考；下一期仍为独立随机事件，不构成中奖承诺或投资建议。
{_prediction_md_appendix_budget_rules("双色球", _ssq_appendix_five_singles_line())}
"""


# ── 快乐八预测 ────────────────────────────────────────────────

def prediction_block_kl8(df: pd.DataFrame, n_last: int = DEFAULT_STATS_WINDOW) -> str:
    df = _norm_df(df)
    draws_all, pids_all = _kl8_draw_rows(df)
    full_n = len(draws_all)
    if full_n == 0:
        return "# 快乐八 — 统计型预测参考归档\n\n（无数据行）\n"
    cap = min(n_last, full_n)
    draws = draws_all[-cap:]
    pids = pids_all[-cap:]
    n = len(draws)
    fq, fcur, _ = freq_miss_from_draws(draws, pids, 80)
    pid_min, pid_max = int(min(pids)), int(max(pids))
    last_pid = int(pids[-1]) if pids else pid_max
    pid_full_min, pid_full_max = int(min(pids_all)), int(max(pids_all))

    hot5 = topk(fq, 5, high=True)
    low5 = topk(fq, 5, high=False)
    top_miss = sorted([(i, int(fcur[i])) for i in range(1, 81)], key=lambda t: -t[1])[:5]
    markov_raw = _markov_next_probabilities(draws_all, 80)
    markov_norm = _minmax01_ball(markov_raw, 80)
    twenty = _kl8_twenty_from_patterns(fq, fcur, draws, markov_raw)
    twenty_zone_counts = _assert_kl8_zone_bounds(twenty, "参考开奖20码")
    twenty_fmt = ",".join(_fmt2(x) for x in twenty)
    eleven = _kl8_eleven_random_from_twenty(twenty)
    eleven_zone_counts = _assert_kl8_zone_bounds(eleven, "选十参考11码")
    eleven_fmt = ",".join(_fmt2(x) for x in eleven)
    twenty_markov_detail = "；".join(
        [
            f"{_fmt2(x)}:P={float(markov_raw[x]):.4f},N={float(markov_norm[x]):.3f},C≈{PATTERN_W_MARKOV * float(markov_norm[x]):.3f}"
            for x in twenty
        ]
    )
    eleven_markov_detail = "；".join(
        [
            f"{_fmt2(x)}:P={float(markov_raw[x]):.4f},N={float(markov_norm[x]):.3f},C≈{PATTERN_W_MARKOV * float(markov_norm[x]):.3f}"
            for x in eleven
        ]
    )

    hot_line = "；".join([f"`{a}`（**{b}** 次）" for a, b in hot5])
    low_line = "；".join([f"`{a}`（**{b}** 次）" for a, b in low5])
    miss_line = "；".join([f"`{a}`（**{b}** 期）" for a, b in top_miss])
    wline = _pattern_weight_md_line()

    return f"""# 快乐八 — 统计型预测参考归档

> **最后更新**：{now_cn_iso()}
> **统计窗口（默认）**：近 **{n}** 期，期号 **`{pid_min}`–`{pid_max}`**（期末尾连续段，至多 **{n_last}** 期）。
> **随机种子**：`{_ACTIVE_RANDOM_SEED}`（同数据同种子可复现）。
> **全表收录**：`kl8_draws.csv` 共 **{full_n}** 行，期号 **`{pid_full_min}`–`{pid_full_max}`**（见 `data/processed/manifest.json` 中 `lottery_type` 为 `kl8` 的条目）
> **所用数据路径**：`data/processed/kl8_draws.csv`
> **manifest 路径**：`data/processed/manifest.json`（`outputs` 中 `lottery_type: "kl8"`；第三方批次等以 manifest 为准，建议与福彩官方公告抽样核对）
> **样本说明**：默认窗口 **{n}** 期；全表 **{full_n}** 期相对快乐八全历史仍可能为**短样本**；统计结论**不可**外推为长期规律。
> **引用分析归档**（可选复查）：`history/kuaileba_analysis.md`

---

## 开奖 20 码统计 ≠ 选十自选 10 码中奖逻辑（须区分）

| 项目 | 本归档统计 | 选十玩法 |
|------|------------|----------|
| **对象** | 每期官方开出的 **20** 个开奖号码在样本内的出现频次与「自上次开出至最后一期」的遗漏期数 | 购彩者自 **80** 码中选 **10** 码投注，按官方规则与开奖结果比对计奖 |
| **可复现指标** | 对 01–80 各号在样本「20 码集合」中的计数与当前遗漏 | 涉及命中个数、奖级与奖金结构，**不能**由「20 码频次表」直接等同为「选十中奖概率或期望」 |

**结论**：下文「热号 / 冷号」仅描述 **开奖 20 码** 在已入库样本中的历史频率与遗漏，**不是**选十玩法下投注单的命中分析；二者不可混为一谈。

---

## 口径说明

- **彩种**：中国福利彩票 **快乐八**（KL8）。
- **期号范围（统计窗口）**：`{pid_min}` 至 `{pid_max}`，共 **{n}** 期。
- **指标定义**：
  - **出现次数（频次）**：在上述 **{n}** 期窗口内，该号码出现在每期 `n01`–`n20` 中的总次数（每期最多计 1 次）。
  - **当前遗漏（期）**：自该号码**最近一次**出现之后，至**最后一期 `{last_pid}`** 为止所经过的期数；若最后一期开出该号，则遗漏为 **0**。
- **数据来源**：`data/processed/kl8_draws.csv`；溯源见 `manifest.json` 中 `kl8` 条目。
- **「规律线」参考 20 码（脚本）**：对 01–80 各号计算 **8** 项原始分（全窗口频次、当前遗漏、近 **{PATTERN_RECENT_K}** 期出现密度、与窗口内「每期 20 码奇数个数均值」的奇偶对齐、**01–40 / 41–80** 半区占比对齐、**20 码和值**相对中位带的条件对齐、**四区** 01–20 / 21–40 / 41–60 / 61–80 区段热度、**马尔可夫链转移概率**）；其中马尔可夫项按**全历史开奖**每次重算转移矩阵，并基于**最新一期状态**计算下一期出现条件概率。**每项先 min-max 归一到 [0,1]**，再按权重 **{wline}** 合成，分高者优先（**同分随机**）；取号时按 **8 个十码段（01–10,…,71–80）每段至少 {KL8_MIN_PER_PICK_ZONE} 个且至多 {KL8_MAX_PER_PICK_ZONE} 个** 贪心取满 **20** 个互异号码后升序展示。**不是**从「最后一期已开出的 20 个号」里抽样，也**不是**单纯频次 Top20；仍属历史统计投影，**非**科学预测。

---

## 结果摘要

### 热号（频次 Top5，样本内描述）

{hot_line}

### 冷号（频次 Top5，样本内描述）

{low_line}

### 当前遗漏（节选，截至 `{last_pid}`）

{miss_line}

---

## 参考开奖 20 码（规律线 → 模拟一期 20 个开奖号）

> 基于**当前 {n} 期窗口**的统计规律（**非**从最后一期已开 20 码中随机）：对每号 **8** 项因子 min-max 归一后按权重 **{wline}** 合成综合分，在 **8 个十码段每段至少 {KL8_MIN_PER_PICK_ZONE} 个且至多 {KL8_MAX_PER_PICK_ZONE} 个** 约束下贪心取满 **20** 个互异号码（**同分随机**，每次运行可不同），升序排列，作为「下一期可参考的一注 20 码开奖形态」的**机械候选**；**非**官方开奖预告、**非**必中依据。

- **参考开奖 20 码（升序）**：**{twenty_fmt}**
- **分区计数校验（01-10..71-80）**：`{twenty_zone_counts}`（每区至少 {KL8_MIN_PER_PICK_ZONE}、至多 {KL8_MAX_PER_PICK_ZONE}）
- **马尔可夫因子明细（P=原始概率, N=归一值, C=权重贡献）**：{twenty_markov_detail}

---

## 明确号码输出（强制，选十视角统计参考）

> 在上一节由**规律线综合分**得到的 **20 个参考开奖号码**中，**无放回随机抽取 11 个**，且满足 **8 个十码段每段至少 {KL8_MIN_PER_PICK_ZONE} 个且至多 {KL8_MAX_PER_PICK_ZONE} 个**（与 20 码同一分段），升序排列，供选十 **11 码复式**或裁剪为 10 码参考。**每次重新运行**生成脚本，**11 码可能与上次不同**（**20 码**在相同数据与常量下不变，但同分边界仍受随机影响时可变）；仍属娱乐向统计参考，**非**必中依据。

- **选十参考 11 码（升序）**：**{eleven_fmt}**
- **分区计数校验（01-10..71-80）**：`{eleven_zone_counts}`（每区至少 {KL8_MIN_PER_PICK_ZONE}、至多 {KL8_MAX_PER_PICK_ZONE}）
- **马尔可夫因子明细（P=原始概率, N=归一值, C=权重贡献）**：{eleven_markov_detail}

## 使用说明

以上全部内容均为对**已发生开奖记录**在声明口径下的**描述性统计**，用于娱乐与自行复盘参考。**下一期开奖仍为独立随机事件**，历史冷热、遗漏长短**不构成**对未来开奖的任何保证或「必出」依据；本归档**不包含**中奖承诺与投注金额建议。
{_prediction_md_appendix_kl8_bet(eleven_fmt)}

---

> **提示**：本文件由 `python src/scripts/lottery.py regenerate-history --only kl8`（**同时**重写 `history/kuaileba_analysis.md`）或 `regenerate-history --only all`（存在 `kl8_draws.csv` 时）生成；文末附录含 **10～30 元** 带内机械复式示例。若追加更复杂方案，可再请 **`lottery-combo-optimize`** 并写投注原因。
"""
