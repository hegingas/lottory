"""测试 selection 模块选号算法。"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lottery.selection import (
    _zone_index_for_ball,
    _pick_top_indices_zone_capped,
    _pick_top_indices_zone_bounded,
)
from lottery.config import (
    DLT_FRONT_ZONES_CAP,
    DLT_FRONT_MAX_PER_ZONE,
    KL8_PICK_ZONES_CAP,
    KL8_MIN_PER_PICK_ZONE,
    KL8_MAX_PER_PICK_ZONE,
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
