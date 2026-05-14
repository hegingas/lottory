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


def markov_next_bitmap(
    draws_balls: list[list[int]],
    zones: list[tuple[int, int]],
    laplace: float | None = None,
) -> tuple[int, int, float, int, bool]:
    """全历史相邻期区间命中图的一阶马尔可夫 + 拉普拉斯平滑，预测下一期掩码。

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

    best_s = 0
    best_p = -1.0
    for s2 in range(n_states):
        c = int(row.get(s2, 0))
        p = (c + alpha) / (row_total + alpha * n_states)
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
