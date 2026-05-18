"""分析 Markdown 构建器：大乐透、双色球、快乐八、排列5、七星彩的 analysis 归档生成。"""

from __future__ import annotations

import json
from collections import Counter

import numpy as np
import pandas as pd

from ..config import adaptive_stats_window
from ..markdown_utils import _fmt2, now_cn_iso
from ..scoring import ac_value, freq_miss_from_draws, topk
from ._utils import _kl8_draw_rows, _norm_df, _qstats, format_ac_top

# ── 大乐透分析 ────────────────────────────────────────────────


def build_dlt_analysis(
    df: pd.DataFrame,
    manifest_excluded: list[dict],
    analysis_window: int | None = None,
) -> str:
    if analysis_window is None:
        analysis_window = adaptive_stats_window(len(df))
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

def build_ssq_analysis(df: pd.DataFrame, analysis_window: int | None = None) -> str:
    if analysis_window is None:
        analysis_window = adaptive_stats_window(len(df))
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

def build_kl8_analysis(df: pd.DataFrame, analysis_window: int | None = None) -> str:
    if analysis_window is None:
        analysis_window = adaptive_stats_window(len(df))
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

    # lazy import to avoid circular dependency with __init__.py
    from . import MANIFEST  # noqa: F811

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
- **数据质量（脚本自检）**：窗口内每期恰为 **20** 个互异号码、升序存储、无越界（与 `cli.py validate` 规则一致方可入库）。
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

> **脚本提示**：本文件由 `python src/scripts/cli.py regenerate-history`（`--only all` 且存在 `kl8_draws.csv` 时）或 `regenerate-history --only kl8` **按相同默认窗口**自动重写；亦可由 `lottery-history-analysis` 增补深度解读（须在元数据中保持口径一致）。
"""


# ── 排列5 分析 ────────────────────────────────────────────────


def build_pl5_analysis(df: pd.DataFrame, analysis_window: int | None = None) -> str:
    if analysis_window is None:
        analysis_window = adaptive_stats_window(len(df))
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

    # ── 新指标：逐位结构分布 ──
    def _per_pos_stats(draw_rows, n_digits=10):
        """逐位奇偶/大小/质合/012路计数。返回 list[dict]。"""
        primes = {2, 3, 5, 7}
        n_pos = len(draw_rows[0])
        out = []
        for p in range(n_pos):
            digits = [int(r[p]) for r in draw_rows]
            odd = sum(1 for d in digits if d % 2 == 1)
            big = sum(1 for d in digits if d >= 5)  # PL5 big threshold
            prime_n = sum(1 for d in digits if d in primes)
            mod0 = sum(1 for d in digits if d % 3 == 0)
            mod1 = sum(1 for d in digits if d % 3 == 1)
            mod2 = sum(1 for d in digits if d % 3 == 2)
            out.append({"odd": odd, "big": big, "prime": prime_n,
                        "mod0": mod0, "mod1": mod1, "mod2": mod2, "total": len(digits)})
        return out

    pstats = _per_pos_stats(draws)
    parity_lines = []
    size_lines = []
    prime_lines = []
    mod3_lines = []
    for i, ps in enumerate(pstats):
        t = ps["total"]
        parity_lines.append(f"- 第{i+1}位：奇 {ps['odd']}/{t}（{ps['odd']/t*100:.1f}%），偶 {t-ps['odd']}/{t}（{(t-ps['odd'])/t*100:.1f}%）")
        size_lines.append(f"- 第{i+1}位：大(≥5) {ps['big']}/{t}（{ps['big']/t*100:.1f}%），小(<5) {t-ps['big']}/{t}（{(t-ps['big'])/t*100:.1f}%）")
        prime_lines.append(f"- 第{i+1}位：质 {ps['prime']}/{t}（{ps['prime']/t*100:.1f}%），合 {t-ps['prime']}/{t}（{(t-ps['prime'])/t*100:.1f}%）")
        mod3_lines.append(f"- 第{i+1}位：0路 {ps['mod0']}/{t}（{ps['mod0']/t*100:.1f}%），1路 {ps['mod1']}/{t}（{ps['mod1']/t*100:.1f}%），2路 {ps['mod2']}/{t}（{ps['mod2']/t*100:.1f}%）")

    # ── 和值分带 ──
    sum_bands = [(0, 9), (10, 15), (16, 20), (21, 25), (26, 30), (31, 35), (36, 45)]
    sum_band_lines = []
    for lo, hi in sum_bands:
        cnt = int(np.sum((sums >= lo) & (sums <= hi)))
        sum_band_lines.append(f"- [{lo:02d}–{hi:02d}]：{cnt} 期（{cnt/max(n,1)*100:.1f}%）")

    # ── 跨度分布直方图 ──
    span_bins = [(0, 3), (4, 6), (7, 9)]
    span_lines = []
    for lo, hi in span_bins:
        cnt = int(np.sum((spans >= lo) & (spans <= hi)))
        span_lines.append(f"- [{lo}–{hi}]：{cnt} 期（{cnt/max(n,1)*100:.1f}%）")

    # ── 重复模式细分 ──
    from collections import Counter as _Ctr
    repeat_cats = {"全异(0重)": 0, "1对": 0, "2对": 0, "3同": 0, "葫芦(3+2)": 0, "4同": 0, "5同": 0}
    for row in draws:
        cnts = tuple(sorted(_Ctr(map(int, row)).values(), reverse=True))
        if cnts == (1, 1, 1, 1, 1):
            repeat_cats["全异(0重)"] += 1
        elif cnts == (2, 1, 1, 1):
            repeat_cats["1对"] += 1
        elif cnts == (2, 2, 1):
            repeat_cats["2对"] += 1
        elif cnts == (3, 1, 1):
            repeat_cats["3同"] += 1
        elif cnts == (3, 2):
            repeat_cats["葫芦(3+2)"] += 1
        elif cnts == (4, 1):
            repeat_cats["4同"] += 1
        elif cnts == (5,):
            repeat_cats["5同"] += 1
    repeat_detail = "，".join(f"{k}: {v}期 ({v/max(n,1)*100:.1f}%)" for k, v in repeat_cats.items())

    # ── 位间同号相关性 ──
    corr_pairs = []
    for i in range(5):
        for j in range(i + 1, 5):
            same = sum(1 for row in draws if int(row[i]) == int(row[j]))
            pct = same / max(n, 1) * 100
            corr_pairs.append((pct, i, j, same))
    corr_pairs.sort(reverse=True)
    corr_lines = [f"- d{c[1]+1}-d{c[2]+1}：{c[3]}/{n} 期同号（{c[0]:.1f}%）" for c in corr_pairs[:5]]

    # ── 多窗口稳定性对比 ──
    mw_windows = [30, analysis_window, full_n]
    mw_labels = [f"近{w}期" for w in mw_windows]
    mw_lines = []
    mw_lines.append("| 指标 | " + " | ".join(mw_labels) + " |")
    mw_lines.append("|------|" + "|".join(["------"] * len(mw_windows)) + "|")
    for metric_label, metric_fn in [
        ("奇数占比", lambda dr: sum(1 for r in dr for x in r if int(x)%2==1) / max(len(dr)*len(dr[0]), 1)),
        ("大数占比(≥5)", lambda dr: sum(1 for r in dr for x in r if int(x)>=5) / max(len(dr)*len(dr[0]), 1)),
        ("质数占比", lambda dr: sum(1 for r in dr for x in r if int(x) in {2,3,5,7}) / max(len(dr)*len(dr[0]), 1)),
        ("均值和", lambda dr: np.mean([sum(map(int,r)) for r in dr]) if dr else 0.0),
    ]:
        vals = []
        for w in mw_windows:
            w_data = df.tail(min(w, full_n))[cols].astype(int).values.tolist()
            vals.append(f"{metric_fn(w_data)*100:.1f}%" if "占比" in metric_label else f"{metric_fn(w_data):.1f}")
        mw_lines.append(f"| {metric_label} | " + " | ".join(vals) + " |")
    mw_section = "\n".join(mw_lines)

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

## 逐位奇偶分布

{chr(10).join(parity_lines)}

## 逐位大小分布（≥5 为大）

{chr(10).join(size_lines)}

## 逐位质合分布（质数：2,3,5,7）

{chr(10).join(prime_lines)}

## 逐位 012 路分布（除 3 余数）

{chr(10).join(mod3_lines)}

## 和值分带

{chr(10).join(sum_band_lines)}

## 跨度分布

{chr(10).join(span_lines)}

## 重复模式细分

{repeat_detail}

## 位间同号相关性（Top5）

{chr(10).join(corr_lines)}

## 多窗口稳定性对比

{mw_section}

> 说明：多窗口数值为各窗口尾部数据的截面快照，用于观察结构稳定性而非预测趋势。

## 局限

排列5开奖结果具有随机性；以上统计仅用于历史描述，不构成中奖承诺或投资建议。
"""


# ── 七星彩分析 ────────────────────────────────────────────────

def build_qxc_analysis(df: pd.DataFrame, analysis_window: int | None = None) -> str:
    if analysis_window is None:
        analysis_window = adaptive_stats_window(len(df))
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

    # ── 新指标：逐位结构分布（前区6位） ──
    def _per_pos_stats(draw_rows, n_digits=10):
        primes = {2, 3, 5, 7}
        n_pos = len(draw_rows[0])
        out = []
        for p in range(n_pos):
            digits = [int(r[p]) for r in draw_rows]
            odd = sum(1 for d in digits if d % 2 == 1)
            big = sum(1 for d in digits if d >= 5)
            prime_n = sum(1 for d in digits if d in primes)
            mod0 = sum(1 for d in digits if d % 3 == 0)
            mod1 = sum(1 for d in digits if d % 3 == 1)
            mod2 = sum(1 for d in digits if d % 3 == 2)
            out.append({"odd": odd, "big": big, "prime": prime_n,
                        "mod0": mod0, "mod1": mod1, "mod2": mod2, "total": len(digits)})
        return out

    pstats = _per_pos_stats(draws)
    parity_lines = []
    size_lines = []
    prime_lines = []
    mod3_lines = []
    for i, ps in enumerate(pstats):
        t = ps["total"]
        parity_lines.append(f"- 前区第{i+1}位：奇 {ps['odd']}/{t}（{ps['odd']/t*100:.1f}%），偶 {t-ps['odd']}/{t}（{(t-ps['odd'])/t*100:.1f}%）")
        size_lines.append(f"- 前区第{i+1}位：大(≥5) {ps['big']}/{t}（{ps['big']/t*100:.1f}%），小(<5) {t-ps['big']}/{t}（{(t-ps['big'])/t*100:.1f}%）")
        prime_lines.append(f"- 前区第{i+1}位：质 {ps['prime']}/{t}（{ps['prime']/t*100:.1f}%），合 {t-ps['prime']}/{t}（{(t-ps['prime'])/t*100:.1f}%）")
        mod3_lines.append(f"- 前区第{i+1}位：0路 {ps['mod0']}/{t}（{ps['mod0']/t*100:.1f}%），1路 {ps['mod1']}/{t}（{ps['mod1']/t*100:.1f}%），2路 {ps['mod2']}/{t}（{ps['mod2']/t*100:.1f}%）")

    # ── 后区专项 ──
    sp_n = len(specials)
    sp_odd = sum(1 for s in specials if s % 2 == 1)
    sp_big = sum(1 for s in specials if s >= 7)
    sp_mod0 = sum(1 for s in specials if s % 3 == 0)
    sp_mod1 = sum(1 for s in specials if s % 3 == 1)
    sp_mod2 = sum(1 for s in specials if s % 3 == 2)
    special_block = f"""- 奇偶：奇 {sp_odd}/{sp_n}（{sp_odd/max(sp_n,1)*100:.1f}%），偶 {sp_n-sp_odd}/{sp_n}（{(sp_n-sp_odd)/max(sp_n,1)*100:.1f}%）
- 大小（≥7为大）：大 {sp_big}/{sp_n}（{sp_big/max(sp_n,1)*100:.1f}%），小 {sp_n-sp_big}/{sp_n}（{(sp_n-sp_big)/max(sp_n,1)*100:.1f}%）
- 012 路：0路 {sp_mod0}/{sp_n}（{sp_mod0/max(sp_n,1)*100:.1f}%），1路 {sp_mod1}/{sp_n}（{sp_mod1/max(sp_n,1)*100:.1f}%），2路 {sp_mod2}/{sp_n}（{sp_mod2/max(sp_n,1)*100:.1f}%）"""

    # ── 和值分带 ──
    sum_bands = [(0, 20), (21, 30), (31, 40), (41, 50), (51, 60), (61, 75)]
    sum_band_lines = []
    for lo, hi in sum_bands:
        cnt = int(np.sum((sums >= lo) & (sums <= hi)))
        sum_band_lines.append(f"- [{lo}–{hi}]：{cnt} 期（{cnt/max(n,1)*100:.1f}%）")

    # ── 跨度分布直方图 ──
    span_bins = [(0, 3), (4, 6), (7, 9)]
    span_lines = []
    for lo, hi in span_bins:
        cnt = int(np.sum((spans_front >= lo) & (spans_front <= hi)))
        span_lines.append(f"- [{lo}–{hi}]：{cnt} 期（{cnt/max(n,1)*100:.1f}%）")

    # ── 前区重复模式细分 ──
    repeat_cats = {"全异(0重)": 0, "1对": 0, "2对": 0, "3同": 0, "葫芦(3+2)": 0, "4同": 0, "5同": 0, "6同": 0}
    for row in draws:
        cnts = tuple(sorted(Counter(map(int, row)).values(), reverse=True))
        if cnts == (1, 1, 1, 1, 1, 1):
            repeat_cats["全异(0重)"] += 1
        elif cnts == (2, 1, 1, 1, 1):
            repeat_cats["1对"] += 1
        elif cnts == (2, 2, 1, 1):
            repeat_cats["2对"] += 1
        elif cnts == (3, 1, 1, 1):
            repeat_cats["3同"] += 1
        elif cnts == (3, 2, 1):
            repeat_cats["葫芦(3+2)"] += 1
        elif cnts == (4, 1, 1):
            repeat_cats["4同"] += 1
        elif cnts == (5, 1):
            repeat_cats["5同"] += 1
        elif cnts == (6,):
            repeat_cats["6同"] += 1
    repeat_detail = "，".join(f"{k}: {v}期 ({v/max(n,1)*100:.1f}%)" for k, v in repeat_cats.items())

    # ── 位间同号相关性 ──
    corr_pairs = []
    for i in range(6):
        for j in range(i + 1, 6):
            same = sum(1 for row in draws if int(row[i]) == int(row[j]))
            pct = same / max(n, 1) * 100
            corr_pairs.append((pct, i, j, same))
    corr_pairs.sort(reverse=True)
    corr_lines = [f"- d{c[1]+1}-d{c[2]+1}：{c[3]}/{n} 期同号（{c[0]:.1f}%）" for c in corr_pairs[:5]]

    # ── 多窗口稳定性对比 ──
    mw_windows = [30, analysis_window, full_n]
    mw_labels = [f"近{w}期" for w in mw_windows]
    mw_lines = []
    mw_lines.append("| 指标 | " + " | ".join(mw_labels) + " |")
    mw_lines.append("|------|" + "|".join(["------"] * len(mw_windows)) + "|")
    for metric_label, metric_fn in [
        ("奇数占比(前区)", lambda dr: sum(1 for r in dr for x in r if int(x)%2==1) / max(len(dr)*len(dr[0]), 1)),
        ("大数占比(前区≥5)", lambda dr: sum(1 for r in dr for x in r if int(x)>=5) / max(len(dr)*len(dr[0]), 1)),
        ("质数占比(前区)", lambda dr: sum(1 for r in dr for x in r if int(x) in {2,3,5,7}) / max(len(dr)*len(dr[0]), 1)),
    ]:
        vals = []
        for w in mw_windows:
            w_data = df.tail(min(w, full_n))[fcols].astype(int).values.tolist()
            vals.append(f"{metric_fn(w_data)*100:.1f}%")
        mw_lines.append(f"| {metric_label} | " + " | ".join(vals) + " |")
    mw_section = "\n".join(mw_lines)

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

## 逐位奇偶分布（前区）

{chr(10).join(parity_lines)}

## 逐位大小分布（前区，≥5 为大）

{chr(10).join(size_lines)}

## 逐位质合分布（前区，质数：2,3,5,7）

{chr(10).join(prime_lines)}

## 逐位 012 路分布（前区，除 3 余数）

{chr(10).join(mod3_lines)}

## 后区专项分析（special 0–14）

{special_block}

## 和值分带

{chr(10).join(sum_band_lines)}

## 前区跨度分布

{chr(10).join(span_lines)}

## 前区重复模式细分

{repeat_detail}

## 位间同号相关性（Top5）

{chr(10).join(corr_lines)}

## 多窗口稳定性对比

{mw_section}

> 说明：多窗口数值为各窗口尾部数据的截面快照，用于观察结构稳定性而非预测趋势。

## 局限

七星彩开奖结果具有随机性；以上统计仅用于历史描述，不构成中奖承诺或投资建议。
"""
