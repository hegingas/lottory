"""通用辅助函数：数据规范化、统计摘要、排列5马尔可夫工具。"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ── 通用辅助 ──────────────────────────────────────────────────


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


# ── 排列5 马尔可夫工具 ──────────────────────────────────────────


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


# ── 逐位结构对齐因子 ─────────────────────────────────────────────


def _pl5_parity_alignment(draws: list[list[int]], pos: int, n_digits: int = 10) -> np.ndarray:
    """排列5逐位奇偶对齐分。

    score[d] = p_odd * is_odd(d) + (1-p_odd) * (1-is_odd(d))
    其中 p_odd = 该位置历史奇数出现比例。
    """
    n = len(draws)
    odd_count = sum(1 for row in draws if int(row[pos]) % 2 == 1)
    p_odd = odd_count / max(n, 1)
    out = np.zeros(n_digits, dtype=float)
    for d in range(n_digits):
        is_odd = float(d % 2)
        out[d] = p_odd * is_odd + (1.0 - p_odd) * (1.0 - is_odd)
    return out


def _pl5_size_alignment(draws: list[list[int]], pos: int, n_digits: int = 10,
                        big_threshold: int = 5) -> np.ndarray:
    """排列5逐位大小对齐分。digit >= big_threshold 为"大"（默认 >=5）。"""
    n = len(draws)
    big_count = sum(1 for row in draws if int(row[pos]) >= big_threshold)
    p_big = big_count / max(n, 1)
    out = np.zeros(n_digits, dtype=float)
    for d in range(n_digits):
        is_big = 1.0 if d >= big_threshold else 0.0
        out[d] = p_big * is_big + (1.0 - p_big) * (1.0 - is_big)
    return out


def _qxc_parity_alignment(draws: list[list[int]], pos: int, n_digits: int) -> np.ndarray:
    """七星彩逐位奇偶对齐分。n_digits=10(前区)或15(后区0-14)。"""
    n = len(draws)
    odd_count = sum(1 for row in draws if int(row[pos]) % 2 == 1)
    p_odd = odd_count / max(n, 1)
    out = np.zeros(n_digits, dtype=float)
    for d in range(n_digits):
        is_odd = float(d % 2)
        out[d] = p_odd * is_odd + (1.0 - p_odd) * (1.0 - is_odd)
    return out


def _qxc_size_alignment(draws: list[list[int]], pos: int, n_digits: int,
                        big_threshold: int) -> np.ndarray:
    """七星彩逐位大小对齐分。前区 big_threshold=5，后区 big_threshold=7。"""
    n = len(draws)
    big_count = sum(1 for row in draws if int(row[pos]) >= big_threshold)
    p_big = big_count / max(n, 1)
    out = np.zeros(n_digits, dtype=float)
    for d in range(n_digits):
        is_big = 1.0 if d >= big_threshold else 0.0
        out[d] = p_big * is_big + (1.0 - p_big) * (1.0 - is_big)
    return out


# ── 6因子逐位综合评分 ─────────────────────────────────────────────


def _pl5_6f_position_scores(
    draws: list[list[int]],
    draws_all: list[list[int]],
    pos: int,
    n_win: int,
    recent_k: int,
    weights: dict[str, float],
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """排列5单位置 6 因子综合评分。

    Returns:
        (composite_10d, raw_factors) where raw_factors keys:
        "markov", "miss", "freq", "recency", "parity", "size"
    """
    n_digits = 10
    freq = np.zeros(n_digits, dtype=float)
    miss = np.zeros(n_digits, dtype=float)
    rec = np.zeros(n_digits, dtype=float)

    for row in draws:
        freq[int(row[pos])] += 1.0
    for d in range(n_digits):
        m = n_win
        for k in range(n_win - 1, -1, -1):
            if int(draws[k][pos]) == d:
                m = n_win - 1 - k
                break
        miss[d] = float(m)
    for row in draws[-min(recent_k, n_win):]:
        rec[int(row[pos])] += 1.0

    mk = _pl5_markov_blended(draws_all, pos)
    parity = _pl5_parity_alignment(draws, pos, n_digits)
    size = _pl5_size_alignment(draws, pos, n_digits)

    sc = (
        weights["markov"] * _pl5_norm01(mk)
        + weights["miss"] * _pl5_norm01(miss)
        + weights["freq"] * _pl5_norm01(freq)
        + weights["recency"] * _pl5_norm01(rec)
        + weights["parity"] * _pl5_norm01(parity)
        + weights["size"] * _pl5_norm01(size)
    )
    raw = {"markov": mk, "miss": miss, "freq": freq, "recency": rec, "parity": parity, "size": size}
    return sc, raw


def _qxc_6f_position_scores(
    draws: list[list[int]],
    draws_all: list[list[int]],
    pos: int,
    n_digits: int,
    n_win: int,
    recent_k: int,
    weights: dict[str, float],
    big_threshold: int = 5,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """七星彩单位置 6 因子综合评分（前区 n_digits=10/big=5，后区 n_digits=15/big=7）。"""
    freq = np.zeros(n_digits, dtype=float)
    miss = np.zeros(n_digits, dtype=float)
    rec = np.zeros(n_digits, dtype=float)

    for row in draws:
        freq[int(row[pos])] += 1.0
    for d in range(n_digits):
        m = n_win
        for k in range(n_win - 1, -1, -1):
            if int(draws[k][pos]) == d:
                m = n_win - 1 - k
                break
        miss[d] = float(m)
    for row in draws[-min(recent_k, n_win):]:
        rec[int(row[pos])] += 1.0

    mk = _qxc_markov_blended(draws_all, pos, n_digits)
    parity = _qxc_parity_alignment(draws, pos, n_digits)
    size = _qxc_size_alignment(draws, pos, n_digits, big_threshold)

    sc = (
        weights["markov"] * _qxc_norm01(mk)
        + weights["miss"] * _qxc_norm01(miss)
        + weights["freq"] * _qxc_norm01(freq)
        + weights["recency"] * _qxc_norm01(rec)
        + weights["parity"] * _qxc_norm01(parity)
        + weights["size"] * _qxc_norm01(size)
    )
    raw = {"markov": mk, "miss": miss, "freq": freq, "recency": rec, "parity": parity, "size": size}
    return sc, raw


# ── 七星彩马尔可夫工具（从 scoring.py 的 _qxc_* 系列重新导出） ──

def _qxc_markov_probs(draws: list[list[int]], pos: int, n_digits: int = 10,
                      laplace: float = 1.0) -> np.ndarray:
    """一阶马尔可夫（按位）：基于相邻期 digit 转移矩阵。"""
    out = np.full(n_digits, 1.0 / n_digits, dtype=float)
    if len(draws) < 2:
        return out
    trans = np.zeros((n_digits, n_digits), dtype=float)
    for t in range(1, len(draws)):
        prev = int(draws[t - 1][pos])
        cur = int(draws[t][pos])
        trans[prev, cur] += 1.0
    latest = int(draws[-1][pos])
    row = trans[latest]
    den = float(row.sum() + n_digits * laplace)
    for d in range(n_digits):
        out[d] = (float(row[d]) + laplace) / den
    return out


def _qxc_markov_probs_2nd(draws: list[list[int]], pos: int, n_digits: int = 10,
                          laplace: float = 1.0) -> np.ndarray:
    """二阶马尔可夫（按位）：基于 (d_{t-2}, d_{t-1}) → d_t。"""
    out = np.full(n_digits, 1.0 / n_digits, dtype=float)
    if len(draws) < 3:
        return out
    trans = np.zeros((n_digits, n_digits, n_digits), dtype=float)
    for t in range(2, len(draws)):
        prev2 = int(draws[t - 2][pos])
        prev1 = int(draws[t - 1][pos])
        cur = int(draws[t][pos])
        trans[prev2, prev1, cur] += 1.0
    prev2_latest = int(draws[-2][pos])
    prev1_latest = int(draws[-1][pos])
    row = trans[prev2_latest, prev1_latest]
    den = float(row.sum() + n_digits * laplace)
    for d in range(n_digits):
        out[d] = (float(row[d]) + laplace) / den
    return out


def _qxc_markov_blended(draws: list[list[int]], pos: int, n_digits: int = 10,
                        laplace: float = 1.0, w1: float = 0.40, w2: float = 0.60) -> np.ndarray:
    """一阶 + 二阶马尔可夫混合概率（按位）。不足 3 期时退化为纯一阶。"""
    p1 = _qxc_markov_probs(draws, pos, n_digits, laplace)
    if len(draws) < 3:
        return p1
    p2 = _qxc_markov_probs_2nd(draws, pos, n_digits, laplace)
    return w1 * p1 + w2 * p2


def _qxc_norm01(vals: np.ndarray) -> np.ndarray:
    """Min-max 归一化到 [0,1]。全相等时返回 0.5。"""
    arr = vals.astype(float)
    lo = float(arr.min())
    hi = float(arr.max())
    if hi <= lo:
        return np.full_like(arr, 0.5, dtype=float)
    return (arr - lo) / (hi - lo)
