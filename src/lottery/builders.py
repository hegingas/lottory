"""分析/预测 Markdown 构建器：大乐透、双色球、快乐八的分析与预测归档生成。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as _lottery_config
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
    DLT_FRONT_MAX_ACTIVE_ZONES,
    DLT_BACK_MAX_ACTIVE_ZONES,
    SSQ_RED_MAX_ACTIVE_ZONES,
    SSQ_BLUE_MAX_ACTIVE_ZONES,
    KL8_MAX_ACTIVE_ZONES,
    PREDICTION_SINGLE_LINES,
    PATTERN_RECENT_K,
    PATTERN_W_MARKOV,
    KL8_MIN_PER_PICK_ZONE,
    KL8_MAX_PER_PICK_ZONE,
    KL8_PICK_ZONES_CAP,
    KL8_ELEVEN_OVERLAP_MAX,
    MARKOV_LAPLACE_ALPHA,
)
from .interval_markov import (
    expand_kl8_decadic_mask,
    expand_mask_until_pickable,
    format_mask_zones,
    markov_next_bitmap,
    mask_to_active_zone_ranges,
    mask_to_allowed_balls,
    valid_mask_set,
)
from .scoring import (
    ac_value,
    freq_miss_from_draws,
    topk,
    _minmax01_ball,
    _markov_next_probabilities,
    _markov_blended_probabilities,
    _recency_counts,
    _dlt_front_scores,
    _dlt_back_scores,
    _ssq_red_scores,
    _ssq_blue_scores,
    _kl8_twenty_scores,
)
from .selection import (
    _dlt_collect_five_unique_tickets,
    _ssq_collect_five_unique_tickets,
    _kl8_eleven_from_patterns,
    _kl8_eleven_cap_overlap_latest,
    _assert_kl8_zone_bounds,
    _kl8_decadic_zone_totals,
    _zone_index_for_ball,
    _pick_top_indices_zone_capped,
    _dlt_ticket_passes_history_rules,
    _ssq_ticket_passes_history_rules,
    _qxc_collect_five_tickets,
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
    f_mk = _markov_blended_probabilities(f_draws, 35)
    b_mk = _markov_blended_probabilities(b_draws, 12)
    fs = _dlt_front_scores(f_draws, fq, fcur, f_mk)
    bs = _dlt_back_scores(b_draws, bq, bcur, b_mk)
    fa = [list(map(int, row)) for row in f_draws]
    ba = [list(map(int, row)) for row in b_draws]
    _, mf, _, _, _ = markov_next_bitmap(fa, DLT_FRONT_ZONES_CAP, valid_set=valid_mask_set(7, DLT_FRONT_MAX_ACTIVE_ZONES))
    af = mask_to_allowed_balls(
        expand_mask_until_pickable(mf, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE, 5),
        DLT_FRONT_ZONES_CAP,
    )
    _, mb, _, _, _ = markov_next_bitmap(ba, DLT_BACK_ZONES_CAP, valid_set=valid_mask_set(4, DLT_BACK_MAX_ACTIVE_ZONES))
    ab = mask_to_allowed_balls(
        expand_mask_until_pickable(mb, DLT_BACK_ZONES_CAP, DLT_BACK_MAX_PER_ZONE, 2),
        DLT_BACK_ZONES_CAP,
    )
    f0, b0 = _dlt_collect_five_unique_tickets(fs, bs, allowed_front=af, allowed_back=ab)[0]
    return ",".join(_fmt2(x) for x in f0), ",".join(_fmt2(x) for x in b0)


def ssq_explicit_from_patterns(
    r_draws: list[list[int]],
    blues: list[int],
    rq: np.ndarray,
    rcur: np.ndarray,
    bq: np.ndarray,
    bcur: np.ndarray,
) -> tuple[str, str]:
    r_mk = _markov_blended_probabilities(r_draws, 33)
    b_mk = _markov_blended_probabilities([[int(x)] for x in blues], 16)
    rs = _ssq_red_scores(r_draws, rq, rcur, r_mk)
    bs = _ssq_blue_scores(blues, bq, bcur, b_mk)
    ra = [list(map(int, row)) for row in r_draws]
    ba = [[int(b)] for b in blues]
    _, mr, _, _, _ = markov_next_bitmap(ra, SSQ_RED_ZONES_CAP, valid_set=valid_mask_set(7, SSQ_RED_MAX_ACTIVE_ZONES))
    ar = mask_to_allowed_balls(
        expand_mask_until_pickable(mr, SSQ_RED_ZONES_CAP, SSQ_RED_MAX_PER_ZONE, 6),
        SSQ_RED_ZONES_CAP,
    )
    _, mbl, _, _, _ = markov_next_bitmap(ba, SSQ_BLUE_ZONES_CAP, valid_set=valid_mask_set(4, SSQ_BLUE_MAX_ACTIVE_ZONES))
    abl = mask_to_allowed_balls(
        expand_mask_until_pickable(mbl, SSQ_BLUE_ZONES_CAP, SSQ_BLUE_MAX_PER_ZONE, 1),
        SSQ_BLUE_ZONES_CAP,
    )
    r0, b0 = _ssq_collect_five_unique_tickets(rs, bs, allowed_red=ar, allowed_blue=abl)[0]
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
    f_mk = _markov_blended_probabilities([list(map(int, r)) for r in f_draws_all], 35)
    b_mk = _markov_blended_probabilities([list(map(int, r)) for r in b_draws_all], 12)
    f_mk_n = _minmax01_ball(f_mk, 35)
    b_mk_n = _minmax01_ball(b_mk, 12)
    fs = _dlt_front_scores(f_draws, fq, fcur, f_mk)
    bs = _dlt_back_scores(b_draws, bq, bcur, b_mk)
    hist_keys_dlt: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()
    for _, row in full.iterrows():
        f_t = tuple(sorted(int(row[f"front_{i}"]) for i in range(1, 6)))
        b_t = tuple(sorted((int(row["back_1"]), int(row["back_2"]))))
        hist_keys_dlt.add((f_t, b_t))
    lr_d = full.iloc[-1]
    latest_dlt_seven = set(int(lr_d[f"front_{i}"]) for i in range(1, 6)) | {
        int(lr_d["back_1"]),
        int(lr_d["back_2"]),
    }
    f_all_rows = [list(map(int, r)) for r in f_draws_all]
    b_all_rows = [list(map(int, r)) for r in b_draws_all]
    s_last_f, m_front, p_front, row_f, short_fb_f = markov_next_bitmap(f_all_rows, DLT_FRONT_ZONES_CAP, valid_set=valid_mask_set(7, DLT_FRONT_MAX_ACTIVE_ZONES))
    m_front_e = expand_mask_until_pickable(
        m_front, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE, 5
    )
    allowed_front_dlt = mask_to_allowed_balls(m_front_e, DLT_FRONT_ZONES_CAP)
    s_last_b, m_back, p_back, row_b, short_fb_b = markov_next_bitmap(b_all_rows, DLT_BACK_ZONES_CAP, valid_set=valid_mask_set(4, DLT_BACK_MAX_ACTIVE_ZONES))
    m_back_e = expand_mask_until_pickable(
        m_back, DLT_BACK_ZONES_CAP, DLT_BACK_MAX_PER_ZONE, 2
    )
    allowed_back_dlt = mask_to_allowed_balls(m_back_e, DLT_BACK_ZONES_CAP)

    # ── 区间选择原因说明 ──
    full_n_dlt = len(f_all_rows)
    last_pid_dlt = int(full["period_id"].iloc[-1])
    dlt_markov_bullet = (
        f"对**全表 {full_n_dlt} 期**：将每期前区 5 码映射到 **7** 个五码段（01–05 / 06–10 / 11–15 / 16–20 / 21–25 / 26–30 / 31–35），"
        f"后区 2 码映射到 **4** 个三段（01–03 / 04–06 / 07–09 / 10–12），各段至少 1 球则对应位为 1，按段序拼成二进制掩码；"
        f"统计相邻期掩码的一阶转移并对条件行施加拉普拉斯 **α={MARKOV_LAPLACE_ALPHA}**。"
        f"以最后一期 **`{last_pid_dlt}`** 为条件：\n"
        f"- **前区**：末态掩码 **{format_mask_zones(s_last_f, DLT_FRONT_ZONES_CAP)}**（`{s_last_f}`），"
        f"平滑后概率最大的下一掩码 **{format_mask_zones(m_front, DLT_FRONT_ZONES_CAP)}**（`{m_front}`，平滑概率 **{p_front:.4f}**；该条件行历史转移条数 **{row_f}**）；"
        f"按「每区至多 {DLT_FRONT_MAX_PER_ZONE} 个、共 5 球」展开为 **{format_mask_zones(m_front_e, DLT_FRONT_ZONES_CAP)}**（`{m_front_e}`）\n"
        f"- **后区**：末态掩码 **{format_mask_zones(s_last_b, DLT_BACK_ZONES_CAP)}**（`{s_last_b}`），"
        f"平滑后概率最大的下一掩码 **{format_mask_zones(m_back, DLT_BACK_ZONES_CAP)}**（`{m_back}`，平滑概率 **{p_back:.4f}**；该条件行历史转移条数 **{row_b}**）；"
        f"按「每区至多 {DLT_BACK_MAX_PER_ZONE} 个、共 2 球」展开为 **{format_mask_zones(m_back_e, DLT_BACK_ZONES_CAP)}**（`{m_back_e}`）"
    )
    if short_fb_f or short_fb_b:
        dlt_markov_bullet += " **说明**：全表不足 **2** 期时条件不足，展开掩码退化为全开。"
    elif (row_f == 0 or row_b == 0) and full_n_dlt >= 2:
        dlt_markov_bullet += (
            " **说明**：末态在全表除最后一期外的历史中从未作为某期前一状态出现，下一掩码主要由平滑先验在全部候选间竞争决定。"
        )

    five = _dlt_collect_five_unique_tickets(
        fs,
        bs,
        hist_keys=hist_keys_dlt,
        latest_seven=latest_dlt_seven,
        allowed_front=allowed_front_dlt,
        allowed_back=allowed_back_dlt,
    )
    numbers_md = _build_dlt_five_numbers_md(
        five,
        fs,
        bs,
        fq,
        fcur,
        bq,
        bcur,
        f_mk,
        f_mk_n,
        b_mk,
        b_mk_n,
        n_win,
        pred_ts,
        hist_keys_dlt,
        latest_dlt_seven,
    )

    try:
        fi_p = sorted(_pick_top_indices_zone_capped(fs, 1, 35, 5, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE))
        bi_p = sorted(_pick_top_indices_zone_capped(bs, 1, 12, 2, DLT_BACK_ZONES_CAP, DLT_BACK_MAX_PER_ZONE))
        if not _dlt_ticket_passes_history_rules(fi_p, bi_p, hist_keys_dlt, latest_dlt_seven):
            fi_p, bi_p = five[0]
        best_score = sum(float(fs[i]) for i in fi_p) + sum(float(bs[i]) for i in bi_p)
    except Exception:
        fi_p, bi_p = five[0]
        best_score = sum(float(fs[i]) for i in fi_p) + sum(float(bs[i]) for i in bi_p)

    pred_data = {
        "lottery_type": "dlt",
        "prediction_date": pred_ts,
        "window_start": int(pmin),
        "window_end": int(pmax),
        "tickets": [{"index": i, "numbers": {"front": list(f), "back": list(b)}} for i, (f, b) in enumerate(five, 1)],
        "best": {"numbers": {"front": fi_p, "back": bi_p}, "score": best_score},
    }

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
- **{PREDICTION_SINGLE_LINES} 注单式（机械）**：每注前区 5 + 后区 2；各号多因子原始分 **min-max 归一** 后按权重合成综合分，再按下述小区上限贪心取号（**同分随机**）。**前区**：**7** 段、每段连续 **5** 个号（**01–05 / 06–10 / 11–15 / 16–20 / 21–25 / 26–30 / 31–35**），每段至多 **{DLT_FRONT_MAX_PER_ZONE}** 个；**后区**：**4** 段（**01–03 / 04–06 / 07–09 / 10–12**），每段至多 **{DLT_BACK_MAX_PER_ZONE}** 个。**选号域（区间掩码马尔可夫 — 为什么选择这些区间）**：
{dlt_markov_bullet}
在展开后的掩码并集号码内用综合分取号。**{PREDICTION_SINGLE_LINES} 注**之间对**已出现过的号码**在下一轮综合分上施加**递减惩罚**，以拉开互异组合；仍不足则换随机种子补全互异注。**权重**：**{_pattern_weight_md_line()}**；因子含 **近 {PATTERN_RECENT_K} 期密度、奇偶结构、大小（前≥18 / 后≥7）、和值带、区段划分**（区间热度与取号分区一致），并含 **马尔可夫链转移因子**（最大权重）：基于**全历史**同时计算**一阶**与**二阶**二状态转移矩阵，按 **40% 一阶 + 60% 二阶** 混合后取最新状态对应的下一期出现条件概率（与上文「区间掩码马尔可夫」为不同层次：前者约束候选球集合，后者进入按号评分）。

## 结果摘要

- 前区热号：{ "、".join([f"`{a}（{b}）`" for a,b in hotf]) }
- 前区冷号：{ "、".join([f"`{a}（{b}）`" for a,b in lowf]) }
- 后区热号：{ "、".join([f"`{a}（{b}）`" for a,b in hotb]) }
- 后区冷号：{ "、".join([f"`{a}（{b}）`" for a,b in lowb]) }
- 奇偶主结构：{ "；".join([f"`{k}`（{v}期）" for k,v in top_odd]) }
- 大小主结构：{ "；".join([f"`{k}`（{v}期）" for k,v in top_sz]) }
- 和值：中位数约 `{qs[1]:.0f}`，Q1–Q3 约 `{qs[0]:.0f}`–`{qs[2]:.0f}`，均值 `{s.mean():.2f}`
- 跨度：中位数约 `{qsp[1]:.0f}`，Q1–Q3 约 `{qsp[0]:.0f}`–`{qsp[2]:.0f}`
- **去核心化**：已执行去核心化约束——选号在多因子加权、小区上限与注间递减惩罚下进行，未直接采用「最近窗口纯频次 Top 骨架」作为唯一依据。
- **防重合**：防重合约束已执行（**历史任一期开奖与预测单式不完全相同**，且与**最新一期** 7 码集合重合 **≤3**）。

## 明确号码输出（强制，统计参考）

{numbers_md}

## 使用说明

以上仅为近 **{n_win}** 期历史统计参考，用于娱乐与信息整理；下一期开奖仍为独立随机事件，不构成中奖承诺或投资建议。
{_prediction_md_appendix_budget_rules("大乐透", _dlt_appendix_five_singles_line())}
""", pred_data


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
    r_mk = _markov_blended_probabilities([list(map(int, r)) for r in reds_all], 33)
    b_mk = _markov_blended_probabilities([[int(x)] for x in blues_all], 16)
    r_mk_n = _minmax01_ball(r_mk, 33)
    b_mk_n = _minmax01_ball(b_mk, 16)
    rs = _ssq_red_scores(r_draws, rq, rcur, r_mk)
    bs_sc = _ssq_blue_scores(blues_list, bq, bcur, b_mk)
    hist_keys_ssq: set[tuple[tuple[int, ...], int]] = set()
    for _, row in full.iterrows():
        r_t = tuple(sorted(int(row[f"red_{i}"]) for i in range(1, 7)))
        b_t = int(row["blue"])
        hist_keys_ssq.add((r_t, b_t))
    lr_s = full.iloc[-1]
    latest_ssq_seven = set(int(lr_s[f"red_{i}"]) for i in range(1, 7)) | {int(lr_s["blue"])}
    r_all_rows = [list(map(int, r)) for r in reds_all]
    b_all_rows = [[int(x)] for x in blues_all]
    s_last_r, m_red, p_red, row_r, short_fb_r = markov_next_bitmap(r_all_rows, SSQ_RED_ZONES_CAP, valid_set=valid_mask_set(7, SSQ_RED_MAX_ACTIVE_ZONES))
    m_red_e = expand_mask_until_pickable(
        m_red, SSQ_RED_ZONES_CAP, SSQ_RED_MAX_PER_ZONE, 6
    )
    allowed_red_ssq = mask_to_allowed_balls(m_red_e, SSQ_RED_ZONES_CAP)
    s_last_b, m_blue, p_blue, row_b, short_fb_b = markov_next_bitmap(b_all_rows, SSQ_BLUE_ZONES_CAP, valid_set=valid_mask_set(4, SSQ_BLUE_MAX_ACTIVE_ZONES))
    m_blue_e = expand_mask_until_pickable(
        m_blue, SSQ_BLUE_ZONES_CAP, SSQ_BLUE_MAX_PER_ZONE, 1
    )
    allowed_blue_ssq = mask_to_allowed_balls(m_blue_e, SSQ_BLUE_ZONES_CAP)

    # ── 区间选择原因说明 ──
    full_n_ssq = len(r_all_rows)
    last_pid_ssq = int(full["period_id"].iloc[-1])
    ssq_markov_bullet = (
        f"对**全表 {full_n_ssq} 期**：将每期红球 6 码映射到 **7** 个五码段（01–05 / 06–10 / 11–15 / 16–20 / 21–25 / 26–30 / 31–33），"
        f"蓝球 1 码映射到 **4** 个四码段（01–04 / 05–08 / 09–12 / 13–16），各段至少 1 球则对应位为 1，按段序拼成二进制掩码；"
        f"统计相邻期掩码的一阶转移并对条件行施加拉普拉斯 **α={MARKOV_LAPLACE_ALPHA}**。"
        f"以最后一期 **`{last_pid_ssq}`** 为条件：\n"
        f"- **红球**：末态掩码 **{format_mask_zones(s_last_r, SSQ_RED_ZONES_CAP)}**（`{s_last_r}`），"
        f"平滑后概率最大的下一掩码 **{format_mask_zones(m_red, SSQ_RED_ZONES_CAP)}**（`{m_red}`，平滑概率 **{p_red:.4f}**；该条件行历史转移条数 **{row_r}**）；"
        f"按「每区至多 {SSQ_RED_MAX_PER_ZONE} 个、共 6 球」展开为 **{format_mask_zones(m_red_e, SSQ_RED_ZONES_CAP)}**（`{m_red_e}`）\n"
        f"- **蓝球**：末态掩码 **{format_mask_zones(s_last_b, SSQ_BLUE_ZONES_CAP)}**（`{s_last_b}`），"
        f"平滑后概率最大的下一掩码 **{format_mask_zones(m_blue, SSQ_BLUE_ZONES_CAP)}**（`{m_blue}`，平滑概率 **{p_blue:.4f}**；该条件行历史转移条数 **{row_b}**）；"
        f"按「每区至多 {SSQ_BLUE_MAX_PER_ZONE} 个、共 1 球」展开为 **{format_mask_zones(m_blue_e, SSQ_BLUE_ZONES_CAP)}**（`{m_blue_e}`）"
    )
    if short_fb_r or short_fb_b:
        ssq_markov_bullet += " **说明**：全表不足 **2** 期时条件不足，展开掩码退化为全开。"
    elif (row_r == 0 or row_b == 0) and full_n_ssq >= 2:
        ssq_markov_bullet += (
            " **说明**：末态在全表除最后一期外的历史中从未作为某期前一状态出现，下一掩码主要由平滑先验在全部候选间竞争决定。"
        )

    five = _ssq_collect_five_unique_tickets(
        rs,
        bs_sc,
        hist_keys=hist_keys_ssq,
        latest_seven=latest_ssq_seven,
        allowed_red=allowed_red_ssq,
        allowed_blue=allowed_blue_ssq,
    )
    numbers_md = _build_ssq_five_numbers_md(
        five,
        rs,
        bs_sc,
        rq,
        rcur,
        bq,
        bcur,
        r_mk,
        r_mk_n,
        b_mk,
        b_mk_n,
        n_win,
        pred_ts,
        hist_keys_ssq,
        latest_ssq_seven,
    )

    try:
        ri_p = sorted(_pick_top_indices_zone_capped(rs, 1, 33, 6, SSQ_RED_ZONES_CAP, SSQ_RED_MAX_PER_ZONE))
        bi_p_raw = _pick_top_indices_zone_capped(bs_sc, 1, 16, 1, SSQ_BLUE_ZONES_CAP, SSQ_BLUE_MAX_PER_ZONE)
        bl_p = int(bi_p_raw[0])
        if not _ssq_ticket_passes_history_rules(ri_p, bl_p, hist_keys_ssq, latest_ssq_seven):
            ri_p, bl_p = five[0]
        best_score = sum(float(rs[i]) for i in ri_p) + float(bs_sc[bl_p])
    except Exception:
        ri_p, bl_p = five[0]
        best_score = sum(float(rs[i]) for i in ri_p) + float(bs_sc[bl_p])

    pred_data = {
        "lottery_type": "ssq",
        "prediction_date": pred_ts,
        "window_start": int(pmin),
        "window_end": int(pmax),
        "tickets": [{"index": i, "numbers": {"red": list(r), "blue": int(bl)}} for i, (r, bl) in enumerate(five, 1)],
        "best": {"numbers": {"red": ri_p, "blue": bl_p}, "score": best_score},
    }

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
- **{PREDICTION_SINGLE_LINES} 注单式（机械）**：每注红球 6 + 蓝球 1；多因子 **min-max 归一** 后加权合成，再按下述小区上限贪心取号（**同分随机**）。**红球**：**7** 段、每段连续 **5** 个号（末段 **31–33** 仅 3 个号：**01–05 / 06–10 / 11–15 / 16–20 / 21–25 / 26–30 / 31–33**），每段至多 **{SSQ_RED_MAX_PER_ZONE}** 个；**蓝球**：**4** 段、每段连续 **4** 个号（**01–04 / 05–08 / 09–12 / 13–16**），每段至多 **{SSQ_BLUE_MAX_PER_ZONE}** 个（单码取蓝时自然满足）。**选号域（区间掩码马尔可夫 — 为什么选择这些区间）**：
{ssq_markov_bullet}
在展开后的掩码并集号码内用综合分取号。**{PREDICTION_SINGLE_LINES} 注**间对**已出现过的号码**在下一轮综合分上施加**递减惩罚**以拉开互异组合；仍不足则换随机种子补全。**权重**：**{_pattern_weight_md_line()}**；红球另有 **近 {PATTERN_RECENT_K} 期密度、奇偶/大小（≥17）、和值带、五码段划分**；蓝球另有 **近 {PATTERN_RECENT_K} 期密度、奇偶、中位蓝贴近、大号占比（≥9）**，并含 **马尔可夫链转移因子**（最大权重）：每次预测都基于**全历史**重算一阶与二阶转移矩阵，按 **40% 一阶 + 60% 二阶** 混合后取最新状态对应下一期条件概率入权重（与「区间掩码马尔可夫」层次区分同大乐透口径）。

## 结果摘要

- 红球热号：{ "、".join([f"`{a}（{b}）`" for a,b in hotr]) }
- 红球冷号：{ "、".join([f"`{a}（{b}）`" for a,b in lowr]) }
- 蓝球热号：{ "、".join([f"`{a}（{b}）`" for a,b in hotb]) }
- 蓝球冷号：{ "、".join([f"`{a}（{b}）`" for a,b in lowb]) }
- 奇偶主结构：{ "；".join([f"`{k}`（{v}期）" for k,v in top_odd]) }
- 大小主结构：{ "；".join([f"`{k}`（{v}期）" for k,v in top_sz]) }
- 和值：中位数约 `{qs[1]:.0f}`，Q1–Q3 约 `{qs[0]:.0f}`–`{qs[2]:.0f}`，均值 `{s.mean():.2f}`
- 跨度：中位数约 `{qsp[1]:.0f}`，Q1–Q3 约 `{qsp[0]:.0f}`–`{qsp[2]:.0f}`
- **去核心化**：已执行去核心化约束——选号在多因子加权、小区上限与注间递减惩罚下进行，未直接采用「最近窗口纯频次 Top 骨架」作为唯一依据。
- **防重合**：防重合约束已执行（**历史任一期开奖与预测单式不完全相同**，且与**最新一期** 7 码集合重合 **≤3**）。

## 明确号码输出（强制，统计参考）

{numbers_md}

## 使用说明

以上仅为近 **{n_win}** 期历史统计参考；下一期仍为独立随机事件，不构成中奖承诺或投资建议。
{_prediction_md_appendix_budget_rules("双色球", _ssq_appendix_five_singles_line())}
""", pred_data


def _kl8_collect_one_path_outputs(
    fq: np.ndarray,
    fcur: np.ndarray,
    draws: list[list[int]],
    markov_raw: np.ndarray,
    active_zones: list[tuple[int, int]],
    kl8_scores: np.ndarray,
    latest20_set: set[int],
    markov_norm: np.ndarray,
) -> dict[str, object]:
    """单路径：给定活跃十码段，直接生成 11 码、分区校验与马尔可夫因子明细。"""
    eleven, _ = _kl8_eleven_from_patterns(fq, fcur, draws, markov_raw, active_zones)
    eleven = _kl8_eleven_cap_overlap_latest(eleven, latest20_set, kl8_scores, active_zones)
    olap = len(set(eleven) & latest20_set)
    eleven_zone_counts = _assert_kl8_zone_bounds(eleven, "选十参考11码", active_zones)
    eleven_fmt = ",".join(_fmt2(x) for x in eleven)
    pref11_score = sum(float(kl8_scores[int(x)]) for x in eleven)
    eleven_markov_detail = "；".join(
        [
            f"{_fmt2(x)}:P={float(markov_raw[x]):.4f},N={float(markov_norm[x]):.3f},C≈{PATTERN_W_MARKOV * float(markov_norm[x]):.3f}"
            for x in eleven
        ]
    )
    return {
        "olap": olap,
        "eleven": eleven,
        "eleven_zone_counts": eleven_zone_counts,
        "eleven_fmt": eleven_fmt,
        "pref11_score": pref11_score,
        "eleven_markov_detail": eleven_markov_detail,
    }


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
    markov_raw = _markov_blended_probabilities(draws_all, 80)
    markov_norm = _minmax01_ball(markov_raw, 80)
    kl8_scores = _kl8_twenty_scores(fq, fcur, draws, markov_raw)
    latest20_set = set(int(x) for x in draws_all[-1])

    pred_ts = now_cn_iso()

    s_last_k, s_pred_k, p_pred_k, row_total_k, short_fb_k = markov_next_bitmap(
        draws_all, KL8_PICK_ZONES_CAP, valid_set=valid_mask_set(8, KL8_MAX_ACTIVE_ZONES)
    )
    m_exp_k = expand_kl8_decadic_mask(
        s_pred_k, KL8_PICK_ZONES_CAP, 11, KL8_MAX_PER_PICK_ZONE
    )
    active_zones = mask_to_active_zone_ranges(m_exp_k, KL8_PICK_ZONES_CAP)
    w = _kl8_collect_one_path_outputs(
        fq, fcur, draws, markov_raw, active_zones, kl8_scores, latest20_set, markov_norm
    )

    totals8w = _kl8_decadic_zone_totals(draws)
    active_zone_choice_md = "；".join(
        f"`{_fmt2(lo)}–{_fmt2(hi)}`（该十码段在窗口内累计 **{totals8w[_zone_index_for_ball(lo, KL8_PICK_ZONES_CAP)]}** 次）"
        for lo, hi in active_zones
    )

    markov_path_bullet = (
        f"对**全表 {full_n} 期**：将每期开奖 **20** 码映射到 **8** 个十码段，若某段至少出现 **1** 球则对应位为 **1**，按段序拼成 **8** 位二进制掩码；"
        f"统计相邻期掩码的一阶转移并对条件行施加拉普拉斯 **α={MARKOV_LAPLACE_ALPHA}**。以最后一期 **`{last_pid}`** 的掩码 **{format_mask_zones(s_last_k, KL8_PICK_ZONES_CAP)}**（`{s_last_k}`）为条件，"
        f"取平滑后概率最大的下一掩码 **{format_mask_zones(s_pred_k, KL8_PICK_ZONES_CAP)}**（`{s_pred_k}`，平滑概率 **{p_pred_k:.4f}**；该条件行历史转移条数 **{row_total_k}**）。"
        f"再按快乐八规则将掩码扩展至至少 **4** 个活跃段且在「每段至多 **{KL8_MAX_PER_PICK_ZONE}** 个」下可凑满 **11** 码（仍不足则全开）；展开后为 **{format_mask_zones(m_exp_k, KL8_PICK_ZONES_CAP)}**（`{m_exp_k}`）。"
    )
    if short_fb_k:
        markov_path_bullet += " **说明**：全表不足 **2** 期时条件不足，展开掩码退化为全开。"
    elif row_total_k == 0 and full_n >= 2:
        markov_path_bullet += (
            " **说明**：末态在全表除最后一期外的历史中从未作为某期前一状态出现，下一掩码主要由平滑先验在全部候选间竞争决定。"
        )

    olap = int(w["olap"])
    eleven_codes = list(w["eleven"])
    eleven_fmt = str(w["eleven_fmt"])
    eleven_zone_counts = w["eleven_zone_counts"]
    eleven_markov_detail = str(w["eleven_markov_detail"])
    pref11 = float(w["pref11_score"])

    hot_line = "；".join([f"`{a}`（**{b}** 次）" for a, b in hot5])
    low_line = "；".join([f"`{a}`（**{b}** 次）" for a, b in low5])
    miss_line = "；".join([f"`{a}`（**{b}** 期）" for a, b in top_miss])
    wline = _pattern_weight_md_line()

    pred_data = {
        "lottery_type": "kl8",
        "prediction_date": pred_ts,
        "window_start": int(pid_min),
        "window_end": int(pid_max),
        "tickets": [{"index": 1, "numbers": {"codes": eleven_codes}}],
        "best": {"numbers": {"codes": eleven_codes}, "score": float(pref11)},
    }

    return f"""# 快乐八 — 统计型预测参考归档

> **最后更新**：{pred_ts}
> **统计窗口（默认）**：近 **{n}** 期，期号 **`{pid_min}`–`{pid_max}`**（期末尾连续段，至多 **{n_last}** 期）。
> **随机种子**：`{_lottery_config._ACTIVE_RANDOM_SEED}`（同数据同种子可复现）。
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
- **「规律线」综合分**：对 01–80 各号计算 **8** 项原始分（全窗口频次、当前遗漏、近 **{PATTERN_RECENT_K}** 期出现密度、与窗口内「每期 20 码奇数个数均值」的奇偶对齐、**01–40 / 41–80** 半区占比对齐、**20 码和值**相对中位带的条件对齐、**四区** 01–20 / 21–40 / 41–60 / 61–80 区段热度、**马尔可夫链转移概率**）；其中马尔可夫项（最大权重）按**全历史开奖**每次重算一阶与二阶转移矩阵，按 **40% 一阶 + 60% 二阶** 混合后基于最新两期状态计算下一期出现条件概率。**每项先 min-max 归一到 [0,1]**，再按权重 **{wline}** 合成，分高者优先（**同分随机**）。**不是**从「最后一期已开出的 20 个号」里抽样，也**不是**单纯频次 Top20；仍属历史统计投影，**非**科学预测。
- **活跃十码段（区间二进制掩码 → 一阶马尔可夫 → 展开）**：{markov_path_bullet}在展开后的活跃十码段并集内直接取满 **11** 码：各段 **{KL8_MIN_PER_PICK_ZONE}–{KL8_MAX_PER_PICK_ZONE}** 个，非活跃段 **0** 个。本窗口各活跃段频次摘要：{active_zone_choice_md}。

---

## 结果摘要

### 热号（频次 Top5，样本内描述）

{hot_line}

### 冷号（频次 Top5，样本内描述）

{low_line}

### 当前遗漏（节选，截至 `{last_pid}`）

{miss_line}

### 合规与去核心化（仓库硬规则）

- **去核心化**：在多因子与**马尔可夫展开后的活跃十码段**上下限内取号，**不是**单纯频次 Top11，也**不是**从上一期 20 码中抽样。
- **重合约束**：与**最新一期 `{last_pid}`** 真实开奖 20 码重合 **{olap}** 个（目标 **≤{KL8_ELEVEN_OVERLAP_MAX}**；超出时按「重合球中综合分从低到高」替换，且替换号**仍须落在活跃段并集内**；仍建议与官方公告核对）。

---

## 明确号码输出（强制，选十视角统计参考）

> 在近 **{n}** 期窗口综合分下，**仅在**上文马尔可夫展开后的活跃十码段并集内直接贪心取 **11** 个互异号码（**同分随机**），并执行重合上限修正。

- **选十参考 11 码（升序）**：**{eleven_fmt}**
- **活跃十码段**：{active_zone_choice_md}
- **分区计数（8 段，非活跃段须为 0）**：`{eleven_zone_counts}`（活跃段每段 {KL8_MIN_PER_PICK_ZONE}–{KL8_MAX_PER_PICK_ZONE} 个）
- **马尔可夫因子明细**：{eleven_markov_detail}

## 单式优选（强制，选十 11 码复式参考）

> **生成时间**：`{pred_ts}`（北京时间）。

- **11 码（C(11,10) 复式）**：**{eleven_fmt}**；综合分之和 **{pref11:.3f}**
- **关键因子**：频次、遗漏、近端密度、奇偶/半区/和值带、区段热度、马尔可夫等，见上文权重。

## 使用说明

以上全部内容均为对**已发生开奖记录**在声明口径下的**描述性统计**，用于娱乐与自行复盘参考。**下一期开奖仍为独立随机事件**，历史冷热、遗漏长短**不构成**对未来开奖的任何保证或「必出」依据；本归档**不包含**中奖承诺与投注金额建议。
{_prediction_md_appendix_kl8_bet(eleven_fmt)}

---

> **提示**：本文件由 `python src/scripts/lottery.py regenerate-history --only kl8`（**同时**重写 `history/kuaileba_analysis.md`）或 `regenerate-history --only all`（存在 `kl8_draws.csv` 时）生成；文末附录含 **10～30 元** 带内机械复式示例。若追加更复杂方案，可再请 **`lottery-combo-optimize`** 并写投注原因。
""", pred_data


# ── 排列5分析与预测 ──────────────────────────────────────────────

def _pl5_norm01(vals: np.ndarray) -> np.ndarray:
    arr = vals.astype(float)
    lo = float(arr.min())
    hi = float(arr.max())
    if hi <= lo:
        return np.full_like(arr, 0.5, dtype=float)
    return (arr - lo) / (hi - lo)


def _pl5_markov_probs(draws: list[list[int]], pos: int, laplace: float = 1.0) -> np.ndarray:
    """一阶马尔可夫（按位）：基于相邻期 digit 转移矩阵 + 最新一期 digit → 下一期各 digit 条件概率。"""
    out = np.full(10, 0.1, dtype=float)
    if len(draws) < 2:
        return out
    trans = np.zeros((10, 10), dtype=float)
    for t in range(1, len(draws)):
        prev = int(draws[t - 1][pos])
        cur = int(draws[t][pos])
        trans[prev, cur] += 1.0
    latest = int(draws[-1][pos])
    row = trans[latest]
    den = float(row.sum() + 10.0 * laplace)
    for d in range(10):
        out[d] = (float(row[d]) + laplace) / den
    return out


def _pl5_markov_probs_2nd(draws: list[list[int]], pos: int, laplace: float = 1.0) -> np.ndarray:
    """二阶马尔可夫（按位）：基于 (digit_{t-2}, digit_{t-1}) → digit_t 转移矩阵。"""
    out = np.full(10, 0.1, dtype=float)
    if len(draws) < 3:
        return out
    trans = np.zeros((10, 10, 10), dtype=float)
    for t in range(2, len(draws)):
        prev2 = int(draws[t - 2][pos])
        prev1 = int(draws[t - 1][pos])
        cur = int(draws[t][pos])
        trans[prev2, prev1, cur] += 1.0
    prev2_latest = int(draws[-2][pos])
    prev1_latest = int(draws[-1][pos])
    row = trans[prev2_latest, prev1_latest]
    den = float(row.sum() + 10.0 * laplace)
    for d in range(10):
        out[d] = (float(row[d]) + laplace) / den
    return out


def _pl5_markov_blended(draws: list[list[int]], pos: int, laplace: float = 1.0,
                        w1: float = 0.40, w2: float = 0.60) -> np.ndarray:
    """一阶 + 二阶马尔可夫混合概率（按位）。不足 3 期时退化为纯一阶。"""
    p1 = _pl5_markov_probs(draws, pos, laplace)
    if len(draws) < 3:
        return p1
    p2 = _pl5_markov_probs_2nd(draws, pos, laplace)
    return w1 * p1 + w2 * p2


def build_pl5_analysis(df: pd.DataFrame, analysis_window: int = DEFAULT_STATS_WINDOW) -> str:
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    df = df.sort_values("period_id").reset_index(drop=True)
    full_n = len(df)
    if full_n == 0:
        return "# 排列5 — 历史数据分析归档\n\n（无数据行）\n"
    pid_full_min, pid_full_max = int(df["period_id"].iloc[0]), int(df["period_id"].iloc[-1])
    win = df.tail(min(analysis_window, full_n)).reset_index(drop=True)
    n = len(win)
    pid_min, pid_max = int(win["period_id"].min()), int(win["period_id"].max())

    cols = [f"d{i}" for i in range(1, 6)]
    draws = win[cols].astype(int).values.tolist()
    flat = [x for row in draws for x in row]
    ctr = Counter(flat)
    hot = sorted(ctr.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    cold = sorted(ctr.items(), key=lambda kv: (kv[1], kv[0]))[:5]

    pos_lines: list[str] = []
    for i in range(5):
        c = Counter(int(row[i]) for row in draws)
        top3 = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        pos_lines.append(
            f"- 第{i + 1}位：{ '、'.join([f'`{d}`（{ct}次）' for d, ct in top3]) }"
        )

    sums = np.array([sum(map(int, row)) for row in draws], dtype=float)
    spans = np.array([max(map(int, row)) - min(map(int, row)) for row in draws], dtype=float)
    repeat_n = sum(1 for row in draws if len(set(map(int, row))) < 5)

    return f"""# 排列5 — 历史数据分析归档

> **最后更新**：{now_cn_iso()}
> **统计窗口（默认）**：近 **{n}** 期，期号 **`{pid_min}`–`{pid_max}`**（期末尾连续段，至多 **{analysis_window}** 期）。
> **全表收录**：`data/processed/pl5_draws.csv` 共 **{full_n}** 期，期号 **`{pid_full_min}`–`{pid_full_max}`**（溯源见 `data/processed/manifest.json`）

---

## 摘要（数据范围与口径）

本次基于 `data/processed/pl5_draws.csv` 进行描述性统计。每期包含 **5** 位数字（`d1`–`d5`），取值范围 **0–9**，**允许重复数字**。

## 结果摘要

- 全窗口数字热度 Top5：{ "、".join([f"`{d}`（{ct}次）" for d, ct in hot]) }
- 全窗口数字冷度 Top5：{ "、".join([f"`{d}`（{ct}次）" for d, ct in cold]) }
- 含重复数字的期数占比：**{repeat_n}/{n} = {repeat_n / max(n, 1) * 100:.2f}%**
- 和值：{_qstats(sums)}
- 跨度（max-min）：{_qstats(spans)}

## 分位热度（Top3）

{chr(10).join(pos_lines)}

## 局限

排列5开奖结果具有随机性；以上统计仅用于历史描述，不构成中奖承诺或投资建议。
"""


def prediction_block_pl5(df: pd.DataFrame, n_last: int = DEFAULT_STATS_WINDOW) -> str:
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    full = df.sort_values("period_id").reset_index(drop=True)
    if len(full) == 0:
        return "# 排列5 — 统计型预测参考归档\n\n（无数据行）\n"
    tail = full.tail(min(n_last, len(full))).reset_index(drop=True)
    pmin, pmax = int(tail["period_id"].min()), int(tail["period_id"].max())
    cols = [f"d{i}" for i in range(1, 6)]
    draws_all = full[cols].astype(int).values.tolist()
    draws = tail[cols].astype(int).values.tolist()
    n_win = len(draws)
    pred_ts = now_cn_iso()

    scores_by_pos: list[np.ndarray] = []
    mk_by_pos: list[np.ndarray] = []
    for pos in range(5):
        freq = np.zeros(10, dtype=float)
        miss = np.zeros(10, dtype=float)
        rec = np.zeros(10, dtype=float)
        for row in draws:
            freq[int(row[pos])] += 1.0
        for d in range(10):
            m = n_win
            for k in range(n_win - 1, -1, -1):
                if int(draws[k][pos]) == d:
                    m = n_win - 1 - k
                    break
            miss[d] = float(m)
        for row in draws[-min(PATTERN_RECENT_K, n_win):]:
            rec[int(row[pos])] += 1.0
        mk = _pl5_markov_blended(draws_all, pos)
        mk_by_pos.append(mk)
        sc = (
            _lottery_config.QXC_W_MISS    * _pl5_norm01(miss)
            + _lottery_config.QXC_W_FREQ  * _pl5_norm01(freq)
            + _lottery_config.QXC_W_RECENCY * _pl5_norm01(rec)
            + _lottery_config.QXC_W_MARKOV * _pl5_norm01(mk)
        )
        scores_by_pos.append(sc)

    tickets: list[list[int]] = []
    used_pos_counts = np.zeros((5, 10), dtype=float)
    for _ in range(PREDICTION_SINGLE_LINES):
        ticket: list[int] = []
        for pos in range(5):
            adj = scores_by_pos[pos] - 0.08 * used_pos_counts[pos]
            digit = int(np.argmax(adj))
            ticket.append(digit)
            used_pos_counts[pos, digit] += 1.0
        if ticket in tickets:
            # 轻量去重：最后一位改为次优
            pos = 4
            adj = scores_by_pos[pos] - 0.08 * used_pos_counts[pos]
            order = list(np.argsort(-adj))
            for d in order:
                cand = ticket[:-1] + [int(d)]
                if cand not in tickets:
                    ticket = cand
                    used_pos_counts[pos, int(d)] += 1.0
                    break
        tickets.append(ticket)

    hot_lines: list[str] = []
    for pos in range(5):
        arr = scores_by_pos[pos]
        best = int(np.argmax(arr))
        hot_lines.append(
            f"- 第{pos + 1}位：优先 `[{best}]`（综合分 {float(arr[best]):.3f}，马尔可夫P≈{float(mk_by_pos[pos][best]):.4f}）"
        )

    numbers_md = []
    for i, t in enumerate(tickets, 1):
        num = "".join(str(int(x)) for x in t)
        numbers_md.append(f"- 第{i}注：**{num}**（分位：{','.join(str(int(x)) for x in t)}）")

    mech_line = (
        f"- **机械方案（{PREDICTION_SINGLE_LINES} 注单式）**：正文 {PREDICTION_SINGLE_LINES} 组单式号码，"
        f"每组按 **2 元**计，合计 **{PREDICTION_SINGLE_LINES * 2} 元**（落在 10～30 元带内）。"
    )

    pref_digits = [int(np.argmax(scores_by_pos[i])) for i in range(5)]
    pl5_pref_num = "".join(str(d) for d in pref_digits)
    pl5_pref_csv = ",".join(str(d) for d in pref_digits)
    pl5_pref_tot = sum(float(scores_by_pos[i][pref_digits[i]]) for i in range(5))

    pred_data = {
        "lottery_type": "pl5",
        "prediction_date": pred_ts,
        "window_start": int(pmin),
        "window_end": int(pmax),
        "tickets": [{"index": i, "numbers": {"digits": list(t)}} for i, t in enumerate(tickets, 1)],
        "best": {"numbers": {"digits": pref_digits}, "score": float(pl5_pref_tot)},
    }

    return f"""# 排列5 — 统计型预测参考归档

> **最后更新**：{pred_ts}
> **统计窗口**：近 **{n_win}** 期（至多 **{n_last}** 期，期末尾连续段）
> **期号范围**：`{pmin}`–`{pmax}`
> **所用数据路径**：`data/processed/pl5_draws.csv`
> **随机种子**：`{_lottery_config._ACTIVE_RANDOM_SEED}`（同数据同种子可复现）

---

## 口径说明

- 彩种：排列5
- 窗口：近 **{n_win}** 期（至多 **{n_last}** 期）
- 因子：分位频次、当前遗漏、近 **{PATTERN_RECENT_K}** 期密度、马尔可夫转移概率（一阶+二阶混合，基于全历史重算）
- 评分：按 `0.40×马尔可夫（一阶+二阶混合） + 0.20×遗漏 + 0.20×频次 + 0.20×近端密度` 合成分位综合分，5注之间施加轻度去重惩罚。

## 结果摘要

{chr(10).join(hot_lines)}

- **去核心化**：已执行去核心化约束——各注在分位综合分与注间去重惩罚下生成，未直接采用「每位单纯 Top1 热号」拼成 5 注不变体。

## 明确号码输出（强制，统计参考）

{chr(10).join(numbers_md)}

## 单式优选（强制）

> **生成时间**：`{pred_ts}`（北京时间）。

- **号码（5 位）**：**{pl5_pref_num}**（分位：`{pl5_pref_csv}`）
- **总分（五位综合分之和）**：**{pl5_pref_tot:.3f}**
- **关键因子**：遗漏、频次、近端密度、马尔可夫（见口径说明）。

## 使用说明

以上仅为历史统计参考，下一期开奖仍为独立随机事件，不构成中奖承诺或投资建议。

---

## 附录：预算与投注推荐（仓库默认）

- **金额带（强制）**：统计规律输出完成后，至少提供一套 **10～30 元（含）** 的打票参考。
{mech_line}
- **说明**：本附录仅作金额示例；若用户指定其他预算或倍投口径，以用户要求为准。
""", pred_data


# ── 七星彩分析与预测 ─────────────────────────────────────────────

def build_qxc_analysis(df: pd.DataFrame, analysis_window: int = DEFAULT_STATS_WINDOW) -> str:
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    df = df.sort_values("period_id").reset_index(drop=True)
    full_n = len(df)
    if full_n == 0:
        return "# 七星彩 — 历史数据分析归档\n\n（无数据行）\n"
    pid_full_min, pid_full_max = int(df["period_id"].iloc[0]), int(df["period_id"].iloc[-1])
    win = df.tail(min(analysis_window, full_n)).reset_index(drop=True)
    n = len(win)
    pid_min, pid_max = int(win["period_id"].min()), int(win["period_id"].max())

    fcols = [f"d{i}" for i in range(1, 7)]
    draws = win[fcols].astype(int).values.tolist()
    specials = win["special"].astype(int).tolist()

    flat_front = [x for row in draws for x in row]
    ctr_front = Counter(flat_front)
    hot_front = sorted(ctr_front.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    cold_front = sorted(ctr_front.items(), key=lambda kv: (kv[1], kv[0]))[:5]
    ctr_special = Counter(specials)
    hot_special = sorted(ctr_special.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    cold_special = sorted(ctr_special.items(), key=lambda kv: (kv[1], kv[0]))[:5]

    pos_lines: list[str] = []
    for i in range(6):
        c = Counter(int(row[i]) for row in draws)
        top3 = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        pos_lines.append(
            f"- 前区第{i + 1}位：{ '、'.join([f'`{d}`（{ct}次）' for d, ct in top3]) }"
        )
    pos_lines.append(
        f"- 后区（special 0–14）：{ '、'.join([f'`{d}`（{ct}次）' for d, ct in hot_special[:3]]) }"
    )

    sums = np.array([sum(map(int, row)) + int(specials[j]) for j, row in enumerate(draws)], dtype=float)
    spans_front = np.array([max(map(int, row)) - min(map(int, row)) for row in draws], dtype=float)
    repeat_n = sum(1 for row in draws if len(set(map(int, row))) < 6)

    return f"""# 七星彩 — 历史数据分析归档

> **最后更新**：{now_cn_iso()}
> **统计窗口（默认）**：近 **{n}** 期，期号 **`{pid_min}`–`{pid_max}`**（期末尾连续段，至多 **{analysis_window}** 期）。
> **全表收录**：`data/processed/qxc_draws.csv` 共 **{full_n}** 期，期号 **`{pid_full_min}`–`{pid_full_max}`**（溯源见 `data/processed/manifest.json`）

---

## 摘要（数据范围与口径）

本次基于 `data/processed/qxc_draws.csv` 进行描述性统计。每期包含 **前区 6 位**（`d1`–`d6`，0–9，允许重复）+ **后区 1 位**（`special`，0–14）。

## 结果摘要

- 前区 6 位数字热度 Top5：{ "、".join([f'`{d}`（{ct}次）' for d, ct in hot_front]) }
- 前区 6 位数字冷度 Top5：{ "、".join([f'`{d}`（{ct}次）' for d, ct in cold_front]) }
- 后区数字热度 Top5：{ "、".join([f'`{d}`（{ct}次）' for d, ct in hot_special]) }
- 后区数字冷度 Top5：{ "、".join([f'`{d}`（{ct}次）' for d, ct in cold_special]) }
- 前区含重复数字的期数占比：**{repeat_n}/{n} = {repeat_n / max(n, 1) * 100:.2f}%**
- 七星和值（前区+后区）：{_qstats(sums)}
- 前区跨度（max−min）：{_qstats(spans_front)}

## 分位热度（Top3）

{chr(10).join(pos_lines)}

## 局限

七星彩开奖结果具有随机性；以上统计仅用于历史描述，不构成中奖承诺或投资建议。
"""


def prediction_block_qxc(df: pd.DataFrame, n_last: int = DEFAULT_STATS_WINDOW) -> str:
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    full = df.sort_values("period_id").reset_index(drop=True)
    if len(full) == 0:
        return "# 七星彩 — 统计型预测参考归档\n\n（无数据行）\n"
    tail = full.tail(min(n_last, len(full))).reset_index(drop=True)
    pmin, pmax = int(tail["period_id"].min()), int(tail["period_id"].max())
    fcols = [f"d{i}" for i in range(1, 7)]
    draws = tail[fcols].astype(int).values.tolist()
    specials_all = full["special"].astype(int).tolist()
    specials_win = tail["special"].astype(int).tolist()
    n_win = len(draws)
    pred_ts = now_cn_iso()

    from .scoring import _qxc_position_scores
    from .selection import _qxc_collect_five_tickets

    scores_by_pos: list[np.ndarray] = []
    mk_by_pos: list[np.ndarray] = []
    for pos in range(6):
        sc, mk = _qxc_position_scores(draws, pos, 10, _lottery_config.QXC_W_MISS, _lottery_config.QXC_W_FREQ, _lottery_config.QXC_W_RECENCY, _lottery_config.QXC_W_MARKOV, PATTERN_RECENT_K)
        scores_by_pos.append(sc)
        mk_by_pos.append(mk)
    sc_special, mk_special = _qxc_position_scores(
        [[s] for s in specials_win], 0, 15, _lottery_config.QXC_W_MISS, _lottery_config.QXC_W_FREQ, _lottery_config.QXC_W_RECENCY, _lottery_config.QXC_W_MARKOV, PATTERN_RECENT_K
    )
    scores_by_pos.append(sc_special)
    mk_by_pos.append(mk_special)

    tickets = _qxc_collect_five_tickets(scores_by_pos)

    hot_lines: list[str] = []
    for pos in range(6):
        arr = scores_by_pos[pos]
        best = int(np.argmax(arr))
        hot_lines.append(
            f"- 前区第{pos + 1}位：优先 `[{best}]`（综合分 {float(arr[best]):.3f}，马尔可夫P≈{float(mk_by_pos[pos][best]):.4f}）"
        )
    hot_lines.append(
        f"- 后区：优先 `[{int(np.argmax(sc_special))}]`（综合分 {float(sc_special.max()):.3f}）"
    )

    numbers_md = []
    for i, t in enumerate(tickets, 1):
        front = ",".join(str(int(x)) for x in t[:6])
        sp = int(t[6])
        numbers_md.append(f"- 第{i}注：前区 **{front}** + 后区 `{sp}`（全码：`{front},{sp}`）")

    pref_front = [int(np.argmax(scores_by_pos[i])) for i in range(6)]
    pref_sp = int(np.argmax(sc_special))
    qxc_pref_front = ",".join(str(d) for d in pref_front)
    qxc_pref_full = f"{qxc_pref_front},{pref_sp}"
    qxc_pref_tot = sum(float(scores_by_pos[i][pref_front[i]]) for i in range(6)) + float(sc_special[pref_sp])

    pred_data = {
        "lottery_type": "qxc",
        "prediction_date": pred_ts,
        "window_start": int(pmin),
        "window_end": int(pmax),
        "tickets": [{"index": i, "numbers": {"front": [int(x) for x in t[:6]], "special": int(t[6])}} for i, t in enumerate(tickets, 1)],
        "best": {"numbers": {"front": pref_front, "special": pref_sp}, "score": float(qxc_pref_tot)},
    }

    mech_line = (
        f"- **机械方案（{PREDICTION_SINGLE_LINES} 注单式）**：正文 {PREDICTION_SINGLE_LINES} 组「前 6+后 1」单式，"
        f"每组按 **2 元**计，合计 **{PREDICTION_SINGLE_LINES * 2} 元**（落在 10～30 元带内）。"
    )

    return f"""# 七星彩 — 统计型预测参考归档

> **最后更新**：{pred_ts}
> **统计窗口**：近 **{n_win}** 期（至多 **{n_last}** 期，期末尾连续段）
> **期号范围**：`{pmin}`–`{pmax}`
> **所用数据路径**：`data/processed/qxc_draws.csv`
> **随机种子**：`{_lottery_config._ACTIVE_RANDOM_SEED}`（同数据同种子可复现）

---

## 口径说明

- 彩种：七星彩（前区 6 位 0–9 + 后区 1 位 0–14）
- 窗口：近 **{n_win}** 期（至多 **{n_last}** 期）
- 因子：分位频次、当前遗漏、近 **{PATTERN_RECENT_K}** 期密度、马尔可夫转移概率（一阶+二阶混合，基于全历史重算）
- 评分：按 `0.40×马尔可夫（一阶+二阶混合） + 0.20×遗漏 + 0.20×频次 + 0.20×近端密度` 合成分位综合分，5 注之间施加轻度去重惩罚。
- 七星彩为按位匹配游戏，不适用「与历史开奖完全重合」或「与最新期 ≤3 重合」的防重合约束。

## 结果摘要

{chr(10).join(hot_lines)}

- **去核心化**：已执行去核心化约束——各注在分位综合分与注间去重惩罚下生成，未直接采用「每位单纯 Top1 热号」拼成 5 注不变体。

## 明确号码输出（强制，统计参考）

{chr(10).join(numbers_md)}

## 单式优选（强制）

> **生成时间**：`{pred_ts}`（北京时间）。

- **号码（7 位）**：**{qxc_pref_full}**（前区：`{qxc_pref_front}`，后区：`{pref_sp}`）
- **总分（七位综合分之和）**：**{qxc_pref_tot:.3f}**
- **关键因子**：遗漏、频次、近端密度、马尔可夫（见口径说明）。

## 使用说明

以上仅为历史统计参考，下一期开奖仍为独立随机事件，不构成中奖承诺或投资建议。

---

## 附录：预算与投注推荐（仓库默认）

- **金额带（强制）**：统计规律输出完成后，至少提供一套 **10～30 元（含）** 的打票参考。
{mech_line}
- **说明**：本附录仅作金额示例；若用户指定其他预算或倍投口径，以用户要求为准。
""", pred_data
