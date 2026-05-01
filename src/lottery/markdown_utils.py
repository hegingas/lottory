"""Markdown 格式化工具：原因行、注单构建、附录、日间戳等。"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import numpy as np

from . import config as _lottery_config
from .config import (
    PATTERN_RECENT_K,
    PATTERN_W_MISS,
    PATTERN_W_FREQ,
    PATTERN_W_ZONE,
    PATTERN_W_RECENCY,
    PATTERN_W_PARITY,
    PATTERN_W_SIZE,
    PATTERN_W_SUM,
    PATTERN_W_MARKOV,
    DLT_FRONT_ZONES_CAP,
    DLT_FRONT_MAX_PER_ZONE,
    DLT_BACK_ZONES_CAP,
    DLT_BACK_MAX_PER_ZONE,
    SSQ_RED_ZONES_CAP,
    SSQ_RED_MAX_PER_ZONE,
    SSQ_BLUE_ZONES_CAP,
    SSQ_BLUE_MAX_PER_ZONE,
    DEFAULT_COMBO_BUDGET_MIN_YUAN,
    DEFAULT_COMBO_BUDGET_MAX_YUAN,
    PREDICTION_SINGLE_LINES,
    _fmt2,
)
from .selection import (
    _pick_top_indices_zone_capped,
    _dlt_ticket_passes_history_rules,
    _ssq_ticket_passes_history_rules,
)


def now_cn_iso() -> str:
    return (datetime.now(timezone(timedelta(hours=8)))).replace(microsecond=0).isoformat()


def _pattern_weight_md_line() -> str:
    return (
        f"{PATTERN_W_MISS:.0%}×当前遗漏 + {PATTERN_W_FREQ:.0%}×频次 + {PATTERN_W_ZONE:.0%}×区间热度 + "
        f"{PATTERN_W_RECENCY:.0%}×近{PATTERN_RECENT_K}期密度 + {PATTERN_W_PARITY:.0%}×奇偶对齐 + "
        f"{PATTERN_W_SIZE:.0%}×大小/半区对齐 + {PATTERN_W_SUM:.0%}×和值带对齐 + "
        f"{PATTERN_W_MARKOV:.0%}×马尔可夫转移"
    )


# ── 单号原因行 ─────────────────────────────────────────────────

def _reason_dlt_front_line(
    ball: int,
    n_win: int,
    fq: np.ndarray,
    fcur: np.ndarray,
    fs: np.ndarray,
    mk_raw: np.ndarray,
    mk_norm: np.ndarray,
) -> str:
    from .selection import _zone_label_for_ball

    ct = int(fq[ball])
    ms = int(fcur[ball])
    sc = float(fs[ball])
    z = _zone_label_for_ball(ball, DLT_FRONT_ZONES_CAP, "前区")
    mkp = float(mk_raw[ball])
    mkn = float(mk_norm[ball])
    mkc = PATTERN_W_MARKOV * mkn
    return (
        f"**`{_fmt2(ball)}`**（{z}）：近 **{n_win}** 期出现 **{ct}** 次，当前遗漏 **{ms}** 期；"
        f"加权综合分 **{sc:.3f}**（权重见**口径说明**）；"
        f"马尔可夫 `P(下一期出现|最新状态)`≈**{mkp:.4f}**，归一值 **{mkn:.3f}**，"
        f"权重贡献约 **{mkc:.3f}**；"
        f"本注按「每 **5** 个连续号为一小区，每小区至多 **{DLT_FRONT_MAX_PER_ZONE}** 个」由前区综合分序列贪心入选。"
    )


def _reason_dlt_back_line(
    ball: int,
    n_win: int,
    bq: np.ndarray,
    bcur: np.ndarray,
    bs: np.ndarray,
    mk_raw: np.ndarray,
    mk_norm: np.ndarray,
) -> str:
    from .selection import _zone_label_for_ball

    ct = int(bq[ball])
    ms = int(bcur[ball])
    sc = float(bs[ball])
    z = _zone_label_for_ball(ball, DLT_BACK_ZONES_CAP, "后区")
    mkp = float(mk_raw[ball])
    mkn = float(mk_norm[ball])
    mkc = PATTERN_W_MARKOV * mkn
    return (
        f"**`{_fmt2(ball)}`**（{z}）：近 **{n_win}** 期出现 **{ct}** 次，当前遗漏 **{ms}** 期；"
        f"加权综合分 **{sc:.3f}**（权重见**口径说明**）；"
        f"马尔可夫 `P(下一期出现|最新状态)`≈**{mkp:.4f}**，归一值 **{mkn:.3f}**，"
        f"权重贡献约 **{mkc:.3f}**；"
        f"本注按「每 **4** 个号一小区、每小区至多 **{DLT_BACK_MAX_PER_ZONE}** 个」由后区综合分贪心入选。"
    )


def _reason_ssq_red_line(
    ball: int,
    n_win: int,
    rq: np.ndarray,
    rcur: np.ndarray,
    rs: np.ndarray,
    mk_raw: np.ndarray,
    mk_norm: np.ndarray,
) -> str:
    from .selection import _zone_label_for_ball

    ct = int(rq[ball])
    ms = int(rcur[ball])
    sc = float(rs[ball])
    z = _zone_label_for_ball(ball, SSQ_RED_ZONES_CAP, "红球")
    mkp = float(mk_raw[ball])
    mkn = float(mk_norm[ball])
    mkc = PATTERN_W_MARKOV * mkn
    return (
        f"**`{_fmt2(ball)}`**（{z}）：近 **{n_win}** 期出现 **{ct}** 次，当前遗漏 **{ms}** 期；"
        f"加权综合分 **{sc:.3f}**（权重见**口径说明**）；"
        f"马尔可夫 `P(下一期出现|最新状态)`≈**{mkp:.4f}**，归一值 **{mkn:.3f}**，"
        f"权重贡献约 **{mkc:.3f}**；"
        f"本注按「每 **5** 个连续号为一小区，每小区至多 **{SSQ_RED_MAX_PER_ZONE}** 个」由红球综合分序列贪心入选。"
    )


def _reason_ssq_blue_line(
    ball: int,
    n_win: int,
    bq: np.ndarray,
    bcur: np.ndarray,
    bs: np.ndarray,
    mk_raw: np.ndarray,
    mk_norm: np.ndarray,
) -> str:
    from .selection import _zone_label_for_ball

    ct = int(bq[ball])
    ms = int(bcur[ball])
    sc = float(bs[ball])
    z = _zone_label_for_ball(ball, SSQ_BLUE_ZONES_CAP, "蓝球")
    mkp = float(mk_raw[ball])
    mkn = float(mk_norm[ball])
    mkc = PATTERN_W_MARKOV * mkn
    return (
        f"**`{_fmt2(ball)}`**（{z}）：近 **{n_win}** 期出现 **{ct}** 次，当前遗漏 **{ms}** 期；"
        f"加权综合分 **{sc:.3f}**（权重见**口径说明**）；"
        f"马尔可夫 `P(下一期出现|最新状态)`≈**{mkp:.4f}**，归一值 **{mkn:.3f}**，"
        f"权重贡献约 **{mkc:.3f}**；本注为蓝球单码优选（四码段每段至多 **{SSQ_BLUE_MAX_PER_ZONE}** 个，取 1 个蓝球时自然满足）。"
    )


# ── 多注单式 Markdown 构建 ─────────────────────────────────────

def _build_dlt_five_numbers_md(
    five: list[tuple[list[int], list[int]]],
    fs: np.ndarray,
    bs: np.ndarray,
    fq: np.ndarray,
    fcur: np.ndarray,
    bq: np.ndarray,
    bcur: np.ndarray,
    fmk_raw: np.ndarray,
    fmk_norm: np.ndarray,
    bmk_raw: np.ndarray,
    bmk_norm: np.ndarray,
    n_win: int,
    pred_ts: str,
    hist_keys: set[tuple[tuple[int, ...], tuple[int, ...]]] | None = None,
    latest_seven: set[int] | None = None,
) -> str:
    parts: list[str] = [
        f"> **预测生成时间**：`{pred_ts}`（北京时间，ISO-8601）。\n",
        f"> **随机种子**：`{_lottery_config._ACTIVE_RANDOM_SEED}`（同数据同种子可复现）。\n",
        f"> 共 **{PREDICTION_SINGLE_LINES}** 注单式，每注 **2** 元；下列「选择原因」均为窗口内统计指标说明，**非**开奖承诺。\n\n",
    ]
    for i, (f, b) in enumerate(five, 1):
        ff = ",".join(_fmt2(x) for x in f)
        bb = ",".join(_fmt2(x) for x in b)
        parts.append(f"### 第 {i} 注（单式）\n\n")
        parts.append(f"- **号码**：前区 **{ff}**；后区 **{bb}**\n\n")
        parts.append("- **各号选择原因**：\n\n")
        for x in f:
            parts.append(
                f"  - {_reason_dlt_front_line(int(x), n_win, fq, fcur, fs, fmk_raw, fmk_norm)}\n\n"
            )
        for x in b:
            parts.append(
                f"  - {_reason_dlt_back_line(int(x), n_win, bq, bcur, bs, bmk_raw, bmk_norm)}\n\n"
            )
    try:
        fi_p = sorted(
            _pick_top_indices_zone_capped(
                fs, 1, 35, 5, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE
            )
        )
        bi_p = sorted(
            _pick_top_indices_zone_capped(
                bs, 1, 12, 2, DLT_BACK_ZONES_CAP, DLT_BACK_MAX_PER_ZONE
            )
        )
        if not _dlt_ticket_passes_history_rules(fi_p, bi_p, hist_keys, latest_seven):
            fi_p, bi_p = five[0]
        tot = sum(float(fs[i]) for i in fi_p) + sum(float(bs[i]) for i in bi_p)
        ff_p = ",".join(_fmt2(x) for x in fi_p)
        bb_p = ",".join(_fmt2(x) for x in bi_p)
        parts.append(
            "\n## 单式优选（强制）\n\n"
            f"> **生成时间**：`{pred_ts}`（北京时间）。\n\n"
            f"- **号码**：前区 **{ff_p}**；后区 **{bb_p}**\n"
            f"- **总分（前区+后区综合分之和，同正文口径）**：**{tot:.3f}**\n"
            "- **关键因子**：遗漏、频次、区间热度、近端密度、奇偶/大小/和值带、马尔可夫转移（见口径说明权重）。\n"
        )
    except Exception:
        fi_p, bi_p = five[0]
        tot = sum(float(fs[i]) for i in fi_p) + sum(float(bs[i]) for i in bi_p)
        ff_p = ",".join(_fmt2(x) for x in fi_p)
        bb_p = ",".join(_fmt2(x) for x in bi_p)
        parts.append(
            "\n## 单式优选（强制）\n\n"
            f"> **生成时间**：`{pred_ts}`（北京时间）。\n\n"
            f"- **号码**：前区 **{ff_p}**；后区 **{bb_p}**\n"
            f"- **总分（前区+后区综合分之和，同正文口径）**：**{tot:.3f}**\n"
            "- **说明**：分区贪心回退为正文第 1 注（已满足防重合时与优选一致或近似）。\n"
        )
    return "".join(parts).rstrip() + "\n"


def _build_ssq_five_numbers_md(
    five: list[tuple[list[int], int]],
    rs: np.ndarray,
    bs: np.ndarray,
    rq: np.ndarray,
    rcur: np.ndarray,
    bq: np.ndarray,
    bcur: np.ndarray,
    rmk_raw: np.ndarray,
    rmk_norm: np.ndarray,
    bmk_raw: np.ndarray,
    bmk_norm: np.ndarray,
    n_win: int,
    pred_ts: str,
    hist_keys: set[tuple[tuple[int, ...], int]] | None = None,
    latest_seven: set[int] | None = None,
) -> str:
    parts: list[str] = [
        f"> **预测生成时间**：`{pred_ts}`（北京时间，ISO-8601）。\n",
        f"> **随机种子**：`{_lottery_config._ACTIVE_RANDOM_SEED}`（同数据同种子可复现）。\n",
        f"> 共 **{PREDICTION_SINGLE_LINES}** 注单式，每注 **2** 元；下列「选择原因」均为窗口内统计指标说明，**非**开奖承诺。\n\n",
    ]
    for i, (r, bl) in enumerate(five, 1):
        rs_s = ",".join(_fmt2(x) for x in r)
        parts.append(f"### 第 {i} 注（单式）\n\n")
        parts.append(f"- **号码**：红球 **{rs_s}**；蓝球 **`{_fmt2(bl)}`**\n\n")
        parts.append("- **各号选择原因**：\n\n")
        for x in r:
            parts.append(
                f"  - {_reason_ssq_red_line(int(x), n_win, rq, rcur, rs, rmk_raw, rmk_norm)}\n\n"
            )
        parts.append(
            f"  - {_reason_ssq_blue_line(bl, n_win, bq, bcur, bs, bmk_raw, bmk_norm)}\n\n"
        )
    try:
        ri_p = sorted(
            _pick_top_indices_zone_capped(
                rs, 1, 33, 6, SSQ_RED_ZONES_CAP, SSQ_RED_MAX_PER_ZONE
            )
        )
        bi_p = _pick_top_indices_zone_capped(
            bs, 1, 16, 1, SSQ_BLUE_ZONES_CAP, SSQ_BLUE_MAX_PER_ZONE
        )
        bl_p = int(bi_p[0])
        if not _ssq_ticket_passes_history_rules(ri_p, bl_p, hist_keys, latest_seven):
            ri_p, bl_p = five[0]
        tot = sum(float(rs[i]) for i in ri_p) + float(bs[bl_p])
        rs_s = ",".join(_fmt2(x) for x in ri_p)
        parts.append(
            "\n## 单式优选（强制）\n\n"
            f"> **生成时间**：`{pred_ts}`（北京时间）。\n\n"
            f"- **号码**：红球 **{rs_s}**；蓝球 **`{_fmt2(bl_p)}`**\n"
            f"- **总分（红球+蓝球综合分之和，同正文口径）**：**{tot:.3f}**\n"
            "- **关键因子**：遗漏、频次、区间热度、近端密度、奇偶/大小/和值带、马尔可夫转移（见口径说明权重）。\n"
        )
    except Exception:
        ri_p, bl_p = five[0]
        tot = sum(float(rs[i]) for i in ri_p) + float(bs[bl_p])
        rs_s = ",".join(_fmt2(x) for x in ri_p)
        parts.append(
            "\n## 单式优选（强制）\n\n"
            f"> **生成时间**：`{pred_ts}`（北京时间）。\n\n"
            f"- **号码**：红球 **{rs_s}**；蓝球 **`{_fmt2(bl_p)}`**\n"
            f"- **总分（红球+蓝球综合分之和，同正文口径）**：**{tot:.3f}**\n"
            "- **说明**：分区贪心回退为正文第 1 注（已满足防重合时与优选一致或近似）。\n"
        )
    return "".join(parts).rstrip() + "\n"


# ── 附录 ──────────────────────────────────────────────────────

def _dlt_appendix_five_singles_line() -> str:
    lo, hi = DEFAULT_COMBO_BUDGET_MIN_YUAN, DEFAULT_COMBO_BUDGET_MAX_YUAN
    n = PREDICTION_SINGLE_LINES
    return (
        f"- **机械方案（{n} 注单式）**：正文 **{n}** 组前 5+后 2 单式，每组 **2** 元，合计 **{n}×2={n * 2} 元**（落在 **{lo}～{hi} 元**；无复式、无倍投）。"
        f"如需复式/胆拖/多方案仍由 **`lottery-combo-optimize`** 在金额带内优化。"
    )


def _ssq_appendix_five_singles_line() -> str:
    n = PREDICTION_SINGLE_LINES
    lo, hi = DEFAULT_COMBO_BUDGET_MIN_YUAN, DEFAULT_COMBO_BUDGET_MAX_YUAN
    return (
        f"- **机械方案（{n} 注单式）**：正文 **{n}** 组红 6+蓝 1 单式，每组 **2** 元，合计 **{n}×2={n * 2} 元**（落在 **{lo}～{hi} 元**；无复式、无倍投）。"
        f"如需复式/胆拖/多方案仍由 **`lottery-combo-optimize`** 在金额带内优化。"
    )


def _prediction_md_appendix_budget_rules(lottery_cn: str, mechanical_example_line: str) -> str:
    lo, hi = DEFAULT_COMBO_BUDGET_MIN_YUAN, DEFAULT_COMBO_BUDGET_MAX_YUAN
    return f"""

---

## 附录：预算与投注推荐（仓库默认）

- **金额带（强制）**：统计规律输出完成后，须配套至少一套 **合计 {lo}～{hi} 元（含端点）** 的投注推荐；不得仅以 **单注 2 元**且无其它带内方案作为唯一收尾（正文 **{PREDICTION_SINGLE_LINES} 注单式** 已 **{PREDICTION_SINGLE_LINES * 2} 元**，满足带内示例）。
- **倍投**：本仓库脚本附录**不提供倍投示例**；若需复式、胆拖或多票混合，请用 **`lottery-combo-optimize`** 在 **{lo}～{hi} 元** 内优化。
{mechanical_example_line}
- **上限与专精**：默认单期合计 **不超过 {hi} 元**（另有声明除外）；复式 / 胆拖 / 多票混合优先由 **`lottery-combo-optimize`** 在 **{lo}～{hi} 元** 内优化，并强制包含：**玩法类型、号码、注数公式、小计与合计校验、投注原因**（见该技能「输出清单」）。
- **玩法范围**：**{lottery_cn}** 支持单式、复式、胆拖及混合（以官方规则计注数）；快乐八见快乐八预测文末附录。
- **单价**：大乐透 / 双色球按 **2 元/注** 估算（以当期官方为准）。
- **刷新说明**：`regenerate-history --only dlt-ssq` 会重写正文与本节；正文 **{PREDICTION_SINGLE_LINES} 注单式** 与金额说明随数据与随机次序变化；更复杂方案可追加专节或由专精 Agent 补写。
"""


def _prediction_md_appendix_kl8_bet(eleven_fmt: str) -> str:
    lo, hi = DEFAULT_COMBO_BUDGET_MIN_YUAN, DEFAULT_COMBO_BUDGET_MAX_YUAN
    return f"""

---

## 附录：预算与投注推荐（仓库默认）

- **金额带（强制）**：统计规律输出完成后，须配套至少一套 **合计 {lo}～{hi} 元（含端点）** 的投注推荐。
- **本文件机械推荐（选十 11 码复式）**：号码（升序）**{eleven_fmt}**；注数 **C(11,10)=11**；金额 **11×2=22 元**（落在 **{lo}～{hi} 元** 内；单价以福彩官方为准）。
- 若需换号、多方案或与其他约束混合，请用 **`lottery-combo-optimize`** 仍控制在 **{lo}～{hi} 元**，并写清投注原因。
"""
