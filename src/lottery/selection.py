"""选号算法：分区约束贪心选取、同分随机、多注互异收集、快乐八 20/11 选号。"""

from __future__ import annotations

import random
import numpy as np

from .config import (
    DLT_FRONT_ZONES_CAP,
    DLT_FRONT_MAX_PER_ZONE,
    DLT_BACK_ZONES_CAP,
    DLT_BACK_MAX_PER_ZONE,
    SSQ_RED_ZONES_CAP,
    SSQ_RED_MAX_PER_ZONE,
    SSQ_BLUE_ZONES_CAP,
    SSQ_BLUE_MAX_PER_ZONE,
    KL8_PICK_ZONES_CAP,
    KL8_MIN_PER_PICK_ZONE,
    KL8_MAX_PER_PICK_ZONE,
    PREDICTION_SINGLE_LINES,
    TICKET_COLLECT_MAX_ITER,
    TICKET_COLLECT_PENALTY_INIT,
    TICKET_COLLECT_FALLBACK_MAX,
    KL8_ELEVEN_RANDOM_TRIES,
    _fmt2,
)
from .scoring import _kl8_twenty_scores


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
    for i, (lo, hi) in enumerate(zones, 1):
        if lo <= ball <= hi:
            return f"{prefix}第{i}小区（{_fmt2(lo)}–{_fmt2(hi)}）"
    return f"{prefix}（分区未覆盖）"


def _pick_top_scored_pairs_random_tie(
    scores: np.ndarray, i_lo: int, i_hi: int, k: int
) -> list[tuple[int, float]]:
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


def _pick_top_indices_zone_bounded(
    scores: np.ndarray,
    i_lo: int,
    i_hi: int,
    k: int,
    zones: list[tuple[int, int]],
    min_per_zone: int,
    max_per_zone: int,
    rng: random.Random | None = None,
) -> list[int]:
    if min_per_zone < 0 or max_per_zone < 0 or min_per_zone > max_per_zone:
        raise ValueError(
            f"非法分区边界：min_per_zone={min_per_zone}, max_per_zone={max_per_zone}"
        )
    n_zone = len(zones)
    if min_per_zone * n_zone > k:
        raise ValueError(
            f"分区下限不可行：{n_zone} 个分区 × 至少 {min_per_zone} 个 > 目标 {k} 个"
        )
    if max_per_zone * n_zone < k:
        raise ValueError(
            f"分区上限不可行：{n_zone} 个分区 × 至多 {max_per_zone} 个 < 目标 {k} 个"
        )

    rnd = rng if rng is not None else random
    ix = list(range(i_lo, i_hi + 1))
    rnd.shuffle(ix)
    ix.sort(key=lambda i: -scores[i])

    zone_to_idx: list[list[int]] = [[] for _ in range(n_zone)]
    for i in ix:
        zi = _zone_index_for_ball(i, zones)
        zone_to_idx[zi].append(i)

    out: list[int] = []
    zc = [0] * n_zone
    picked: set[int] = set()

    if min_per_zone > 0:
        for zi in range(n_zone):
            need = min_per_zone
            if len(zone_to_idx[zi]) < need:
                raise ValueError(
                    f"分区 {zi + 1} 可选号码不足：需要至少 {need} 个，实际 {len(zone_to_idx[zi])} 个"
                )
            for i in zone_to_idx[zi]:
                if zc[zi] >= need:
                    break
                out.append(i)
                picked.add(i)
                zc[zi] += 1

    for i in ix:
        if len(out) >= k:
            break
        if i in picked:
            continue
        zi = _zone_index_for_ball(i, zones)
        if zc[zi] >= max_per_zone:
            continue
        out.append(i)
        picked.add(i)
        zc[zi] += 1

    if len(out) < k:
        raise ValueError(
            f"在每区至少 {min_per_zone} 且至多 {max_per_zone} 约束下无法取满 {k} 个（已取 {len(out)}，zones={zones}）"
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


# ── 大乐透 / 双色球 多注互异收集 ──────────────────────────────

def _dlt_collect_five_unique_tickets(
    fs: np.ndarray,
    bs: np.ndarray,
    n_lines: int = PREDICTION_SINGLE_LINES,
    max_iter: int = TICKET_COLLECT_MAX_ITER,
    penalty0: float = TICKET_COLLECT_PENALTY_INIT,
) -> list[tuple[list[int], list[int]]]:
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
                fs_adj, 1, 35, 5, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE
            )
            bi = _pick_top_indices_zone_capped(
                bs_adj, 1, 12, 2, DLT_BACK_ZONES_CAP, DLT_BACK_MAX_PER_ZONE
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
        for seed in range(TICKET_COLLECT_FALLBACK_MAX):
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
    max_iter: int = TICKET_COLLECT_MAX_ITER,
    penalty0: float = TICKET_COLLECT_PENALTY_INIT,
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
                rs_adj, 1, 33, 6, SSQ_RED_ZONES_CAP, SSQ_RED_MAX_PER_ZONE
            )
            bi = _pick_top_indices_zone_capped(
                bs_adj, 1, 16, 1, SSQ_BLUE_ZONES_CAP, SSQ_BLUE_MAX_PER_ZONE
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
        for seed in range(TICKET_COLLECT_FALLBACK_MAX):
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


# ── 快乐八 20/11 选号 ──────────────────────────────────────────

def _kl8_twenty_from_patterns(
    freq: np.ndarray,
    cur_miss: np.ndarray,
    draws: list[list[int]],
    markov_raw: np.ndarray,
) -> list[int]:
    scores = _kl8_twenty_scores(freq, cur_miss, draws, markov_raw)
    ranked = _pick_top_indices_zone_bounded(
        scores,
        1,
        80,
        20,
        KL8_PICK_ZONES_CAP,
        KL8_MIN_PER_PICK_ZONE,
        KL8_MAX_PER_PICK_ZONE,
    )
    return sorted(ranked)


def _kl8_eleven_zone_capped_from_twenty(twenty: list[int]) -> list[int]:
    if len(twenty) != 20 or len(set(twenty)) != 20:
        raise ValueError("twenty 须为 20 个互异号码")
    zones = KL8_PICK_ZONES_CAP
    for _ in range(KL8_ELEVEN_RANDOM_TRIES):
        s = random.sample(twenty, 11)
        zc_try = _counts_per_zone_for_balls(s, zones)
        if all(KL8_MIN_PER_PICK_ZONE <= c <= KL8_MAX_PER_PICK_ZONE for c in zc_try):
            return sorted(s)
    aux_scores = np.zeros(81, dtype=float)
    for rank, x in enumerate(sorted(twenty)):
        aux_scores[int(x)] = float(len(twenty) - rank)
    out = _pick_top_indices_zone_bounded(
        aux_scores,
        1,
        80,
        11,
        zones,
        KL8_MIN_PER_PICK_ZONE,
        KL8_MAX_PER_PICK_ZONE,
    )
    if len(out) < 11:
        raise ValueError(
            f"20 码在十码段每区[{KL8_MIN_PER_PICK_ZONE},{KL8_MAX_PER_PICK_ZONE}]约束下无法凑满11码"
        )
    return sorted(out)


def _kl8_eleven_random_from_twenty(twenty: list[int]) -> list[int]:
    return _kl8_eleven_zone_capped_from_twenty(twenty)


def _assert_kl8_zone_bounds(nums: list[int], label: str) -> list[int]:
    zc = _counts_per_zone_for_balls(nums, KL8_PICK_ZONES_CAP)
    bad = []
    for zi, c in enumerate(zc, 1):
        if c < KL8_MIN_PER_PICK_ZONE or c > KL8_MAX_PER_PICK_ZONE:
            lo, hi = KL8_PICK_ZONES_CAP[zi - 1]
            bad.append(f"zone{zi}({_fmt2(lo)}-{_fmt2(hi)}):{c}")
    if bad:
        raise ValueError(
            f"{label} 分区校验失败：要求每小区[{KL8_MIN_PER_PICK_ZONE},{KL8_MAX_PER_PICK_ZONE}]，实际 {', '.join(bad)}；全量计数={zc}"
        )
    return zc
