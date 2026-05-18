"""区间命中 0/1 → 二进制状态 → 一阶马尔可夫预测下一期活跃区间。

用于大乐透前/后区、双色球红/蓝球、快乐八十码段：每期看各区是否至少出过 1 个球，
按段序组成整数状态 S_t，在全历史上统计 (S_t → S_{t+1})，对末态平滑后取 argmax 得下期掩码，
再按需扩展掩码，使「每区至多 max_per_zone」下仍能取满所需球数。
"""

from __future__ import annotations

from collections import defaultdict

from .config import MARKOV_LAPLACE_ALPHA, _fmt2


def bitmap_zone_hits(balls: list[int], zones: list[tuple[int, int]]) -> int:
    """各区间若至少有一枚球在 [lo,hi] 内则对应 bit 为 1，bit0 对应 zones[0]。"""
    m = 0
    for zi, (lo, hi) in enumerate(zones):
        if any(int(lo) <= int(x) <= int(hi) for x in balls):
            m |= 1 << zi
    return m


def max_pickable_with_mask(mask: int, zones: list[tuple[int, int]], max_per_zone: int) -> int:
    """在掩码为 1 的区间内，每区至多 max_per_zone 个时，至多能取多少个互异号码。"""
    tot = 0
    for zi, (lo, hi) in enumerate(zones):
        if (mask >> zi) & 1:
            w = int(hi) - int(lo) + 1
            tot += min(max_per_zone, w)
    return tot


def expand_mask_until_pickable(
    mask: int,
    zones: list[tuple[int, int]],
    max_per_zone: int,
    need: int,
) -> int:
    """按段序依次并入新区，直到 max_pickable>=need；仍不足则全开。"""
    nz = len(zones)
    m = int(mask) & ((1 << nz) - 1)
    full = (1 << nz) - 1
    guard = 0
    while max_pickable_with_mask(m, zones, max_per_zone) < need and m < full and guard < nz + 2:
        guard += 1
        for zi in range(nz):
            if not ((m >> zi) & 1):
                m |= 1 << zi
                break
    if max_pickable_with_mask(m, zones, max_per_zone) < need:
        return full
    return m


def expand_kl8_decadic_mask(mask: int, zones: list[tuple[int, int]], need: int, max_per_zone: int) -> int:
    """快乐八：至少 4 个活跃十码段且 4×max_per_zone>=need（默认 20、每段至多 5）。"""
    nz = len(zones)
    m = int(mask) & ((1 << nz) - 1)
    full = (1 << nz) - 1
    guard = 0
    while guard < nz + 4:
        pc = bin(m).count("1")
        cap = max_pickable_with_mask(m, zones, max_per_zone)
        if pc >= 4 and cap >= need:
            break
        guard += 1
        added = False
        for zi in range(nz):
            if not ((m >> zi) & 1):
                m |= 1 << zi
                added = True
                break
        if not added:
            break
    if bin(m).count("1") < 4 or max_pickable_with_mask(m, zones, max_per_zone) < need:
        return full
    return m


def mask_to_allowed_balls(mask: int, zones: list[tuple[int, int]]) -> set[int]:
    s: set[int] = set()
    for zi, (lo, hi) in enumerate(zones):
        if (mask >> zi) & 1:
            for x in range(int(lo), int(hi) + 1):
                s.add(x)
    return s


def mask_to_active_zone_ranges(mask: int, zones: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out = [zones[zi] for zi in range(len(zones)) if (mask >> zi) & 1]
    return sorted(out, key=lambda t: t[0])


def valid_mask_set(n_zones: int, max_active: int) -> set[int]:
    """返回活跃段数 ≤ max_active 的所有掩码集合（排除全零）。"""
    valid: set[int] = set()
    for m in range(1, 1 << n_zones):
        if m.bit_count() <= max_active:
            valid.add(m)
    return valid


def markov_next_bitmap(
    draws_balls: list[list[int]],
    zones: list[tuple[int, int]],
    laplace: float | None = None,
    valid_set: set[int] | None = None,
) -> tuple[int, int, float, int, bool]:
    """全历史相邻期区间命中图的一阶马尔可夫 + 拉普拉斯平滑，预测下一期掩码。

    若提供 valid_set，Laplace 平滑仅在这些数学上可能的掩码内分配概率质量。

    Returns:
        s_last, s_pred, p_pred, row_total_from_s_last, short_history_fallback
    """
    alpha = float(MARKOV_LAPLACE_ALPHA if laplace is None else laplace)
    nz = len(zones)
    n_states = 1 << nz
    if len(draws_balls) < 2:
        return 0, n_states - 1, 1.0, 0, True

    trans: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for t in range(len(draws_balls) - 1):
        a = bitmap_zone_hits(draws_balls[t], zones)
        b = bitmap_zone_hits(draws_balls[t + 1], zones)
        trans[a][b] += 1

    s_last = bitmap_zone_hits(draws_balls[-1], zones)
    row = trans[s_last]
    row_total = int(sum(row.values()))

    candidates = valid_set if valid_set is not None else set(range(n_states))
    n_valid = len(candidates)
    best_s = 0
    best_p = -1.0
    for s2 in candidates:
        c = int(row.get(s2, 0))
        p = (c + alpha) / (row_total + alpha * n_valid)
        if best_p < 0 or p > best_p + 1e-18:
            best_p = p
            best_s = s2
        elif abs(p - best_p) <= 1e-18 and s2 < best_s:
            best_s = s2
    return s_last, best_s, float(best_p), row_total, False


def format_mask_zones(mask: int, zones: list[tuple[int, int]]) -> str:
    """人类可读：列出掩码为 1 的区间。"""
    parts: list[str] = []
    for zi, (lo, hi) in enumerate(zones):
        if (mask >> zi) & 1:
            parts.append(f"`{_fmt2(lo)}–{_fmt2(hi)}`")
    return "、".join(parts) if parts else "（空）"


def markov_next_bitmap_2nd_order(
    draws_balls: list[list[int]],
    zones: list[tuple[int, int]],
    laplace: float | None = None,
    valid_set: set[int] | None = None,
) -> tuple[int, int, float, int, bool]:
    """全历史相邻期区间命中图的**二阶**马尔可夫 + 拉普拉斯平滑。

    条件为 (S_{t-2}, S_{t-1}) → S_t，使用倒数第二期与最后一期的掩码对。
    若历史不足 3 期或条件从未出现，回退至一阶。

    Returns:
        s_last, s_pred, p_pred, row_total, short_history_fallback
    """
    alpha = float(MARKOV_LAPLACE_ALPHA if laplace is None else laplace)
    nz = len(zones)
    n_states = 1 << nz
    if len(draws_balls) < 3:
        return markov_next_bitmap(draws_balls, zones, laplace, valid_set)

    trans: dict[tuple[int, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for t in range(len(draws_balls) - 2):
        s0 = bitmap_zone_hits(draws_balls[t], zones)
        s1 = bitmap_zone_hits(draws_balls[t + 1], zones)
        s2 = bitmap_zone_hits(draws_balls[t + 2], zones)
        trans[(s0, s1)][s2] += 1

    s_last = bitmap_zone_hits(draws_balls[-1], zones)
    s_prev = bitmap_zone_hits(draws_balls[-2], zones)
    cond = (s_prev, s_last)
    row = trans[cond]
    row_total = int(sum(row.values()))

    if row_total == 0:
        # 二阶条件从未出现，回退一阶
        return markov_next_bitmap(draws_balls, zones, laplace, valid_set)

    candidates = valid_set if valid_set is not None else set(range(n_states))
    n_valid = len(candidates)
    best_s = 0
    best_p = -1.0
    for s2 in candidates:
        c = int(row.get(s2, 0))
        p = (c + alpha) / (row_total + alpha * n_valid)
        if best_p < 0 or p > best_p + 1e-18:
            best_p = p
            best_s = s2
        elif abs(p - best_p) <= 1e-18 and s2 < best_s:
            best_s = s2
    return s_last, best_s, float(best_p), row_total, False


def markov_next_bitmap_blended(
    draws_balls: list[list[int]],
    zones: list[tuple[int, int]],
    w1: float = 0.4,
    w2: float = 0.6,
    laplace: float | None = None,
    valid_set: set[int] | None = None,
) -> tuple[int, int, float, float, int, int, bool]:
    """一阶 + 二阶混合预测：对各候选状态的概率分布加权平均后取 argmax。

    一阶权重 w1（默认 0.4），二阶权重 w2（默认 0.6），与按号马尔可夫方法论对齐。
    二阶不可用时自动退化为纯一阶（w1=1.0, w2=0.0）。

    Returns:
        s_last, s_pred, p_pred, p_1st_of_pred, row_total_1st, row_total_2nd, short_fb
    """
    alpha = float(MARKOV_LAPLACE_ALPHA if laplace is None else laplace)
    nz = len(zones)
    n_states = 1 << nz

    # 一阶分布
    s_last_1, _, _, row_1st, short_fb = markov_next_bitmap(
        draws_balls, zones, laplace, valid_set
    )
    p1 = _markov_prob_dist(draws_balls, zones, alpha, valid_set, order=1)

    # 二阶分布（不可用时用一阶替代）
    p2 = _markov_prob_dist(draws_balls, zones, alpha, valid_set, order=2)
    if p2 is None:
        # 二阶不可用，纯一阶
        assert p1 is not None
        _s_pred, _p_pred = s_last_1, 0.0
        candidates = valid_set if valid_set is not None else set(range(n_states))
        best_s = 0
        best_p = -1.0
        for s2 in candidates:
            p = p1.get(s2, 0.0)
            if best_p < 0 or p > best_p + 1e-18:
                best_p = p
                best_s = s2
        return s_last_1, best_s, float(best_p), p1.get(best_s, 0.0), row_1st, 0, short_fb

    # 混合
    assert p1 is not None
    candidates = valid_set if valid_set is not None else set(range(n_states))
    best_s = 0
    best_p = -1.0
    best_p1 = 0.0
    for s2 in candidates:
        p = w1 * p1.get(s2, 0.0) + w2 * p2.get(s2, 0.0)
        if best_p < 0 or p > best_p + 1e-18:
            best_p = p
            best_s = s2
            best_p1 = p1.get(s2, 0.0)
        elif abs(p - best_p) <= 1e-18 and s2 < best_s:
            best_s = s2
            best_p1 = p1.get(s2, 0.0)

    # 二阶行总数
    if len(draws_balls) >= 3:
        trans2: dict[tuple[int, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for t in range(len(draws_balls) - 2):
            s0 = bitmap_zone_hits(draws_balls[t], zones)
            s1 = bitmap_zone_hits(draws_balls[t + 1], zones)
            s2_ = bitmap_zone_hits(draws_balls[t + 2], zones)
            trans2[(s0, s1)][s2_] += 1
        s_l = bitmap_zone_hits(draws_balls[-1], zones)
        s_p = bitmap_zone_hits(draws_balls[-2], zones)
        row_2nd = int(sum(trans2.get((s_p, s_l), {}).values()))
    else:
        row_2nd = 0

    return s_last_1, best_s, float(best_p), float(best_p1), row_1st, row_2nd, short_fb


def _markov_prob_dist(
    draws_balls: list[list[int]],
    zones: list[tuple[int, int]],
    alpha: float,
    valid_set: set[int] | None = None,
    order: int = 1,
) -> dict[int, float] | None:
    """计算末态条件下各候选状态的平滑概率分布（一阶或二阶）。二阶不可用返回 None。"""
    nz = len(zones)
    n_states = 1 << nz
    candidates = valid_set if valid_set is not None else set(range(n_states))
    n_valid = len(candidates)

    if order == 1:
        if len(draws_balls) < 2:
            return None
        trans: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for t in range(len(draws_balls) - 1):
            a = bitmap_zone_hits(draws_balls[t], zones)
            b = bitmap_zone_hits(draws_balls[t + 1], zones)
            trans[a][b] += 1
        s_last = bitmap_zone_hits(draws_balls[-1], zones)
        row = trans[s_last]
        row_total = int(sum(row.values()))
        dist: dict[int, float] = {}
        for s2 in candidates:
            c = int(row.get(s2, 0))
            dist[s2] = (c + alpha) / (row_total + alpha * n_valid)
        return dist

    # 二阶
    if len(draws_balls) < 3:
        return None
    trans2: dict[tuple[int, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for t in range(len(draws_balls) - 2):
        s0 = bitmap_zone_hits(draws_balls[t], zones)
        s1 = bitmap_zone_hits(draws_balls[t + 1], zones)
        s2_ = bitmap_zone_hits(draws_balls[t + 2], zones)
        trans2[(s0, s1)][s2_] += 1
    s_last = bitmap_zone_hits(draws_balls[-1], zones)
    s_prev = bitmap_zone_hits(draws_balls[-2], zones)
    row = trans2.get((s_prev, s_last), {})
    row_total = int(sum(row.values()))
    if row_total == 0:
        return None
    dist = {}
    for s2 in candidates:
        c = int(row.get(s2, 0))
        dist[s2] = (c + alpha) / (row_total + alpha * n_valid)
    return dist
