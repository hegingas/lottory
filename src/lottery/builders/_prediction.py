"""预测 Markdown 构建器：大乐透、双色球、快乐八、排列5、七星彩的 prediction 归档生成。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .. import config as _lottery_config
from ..config import (
    DEFAULT_4F_WEIGHTS,
    DEFAULT_PL5_6F_WEIGHTS,
    DEFAULT_QXC_6F_WEIGHTS,
    DLT_BACK_MAX_ACTIVE_ZONES,
    DLT_BACK_MAX_PER_ZONE,
    DLT_BACK_ZONES_CAP,
    DLT_FRONT_MAX_ACTIVE_ZONES,
    DLT_FRONT_MAX_PER_ZONE,
    DLT_FRONT_ZONES_CAP,
    KL8_ELEVEN_OVERLAP_MAX,
    KL8_MAX_ACTIVE_ZONES,
    KL8_MAX_PER_PICK_ZONE,
    KL8_MIN_PER_PICK_ZONE,
    KL8_PICK_ZONES_CAP,
    MARKOV_LAPLACE_ALPHA,
    PATTERN_RECENT_K,
    PATTERN_W_MARKOV,
    PREDICTION_SINGLE_LINES,
    SSQ_BLUE_MAX_ACTIVE_ZONES,
    SSQ_BLUE_MAX_PER_ZONE,
    SSQ_BLUE_ZONES_CAP,
    SSQ_RED_MAX_ACTIVE_ZONES,
    SSQ_RED_MAX_PER_ZONE,
    SSQ_RED_ZONES_CAP,
    adaptive_stats_window,
)
from ..interval_markov import (
    expand_kl8_decadic_mask,
    expand_mask_until_pickable,
    format_mask_zones,
    markov_next_bitmap_blended,
    mask_to_active_zone_ranges,
    mask_to_allowed_balls,
    valid_mask_set,
)
from ..markdown_utils import (
    _build_dlt_five_numbers_md,
    _build_ssq_five_numbers_md,
    _dlt_appendix_five_singles_line,
    _fmt2,
    _pattern_weight_md_line,
    _prediction_md_appendix_budget_rules,
    _prediction_md_appendix_kl8_bet,
    _ssq_appendix_five_singles_line,
    now_cn_iso,
)
from ..scoring import (
    _dlt_back_scores,
    _dlt_front_scores,
    _kl8_twenty_scores,
    _markov_blended_probabilities,
    _minmax01_ball,
    _ssq_blue_scores,
    _ssq_red_scores,
    freq_miss_from_draws,
    topk,
)
from ..selection import (
    _assert_kl8_zone_bounds,
    _dlt_collect_five_unique_tickets,
    _dlt_ticket_passes_history_rules,
    _kl8_decadic_zone_totals,
    _kl8_eleven_cap_overlap_latest,
    _kl8_eleven_from_patterns,
    _kl8_eleven_from_twenty_rerank,
    _kl8_twenty_cap_overlap_latest,
    _kl8_twenty_from_patterns,
    _pick_top_indices_zone_capped,
    _qxc_collect_five_tickets,
    _ssq_collect_five_unique_tickets,
    _ssq_ticket_passes_history_rules,
    _zone_index_for_ball,
)
from ._utils import (
    _kl8_draw_rows,
    _norm_df,
    _pl5_6f_position_scores,
    _pl5_markov_blended,
    _pl5_norm01,
    _pl5_parity_alignment,
    _pl5_size_alignment,
    _qxc_6f_position_scores,
)

# ── 大乐透预测 ────────────────────────────────────────────────


def prediction_block_dlt(df: pd.DataFrame, n_last: int | None = None, weights: dict[str, float] | None = None, whiten: bool = False, use_mask: bool = True) -> tuple[str, dict[str, Any]]:
    # DLT: 白化倒退 -2.7%，保持原始因子空间
    if n_last is None:
        n_last = adaptive_stats_window(len(df))
    if weights is None:
        weights = _lottery_config.get_optimized_weights("dlt")
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
    for frow in fronts:
        frow = list(map(int, frow))
        odds = sum(1 for x in frow if x % 2)
        odd_pairs[f"{odds}:{5-odds}"] = odd_pairs.get(f"{odds}:{5-odds}", 0) + 1
        big = sum(1 for x in frow if x >= 18)
        size_pairs[f"{big}:{5-big}"] = size_pairs.get(f"{big}:{5-big}", 0) + 1
        sums.append(sum(frow))
        spans.append(max(frow) - min(frow))
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
    fs = _dlt_front_scores(f_draws, fq, fcur, f_mk, weights=weights, whiten=whiten)
    bs = _dlt_back_scores(b_draws, bq, bcur, b_mk, weights=weights, whiten=whiten)
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
    s_last_f, m_front, p_front, p_front_1st, row_f, row_f_2nd, short_fb_f = markov_next_bitmap_blended(f_all_rows, DLT_FRONT_ZONES_CAP, valid_set=valid_mask_set(7, DLT_FRONT_MAX_ACTIVE_ZONES))
    m_front_e = expand_mask_until_pickable(
        m_front, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE, 5
    )
    allowed_front_dlt = mask_to_allowed_balls(m_front_e, DLT_FRONT_ZONES_CAP)
    s_last_b, m_back, p_back, p_back_1st, row_b, row_b_2nd, short_fb_b = markov_next_bitmap_blended(b_all_rows, DLT_BACK_ZONES_CAP, valid_set=valid_mask_set(4, DLT_BACK_MAX_ACTIVE_ZONES))
    m_back_e = expand_mask_until_pickable(
        m_back, DLT_BACK_ZONES_CAP, DLT_BACK_MAX_PER_ZONE, 2
    )
    allowed_back_dlt = mask_to_allowed_balls(m_back_e, DLT_BACK_ZONES_CAP)

    # ── 区间选择原因说明 ──
    full_n_dlt = len(f_all_rows)
    last_pid_dlt = int(full["period_id"].iloc[-1])
    dlt_2nd_avail_f = row_f_2nd > 0
    dlt_2nd_avail_b = row_b_2nd > 0
    dlt_markov_bullet = (
        f"对**全表 {full_n_dlt} 期**：将每期前区 5 码映射到 **7** 个五码段（01–05 / 06–10 / 11–15 / 16–20 / 21–25 / 26–30 / 31–35），"
        f"后区 2 码映射到 **4** 个三段（01–03 / 04–06 / 07–09 / 10–12），各段至少 1 球则对应位为 1，按段序拼成二进制掩码；"
        f"统计相邻期掩码的**一阶+二阶混合转移**（一阶 40% + 二阶 60%，与按号马尔可夫方法论对齐），对条件行施加拉普拉斯 **α={MARKOV_LAPLACE_ALPHA}**。"
        f"以最后一期 **`{last_pid_dlt}`** 为条件：\n"
        f"- **前区**：末态掩码 **{format_mask_zones(s_last_f, DLT_FRONT_ZONES_CAP)}**（`{s_last_f}`），"
        f"混合后概率最大的下一掩码 **{format_mask_zones(m_front, DLT_FRONT_ZONES_CAP)}**（`{m_front}`，混合概率 **{p_front:.4f}**；一阶行 **{row_f}** 条" + (
            f"，二阶行 **{row_f_2nd}** 条" if dlt_2nd_avail_f else "，二阶不可用回退纯一阶") + "）；"
        f"按「每区至多 {DLT_FRONT_MAX_PER_ZONE} 个、共 5 球」展开为 **{format_mask_zones(m_front_e, DLT_FRONT_ZONES_CAP)}**（`{m_front_e}`）\n"
        f"- **后区**：末态掩码 **{format_mask_zones(s_last_b, DLT_BACK_ZONES_CAP)}**（`{s_last_b}`），"
        f"混合后概率最大的下一掩码 **{format_mask_zones(m_back, DLT_BACK_ZONES_CAP)}**（`{m_back}`，混合概率 **{p_back:.4f}**；一阶行 **{row_b}** 条" + (
            f"，二阶行 **{row_b_2nd}** 条" if dlt_2nd_avail_b else "，二阶不可用回退纯一阶") + "）；"
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
        allowed_front=allowed_front_dlt if use_mask else None,
        allowed_back=allowed_back_dlt if use_mask else None,
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
        "use_mask": use_mask,
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
在展开后的掩码并集号码内用综合分取号。**{PREDICTION_SINGLE_LINES} 注**之间对**已出现过的号码**在下一轮综合分上施加**递减惩罚**，以拉开互异组合；仍不足则换随机种子补全互异注。**权重**：**{_pattern_weight_md_line(weights)}**；因子含 **近 {PATTERN_RECENT_K} 期密度、奇偶结构、大小（前≥18 / 后≥7）、和值带、区段划分**（区间热度与取号分区一致），并含 **马尔可夫链转移因子**（最大权重）：基于**全历史**同时计算**一阶**与**二阶**二状态转移矩阵，按 **40% 一阶 + 60% 二阶** 混合后取最新状态对应的下一期出现条件概率（与上文「区间掩码马尔可夫」为不同层次：前者约束候选球集合，后者进入按号评分）。

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

def prediction_block_ssq(df: pd.DataFrame, n_last: int | None = None, weights: dict[str, float] | None = None, whiten: bool | None = None, use_mask: bool = True) -> tuple[str, dict[str, Any]]:
    # SSQ: 白化 +4.0%，默认开启
    if n_last is None:
        n_last = adaptive_stats_window(len(df))
    if whiten is None:
        whiten = True
    if weights is None:
        weights = _lottery_config.get_optimized_weights("ssq")
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
    for rrow in reds:
        rrow = list(map(int, rrow))
        odds = sum(1 for x in rrow if x % 2)
        odd_pairs[f"{odds}:{6-odds}"] = odd_pairs.get(f"{odds}:{6-odds}", 0) + 1
        big = sum(1 for x in rrow if x >= 17)
        size_pairs[f"{big}:{6-big}"] = size_pairs.get(f"{big}:{6-big}", 0) + 1
        sums.append(sum(rrow))
        spans.append(max(rrow) - min(rrow))
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
    rs = _ssq_red_scores(r_draws, rq, rcur, r_mk, weights=weights, whiten=whiten)
    bs_sc = _ssq_blue_scores(blues_list, bq, bcur, b_mk, weights=weights, whiten=whiten)
    hist_keys_ssq: set[tuple[tuple[int, ...], int]] = set()
    for _, row in full.iterrows():
        r_t = tuple(sorted(int(row[f"red_{i}"]) for i in range(1, 7)))
        b_t = int(row["blue"])
        hist_keys_ssq.add((r_t, b_t))
    lr_s = full.iloc[-1]
    latest_ssq_seven = set(int(lr_s[f"red_{i}"]) for i in range(1, 7)) | {int(lr_s["blue"])}
    r_all_rows = [list(map(int, r)) for r in reds_all]
    b_all_rows = [[int(x)] for x in blues_all]
    s_last_r, m_red, p_red, p_red_1st, row_r, row_r_2nd, short_fb_r = markov_next_bitmap_blended(r_all_rows, SSQ_RED_ZONES_CAP, valid_set=valid_mask_set(7, SSQ_RED_MAX_ACTIVE_ZONES))
    m_red_e = expand_mask_until_pickable(
        m_red, SSQ_RED_ZONES_CAP, SSQ_RED_MAX_PER_ZONE, 6
    )
    allowed_red_ssq = mask_to_allowed_balls(m_red_e, SSQ_RED_ZONES_CAP)
    s_last_b, m_blue, p_blue, p_blue_1st, row_b, row_b_2nd, short_fb_b = markov_next_bitmap_blended(b_all_rows, SSQ_BLUE_ZONES_CAP, valid_set=valid_mask_set(4, SSQ_BLUE_MAX_ACTIVE_ZONES))
    m_blue_e = expand_mask_until_pickable(
        m_blue, SSQ_BLUE_ZONES_CAP, SSQ_BLUE_MAX_PER_ZONE, 1
    )
    allowed_blue_ssq = mask_to_allowed_balls(m_blue_e, SSQ_BLUE_ZONES_CAP)

    # ── 区间选择原因说明 ──
    full_n_ssq = len(r_all_rows)
    last_pid_ssq = int(full["period_id"].iloc[-1])
    ssq_2nd_avail_r = row_r_2nd > 0
    ssq_2nd_avail_b = row_b_2nd > 0
    ssq_markov_bullet = (
        f"对**全表 {full_n_ssq} 期**：将每期红球 6 码映射到 **7** 个五码段（01–05 / 06–10 / 11–15 / 16–20 / 21–25 / 26–30 / 31–33），"
        f"蓝球 1 码映射到 **4** 个四码段（01–04 / 05–08 / 09–12 / 13–16），各段至少 1 球则对应位为 1，按段序拼成二进制掩码；"
        f"统计相邻期掩码的**一阶+二阶混合转移**（一阶 40% + 二阶 60%，与按号马尔可夫方法论对齐），对条件行施加拉普拉斯 **α={MARKOV_LAPLACE_ALPHA}**。"
        f"以最后一期 **`{last_pid_ssq}`** 为条件：\n"
        f"- **红球**：末态掩码 **{format_mask_zones(s_last_r, SSQ_RED_ZONES_CAP)}**（`{s_last_r}`），"
        f"混合后概率最大的下一掩码 **{format_mask_zones(m_red, SSQ_RED_ZONES_CAP)}**（`{m_red}`，混合概率 **{p_red:.4f}**；一阶行 **{row_r}** 条" + (
            f"，二阶行 **{row_r_2nd}** 条" if ssq_2nd_avail_r else "，二阶不可用回退纯一阶") + "）；"
        f"按「每区至多 {SSQ_RED_MAX_PER_ZONE} 个、共 6 球」展开为 **{format_mask_zones(m_red_e, SSQ_RED_ZONES_CAP)}**（`{m_red_e}`）\n"
        f"- **蓝球**：末态掩码 **{format_mask_zones(s_last_b, SSQ_BLUE_ZONES_CAP)}**（`{s_last_b}`），"
        f"混合后概率最大的下一掩码 **{format_mask_zones(m_blue, SSQ_BLUE_ZONES_CAP)}**（`{m_blue}`，混合概率 **{p_blue:.4f}**；一阶行 **{row_b}** 条" + (
            f"，二阶行 **{row_b_2nd}** 条" if ssq_2nd_avail_b else "，二阶不可用回退纯一阶") + "）；"
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
        allowed_red=allowed_red_ssq if use_mask else None,
        allowed_blue=allowed_blue_ssq if use_mask else None,
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
        "use_mask": use_mask,
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
在展开后的掩码并集号码内用综合分取号。**{PREDICTION_SINGLE_LINES} 注**间对**已出现过的号码**在下一轮综合分上施加**递减惩罚**以拉开互异组合；仍不足则换随机种子补全。**权重**：**{_pattern_weight_md_line(weights)}**；红球另有 **近 {PATTERN_RECENT_K} 期密度、奇偶/大小（≥17）、和值带、五码段划分**；蓝球另有 **近 {PATTERN_RECENT_K} 期密度、奇偶、中位蓝贴近、大号占比（≥9）**，并含 **马尔可夫链转移因子**（最大权重）：每次预测都基于**全历史**重算一阶与二阶转移矩阵，按 **40% 一阶 + 60% 二阶** 混合后取最新状态对应下一期条件概率入权重（与「区间掩码马尔可夫」层次区分同大乐透口径）。

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
) -> dict[str, Any]:
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


def _kl8_collect_one_path_outputs_b(
    fq: np.ndarray,
    fcur: np.ndarray,
    draws: list[list[int]],
    markov_raw: np.ndarray,
    active_zones: list[tuple[int, int]],
    kl8_scores: np.ndarray,
    latest20_set: set[int],
    markov_norm: np.ndarray,
) -> dict[str, Any]:
    """Path B: 先预测 20 码 → 在 20 码池内用完整多因子分数重排位取 11 码。"""
    twenty, _ = _kl8_twenty_from_patterns(fq, fcur, draws, markov_raw, active_zones)
    twenty = _kl8_twenty_cap_overlap_latest(twenty, latest20_set, kl8_scores, active_zones, max_overlap=6)
    twenty_hit = len(set(twenty) & latest20_set)
    twenty_fmt = ",".join(_fmt2(x) for x in sorted(twenty))

    eleven = _kl8_eleven_from_twenty_rerank(twenty, kl8_scores, active_zones)
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
        "twenty": sorted(twenty),
        "twenty_fmt": twenty_fmt,
        "twenty_hit": twenty_hit,
    }


# ── 快乐八预测 ────────────────────────────────────────────────

def prediction_block_kl8(df: pd.DataFrame, n_last: int | None = None, weights: dict[str, float] | None = None, whiten: bool = False, path: str = "B", use_mask: bool = True) -> tuple[str, dict[str, Any]]:
    if n_last is None:
        n_last = adaptive_stats_window(len(df))
    if weights is None:
        weights = _lottery_config.get_optimized_weights("kl8")
    df = _norm_df(df)
    draws_all, pids_all = _kl8_draw_rows(df)
    full_n = len(draws_all)
    if full_n == 0:
        return "# 快乐八 — 统计型预测参考归档\n\n（无数据行）\n", {}
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
    kl8_scores = _kl8_twenty_scores(fq, fcur, draws, markov_raw, weights=weights, whiten=whiten)
    latest20_set = set(int(x) for x in draws_all[-1])

    pred_ts = now_cn_iso()

    s_last_k, s_pred_k, p_pred_k, p_pred_1st_k, row_total_k, row_total_2nd_k, short_fb_k = markov_next_bitmap_blended(
        draws_all, KL8_PICK_ZONES_CAP, valid_set=valid_mask_set(8, KL8_MAX_ACTIVE_ZONES)
    )
    m_exp_k = expand_kl8_decadic_mask(
        s_pred_k, KL8_PICK_ZONES_CAP, 11, KL8_MAX_PER_PICK_ZONE
    )
    active_zones = mask_to_active_zone_ranges(m_exp_k, KL8_PICK_ZONES_CAP)
    if not use_mask:
        active_zones = list(KL8_PICK_ZONES_CAP)
    if path == "B":
        w = _kl8_collect_one_path_outputs_b(
            fq, fcur, draws, markov_raw, active_zones, kl8_scores, latest20_set, markov_norm
        )
    else:
        w = _kl8_collect_one_path_outputs(
            fq, fcur, draws, markov_raw, active_zones, kl8_scores, latest20_set, markov_norm
        )

    totals8w = _kl8_decadic_zone_totals(draws)
    active_zone_choice_md = "；".join(
        f"`{_fmt2(lo)}–{_fmt2(hi)}`（该十码段在窗口内累计 **{totals8w[_zone_index_for_ball(lo, KL8_PICK_ZONES_CAP)]}** 次）"
        for lo, hi in active_zones
    )

    kl8_2nd_avail = row_total_2nd_k > 0
    markov_path_bullet = (
        f"对**全表 {full_n} 期**：将每期开奖 **20** 码映射到 **8** 个十码段，若某段至少出现 **1** 球则对应位为 **1**，按段序拼成 **8** 位二进制掩码；"
        f"统计相邻期掩码的**一阶+二阶混合转移**（一阶 40% + 二阶 60%，与按号马尔可夫方法论对齐），对条件行施加拉普拉斯 **α={MARKOV_LAPLACE_ALPHA}**。"
        f"以最后一期 **`{last_pid}`** 的掩码 **{format_mask_zones(s_last_k, KL8_PICK_ZONES_CAP)}**（`{s_last_k}`）为条件，"
        f"取混合后概率最大的下一掩码 **{format_mask_zones(s_pred_k, KL8_PICK_ZONES_CAP)}**（`{s_pred_k}`，混合概率 **{p_pred_k:.4f}**；一阶行 **{row_total_k}** 条" + (
            f"，二阶行 **{row_total_2nd_k}** 条" if kl8_2nd_avail else "，二阶不可用回退纯一阶") + "）。"
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
    twenty_fmt = str(w.get("twenty_fmt", ""))
    twenty_hit = w.get("twenty_hit", None)
    path_label = {"A": "直接 11 码（跳过 20 码中间层）", "B": "20→11 重排位（先预测 20 码再在池内用完整多因子分数取 11 码）"}.get(path, path)
    path_method_desc = {"A": "直接", "B": "先预测 20 码再重排位"}.get(path, "直接")
    twenty_desc = ""
    if path == "B" and twenty_fmt:
        twenty_desc = f" Path B 先预测 20 码：**{twenty_fmt}**（与最新一期真实 20 码重合 **{twenty_hit}** 个）。"
        twenty_block = f"\n\n> **Path B 20 码中间层**：{twenty_fmt}（与最新一期真实 20 码重合 **{twenty_hit}** 个；在 20 码池内用完整多因子分数重排位取 11 码）。"
    else:
        twenty_block = ""

    hot_line = "；".join([f"`{a}`（**{b}** 次）" for a, b in hot5])
    low_line = "；".join([f"`{a}`（**{b}** 次）" for a, b in low5])
    miss_line = "；".join([f"`{a}`（**{b}** 期）" for a, b in top_miss])
    wline = _pattern_weight_md_line(weights)

    pred_data: dict[str, Any] = {
        "lottery_type": "kl8",
        "prediction_date": pred_ts,
        "window_start": int(pid_min),
        "window_end": int(pid_max),
        "use_mask": use_mask,
        "tickets": [{"index": 1, "numbers": {"codes": eleven_codes}}],
        "best": {"numbers": {"codes": eleven_codes}, "score": float(pref11)},
        "kl8_path": path,
    }
    if path == "B" and twenty_hit is not None:
        pred_data["twenty_hit"] = twenty_hit
        pred_data["twenty_codes"] = w.get("twenty", [])

    return f"""# 快乐八 — 统计型预测参考归档

> **最后更新**：{pred_ts}
> **选号路径**：**{path_label}**
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
- **活跃十码段（区间二进制掩码 → 一阶马尔可夫 → 展开）**：{markov_path_bullet}在展开后的活跃十码段并集内{path_method_desc}取满 **11** 码：各段 **{KL8_MIN_PER_PICK_ZONE}–{KL8_MAX_PER_PICK_ZONE}** 个，非活跃段 **0** 个。本窗口各活跃段频次摘要：{active_zone_choice_md}。{twenty_desc}

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

> 在近 **{n}** 期窗口综合分下，**仅在**上文马尔可夫展开后的活跃十码段并集内{path_method_desc}取 **11** 个互异号码（**同分随机**），并执行重合上限修正。{twenty_block}

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

> **提示**：本文件由 `python src/scripts/cli.py regenerate-history --only kl8`（**同时**重写 `history/kuaileba_analysis.md`）或 `regenerate-history --only all`（存在 `kl8_draws.csv` 时）生成；文末附录含 **10～30 元** 带内机械复式示例。若追加更复杂方案，可再请 **`lottery-combo-optimize`** 并写投注原因。
""", pred_data


# ── 排列5 预测 ────────────────────────────────────────────────

def prediction_block_pl5(df: pd.DataFrame, n_last: int | None = None, weights: dict[str, float] | None = None) -> tuple[str, dict[str, Any]]:
    if n_last is None:
        n_last = adaptive_stats_window(len(df))
    if weights is None:
        weights = _lottery_config.get_optimized_weights("pl5")
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    full = df.sort_values("period_id").reset_index(drop=True)
    if len(full) == 0:
        return "# 排列5 — 统计型预测参考归档\n\n（无数据行）\n", {}
    tail = full.tail(min(n_last, len(full))).reset_index(drop=True)
    pmin, pmax = int(tail["period_id"].min()), int(tail["period_id"].max())
    cols = [f"d{i}" for i in range(1, 6)]
    draws_all = full[cols].astype(int).values.tolist()
    draws = tail[cols].astype(int).values.tolist()
    n_win = len(draws)
    pred_ts = now_cn_iso()

    scores_by_pos: list[np.ndarray] = []
    mk_by_pos: list[np.ndarray] = []
    _is_6f = weights is not None and ("parity" in weights or "size" in weights)
    if _is_6f:
        for pos in range(5):
            sc, raw = _pl5_6f_position_scores(draws, draws_all, pos, n_win, PATTERN_RECENT_K, weights)
            scores_by_pos.append(sc)
            mk_by_pos.append(raw["markov"])
    else:
        w4 = weights if weights is not None else DEFAULT_4F_WEIGHTS
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
                w4["miss"]    * _pl5_norm01(miss)
                + w4["freq"]  * _pl5_norm01(freq)
                + w4["recency"] * _pl5_norm01(rec)
                + w4["markov"] * _pl5_norm01(mk)
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

    w_desc_lines = []
    if _is_6f:
        wd = weights if weights is not None else DEFAULT_PL5_6F_WEIGHTS
        w_desc_lines.append(f"- 因子（**6 因子**）：分位频次、当前遗漏、近 **{PATTERN_RECENT_K}** 期密度、马尔可夫转移概率（一阶+二阶混合，基于全历史重算）、**奇偶对齐**、**大小对齐**")
        w_desc_lines.append(f"- 评分：`{wd['markov']:.3f}×马尔可夫 + {wd['miss']:.3f}×遗漏 + {wd['freq']:.3f}×频次 + {wd['recency']:.3f}×近端密度 + {wd['parity']:.3f}×奇偶对齐 + {wd['size']:.3f}×大小对齐`，5注间轻度去重惩罚。")
    else:
        wd = weights if weights is not None else DEFAULT_4F_WEIGHTS
        w_desc_lines.append(f"- 因子（**4 因子**）：分位频次、当前遗漏、近 **{PATTERN_RECENT_K}** 期密度、马尔可夫转移概率（一阶+二阶混合，基于全历史重算）")
        w_desc_lines.append(f"- 评分：`{wd['markov']:.3f}×马尔可夫 + {wd['miss']:.3f}×遗漏 + {wd['freq']:.3f}×频次 + {wd['recency']:.3f}×近端密度`，5注间轻度去重惩罚。")
    w_desc_section = "\n".join(w_desc_lines)
    key_factors = "遗漏、频次、近端密度、马尔可夫" + ("、奇偶对齐、大小对齐" if _is_6f else "")

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
{w_desc_section}

## 结果摘要

{chr(10).join(hot_lines)}

- **去核心化**：已执行去核心化约束——各注在分位综合分与注间去重惩罚下生成，未直接采用「每位单纯 Top1 热号」拼成 5 注不变体。

## 明确号码输出（强制，统计参考）

{chr(10).join(numbers_md)}

## 单式优选（强制）

> **生成时间**：`{pred_ts}`（北京时间）。

- **号码（5 位）**：**{pl5_pref_num}**（分位：`{pl5_pref_csv}`）
- **总分（五位综合分之和）**：**{pl5_pref_tot:.3f}**
- **关键因子**：{key_factors}（见口径说明）。

## 使用说明

以上仅为历史统计参考，下一期开奖仍为独立随机事件，不构成中奖承诺或投资建议。

---

## 附录：预算与投注推荐（仓库默认）

- **金额带（强制）**：统计规律输出完成后，至少提供一套 **10～30 元（含）** 的打票参考。
{mech_line}
- **说明**：本附录仅作金额示例；若用户指定其他预算或倍投口径，以用户要求为准。
""", pred_data


# ── 七星彩 预测 ────────────────────────────────────────────────

def prediction_block_qxc(df: pd.DataFrame, n_last: int | None = None, weights: dict[str, float] | None = None) -> tuple[str, dict[str, Any]]:
    if n_last is None:
        n_last = adaptive_stats_window(len(df))
    if weights is None:
        weights = _lottery_config.get_optimized_weights("qxc")
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    full = df.sort_values("period_id").reset_index(drop=True)
    if len(full) == 0:
        return "# 七星彩 — 统计型预测参考归档\n\n（无数据行）\n", {}
    tail = full.tail(min(n_last, len(full))).reset_index(drop=True)
    pmin, pmax = int(tail["period_id"].min()), int(tail["period_id"].max())
    fcols = [f"d{i}" for i in range(1, 7)]
    draws = tail[fcols].astype(int).values.tolist()
    draws_all = full[fcols].astype(int).values.tolist()
    specials_win = tail["special"].astype(int).tolist()
    specials_all = full["special"].astype(int).tolist()
    n_win = len(draws)
    pred_ts = now_cn_iso()

    scores_by_pos: list[np.ndarray] = []
    mk_by_pos: list[np.ndarray] = []
    _is_6f = weights is not None and ("parity" in weights or "size" in weights)
    if _is_6f:
        for pos in range(6):
            sc, raw = _qxc_6f_position_scores(draws, draws_all, pos, 10, n_win, PATTERN_RECENT_K, weights, big_threshold=5)
            scores_by_pos.append(sc)
            mk_by_pos.append(raw["markov"])
        sp_draws = [[s] for s in specials_win]
        sp_draws_all = [[s] for s in specials_all]
        sc_special, sp_raw = _qxc_6f_position_scores(sp_draws, sp_draws_all, 0, 15, n_win, PATTERN_RECENT_K, weights, big_threshold=7)
        scores_by_pos.append(sc_special)
        mk_special = sp_raw["markov"]
        mk_by_pos.append(mk_special)
    else:
        from ..scoring import _qxc_position_scores

        w4f = weights if weights is not None else DEFAULT_4F_WEIGHTS
        for pos in range(6):
            sc, mk = _qxc_position_scores(draws, pos, 10, w4f.get("miss", 0.20), w4f.get("freq", 0.20), w4f.get("recency", 0.20), w4f.get("markov", 0.40), PATTERN_RECENT_K, weights=weights)
            scores_by_pos.append(sc)
            mk_by_pos.append(mk)
        sc_special, mk_special = _qxc_position_scores(
            [[s] for s in specials_win], 0, 15, w4f.get("miss", 0.20), w4f.get("freq", 0.20), w4f.get("recency", 0.20), w4f.get("markov", 0.40), PATTERN_RECENT_K, weights=weights
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

    w_desc_lines_qxc = []
    if _is_6f:
        wd_q = weights if weights is not None else DEFAULT_QXC_6F_WEIGHTS
        w_desc_lines_qxc.append(f"- 因子（**6 因子**）：分位频次、当前遗漏、近 **{PATTERN_RECENT_K}** 期密度、马尔可夫转移概率（一阶+二阶混合）、**奇偶对齐**、**大小对齐**")
        w_desc_lines_qxc.append(f"- 评分：`{wd_q['markov']:.3f}×马尔可夫 + {wd_q['miss']:.3f}×遗漏 + {wd_q['freq']:.3f}×频次 + {wd_q['recency']:.3f}×近端密度 + {wd_q['parity']:.3f}×奇偶对齐 + {wd_q['size']:.3f}×大小对齐`，5注间轻度去重惩罚。")
    else:
        wd_q = weights if weights is not None else DEFAULT_4F_WEIGHTS
        w_desc_lines_qxc.append(f"- 因子（**4 因子**）：分位频次、当前遗漏、近 **{PATTERN_RECENT_K}** 期密度、马尔可夫转移概率（一阶+二阶混合，基于全历史重算）")
        w_desc_lines_qxc.append(f"- 评分：`{wd_q['markov']:.3f}×马尔可夫 + {wd_q['miss']:.3f}×遗漏 + {wd_q['freq']:.3f}×频次 + {wd_q['recency']:.3f}×近端密度`，5注间轻度去重惩罚。")
    w_desc_section_qxc = "\n".join(w_desc_lines_qxc)
    qxc_key_factors = "遗漏、频次、近端密度、马尔可夫" + ("、奇偶对齐、大小对齐" if _is_6f else "")

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
{w_desc_section_qxc}
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
- **关键因子**：{qxc_key_factors}（见口径说明）。

## 使用说明

以上仅为历史统计参考，下一期开奖仍为独立随机事件，不构成中奖承诺或投资建议。

---

## 附录：预算与投注推荐（仓库默认）

- **金额带（强制）**：统计规律输出完成后，至少提供一套 **10～30 元（含）** 的打票参考。
{mech_line}
- **说明**：本附录仅作金额示例；若用户指定其他预算或倍投口径，以用户要求为准。
""", pred_data
