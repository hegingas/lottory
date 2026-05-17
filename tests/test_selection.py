"""测试 selection 模块选号算法。"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lottery.config import (
    DLT_FRONT_MAX_PER_ZONE,
    DLT_FRONT_ZONES_CAP,
)
from lottery.selection import (
    _kl8_active_zone_pick_policy_ok,
    _kl8_decadic_zone_totals,
    _pick_top_indices_zone_bounded,
    _pick_top_indices_zone_capped,
    _zone_index_for_ball,
)


def test_zone_index_for_ball():
    zones = [(1, 5), (6, 10), (11, 15)]
    assert _zone_index_for_ball(1, zones) == 0
    assert _zone_index_for_ball(5, zones) == 0
    assert _zone_index_for_ball(6, zones) == 1
    assert _zone_index_for_ball(15, zones) == 2


def test_zone_index_out_of_range():
    with pytest.raises(ValueError):
        _zone_index_for_ball(99, [(1, 10)])


def test_zone_capped_basic():
    scores = np.zeros(36, dtype=float)
    for i in range(1, 36):
        scores[i] = float(i)  # Higher = better
    result = _pick_top_indices_zone_capped(
        scores, 1, 35, 5, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE
    )
    assert len(result) == 5
    assert len(set(result)) == 5
    # All should be in range
    assert all(1 <= x <= 35 for x in result)


def test_zone_capped_max_per_zone():
    zones = [(1, 5), (6, 10)]
    scores = np.zeros(11, dtype=float)
    scores[1] = 100
    scores[2] = 90
    scores[3] = 80
    scores[6] = 70
    scores[7] = 60
    result = _pick_top_indices_zone_capped(scores, 1, 10, 3, zones, max_per_zone=2)
    assert len(result) == 3
    z1_count = sum(1 for x in result if 1 <= x <= 5)
    z2_count = sum(1 for x in result if 6 <= x <= 10)
    assert z1_count <= 2
    assert z2_count <= 2


def test_zone_capped_impossible_raises():
    zones = [(1, 3)]
    scores = np.ones(4, dtype=float)
    with pytest.raises(ValueError):
        _pick_top_indices_zone_capped(scores, 1, 3, 3, zones, max_per_zone=1)


def test_zone_bounded_min_per_zone():
    scores = np.ones(21, dtype=float)
    for i in range(1, 21):
        scores[i] = float(i)
    zones = [(1, 10), (11, 20)]
    result = _pick_top_indices_zone_bounded(scores, 1, 20, 5, zones, min_per_zone=1, max_per_zone=4)
    assert len(result) == 5
    z1 = sum(1 for x in result if 1 <= x <= 10)
    z2 = sum(1 for x in result if 11 <= x <= 20)
    assert z1 >= 1
    assert z2 >= 1


def test_zone_bounded_invalid_args_raises():
    with pytest.raises(ValueError):
        _pick_top_indices_zone_bounded(np.zeros(10), 1, 9, 5, [(1, 9)], min_per_zone=2, max_per_zone=1)


def test_zone_bounded_min_too_high():
    zones = [(1, 5), (6, 10)]
    scores = np.ones(11, dtype=float)
    # min=5 * 2 zones = 10 balls required, but k=6
    with pytest.raises(ValueError):
        _pick_top_indices_zone_bounded(scores, 1, 10, 6, zones, min_per_zone=5, max_per_zone=5)


def test_zone_bounded_max_too_low():
    zones = [(1, 5), (6, 10)]
    scores = np.ones(11, dtype=float)
    # max=3 * 2 zones = 6, but k=8
    with pytest.raises(ValueError):
        _pick_top_indices_zone_bounded(scores, 1, 10, 8, zones, min_per_zone=1, max_per_zone=3)


def test_zone_bounded_partial_universe_kl8_style():
    """zones 未覆盖 [i_lo,i_hi] 全区间时，仅在并集内枚举（快乐八活跃十码段）。"""
    scores = np.zeros(81, dtype=float)
    zones = [(1, 10), (11, 20), (21, 30), (31, 40)]
    for i in range(1, 41):
        scores[i] = float(i)
    result = _pick_top_indices_zone_bounded(scores, 1, 80, 20, zones, min_per_zone=1, max_per_zone=5)
    assert len(result) == 20
    assert all(1 <= x <= 40 for x in result)
    z1 = sum(1 for x in result if 1 <= x <= 10)
    z2 = sum(1 for x in result if 11 <= x <= 20)
    z3 = sum(1 for x in result if 21 <= x <= 30)
    z4 = sum(1 for x in result if 31 <= x <= 40)
    assert z1 >= 1 and z2 >= 1 and z3 >= 1 and z4 >= 1
    assert max(z1, z2, z3, z4) <= 5


def test_kl8_decadic_zone_totals_single_draw():
    draws = [list(range(1, 21))]
    t = _kl8_decadic_zone_totals(draws)
    assert t[0] == 10
    assert t[1] == 10
    assert sum(t[2:]) == 0


def test_zone_capped_allowed_too_small_raises():
    scores = np.zeros(36, dtype=float)
    for i in range(1, 36):
        scores[i] = float(i)
    allowed = {1, 2, 3, 4, 5, 6}
    with pytest.raises(ValueError):
        _pick_top_indices_zone_capped(
            scores, 1, 35, 5, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE, allowed=allowed
        )


def test_zone_capped_allowed_subset_ok():
    scores = np.zeros(36, dtype=float)
    for i in range(1, 36):
        scores[i] = float(i)
    allowed = set(range(1, 36))
    result = _pick_top_indices_zone_capped(
        scores, 1, 35, 5, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE, allowed=allowed
    )
    assert len(result) == 5


def test_kl8_active_zone_pick_policy_ok_twenty():
    active = [(1, 10), (11, 20), (21, 30), (31, 40)]
    balls = list(range(1, 6)) + list(range(11, 16)) + list(range(21, 26)) + list(range(31, 36))
    assert len(balls) == 20
    assert _kl8_active_zone_pick_policy_ok(balls, active)
    assert not _kl8_active_zone_pick_policy_ok(balls + [50], active)
