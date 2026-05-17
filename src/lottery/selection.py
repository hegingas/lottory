"""选号算法：分区约束贪心选取、同分随机、多注互异收集、快乐八 20/11 选号。"""

from __future__ import annotations

import random

import numpy as np

from . import config as _lottery_config
from .config import (
    DLT_BACK_MAX_PER_ZONE,
    DLT_BACK_ZONES_CAP,
    DLT_FRONT_MAX_PER_ZONE,
    DLT_FRONT_ZONES_CAP,
    KL8_ELEVEN_OVERLAP_MAX,
    KL8_ELEVEN_RANDOM_TRIES,
    KL8_MAX_PER_PICK_ZONE,
    KL8_MIN_PER_PICK_ZONE,
    KL8_PICK_ZONES_CAP,
    PREDICTION_SINGLE_LINES,
    SSQ_BLUE_MAX_PER_ZONE,
    SSQ_BLUE_ZONES_CAP,
    SSQ_RED_MAX_PER_ZONE,
    SSQ_RED_ZONES_CAP,
    TICKET_COLLECT_FALLBACK_MAX,
    TICKET_COLLECT_LATEST_SCORE_PENALTY,
    TICKET_COLLECT_MAX_ITER,
    TICKET_COLLECT_PENALTY_INIT,
    TICKET_COLLECT_RANDOM_PHASE_MAX,
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


def _zone_max_cap_ok(
    balls: list[int], zones: list[tuple[int, int]], max_per_zone: int
) -> bool:
    zc = _counts_per_zone_for_balls(balls, zones)
    return all(c <= max_per_zone for c in zc)


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
    allowed: set[int] | None = None,
) -> list[int]:
    rnd = rng if rng is not None else random
    ix = [i for i in range(i_lo, i_hi + 1) if allowed is None or i in allowed]
    rnd.shuffle(ix)
    ix.sort(key=lambda i: -scores[i])
    if len(ix) < k:
        raise ValueError(
            f"候选号不足：allowed 与 [{i_lo},{i_hi}] 交集仅 {len(ix)} 个，需要 {k} 个"
        )
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
    ix = [
        i
        for i in range(i_lo, i_hi + 1)
        if any(int(lo) <= i <= int(hi) for lo, hi in zones)
    ]
    if len(ix) < k:
        raise ValueError(
            f"zones 在 [{i_lo},{i_hi}] 内的并集仅有 {len(ix)} 个候选号，少于目标 {k} 个"
        )
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


def _dlt_draw_one_random_valid(
    rng: random.Random,
    hist_keys: set[tuple[tuple[int, ...], tuple[int, ...]]] | None,
    latest_seven: set[int] | None,
    allowed_front: set[int] | None = None,
    allowed_back: set[int] | None = None,
    max_tries: int = 20000,
) -> tuple[list[int], list[int]] | None:
    """均匀随机一注单式，满足分区上限、历史不全重合、与最新期 7 码重合 ≤3。"""
    pool_f = list(allowed_front) if allowed_front is not None else list(range(1, 36))
    pool_b = list(allowed_back) if allowed_back is not None else list(range(1, 13))
    if len(pool_f) < 5 or len(pool_b) < 2:
        return None
    for _ in range(max_tries):
        f = sorted(rng.sample(pool_f, 5))
        b = sorted(rng.sample(pool_b, 2))
        if not _zone_max_cap_ok(f, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE):
            continue
        if not _zone_max_cap_ok(b, DLT_BACK_ZONES_CAP, DLT_BACK_MAX_PER_ZONE):
            continue
        if not _dlt_ticket_passes_history_rules(f, b, hist_keys, latest_seven):
            continue
        return (f, b)
    return None


def _ssq_draw_one_random_valid(
    rng: random.Random,
    hist_keys: set[tuple[tuple[int, ...], int]] | None,
    latest_seven: set[int] | None,
    allowed_red: set[int] | None = None,
    allowed_blue: set[int] | None = None,
    max_tries: int = 20000,
) -> tuple[list[int], int] | None:
    pool_r = list(allowed_red) if allowed_red is not None else list(range(1, 34))
    pool_b = list(allowed_blue) if allowed_blue is not None else list(range(1, 17))
    if len(pool_r) < 6 or len(pool_b) < 1:
        return None
    for _ in range(max_tries):
        reds = sorted(rng.sample(pool_r, 6))
        blue = int(rng.choice(pool_b))
        if not _zone_max_cap_ok(reds, SSQ_RED_ZONES_CAP, SSQ_RED_MAX_PER_ZONE):
            continue
        if not _zone_max_cap_ok([blue], SSQ_BLUE_ZONES_CAP, SSQ_BLUE_MAX_PER_ZONE):
            continue
        if not _ssq_ticket_passes_history_rules(reds, blue, hist_keys, latest_seven):
            continue
        return (reds, blue)
    return None


def _dlt_ticket_passes_history_rules(
    fi: list[int],
    bi: list[int],
    hist_keys: set[tuple[tuple[int, ...], tuple[int, ...]]] | None,
    latest_seven: set[int] | None,
) -> bool:
    """任一单式不得与历史开奖完全一致；与最新一期 7 码（前 5+后 2）集合重合数须 ≤3。"""
    fs, bs = sorted(int(x) for x in fi), sorted(int(x) for x in bi)
    if hist_keys is not None and (tuple(fs), tuple(bs)) in hist_keys:
        return False
    if latest_seven is not None and len(set(fs + bs) & latest_seven) > 3:
        return False
    return True


def _ssq_ticket_passes_history_rules(
    reds: list[int],
    blue: int,
    hist_keys: set[tuple[tuple[int, ...], int]] | None,
    latest_seven: set[int] | None,
) -> bool:
    rs, b = sorted(int(x) for x in reds), int(blue)
    if hist_keys is not None and (tuple(rs), b) in hist_keys:
        return False
    if latest_seven is not None and len((set(rs) | {b}) & latest_seven) > 3:
        return False
    return True


def _dlt_collect_five_unique_tickets(
    fs: np.ndarray,
    bs: np.ndarray,
    n_lines: int = PREDICTION_SINGLE_LINES,
    max_iter: int = TICKET_COLLECT_MAX_ITER,
    penalty0: float = TICKET_COLLECT_PENALTY_INIT,
    hist_keys: set[tuple[tuple[int, ...], tuple[int, ...]]] | None = None,
    latest_seven: set[int] | None = None,
    allowed_front: set[int] | None = None,
    allowed_back: set[int] | None = None,
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
        if latest_seven is not None:
            lp = float(TICKET_COLLECT_LATEST_SCORE_PENALTY)
            for x in latest_seven:
                xi = int(x)
                if 1 <= xi <= 35:
                    fs_adj[xi] -= lp
                if 1 <= xi <= 12:
                    bs_adj[xi] -= lp
        try:
            fi = _pick_top_indices_zone_capped(
                fs_adj,
                1,
                35,
                5,
                DLT_FRONT_ZONES_CAP,
                DLT_FRONT_MAX_PER_ZONE,
                allowed=allowed_front,
            )
            bi = _pick_top_indices_zone_capped(
                bs_adj,
                1,
                12,
                2,
                DLT_BACK_ZONES_CAP,
                DLT_BACK_MAX_PER_ZONE,
                allowed=allowed_back,
            )
        except ValueError:
            penalty *= 0.88
            continue
        key = (tuple(sorted(fi)), tuple(sorted(bi)))
        if key in seen:
            penalty *= 1.14
            continue
        if not _dlt_ticket_passes_history_rules(fi, bi, hist_keys, latest_seven):
            penalty *= 1.07
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
                    fs,
                    1,
                    35,
                    5,
                    DLT_FRONT_ZONES_CAP,
                    DLT_FRONT_MAX_PER_ZONE,
                    rng=rng,
                    allowed=allowed_front,
                )
                bi = _pick_top_indices_zone_capped(
                    bs,
                    1,
                    12,
                    2,
                    DLT_BACK_ZONES_CAP,
                    DLT_BACK_MAX_PER_ZONE,
                    rng=rng,
                    allowed=allowed_back,
                )
            except ValueError:
                continue
            key = (tuple(sorted(fi)), tuple(sorted(bi)))
            if key in seen:
                continue
            if not _dlt_ticket_passes_history_rules(fi, bi, hist_keys, latest_seven):
                continue
            seen.add(key)
            out.append((sorted(fi), sorted(bi)))
            if len(out) >= n_lines:
                break

    if len(out) < n_lines:
        rng_r = random.Random(int(_lottery_config._ACTIVE_RANDOM_SEED) + 91331)
        for _ in range(TICKET_COLLECT_RANDOM_PHASE_MAX):
            if len(out) >= n_lines:
                break
            one = _dlt_draw_one_random_valid(
                rng_r, hist_keys, latest_seven, allowed_front, allowed_back
            )
            if one is None:
                continue
            fi, bi = one
            key = (tuple(fi), tuple(bi))
            if key in seen:
                continue
            seen.add(key)
            out.append((fi, bi))

    if len(out) < n_lines:
        raise ValueError(f"大乐透：无法在尝试内凑满 {n_lines} 组互异单式（已得 {len(out)}）")
    return out[:n_lines]


def _ssq_collect_five_unique_tickets(
    rs: np.ndarray,
    bs: np.ndarray,
    n_lines: int = PREDICTION_SINGLE_LINES,
    max_iter: int = TICKET_COLLECT_MAX_ITER,
    penalty0: float = TICKET_COLLECT_PENALTY_INIT,
    hist_keys: set[tuple[tuple[int, ...], int]] | None = None,
    latest_seven: set[int] | None = None,
    allowed_red: set[int] | None = None,
    allowed_blue: set[int] | None = None,
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
        if latest_seven is not None:
            lp = float(TICKET_COLLECT_LATEST_SCORE_PENALTY)
            for x in latest_seven:
                xi = int(x)
                if 1 <= xi <= 33:
                    rs_adj[xi] -= lp
                if 1 <= xi <= 16:
                    bs_adj[xi] -= lp
        try:
            fi = _pick_top_indices_zone_capped(
                rs_adj,
                1,
                33,
                6,
                SSQ_RED_ZONES_CAP,
                SSQ_RED_MAX_PER_ZONE,
                allowed=allowed_red,
            )
            bi = _pick_top_indices_zone_capped(
                bs_adj,
                1,
                16,
                1,
                SSQ_BLUE_ZONES_CAP,
                SSQ_BLUE_MAX_PER_ZONE,
                allowed=allowed_blue,
            )
        except ValueError:
            penalty *= 0.88
            continue
        bl = int(bi[0])
        key = (tuple(sorted(fi)), bl)
        if key in seen:
            penalty *= 1.14
            continue
        if not _ssq_ticket_passes_history_rules(fi, bl, hist_keys, latest_seven):
            penalty *= 1.07
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
                    rs,
                    1,
                    33,
                    6,
                    SSQ_RED_ZONES_CAP,
                    SSQ_RED_MAX_PER_ZONE,
                    rng=rng,
                    allowed=allowed_red,
                )
                bi = _pick_top_indices_zone_capped(
                    bs,
                    1,
                    16,
                    1,
                    SSQ_BLUE_ZONES_CAP,
                    SSQ_BLUE_MAX_PER_ZONE,
                    rng=rng,
                    allowed=allowed_blue,
                )
            except ValueError:
                continue
            bl = int(bi[0])
            key = (tuple(sorted(fi)), bl)
            if key in seen:
                continue
            if not _ssq_ticket_passes_history_rules(fi, bl, hist_keys, latest_seven):
                continue
            seen.add(key)
            out.append((sorted(fi), bl))
            if len(out) >= n_lines:
                break

    if len(out) < n_lines:
        rng_r = random.Random(int(_lottery_config._ACTIVE_RANDOM_SEED) + 71477)
        for _ in range(TICKET_COLLECT_RANDOM_PHASE_MAX):
            if len(out) >= n_lines:
                break
            one = _ssq_draw_one_random_valid(
                rng_r, hist_keys, latest_seven, allowed_red, allowed_blue
            )
            if one is None:
                continue
            fi, bl = one
            key = (tuple(fi), bl)
            if key in seen:
                continue
            seen.add(key)
            out.append((sorted(fi), bl))

    if len(out) < n_lines:
        raise ValueError(f"双色球：无法在尝试内凑满 {n_lines} 组互异单式（已得 {len(out)}）")
    return out[:n_lines]


# ── 快乐八 20/11 选号 ──────────────────────────────────────────

def _kl8_decadic_zone_totals(draws: list[list[int]]) -> list[int]:
    """窗口内每期 20 码在各十码段上的出现次数之和（每期一球最多计 1 次）。"""
    counts = [0] * len(KL8_PICK_ZONES_CAP)
    for d in draws:
        for x in d:
            xi = int(x)
            zi = _zone_index_for_ball(xi, KL8_PICK_ZONES_CAP)
            counts[zi] += 1
    return counts


def _kl8_active_ball_set(active_zones: list[tuple[int, int]]) -> set[int]:
    s: set[int] = set()
    for lo, hi in active_zones:
        s.update(range(int(lo), int(hi) + 1))
    return s


def _kl8_scores_masked_to_active_zones(
    scores: np.ndarray, active_zones: list[tuple[int, int]]
) -> np.ndarray:
    allow = _kl8_active_ball_set(active_zones)
    out = scores.astype(np.float64).copy()
    for i in range(1, 81):
        if i not in allow:
            out[i] = -1e18
    return out


def _kl8_active_zone_pick_policy_ok(balls: list[int], active_zones: list[tuple[int, int]]) -> bool:
    """未选用的十码段须 0 个；选用的各段在 [KL8_MIN_PER_PICK_ZONE, KL8_MAX_PER_PICK_ZONE]。"""
    active_set = set(active_zones)
    zc = _counts_per_zone_for_balls(balls, KL8_PICK_ZONES_CAP)
    for zi, c in enumerate(zc):
        ztup = KL8_PICK_ZONES_CAP[zi]
        if ztup in active_set:
            if c < KL8_MIN_PER_PICK_ZONE or c > KL8_MAX_PER_PICK_ZONE:
                return False
        elif c != 0:
            return False
    return True


def _kl8_twenty_from_patterns(
    freq: np.ndarray,
    cur_miss: np.ndarray,
    draws: list[list[int]],
    markov_raw: np.ndarray,
    active_zones: list[tuple[int, int]] | None = None,
) -> tuple[list[int], list[tuple[int, int]]]:
    if active_zones is None:
        active_zones = list(KL8_PICK_ZONES_CAP)
    scores = _kl8_twenty_scores(freq, cur_miss, draws, markov_raw)
    scores_use = _kl8_scores_masked_to_active_zones(scores, active_zones)
    ranked = _pick_top_indices_zone_bounded(
        scores_use,
        1,
        80,
        20,
        active_zones,
        KL8_MIN_PER_PICK_ZONE,
        KL8_MAX_PER_PICK_ZONE,
    )
    return sorted(ranked), active_zones


def _kl8_twenty_cap_overlap_latest(
    twenty: list[int],
    latest20: set[int],
    scores: np.ndarray,
    active_zones: list[tuple[int, int]],
    max_overlap: int = 6,
    max_rounds: int = 500,
) -> list[int]:
    """参考 20 码与最新一期真实 20 码重合数压至 ≤ max_overlap（优先去掉重合中综合分最低者并补分最高且满足十码段约束的号）。"""
    cur = sorted(twenty)
    if len(cur) != 20 or len(set(cur)) != 20:
        return cur
    latest_set = set(latest20)
    allowed = _kl8_active_ball_set(active_zones)
    rnd = 0
    while rnd < max_rounds:
        rnd += 1
        s_cur = set(cur)
        inter = s_cur & latest_set
        if len(inter) <= max_overlap:
            return sorted(cur)
        victim = min(inter, key=lambda x: float(scores[int(x)]))
        s_cur.remove(victim)
        candidates = [i for i in range(1, 81) if i not in s_cur and i in allowed]
        candidates.sort(key=lambda i: -float(scores[int(i)]))
        added = False
        for c in candidates:
            trial = sorted(s_cur | {c})
            if _kl8_active_zone_pick_policy_ok(trial, active_zones):
                cur = trial
                added = True
                break
        if not added:
            break
    return sorted(cur)


def _kl8_eleven_from_patterns(
    freq: np.ndarray,
    cur_miss: np.ndarray,
    draws: list[list[int]],
    markov_raw: np.ndarray,
    active_zones: list[tuple[int, int]] | None = None,
) -> tuple[list[int], list[tuple[int, int]]]:
    """直接在活跃十码段并集内贪心取 11 码（跳过 20 码中间层）。"""
    if active_zones is None:
        active_zones = list(KL8_PICK_ZONES_CAP)
    scores = _kl8_twenty_scores(freq, cur_miss, draws, markov_raw)
    scores_use = _kl8_scores_masked_to_active_zones(scores, active_zones)
    ranked = _pick_top_indices_zone_bounded(
        scores_use,
        1,
        80,
        11,
        active_zones,
        KL8_MIN_PER_PICK_ZONE,
        KL8_MAX_PER_PICK_ZONE,
    )
    return sorted(ranked), active_zones


def _kl8_eleven_cap_overlap_latest(
    eleven: list[int],
    latest20: set[int],
    scores: np.ndarray,
    active_zones: list[tuple[int, int]],
    max_overlap: int = KL8_ELEVEN_OVERLAP_MAX,
    max_rounds: int = 500,
) -> list[int]:
    """直选 11 码与最新一期真实 20 码重合数压至 ≤ max_overlap。"""
    cur = sorted(eleven)
    if len(cur) != 11 or len(set(cur)) != 11:
        return cur
    latest_set = set(latest20)
    allowed = _kl8_active_ball_set(active_zones)
    rnd = 0
    while rnd < max_rounds:
        rnd += 1
        s_cur = set(cur)
        inter = s_cur & latest_set
        if len(inter) <= max_overlap:
            return sorted(cur)
        victim = min(inter, key=lambda x: float(scores[int(x)]))
        s_cur.remove(victim)
        candidates = [i for i in range(1, 81) if i not in s_cur and i in allowed]
        candidates.sort(key=lambda i: -float(scores[int(i)]))
        added = False
        for c in candidates:
            trial = sorted(s_cur | {c})
            if _kl8_active_zone_pick_policy_ok(trial, active_zones):
                cur = trial
                added = True
                break
        if not added:
            break
    return sorted(cur)


def _kl8_eleven_zone_capped_from_twenty(
    twenty: list[int], active_zones: list[tuple[int, int]]
) -> list[int]:
    if len(twenty) != 20 or len(set(twenty)) != 20:
        raise ValueError("twenty 须为 20 个互异号码")
    for _ in range(KL8_ELEVEN_RANDOM_TRIES):
        s = random.sample(twenty, 11)
        if _kl8_active_zone_pick_policy_ok(s, active_zones):
            return sorted(s)
    aux_scores = np.zeros(81, dtype=float)
    for rank, x in enumerate(sorted(twenty)):
        aux_scores[int(x)] = float(len(twenty) - rank)
    aux_use = _kl8_scores_masked_to_active_zones(aux_scores, active_zones)
    out = _pick_top_indices_zone_bounded(
        aux_use,
        1,
        80,
        11,
        active_zones,
        KL8_MIN_PER_PICK_ZONE,
        KL8_MAX_PER_PICK_ZONE,
    )
    if len(out) < 11:
        raise ValueError(
            f"20 码在「活跃十码段」每区[{KL8_MIN_PER_PICK_ZONE},{KL8_MAX_PER_PICK_ZONE}]约束下无法凑满11码"
        )
    return sorted(out)


def _kl8_eleven_from_twenty_rerank(
    twenty: list[int],
    scores: np.ndarray,
    active_zones: list[tuple[int, int]],
) -> list[int]:
    """在 20 码候选池内用完整多因子分数贪心重排位取 11 码（优于辅助排名分数）。"""
    if len(twenty) != 20 or len(set(twenty)) != 20:
        raise ValueError("twenty 须为 20 个互异号码")
    sub_scores = np.zeros(81, dtype=float)
    for x in twenty:
        sub_scores[int(x)] = float(scores[int(x)])
    sub_use = _kl8_scores_masked_to_active_zones(sub_scores, active_zones)
    out = _pick_top_indices_zone_bounded(
        sub_use,
        1,
        80,
        11,
        active_zones,
        KL8_MIN_PER_PICK_ZONE,
        KL8_MAX_PER_PICK_ZONE,
    )
    if len(out) < 11:
        raise ValueError(
            f"20 码在「活跃十码段」每区[{KL8_MIN_PER_PICK_ZONE},{KL8_MAX_PER_PICK_ZONE}]约束下无法凑满11码"
        )
    return sorted(out)


def _kl8_eleven_random_from_twenty(
    twenty: list[int], active_zones: list[tuple[int, int]]
) -> list[int]:
    return _kl8_eleven_zone_capped_from_twenty(twenty, active_zones)


def _assert_kl8_zone_bounds(
    nums: list[int], label: str, active_zones: list[tuple[int, int]] | None = None
) -> list[int]:
    zc = _counts_per_zone_for_balls(nums, KL8_PICK_ZONES_CAP)
    if active_zones is None:
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
    if not _kl8_active_zone_pick_policy_ok(nums, active_zones):
        active_set = set(active_zones)
        bad = []
        for zi, c in enumerate(zc, 1):
            lo, hi = KL8_PICK_ZONES_CAP[zi - 1]
            ztup = KL8_PICK_ZONES_CAP[zi - 1]
            if ztup in active_set:
                if c < KL8_MIN_PER_PICK_ZONE or c > KL8_MAX_PER_PICK_ZONE:
                    bad.append(f"active zone{zi}({_fmt2(lo)}-{_fmt2(hi)}):{c}")
            elif c != 0:
                bad.append(f"inactive zone{zi}({_fmt2(lo)}-{_fmt2(hi)}):{c}")
        raise ValueError(
            f"{label} 分区校验失败（仅允许在活跃十码段内出号）：{', '.join(bad)}；全量计数={zc}"
        )
    return zc


# ── 七星彩 5 注单式收集 ─────────────────────────────────────────

def _qxc_collect_five_tickets(
    scores_by_pos: list[np.ndarray],
    n_lines: int = PREDICTION_SINGLE_LINES,
) -> list[list[int]]:
    tickets: list[list[int]] = []
    n_pos = len(scores_by_pos)
    pos_sizes = [len(s) for s in scores_by_pos]
    max_size = max(pos_sizes)
    used_full = np.zeros((n_pos, max_size), dtype=float)
    for _ in range(n_lines):
        ticket: list[int] = []
        for pos in range(n_pos):
            n_digits = pos_sizes[pos]
            adj = scores_by_pos[pos] - 0.08 * used_full[pos, :n_digits]
            digit = int(np.argmax(adj))
            ticket.append(digit)
            used_full[pos, digit] += 1.0
        if ticket in tickets:
            pos = n_pos - 1
            n_digits_last = pos_sizes[pos]
            adj = scores_by_pos[pos] - 0.08 * used_full[pos, :n_digits_last]
            order = list(np.argsort(-adj))
            for d in order:
                cand = ticket[:-1] + [int(d)]
                if cand not in tickets:
                    ticket = cand
                    used_full[pos, int(d)] += 1.0
                    break
        tickets.append(ticket)
    return tickets
