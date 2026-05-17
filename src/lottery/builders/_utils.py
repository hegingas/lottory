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
