"""核心统计算法：频次、遗漏、AC 值、多因子加权评分、马尔可夫转移概率。"""

from __future__ import annotations

from typing import Any, Callable
import numpy as np

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
    DLT_BACK_ZONES_CAP,
    SSQ_RED_ZONES_CAP,
    SSQ_BLUE_ZONES_CAP,
    MARKOV_LAPLACE_ALPHA,
)


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


def _recency_counts(draws: list[list[int]], k: int, n_ball: int) -> np.ndarray:
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
    markov_raw: np.ndarray,
    n_ball: int,
) -> np.ndarray:
    nm = _minmax01_ball(miss_raw, n_ball)
    nf = _minmax01_ball(freq_raw, n_ball)
    nz = _minmax01_ball(zone_raw, n_ball)
    nr = _minmax01_ball(recency_raw, n_ball)
    np_ = _minmax01_ball(parity_raw, n_ball)
    ns = _minmax01_ball(size_raw, n_ball)
    nsum = _minmax01_ball(sum_raw, n_ball)
    nmk = _minmax01_ball(markov_raw, n_ball)
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
            + PATTERN_W_MARKOV  * nmk[i]
        )
    return out


def _markov_next_probabilities(
    draws: list[list[int]],
    n_ball: int,
    *,
    laplace_alpha: float = MARKOV_LAPLACE_ALPHA,
) -> np.ndarray:
    out = np.full(n_ball + 1, 0.5, dtype=float)
    if not draws:
        return out

    pres = np.zeros((len(draws), n_ball + 1), dtype=np.int8)
    for t, d in enumerate(draws):
        for x in d:
            xi = int(x)
            if 1 <= xi <= n_ball:
                pres[t, xi] = 1

    if len(draws) < 2:
        return out

    trans = np.zeros((n_ball + 1, 2, 2), dtype=np.float64)
    for t in range(1, len(draws)):
        prev_row = pres[t - 1]
        cur_row = pres[t]
        for i in range(1, n_ball + 1):
            trans[i, int(prev_row[i]), int(cur_row[i])] += 1.0

    latest = pres[-1]
    a = float(laplace_alpha)
    for i in range(1, n_ball + 1):
        s = int(latest[i])
        c0 = trans[i, s, 0]
        c1 = trans[i, s, 1]
        out[i] = (c1 + a) / (c0 + c1 + 2.0 * a)
    return out


def _sum_alignment_scores(draws: list[list[int]], n_ball: int) -> np.ndarray:
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
    p = mean_odd_per_draw / max(slots, 1)
    out = np.zeros(n_ball + 1, dtype=float)
    for i in range(1, n_ball + 1):
        is_odd = float(i % 2)
        out[i] = p * is_odd + (1.0 - p) * (1.0 - is_odd)
    return out


def _size_alignment_raw(
    n_ball: int, mean_big_per_draw: float, slots: int, big_pred: Callable[[int], bool]
) -> np.ndarray:
    p = mean_big_per_draw / max(slots, 1)
    out = np.zeros(n_ball + 1, dtype=float)
    for i in range(1, n_ball + 1):
        b = 1.0 if big_pred(i) else 0.0
        out[i] = p * b + (1.0 - p) * (1.0 - b)
    return out


def _kl8_half_alignment_raw(draws: list[list[int]], n_ball: int) -> np.ndarray:
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


# ── 各彩种综合分构建 ────────────────────────────────────────────

def _kl8_twenty_scores(
    freq: np.ndarray,
    cur_miss: np.ndarray,
    draws: list[list[int]],
    markov_raw: np.ndarray,
) -> np.ndarray:
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
    return _weighted_composite(f_miss, f_freq, f_zone, f_rec, f_odd, f_half, f_sum, markov_raw, n_ball)


def _dlt_front_scores(
    f_draws: list[list[int]],
    fq: np.ndarray,
    fcur: np.ndarray,
    markov_raw: np.ndarray,
) -> np.ndarray:
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
    return _weighted_composite(f_miss, f_freq, f_zone, f_rec, f_odd, f_big, f_sum, markov_raw, n_ball)


def _dlt_back_scores(
    b_draws: list[list[int]],
    bq: np.ndarray,
    bcur: np.ndarray,
    markov_raw: np.ndarray,
) -> np.ndarray:
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
    return _weighted_composite(f_miss, f_freq, f_zone, f_rec, f_odd, f_hi, f_sum, markov_raw, n_ball)


def _ssq_red_scores(
    r_draws: list[list[int]],
    rq: np.ndarray,
    rcur: np.ndarray,
    markov_raw: np.ndarray,
) -> np.ndarray:
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
    return _weighted_composite(f_miss, f_freq, f_zone, f_rec, f_odd, f_big, f_sum, markov_raw, n_ball)


def _ssq_blue_scores(
    blues: list[int],
    bq: np.ndarray,
    bcur: np.ndarray,
    markov_raw: np.ndarray,
) -> np.ndarray:
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
    return _weighted_composite(f_miss, f_freq, f_zone, f_rec, f_odd, f_hi, f_med, markov_raw, n_ball)


# ── 七星彩分位评分 ──────────────────────────────────────────────

def _qxc_norm01(vals: np.ndarray) -> np.ndarray:
    arr = vals.astype(float)
    lo = float(arr.min())
    hi = float(arr.max())
    if hi <= lo:
        return np.full_like(arr, 0.5, dtype=float)
    return (arr - lo) / (hi - lo)


def _qxc_markov_probs(draws: list[list[int]], pos: int, n_digits: int, laplace: float = 1.0) -> np.ndarray:
    out = np.full(n_digits, 1.0 / n_digits, dtype=float)
    if len(draws) < 2:
        return out
    trans = np.zeros((n_digits, n_digits), dtype=float)
    for t in range(1, len(draws)):
        prev = int(draws[t - 1][pos])
        cur = int(draws[t][pos])
        if 0 <= prev < n_digits and 0 <= cur < n_digits:
            trans[prev, cur] += 1.0
    latest = int(draws[-1][pos])
    if 0 <= latest < n_digits:
        row = trans[latest]
        den = float(row.sum() + n_digits * laplace)
        for d in range(n_digits):
            out[d] = (float(row[d]) + laplace) / den
    return out


def _qxc_position_scores(
    draws: list[list[int]],
    pos: int,
    n_digits: int,
    w_miss: float,
    w_freq: float,
    w_recency: float,
    w_markov: float,
    recent_k: int = 5,
) -> np.ndarray:
    n_win = len(draws)
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
    mk = _qxc_markov_probs(draws, pos, n_digits)
    sc = (
        w_miss    * _qxc_norm01(miss)
        + w_freq  * _qxc_norm01(freq)
        + w_recency * _qxc_norm01(rec)
        + w_markov * _qxc_norm01(mk)
    )
    return sc, mk
