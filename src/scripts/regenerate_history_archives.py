#!/usr/bin/env python3
"""
基于 data/processed/*.csv 重算并写入 history 下归档（N 默认见 `DEFAULT_STATS_WINDOW`，当前为 30）：
- **大乐透 / 双色球**：各 `*_analysis.md`、`*_prediction.md`（必写）；预测正文为 **5 注单式**，每注逐号**选择原因**，并写**预测生成时间**；文末附 **10～30 元** 金额带与 **5×2=10 元** 单式说明（`DEFAULT_COMBO_BUDGET_MIN_YUAN` / `DEFAULT_COMBO_BUDGET_MAX_YUAN`）；快乐八预测含 **11 码复式**机械示例。
- **快乐八**：在存在 `kl8_draws.csv` 时与大乐透/双色球**同一套规则**（期末尾连续 N 期）同步写 `kuaileba_analysis.md` 与 `kuaileba_prediction.md`。预测正文：**参考开奖 20 码** = 同上加权综合分后，按 **8 个十码段（01–10,…,71–80）每段至多 5 个**（`KL8_MAX_PER_PICK_ZONE`）贪心取满 20（**同分随机**）；**选十 11 码** = 在该 20 码中**无放回随机**抽取 11，且满足**同一十码段每段至多 5 个**。大乐透/双色球正文为 **5 注单式**（同一加权 + 同分随机；前区/红球 **每 5 码一小区至多 2 个**，后区/蓝球 **每 4 码一小区至多 2 个**），各注带**已选惩罚**以拉开互异组合；见 `PREDICTION_SINGLE_LINES` 与各 `*_ZONES_CAP` / `*_MAX_PER_ZONE`。

运行（在仓库根，**统一入口**）：
  python src/scripts/lottery.py regenerate-history [--only all|kl8|dlt-ssq]
  # 或直接：python src/scripts/regenerate_history_archives.py [--only kl8]
  # ``regenerate-kl8-prediction`` 仍为兼容别名，等同 ``--only kl8``。
"""

from __future__ import annotations

import json
import math
import random
from typing import Callable
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
PROC = REPO / "data" / "processed"
HIST = REPO / "history"
MANIFEST = PROC / "manifest.json"

# 大乐透 / 双色球 / 快乐八：一键重算与书面归档的**默认统计窗口**（期末尾连续 N 期）。
# 用户或 Agent 若需其他 N，应手写归档或改此常量后重跑脚本。
DEFAULT_STATS_WINDOW = 30

# 多因子「规律线」：各因子先 **min-max 归一到 [0,1]**，再按独立权重加权合成综合分（大乐透前/后区、双色球红/蓝、快乐八 01–80 同构）。
PATTERN_RECENT_K = 5  # 近 K 期密度因子所用期数（不超过当前窗口长度）
KL8_PATTERN_RECENT_K = PATTERN_RECENT_K  # 兼容旧名
# 7 项因子独立权重（合计 1.0）
PATTERN_W_MISS    = 0.25  # 当前遗漏：遗漏越久分越高，提供覆盖多样性
PATTERN_W_FREQ    = 0.18  # 窗口频次：全窗口出现次数，基础冷热指标
PATTERN_W_ZONE    = 0.17  # 区间热度：区段落球密度
PATTERN_W_RECENCY = 0.15  # 近 K 期密度：近期走势比远期更有参考价值
PATTERN_W_PARITY  = 0.10  # 奇偶对齐：防止全奇/全偶
PATTERN_W_SIZE    = 0.10  # 大小/半区对齐：防止号码全部扎堆在半区
PATTERN_W_SUM     = 0.05  # 和值带对齐：和值是号码选择的结果而非原因，仅微调

# 快乐八取 20/11：**8 个十码段**，每段至多 **KL8_MAX_PER_PICK_ZONE**（8×5≥20，用户可改上限）。
KL8_MAX_PER_PICK_ZONE = 5
KL8_PICK_ZONES_CAP = [(1, 10), (11, 20), (21, 30), (31, 40), (41, 50), (51, 60), (61, 70), (71, 80)]
# 大乐透前区：**每 5 个号** 一区间（7 段）；每段至多 **DLT_FRONT_MAX_PER_ZONE** 个。
DLT_FRONT_ZONES_CAP = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 35)]
DLT_FRONT_MAX_PER_ZONE = 2
# 大乐透后区：**每 4 个号** 一区间（3 段）；每段至多 **DLT_BACK_MAX_PER_ZONE** 个。
DLT_BACK_ZONES_CAP = [(1, 4), (5, 8), (9, 12)]
DLT_BACK_MAX_PER_ZONE = 2
# 双色球红球：**每 5 个号** 一区间（末段 31–33 仅 3 个号）；每段至多 **SSQ_RED_MAX_PER_ZONE** 个。
SSQ_RED_ZONES_CAP = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 33)]
SSQ_RED_MAX_PER_ZONE = 2
# 双色球蓝球：**每 4 个号** 一区间（4 段）；每段至多 **SSQ_BLUE_MAX_PER_ZONE** 个（单码取 1 天然满足）。
SSQ_BLUE_ZONES_CAP = [(1, 4), (5, 8), (9, 12), (13, 16)]
SSQ_BLUE_MAX_PER_ZONE = 2

# 书面预测中与组号 Agent 对齐的默认预算带（见 `AGENTS.md`、`lottery-combo-optimize`）。
DEFAULT_COMBO_BUDGET_MIN_YUAN = 10
DEFAULT_COMBO_BUDGET_MAX_YUAN = 30
DEFAULT_COMBO_BUDGET_YUAN = DEFAULT_COMBO_BUDGET_MAX_YUAN  # 兼容旧名：历史上指「上限」

# 大乐透 / 双色球 `*_prediction.md` 正文「明确号码」：固定 **5 注单式**（每注 2 元，合计 10 元落在默认金额带内）。
PREDICTION_SINGLE_LINES = 5


def _zone_index_for_ball(ball: int, zones: list[tuple[int, int]]) -> int:
    for zi, (lo, hi) in enumerate(zones):
        if lo <= ball <= hi:
            return zi
    raise ValueError(f"球号 {ball} 不在 zones={zones} 内")


def _counts_per_zone_for_balls(balls: list[int], zones: list[tuple[int, int]]) -> list[int]:
    zc = [0] * len(zones)
    for x in balls:
        zc[_zone_index_for_ball(int(x), zones)] += 1
    return zc


def _zone_label_for_ball(ball: int, zones: list[tuple[int, int]], prefix: str) -> str:
    """人类可读小区标签，与 `*_ZONES_CAP` 一致。"""
    for i, (lo, hi) in enumerate(zones, 1):
        if lo <= ball <= hi:
            return f"{prefix}第{i}小区（{_fmt2(lo)}–{_fmt2(hi)}）"
    return f"{prefix}（分区未覆盖）"


def _dlt_appendix_five_singles_line() -> str:
    """正文 5 注单式：5×2=10 元，落在默认金额带内。"""
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
    """大乐透 / 双色球预测文末固定附录：10～30 元投注带 + 无倍投的复式机械示例。"""
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
    """快乐八：11 码复式金额天然落在 10～30 元带内。"""
    lo, hi = DEFAULT_COMBO_BUDGET_MIN_YUAN, DEFAULT_COMBO_BUDGET_MAX_YUAN
    return f"""

---

## 附录：预算与投注推荐（仓库默认）

- **金额带（强制）**：统计规律输出完成后，须配套至少一套 **合计 {lo}～{hi} 元（含端点）** 的投注推荐。
- **本文件机械推荐（选十 11 码复式）**：号码（升序）**{eleven_fmt}**；注数 **C(11,10)=11**；金额 **11×2=22 元**（落在 **{lo}～{hi} 元** 内；单价以福彩官方为准）。
- 若需换号、多方案或与其他约束混合，请用 **`lottery-combo-optimize`** 仍控制在 **{lo}～{hi} 元**，并写清投注原因。
"""


def now_cn_iso() -> str:
    return (datetime.now(timezone(timedelta(hours=8)))).replace(microsecond=0).isoformat()


def ac_value(nums: list[int]) -> int:
    nums = sorted(nums)
    n = len(nums)
    diffs: set[int] = set()
    for i in range(n):
        for j in range(i + 1, n):
            diffs.add(abs(nums[j] - nums[i]))
    return len(diffs) - (n - 1)


def freq_miss_from_draws(
    draws: list[list[int]], period_ids: list[Any], n_ball: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """draws 按期序；返回 freq, current_miss, avg_miss（avg_miss 描述性口径）。"""
    freq = np.zeros(n_ball + 1, dtype=int)
    last = np.full(n_ball + 1, -1, dtype=int)
    for idx, nums in enumerate(draws):
        for x in nums:
            freq[x] += 1
            last[x] = idx
    total = len(draws)
    cur = np.zeros(n_ball + 1, dtype=int)
    for x in range(1, n_ball + 1):
        if last[x] < 0:
            cur[x] = total
        else:
            cur[x] = total - 1 - last[x]
    avg = np.zeros(n_ball + 1, dtype=float)
    for x in range(1, n_ball + 1):
        if freq[x] == 0:
            avg[x] = float("nan")
        else:
            avg[x] = (total - freq[x]) / freq[x]
    return freq, cur, avg


def topk(freq: np.ndarray, k: int, *, high: bool) -> list[tuple[int, int]]:
    pairs = [(i, int(freq[i])) for i in range(1, len(freq))]
    pairs.sort(key=lambda t: t[1], reverse=high)
    return pairs[:k]


def _fmt2(n: int) -> str:
    return f"{int(n):02d}"


def _recency_counts(draws: list[list[int]], k: int, n_ball: int) -> np.ndarray:
    """窗口末尾最近 k 期内各号出现次数（索引 1..n_ball）。"""
    c = np.zeros(n_ball + 1, dtype=int)
    if not draws:
        return c
    k_use = min(max(1, k), len(draws))
    for d in draws[-k_use:]:
        for x in d:
            xi = int(x)
            if 1 <= xi <= n_ball:
                c[xi] += 1
    return c


def _minmax01_ball(raw: np.ndarray, n_ball: int) -> np.ndarray:
    """对 raw[1..n_ball] 做 min-max 到 [0,1]；常数列退化为 0.5。"""
    out = np.zeros(n_ball + 1, dtype=float)
    vals = np.array([float(raw[i]) for i in range(1, n_ball + 1)], dtype=float)
    lo, hi = float(vals.min()), float(vals.max())
    if hi <= lo:
        out[1:] = 0.5
        return out
    for i in range(1, n_ball + 1):
        out[i] = (float(raw[i]) - lo) / (hi - lo)
    return out


def _weighted_composite(
    miss_raw: np.ndarray,
    freq_raw: np.ndarray,
    zone_raw: np.ndarray,
    recency_raw: np.ndarray,
    parity_raw: np.ndarray,
    size_raw: np.ndarray,
    sum_raw: np.ndarray,
    n_ball: int,
) -> np.ndarray:
    """7 项因子独立权重加权合成综合分（每项先 min-max 归一到 [0,1]）。"""
    nm = _minmax01_ball(miss_raw, n_ball)
    nf = _minmax01_ball(freq_raw, n_ball)
    nz = _minmax01_ball(zone_raw, n_ball)
    nr = _minmax01_ball(recency_raw, n_ball)
    np_ = _minmax01_ball(parity_raw, n_ball)
    ns = _minmax01_ball(size_raw, n_ball)
    nsum = _minmax01_ball(sum_raw, n_ball)
    out = np.zeros(n_ball + 1, dtype=float)
    for i in range(1, n_ball + 1):
        out[i] = (
            PATTERN_W_MISS    * nm[i]
            + PATTERN_W_FREQ  * nf[i]
            + PATTERN_W_ZONE  * nz[i]
            + PATTERN_W_RECENCY * nr[i]
            + PATTERN_W_PARITY  * np_[i]
            + PATTERN_W_SIZE    * ns[i]
            + PATTERN_W_SUM     * nsum[i]
        )
    return out


def _pattern_weight_md_line() -> str:
    """口径说明里一行人类可读权重（不含外层 Markdown，便于包在加粗内）。"""
    return (
        f"{PATTERN_W_MISS:.0%}×当前遗漏 + {PATTERN_W_FREQ:.0%}×频次 + {PATTERN_W_ZONE:.0%}×区间热度 + "
        f"{PATTERN_W_RECENCY:.0%}×近{PATTERN_RECENT_K}期密度 + {PATTERN_W_PARITY:.0%}×奇偶对齐 + "
        f"{PATTERN_W_SIZE:.0%}×大小/半区对齐 + {PATTERN_W_SUM:.0%}×和值带对齐"
    )


def _pick_top_scored_pairs_random_tie(
    scores: np.ndarray, i_lo: int, i_hi: int, k: int
) -> list[tuple[int, float]]:
    """(号码, 分) 列表取 Top k；同分随机。"""
    pairs = [(i, float(scores[i])) for i in range(i_lo, i_hi + 1)]
    random.shuffle(pairs)
    pairs.sort(key=lambda t: -t[1])
    return pairs[:k]


def _pick_top_indices_zone_capped(
    scores: np.ndarray,
    i_lo: int,
    i_hi: int,
    k: int,
    zones: list[tuple[int, int]],
    max_per_zone: int = 2,
    rng: random.Random | None = None,
) -> list[int]:
    """按分降序贪心选取；同分由 shuffle 次序决定；每个 zones 分区至多 max_per_zone 个号。"""
    rnd = rng if rng is not None else random
    ix = list(range(i_lo, i_hi + 1))
    rnd.shuffle(ix)
    ix.sort(key=lambda i: -scores[i])
    zc = [0] * len(zones)
    out: list[int] = []
    for i in ix:
        if len(out) >= k:
            break
        zi = _zone_index_for_ball(i, zones)
        if zc[zi] >= max_per_zone:
            continue
        out.append(i)
        zc[zi] += 1
    if len(out) < k:
        raise ValueError(
            f"在「每区至多 {max_per_zone} 个」下无法从 [{i_lo},{i_hi}] 取满 {k} 个号（已取 {len(out)}，zones={zones}）"
        )
    return out


def _pick_top_scored_pairs_zone_capped(
    scores: np.ndarray,
    i_lo: int,
    i_hi: int,
    k: int,
    zones: list[tuple[int, int]],
    max_per_zone: int = 2,
    rng: random.Random | None = None,
) -> list[tuple[int, float]]:
    idx = _pick_top_indices_zone_capped(scores, i_lo, i_hi, k, zones, max_per_zone, rng)
    return sorted([(i, float(scores[i])) for i in idx], key=lambda t: t[0])


def _sum_alignment_scores(draws: list[list[int]], n_ball: int) -> np.ndarray:
    """各号在「所含期的开奖子集和值」相对窗口和值中位数的贴近度（未出现则 0.5）。"""
    out = np.full(n_ball + 1, 0.5, dtype=float)
    if not draws:
        return out
    sums = np.array([sum(d) for d in draws], dtype=float)
    med = float(np.median(sums))
    iqr = float(np.percentile(sums, 75) - np.percentile(sums, 25))
    scale = max(float(iqr), abs(med) * 0.08, 5.0)
    for i in range(1, n_ball + 1):
        when = [sums[idx] for idx, d in enumerate(draws) if i in d]
        if not when:
            continue
        mu = float(np.mean(when))
        out[i] = 1.0 - min(1.0, abs(mu - med) / scale)
    return out


def _zone_density_raw(draws: list[list[int]], n_ball: int, zones: list[tuple[int, int]]) -> np.ndarray:
    """按区段累计窗口内落球占比，号码落在该区则得该区密度（相对全区最大密度）。"""
    out = np.zeros(n_ball + 1, dtype=float)
    counts = np.zeros(len(zones), dtype=float)
    tot = 0.0
    for d in draws:
        for x in d:
            xi = int(x)
            tot += 1.0
            for zi, (lo, hi) in enumerate(zones):
                if lo <= xi <= hi:
                    counts[zi] += 1.0
                    break
    dens = counts / max(tot, 1.0)
    mx = float(dens.max()) if len(dens) else 1.0
    if mx <= 0:
        mx = 1.0
    for i in range(1, n_ball + 1):
        for zi, (lo, hi) in enumerate(zones):
            if lo <= i <= hi:
                out[i] = dens[zi] / mx
                break
    return out


def _parity_alignment_raw(n_ball: int, mean_odd_per_draw: float, slots: int) -> np.ndarray:
    """与近期「奇数个数的期望占比」线性对齐：奇号多时偏好奇号。"""
    p = mean_odd_per_draw / max(slots, 1)
    out = np.zeros(n_ball + 1, dtype=float)
    for i in range(1, n_ball + 1):
        is_odd = float(i % 2)
        out[i] = p * is_odd + (1.0 - p) * (1.0 - is_odd)
    return out


def _size_alignment_raw(
    n_ball: int, mean_big_per_draw: float, slots: int, big_pred: Callable[[int], bool]
) -> np.ndarray:
    """与近期「大号个数期望占比」线性对齐（大乐透前区 ≥18，双色球红 ≥17）。"""
    p = mean_big_per_draw / max(slots, 1)
    out = np.zeros(n_ball + 1, dtype=float)
    for i in range(1, n_ball + 1):
        b = 1.0 if big_pred(i) else 0.0
        out[i] = p * b + (1.0 - p) * (1.0 - b)
    return out


def _kl8_half_alignment_raw(draws: list[list[int]], n_ball: int) -> np.ndarray:
    """01–40 vs 41–80 在窗口内的占比对齐。"""
    lo_c = hi_c = 0.0
    for d in draws:
        for x in d:
            if int(x) <= 40:
                lo_c += 1.0
            else:
                hi_c += 1.0
    tot = lo_c + hi_c
    p_hi = hi_c / max(tot, 1.0)
    out = np.zeros(n_ball + 1, dtype=float)
    for i in range(1, n_ball + 1):
        big = 1.0 if i > 40 else 0.0
        out[i] = p_hi * big + (1.0 - p_hi) * (1.0 - big)
    return out


def _kl8_twenty_scores(freq: np.ndarray, cur_miss: np.ndarray, draws: list[list[int]]) -> np.ndarray:
    """快乐八 01–80 多因子加权综合分（越大越优先）。"""
    n_ball = 80
    f_miss = np.array([float(cur_miss[i]) for i in range(n_ball + 1)], dtype=float)
    f_freq = np.array([float(freq[i]) for i in range(n_ball + 1)], dtype=float)
    f_rec = np.array([float(_recency_counts(draws, PATTERN_RECENT_K, n_ball)[i]) for i in range(n_ball + 1)], dtype=float)
    odds_per = [sum(1 for x in d if int(x) % 2 == 1) for d in draws]
    mean_odd = float(np.mean(odds_per)) if odds_per else 10.0
    f_odd = _parity_alignment_raw(n_ball, mean_odd, 20)
    f_half = _kl8_half_alignment_raw(draws, n_ball)
    f_sum = _sum_alignment_scores(draws, n_ball)
    zones = [(1, 20), (21, 40), (41, 60), (61, 80)]
    f_zone = _zone_density_raw(draws, n_ball, zones)
    return _weighted_composite(f_miss, f_freq, f_zone, f_rec, f_odd, f_half, f_sum, n_ball)


def _dlt_front_scores(f_draws: list[list[int]], fq: np.ndarray, fcur: np.ndarray) -> np.ndarray:
    n_ball = 35
    f_miss = np.array([float(fcur[i]) for i in range(n_ball + 1)], dtype=float)
    f_freq = np.array([float(fq[i]) for i in range(n_ball + 1)], dtype=float)
    f_rec = np.array([float(_recency_counts(f_draws, PATTERN_RECENT_K, n_ball)[i]) for i in range(n_ball + 1)], dtype=float)
    slots = 5
    mean_odd = float(np.mean([sum(1 for x in row if int(x) % 2 == 1) for row in f_draws])) if f_draws else 2.5
    mean_big = float(np.mean([sum(1 for x in row if int(x) >= 18) for row in f_draws])) if f_draws else 2.5
    f_odd = _parity_alignment_raw(n_ball, mean_odd, slots)
    f_big = _size_alignment_raw(n_ball, mean_big, slots, lambda i: i >= 18)
    f_sum = _sum_alignment_scores(f_draws, n_ball)
    f_zone = _zone_density_raw(f_draws, n_ball, DLT_FRONT_ZONES_CAP)
    return _weighted_composite(f_miss, f_freq, f_zone, f_rec, f_odd, f_big, f_sum, n_ball)


def _dlt_back_scores(b_draws: list[list[int]], bq: np.ndarray, bcur: np.ndarray) -> np.ndarray:
    n_ball = 12
    f_miss = np.array([float(bcur[i]) for i in range(n_ball + 1)], dtype=float)
    f_freq = np.array([float(bq[i]) for i in range(n_ball + 1)], dtype=float)
    f_rec = np.array([float(_recency_counts(b_draws, PATTERN_RECENT_K, n_ball)[i]) for i in range(n_ball + 1)], dtype=float)
    slots = 2
    mean_odd = float(np.mean([sum(1 for x in row if int(x) % 2 == 1) for row in b_draws])) if b_draws else 1.0
    f_odd = _parity_alignment_raw(n_ball, mean_odd, slots)
    f_sum = _sum_alignment_scores(b_draws, n_ball)
    f_zone = _zone_density_raw(b_draws, n_ball, DLT_BACK_ZONES_CAP)
    mean_hi = float(np.mean([sum(1 for x in row if int(x) >= 7) for row in b_draws])) if b_draws else 1.0
    f_hi = _size_alignment_raw(n_ball, mean_hi, slots, lambda i: i >= 7)
    return _weighted_composite(f_miss, f_freq, f_zone, f_rec, f_odd, f_hi, f_sum, n_ball)


def _ssq_red_scores(r_draws: list[list[int]], rq: np.ndarray, rcur: np.ndarray) -> np.ndarray:
    n_ball = 33
    f_miss = np.array([float(rcur[i]) for i in range(n_ball + 1)], dtype=float)
    f_freq = np.array([float(rq[i]) for i in range(n_ball + 1)], dtype=float)
    f_rec = np.array([float(_recency_counts(r_draws, PATTERN_RECENT_K, n_ball)[i]) for i in range(n_ball + 1)], dtype=float)
    slots = 6
    mean_odd = float(np.mean([sum(1 for x in row if int(x) % 2 == 1) for row in r_draws])) if r_draws else 3.0
    mean_big = float(np.mean([sum(1 for x in row if int(x) >= 17) for row in r_draws])) if r_draws else 3.0
    f_odd = _parity_alignment_raw(n_ball, mean_odd, slots)
    f_big = _size_alignment_raw(n_ball, mean_big, slots, lambda i: i >= 17)
    f_sum = _sum_alignment_scores(r_draws, n_ball)
    f_zone = _zone_density_raw(r_draws, n_ball, SSQ_RED_ZONES_CAP)
    return _weighted_composite(f_miss, f_freq, f_zone, f_rec, f_odd, f_big, f_sum, n_ball)


def _ssq_blue_scores(blues: list[int], bq: np.ndarray, bcur: np.ndarray) -> np.ndarray:
    """blues 按期序的各期蓝球号码（单号）。"""
    n_ball = 16
    b_draws = [[int(x)] for x in blues]
    if not blues:
        return np.full(n_ball + 1, 0.5, dtype=float)
    f_miss = np.array([float(bcur[i]) for i in range(n_ball + 1)], dtype=float)
    f_freq = np.array([float(bq[i]) for i in range(n_ball + 1)], dtype=float)
    f_rec = np.array([float(_recency_counts(b_draws, PATTERN_RECENT_K, n_ball)[i]) for i in range(n_ball + 1)], dtype=float)
    odd_rate = float(np.mean([1 if int(x) % 2 == 1 else 0 for x in blues])) if blues else 0.5
    f_odd = _parity_alignment_raw(n_ball, odd_rate * 1.0, 1)
    f_zone = _zone_density_raw(b_draws, n_ball, SSQ_BLUE_ZONES_CAP)
    med = float(np.median(np.array(blues, dtype=float))) if blues else 8.5
    scale = max(4.0, float(np.percentile(np.array(blues, dtype=float), 75) - np.percentile(np.array(blues, dtype=float), 25)) if len(blues) > 1 else 4.0)
    f_med = np.zeros(n_ball + 1, dtype=float)
    for i in range(1, n_ball + 1):
        f_med[i] = 1.0 - min(1.0, abs(float(i) - med) / max(scale, 1e-6))
    mean_hi = float(np.mean([1 if int(x) >= 9 else 0 for x in blues])) if blues else 0.5
    f_hi = _size_alignment_raw(n_ball, mean_hi, 1, lambda i: i >= 9)
    return _weighted_composite(f_miss, f_freq, f_zone, f_rec, f_odd, f_hi, f_med, n_ball)


def _reason_dlt_front_line(ball: int, n_win: int, fq: np.ndarray, fcur: np.ndarray, fs: np.ndarray) -> str:
    ct = int(fq[ball])
    ms = int(fcur[ball])
    sc = float(fs[ball])
    z = _zone_label_for_ball(ball, DLT_FRONT_ZONES_CAP, "前区")
    return (
        f"**`{_fmt2(ball)}`**（{z}）：近 **{n_win}** 期出现 **{ct}** 次，当前遗漏 **{ms}** 期；"
        f"加权综合分 **{sc:.3f}**（权重见**口径说明**）；"
        f"本注按「每 **5** 个连续号为一小区，每小区至多 **{DLT_FRONT_MAX_PER_ZONE}** 个」由前区综合分序列贪心入选。"
    )


def _reason_dlt_back_line(ball: int, n_win: int, bq: np.ndarray, bcur: np.ndarray, bs: np.ndarray) -> str:
    ct = int(bq[ball])
    ms = int(bcur[ball])
    sc = float(bs[ball])
    z = _zone_label_for_ball(ball, DLT_BACK_ZONES_CAP, "后区")
    return (
        f"**`{_fmt2(ball)}`**（{z}）：近 **{n_win}** 期出现 **{ct}** 次，当前遗漏 **{ms}** 期；"
        f"加权综合分 **{sc:.3f}**（权重见**口径说明**）；"
        f"本注按「每 **4** 个号一小区、每小区至多 **{DLT_BACK_MAX_PER_ZONE}** 个」由后区综合分贪心入选。"
    )


def _reason_ssq_red_line(ball: int, n_win: int, rq: np.ndarray, rcur: np.ndarray, rs: np.ndarray) -> str:
    ct = int(rq[ball])
    ms = int(rcur[ball])
    sc = float(rs[ball])
    z = _zone_label_for_ball(ball, SSQ_RED_ZONES_CAP, "红球")
    return (
        f"**`{_fmt2(ball)}`**（{z}）：近 **{n_win}** 期出现 **{ct}** 次，当前遗漏 **{ms}** 期；"
        f"加权综合分 **{sc:.3f}**（权重见**口径说明**）；"
        f"本注按「每 **5** 个连续号为一小区，每小区至多 **{SSQ_RED_MAX_PER_ZONE}** 个」由红球综合分序列贪心入选。"
    )


def _reason_ssq_blue_line(ball: int, n_win: int, bq: np.ndarray, bcur: np.ndarray, bs: np.ndarray) -> str:
    ct = int(bq[ball])
    ms = int(bcur[ball])
    sc = float(bs[ball])
    z = _zone_label_for_ball(ball, SSQ_BLUE_ZONES_CAP, "蓝球")
    return (
        f"**`{_fmt2(ball)}`**（{z}）：近 **{n_win}** 期出现 **{ct}** 次，当前遗漏 **{ms}** 期；"
        f"加权综合分 **{sc:.3f}**（权重见**口径说明**）；本注为蓝球单码优选（四码段每段至多 **{SSQ_BLUE_MAX_PER_ZONE}** 个，取 1 个蓝球时自然满足）。"
    )


def _dlt_collect_five_unique_tickets(
    fs: np.ndarray,
    bs: np.ndarray,
    n_lines: int = PREDICTION_SINGLE_LINES,
    max_iter: int = 2000,
    penalty0: float = 0.09,
) -> list[tuple[list[int], list[int]]]:
    """多组互异单式：对已在前面注次出现的号码累加惩罚，拉开组合；不足则随机种子补全。"""
    pick_cf = np.zeros(36, dtype=np.float64)
    pick_cb = np.zeros(13, dtype=np.float64)
    seen: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()
    out: list[tuple[list[int], list[int]]] = []
    penalty = float(penalty0)
    it = 0
    while len(out) < n_lines and it < max_iter:
        it += 1
        fs_adj = fs.astype(np.float64).copy()
        bs_adj = bs.astype(np.float64).copy()
        fs_adj[1:36] -= penalty * pick_cf[1:36]
        bs_adj[1:13] -= penalty * pick_cb[1:13]
        try:
            fi = _pick_top_indices_zone_capped(
                fs_adj, 1, 35, 5, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE, rng=None
            )
            bi = _pick_top_indices_zone_capped(
                bs_adj, 1, 12, 2, DLT_BACK_ZONES_CAP, DLT_BACK_MAX_PER_ZONE, rng=None
            )
        except ValueError:
            penalty *= 0.88
            continue
        key = (tuple(sorted(fi)), tuple(sorted(bi)))
        if key in seen:
            penalty *= 1.14
            continue
        seen.add(key)
        out.append((sorted(fi), sorted(bi)))
        for x in fi:
            pick_cf[int(x)] += 1.0
        for x in bi:
            pick_cb[int(x)] += 1.0
        penalty = float(penalty0)

    if len(out) < n_lines:
        for seed in range(400000):
            rng = random.Random(seed + 17)
            try:
                fi = _pick_top_indices_zone_capped(
                    fs, 1, 35, 5, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE, rng=rng
                )
                bi = _pick_top_indices_zone_capped(
                    bs, 1, 12, 2, DLT_BACK_ZONES_CAP, DLT_BACK_MAX_PER_ZONE, rng=rng
                )
            except ValueError:
                continue
            key = (tuple(sorted(fi)), tuple(sorted(bi)))
            if key in seen:
                continue
            seen.add(key)
            out.append((sorted(fi), sorted(bi)))
            if len(out) >= n_lines:
                break

    if len(out) < n_lines:
        raise ValueError(f"大乐透：无法在尝试内凑满 {n_lines} 组互异单式（已得 {len(out)}）")
    return out[:n_lines]


def _ssq_collect_five_unique_tickets(
    rs: np.ndarray,
    bs: np.ndarray,
    n_lines: int = PREDICTION_SINGLE_LINES,
    max_iter: int = 2000,
    penalty0: float = 0.09,
) -> list[tuple[list[int], int]]:
    pick_cr = np.zeros(34, dtype=np.float64)
    pick_cb = np.zeros(17, dtype=np.float64)
    seen: set[tuple[tuple[int, ...], int]] = set()
    out: list[tuple[list[int], int]] = []
    penalty = float(penalty0)
    it = 0
    while len(out) < n_lines and it < max_iter:
        it += 1
        rs_adj = rs.astype(np.float64).copy()
        bs_adj = bs.astype(np.float64).copy()
        rs_adj[1:34] -= penalty * pick_cr[1:34]
        bs_adj[1:17] -= penalty * pick_cb[1:17]
        try:
            fi = _pick_top_indices_zone_capped(
                rs_adj, 1, 33, 6, SSQ_RED_ZONES_CAP, SSQ_RED_MAX_PER_ZONE, rng=None
            )
            bi = _pick_top_indices_zone_capped(
                bs_adj, 1, 16, 1, SSQ_BLUE_ZONES_CAP, SSQ_BLUE_MAX_PER_ZONE, rng=None
            )
        except ValueError:
            penalty *= 0.88
            continue
        bl = int(bi[0])
        key = (tuple(sorted(fi)), bl)
        if key in seen:
            penalty *= 1.14
            continue
        seen.add(key)
        out.append((sorted(fi), bl))
        for x in fi:
            pick_cr[int(x)] += 1.0
        pick_cb[bl] += 1.0
        penalty = float(penalty0)

    if len(out) < n_lines:
        for seed in range(400000):
            rng = random.Random(seed + 29)
            try:
                fi = _pick_top_indices_zone_capped(
                    rs, 1, 33, 6, SSQ_RED_ZONES_CAP, SSQ_RED_MAX_PER_ZONE, rng=rng
                )
                bi = _pick_top_indices_zone_capped(
                    bs, 1, 16, 1, SSQ_BLUE_ZONES_CAP, SSQ_BLUE_MAX_PER_ZONE, rng=rng
                )
            except ValueError:
                continue
            bl = int(bi[0])
            key = (tuple(sorted(fi)), bl)
            if key in seen:
                continue
            seen.add(key)
            out.append((sorted(fi), bl))
            if len(out) >= n_lines:
                break

    if len(out) < n_lines:
        raise ValueError(f"双色球：无法在尝试内凑满 {n_lines} 组互异单式（已得 {len(out)}）")
    return out[:n_lines]


def _build_dlt_five_numbers_md(
    five: list[tuple[list[int], list[int]]],
    fs: np.ndarray,
    bs: np.ndarray,
    fq: np.ndarray,
    fcur: np.ndarray,
    bq: np.ndarray,
    bcur: np.ndarray,
    n_win: int,
    pred_ts: str,
) -> str:
    parts: list[str] = [
        f"> **预测生成时间**：`{pred_ts}`（北京时间，ISO-8601）。\n",
        f"> 共 **{PREDICTION_SINGLE_LINES}** 注单式，每注 **2** 元；下列「选择原因」均为窗口内统计指标说明，**非**开奖承诺。\n\n",
    ]
    for i, (f, b) in enumerate(five, 1):
        ff = ",".join(_fmt2(x) for x in f)
        bb = ",".join(_fmt2(x) for x in b)
        parts.append(f"### 第 {i} 注（单式）\n\n")
        parts.append(f"- **号码**：前区 **{ff}**；后区 **{bb}**\n\n")
        parts.append("- **各号选择原因**：\n\n")
        for x in f:
            parts.append(f"  - {_reason_dlt_front_line(int(x), n_win, fq, fcur, fs)}\n\n")
        for x in b:
            parts.append(f"  - {_reason_dlt_back_line(int(x), n_win, bq, bcur, bs)}\n\n")
    return "".join(parts).rstrip() + "\n"


def _build_ssq_five_numbers_md(
    five: list[tuple[list[int], int]],
    rs: np.ndarray,
    bs: np.ndarray,
    rq: np.ndarray,
    rcur: np.ndarray,
    bq: np.ndarray,
    bcur: np.ndarray,
    n_win: int,
    pred_ts: str,
) -> str:
    parts: list[str] = [
        f"> **预测生成时间**：`{pred_ts}`（北京时间，ISO-8601）。\n",
        f"> 共 **{PREDICTION_SINGLE_LINES}** 注单式，每注 **2** 元；下列「选择原因」均为窗口内统计指标说明，**非**开奖承诺。\n\n",
    ]
    for i, (r, bl) in enumerate(five, 1):
        rs_s = ",".join(_fmt2(x) for x in r)
        parts.append(f"### 第 {i} 注（单式）\n\n")
        parts.append(f"- **号码**：红球 **{rs_s}**；蓝球 **`{_fmt2(bl)}`**\n\n")
        parts.append("- **各号选择原因**：\n\n")
        for x in r:
            parts.append(f"  - {_reason_ssq_red_line(int(x), n_win, rq, rcur, rs)}\n\n")
        parts.append(f"  - {_reason_ssq_blue_line(bl, n_win, bq, bcur, bs)}\n\n")
    return "".join(parts).rstrip() + "\n"


def dlt_explicit_from_patterns(
    f_draws: list[list[int]],
    b_draws: list[list[int]],
    fq: np.ndarray,
    fcur: np.ndarray,
    bq: np.ndarray,
    bcur: np.ndarray,
) -> tuple[str, str]:
    """兼容：返回 **5 注方案中第 1 注** 的前区、后区 CSV 串（与正文首注一致）。"""
    fs = _dlt_front_scores(f_draws, fq, fcur)
    bs = _dlt_back_scores(b_draws, bq, bcur)
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
    """兼容：返回 **5 注方案中第 1 注** 的红球、蓝球（与正文首注一致）。"""
    rs = _ssq_red_scores(r_draws, rq, rcur)
    bs = _ssq_blue_scores(blues, bq, bcur)
    r0, b0 = _ssq_collect_five_unique_tickets(rs, bs)[0]
    return ",".join(_fmt2(x) for x in r0), _fmt2(b0)


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

    def qstats(a: np.ndarray) -> str:
        qs = np.nanpercentile(a, [25, 50, 75])
        return f"均值 {a.mean():.2f}，中位数 {qs[1]:.0f}，Q1–Q3 约 {qs[0]:.0f}–{qs[2]:.0f}"

    from collections import Counter

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

- 和值：{qstats(sums)}  
- 跨度：{qstats(spans)}  
- AC（算术复杂度，AC = D−(n−1)，n=5）：主要取值分布（Top5）：{format_ac_top(acs)}

### 3) 连号与奇偶结构

- 含至少一对连号占比：{consec_cnt / n * 100:.2f}%  
- 前区奇数个数的常见取值（Top3）：{", ".join([f"`{k}奇:{n-k}偶`（{v}期）" for k,v in top_odd])}

### 4) 局限

历史分布仅为描述性统计，不构成预测或投资建议。

"""


def format_ac_top(acs: np.ndarray) -> str:
    vals, counts = np.unique(acs.astype(int), return_counts=True)
    order = np.argsort(-counts)
    parts = []
    for i in order[:5]:
        parts.append(f"AC={int(vals[i])}（{int(counts[i])}期）")
    return "，".join(parts)


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
    from collections import Counter

    odd_ctr = Counter(odd_rat)
    top_odd = odd_ctr.most_common(3)

    consec_cnt = 0
    for row in r_draws:
        srow = sorted(row)
        if any(srow[i + 1] - srow[i] == 1 for i in range(len(srow) - 1)):
            consec_cnt += 1

    def qstats(a: np.ndarray) -> str:
        qs = np.nanpercentile(a, [25, 50, 75])
        return f"均值 {a.mean():.2f}，中位数 {qs[1]:.0f}，Q1–Q3 约 {qs[0]:.0f}–{qs[2]:.0f}"

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

- 和值：{qstats(sums)}  
- 跨度：{qstats(spans)}  
- AC（n=6，AC=D−5）：{format_ac_top(acs)}

### 3) 连号与奇偶

- 含至少一对连号占比：{consec_cnt / n * 100:.2f}%  
- 红球奇数个数 Top3：{", ".join([f"`{k}奇`（{v}期）" for k,v in top_odd])}

### 4) 局限

历史分布仅为描述性统计，不构成预测或投资建议。

"""


def prediction_block_dlt(df: pd.DataFrame, n_last: int = DEFAULT_STATS_WINDOW) -> str:
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    tail = df.sort_values("period_id").tail(n_last)
    pmin, pmax = int(tail["period_id"].min()), int(tail["period_id"].max())
    fronts = tail[["front_1", "front_2", "front_3", "front_4", "front_5"]].astype(int).values.tolist()
    backs = tail[["back_1", "back_2"]].astype(int).values.tolist()
    f_draws = [list(map(int, r)) for r in fronts]
    b_draws = [list(map(int, r)) for r in backs]
    fq, fcur, _ = freq_miss_from_draws(f_draws, [], 35)
    bq, bcur, _ = freq_miss_from_draws(b_draws, [], 12)
    hotf = topk(fq, 5, high=True)
    lowf = topk(fq, 5, high=False)
    hotb = topk(bq, 5, high=True)
    lowb = topk(bq, 5, high=False)

    # 结构
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
    fs = _dlt_front_scores(f_draws, fq, fcur)
    bs = _dlt_back_scores(b_draws, bq, bcur)
    five = _dlt_collect_five_unique_tickets(fs, bs)
    numbers_md = _build_dlt_five_numbers_md(five, fs, bs, fq, fcur, bq, bcur, n_win, pred_ts)

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
- **{PREDICTION_SINGLE_LINES} 注单式（机械）**：每注前区 5 + 后区 2；各号多因子原始分 **min-max 归一** 后按权重合成综合分，再按下述小区上限贪心取号（**同分随机**）。**前区**：**7** 段、每段连续 **5** 个号（**01–05 / 06–10 / 11–15 / 16–20 / 21–25 / 26–30 / 31–35**），每段至多 **{DLT_FRONT_MAX_PER_ZONE}** 个；**后区**：**3** 段、每段连续 **4** 个号（**01–04 / 05–08 / 09–12**），每段至多 **{DLT_BACK_MAX_PER_ZONE}** 个。**{PREDICTION_SINGLE_LINES} 注**之间对**已出现过的号码**在下一轮综合分上施加**递减惩罚**，以拉开互异组合；仍不足则换随机种子补全互异注。**权重**：**{_pattern_weight_md_line()}**；因子还含 **近 {PATTERN_RECENT_K} 期密度、奇偶结构、大小（前≥18 / 后≥7）、和值带、区段划分**（区间热度与取号分区一致）。

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


def prediction_block_ssq(df: pd.DataFrame, n_last: int = DEFAULT_STATS_WINDOW) -> str:
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    tail = df.sort_values("period_id").tail(n_last)
    pmin, pmax = int(tail["period_id"].min()), int(tail["period_id"].max())
    reds = tail[[f"red_{i}" for i in range(1, 7)]].astype(int).values.tolist()
    blues = tail["blue"].astype(int).tolist()
    r_draws = [list(map(int, r)) for r in reds]
    blues_list = [int(b) for b in blues]
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
    rs = _ssq_red_scores(r_draws, rq, rcur)
    bs_sc = _ssq_blue_scores(blues_list, bq, bcur)
    five = _ssq_collect_five_unique_tickets(rs, bs_sc)
    numbers_md = _build_ssq_five_numbers_md(five, rs, bs_sc, rq, rcur, bq, bcur, n_win, pred_ts)

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
- **{PREDICTION_SINGLE_LINES} 注单式（机械）**：每注红球 6 + 蓝球 1；多因子 **min-max 归一** 后加权合成，再按下述小区上限贪心取号（**同分随机**）。**红球**：**7** 段、每段连续 **5** 个号（末段 **31–33** 仅 3 个号：**01–05 / 06–10 / 11–15 / 16–20 / 21–25 / 26–30 / 31–33**），每段至多 **{SSQ_RED_MAX_PER_ZONE}** 个；**蓝球**：**4** 段、每段连续 **4** 个号（**01–04 / 05–08 / 09–12 / 13–16**），每段至多 **{SSQ_BLUE_MAX_PER_ZONE}** 个（单码取蓝时自然满足）。**{PREDICTION_SINGLE_LINES} 注**间对**已出现过的号码**在下一轮综合分上施加**递减惩罚**以拉开互异组合；仍不足则换随机种子补全。**权重**：**{_pattern_weight_md_line()}**；红球另有 **近 {PATTERN_RECENT_K} 期密度、奇偶/大小（≥17）、和值带、五码段划分**；蓝球另有 **近 {PATTERN_RECENT_K} 期密度、奇偶、中位蓝贴近、大号占比（≥9）**。

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


def _norm_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).lstrip("\ufeff").strip() for c in df.columns]
    return df


def _kl8_draw_rows(df: pd.DataFrame) -> tuple[list[list[int]], list]:
    ncols = [f"n{i:02d}" for i in range(1, 21)]
    df = df.copy()
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    df = df.sort_values("period_id").reset_index(drop=True)
    draws: list[list[int]] = []
    for _, row in df.iterrows():
        draws.append([int(row[c]) for c in ncols])
    return draws, df["period_id"].tolist()


def _kl8_recency_counts(draws: list[list[int]], k: int) -> np.ndarray:
    """窗口末尾最近 k 期内，各号在「开奖 20 码」中出现次数（索引 1..80）。"""
    return _recency_counts(draws, k, 80)


def _kl8_twenty_from_patterns(freq: np.ndarray, cur_miss: np.ndarray, draws: list[list[int]]) -> list[int]:
    """多因子加权综合分取前 20 个互异号码；同分随机；**每十码段至多 5 个**（见 `KL8_MAX_PER_PICK_ZONE`），升序展示。"""
    scores = _kl8_twenty_scores(freq, cur_miss, draws)
    ranked = _pick_top_indices_zone_capped(
        scores, 1, 80, 20, KL8_PICK_ZONES_CAP, KL8_MAX_PER_PICK_ZONE
    )
    return sorted(ranked)


def _kl8_eleven_zone_capped_from_twenty(twenty: list[int]) -> list[int]:
    """从 20 码中取 11 个；**每十码段至多 5 个**；随机尝试失败则贪心补足。"""
    if len(twenty) != 20 or len(set(twenty)) != 20:
        raise ValueError("twenty 须为 20 个互异号码")
    zones = KL8_PICK_ZONES_CAP
    for _ in range(8000):
        s = random.sample(twenty, 11)
        if all(c <= KL8_MAX_PER_PICK_ZONE for c in _counts_per_zone_for_balls(s, zones)):
            return sorted(s)
    pool = twenty[:]
    random.shuffle(pool)
    out: list[int] = []
    zc = [0] * len(zones)
    for x in pool:
        if len(out) >= 11:
            break
        zi = _zone_index_for_ball(x, zones)
        if zc[zi] < KL8_MAX_PER_PICK_ZONE:
            out.append(x)
            zc[zi] += 1
    if len(out) < 11:
        raise ValueError(
            f"20 码在十码段每区≤{KL8_MAX_PER_PICK_ZONE} 约束下无法凑满 11 码"
        )
    return sorted(out)


def _kl8_eleven_random_from_twenty(twenty: list[int]) -> list[int]:
    """在给定的 20 个号码中抽 11 个（**每十码段至多 5 个**），升序；每次运行可不同。"""
    return _kl8_eleven_zone_capped_from_twenty(twenty)


def build_kl8_analysis(df: pd.DataFrame, analysis_window: int = DEFAULT_STATS_WINDOW) -> str:
    """与大乐透/双色球 `build_*_analysis` 对齐：默认期末尾连续 `analysis_window` 期描述性统计。"""
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

    def qstats(a: np.ndarray) -> str:
        qs = np.nanpercentile(a, [25, 50, 75])
        return f"均值 {a.mean():.2f}，中位数 {qs[1]:.0f}，Q1–Q3 约 {qs[0]:.0f}–{qs[2]:.0f}"

    from collections import Counter

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

- 20 码和值：{qstats(sums)}
- 20 码跨度（max−min）：{qstats(spans)}

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
    twenty = _kl8_twenty_from_patterns(fq, fcur, draws)
    twenty_fmt = ",".join(_fmt2(x) for x in twenty)
    eleven = _kl8_eleven_random_from_twenty(twenty)
    eleven_fmt = ",".join(_fmt2(x) for x in eleven)

    hot_line = "；".join([f"`{a}`（**{b}** 次）" for a, b in hot5])
    low_line = "；".join([f"`{a}`（**{b}** 次）" for a, b in low5])
    miss_line = "；".join([f"`{a}`（**{b}** 期）" for a, b in top_miss])
    wline = _pattern_weight_md_line()

    return f"""# 快乐八 — 统计型预测参考归档

> **最后更新**：{now_cn_iso()}  
> **统计窗口（默认）**：近 **{n}** 期，期号 **`{pid_min}`–`{pid_max}`**（期末尾连续段，至多 **{n_last}** 期）。  
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
- **「规律线」参考 20 码（脚本）**：对 01–80 各号计算 **7** 项原始分（全窗口频次、当前遗漏、近 **{PATTERN_RECENT_K}** 期出现密度、与窗口内「每期 20 码奇数个数均值」的奇偶对齐、**01–40 / 41–80** 半区占比对齐、**20 码和值**相对中位带的条件对齐、**四区** 01–20 / 21–40 / 41–60 / 61–80 区段热度）；**每项先 min-max 归一到 [0,1]**，再按权重 **{wline}** 合成，分高者优先（**同分随机**）；取号时按 **8 个十码段（01–10,…,71–80）每段至多 {KL8_MAX_PER_PICK_ZONE} 个** 贪心取满 **20** 个互异号码后升序展示。**不是**从「最后一期已开出的 20 个号」里抽样，也**不是**单纯频次 Top20；仍属历史统计投影，**非**科学预测。

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

> 基于**当前 {n} 期窗口**的统计规律（**非**从最后一期已开 20 码中随机）：对每号 **7** 项因子 min-max 归一后按权重 **{wline}** 合成综合分，在 **8 个十码段每段至多 {KL8_MAX_PER_PICK_ZONE} 个** 约束下贪心取满 **20** 个互异号码（**同分随机**，每次运行可不同），升序排列，作为「下一期可参考的一注 20 码开奖形态」的**机械候选**；**非**官方开奖预告、**非**必中依据。

- **参考开奖 20 码（升序）**：**{twenty_fmt}**

---

## 明确号码输出（强制，选十视角统计参考）

> 在上一节由**规律线综合分**得到的 **20 个参考开奖号码**中，**无放回随机抽取 11 个**，且满足 **8 个十码段每段至多 {KL8_MAX_PER_PICK_ZONE} 个**（与 20 码同一分段），升序排列，供选十 **11 码复式**或裁剪为 10 码参考。**每次重新运行**生成脚本，**11 码可能与上次不同**（**20 码**在相同数据与常量下不变，但同分边界仍受随机影响时可变）；仍属娱乐向统计参考，**非**必中依据。

- **选十参考 11 码（升序）**：**{eleven_fmt}**

## 使用说明

以上全部内容均为对**已发生开奖记录**在声明口径下的**描述性统计**，用于娱乐与自行复盘参考。**下一期开奖仍为独立随机事件**，历史冷热、遗漏长短**不构成**对未来开奖的任何保证或「必出」依据；本归档**不包含**中奖承诺与投注金额建议。
{_prediction_md_appendix_kl8_bet(eleven_fmt)}

---

> **提示**：本文件由 `python src/scripts/lottery.py regenerate-history --only kl8`（**同时**重写 `history/kuaileba_analysis.md`）或 `regenerate-history --only all`（存在 `kl8_draws.csv` 时）生成；文末附录含 **10～30 元** 带内机械复式示例。若追加更复杂方案，可再请 **`lottery-combo-optimize`** 并写投注原因。
"""


def regenerate_kl8_prediction() -> int:
    """兼容别名：等同 `main(only="kl8")`，请优先使用 `regenerate-history --only kl8`。"""
    return main(only="kl8")


def _normalize_only(only: str) -> str:
    o = (only or "all").strip().lower().replace("-", "_")
    if o == "dltssq":
        return "dlt_ssq"
    return o


def main(only: str = "all") -> int:
    """按 `only` 刷新 `history/` 下书面归档（默认近 30 期见 `DEFAULT_STATS_WINDOW`）。

    only:
      - ``all``：大乐透+双色球四文件；若存在 ``kl8_draws.csv`` 再写快乐八两文件。
      - ``dlt_ssq``：仅大乐透+双色球四文件（不写快乐八，即使存在 kl8）。
      - ``kl8``：仅 ``kuaileba_analysis.md`` + ``kuaileba_prediction.md``。
    """
    only_n = _normalize_only(only)
    if only_n not in ("all", "kl8", "dlt_ssq"):
        print(
            json.dumps(
                {"ok": False, "error": f"invalid only={only!r}; use all | kl8 | dlt-ssq"},
                ensure_ascii=True,
            )
        )
        return 1

    HIST.mkdir(parents=True, exist_ok=True)
    wrote: list[str] = []

    manifest_excl: list[dict] = []
    if MANIFEST.exists():
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for block in m.get("outputs", []):
            if block.get("lottery_type") == "dlt":
                manifest_excl.extend(block.get("excluded", []))

    if only_n in ("all", "dlt_ssq"):
        dlt_path = PROC / "dlt_draws.csv"
        ssq_path = PROC / "ssq_draws.csv"
        if not dlt_path.exists() or not ssq_path.exists():
            raise SystemExit("缺少 data/processed/dlt_draws.csv 或 ssq_draws.csv；请补全 CSV 或使用 lottery-draw-dlt-ssq / lottery-draw-sync。")
        dlt = pd.read_csv(dlt_path)
        ssq = pd.read_csv(ssq_path)
        (HIST / "daletou_analysis.md").write_text(build_dlt_analysis(dlt, manifest_excl), encoding="utf-8")
        (HIST / "shuangseqiu_analysis.md").write_text(build_ssq_analysis(ssq), encoding="utf-8")
        (HIST / "daletou_prediction.md").write_text(prediction_block_dlt(dlt), encoding="utf-8")
        (HIST / "shuangseqiu_prediction.md").write_text(prediction_block_ssq(ssq), encoding="utf-8")
        wrote.extend(
            [
                "history/daletou_analysis.md",
                "history/shuangseqiu_analysis.md",
                "history/daletou_prediction.md",
                "history/shuangseqiu_prediction.md",
            ]
        )

    if only_n in ("all", "kl8"):
        kl8_path = PROC / "kl8_draws.csv"
        if not kl8_path.is_file():
            if only_n == "kl8":
                raise SystemExit("缺少 data/processed/kl8_draws.csv；请先补数或使用 lottery-draw-sync。")
        else:
            kl8 = pd.read_csv(kl8_path, encoding="utf-8-sig")
            (HIST / "kuaileba_analysis.md").write_text(build_kl8_analysis(kl8), encoding="utf-8")
            (HIST / "kuaileba_prediction.md").write_text(prediction_block_kl8(kl8), encoding="utf-8")
            wrote.extend(["history/kuaileba_analysis.md", "history/kuaileba_prediction.md"])

    if not wrote:
        print(
            json.dumps(
                {"ok": False, "error": "未写入任何文件；检查 --only 与 processed CSV 是否存在"},
                ensure_ascii=True,
            )
        )
        return 1

    print(json.dumps({"ok": True, "only": only_n, "wrote": wrote}, ensure_ascii=True))
    return 0


def _cli_only_from_argv(argv: list[str]) -> str:
    """供 ``python src/scripts/regenerate_history_archives.py --only kl8`` 使用。"""
    only = "all"
    i = 0
    while i < len(argv):
        if argv[i] == "--only" and i + 1 < len(argv):
            only = argv[i + 1]
            i += 2
        else:
            i += 1
    return only


if __name__ == "__main__":
    import sys

    raise SystemExit(main(only=_cli_only_from_argv(sys.argv[1:])))
