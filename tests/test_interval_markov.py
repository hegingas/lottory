"""interval_markov：区间命中掩码与展开逻辑。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lottery.config import DLT_FRONT_MAX_PER_ZONE, DLT_FRONT_ZONES_CAP, KL8_PICK_ZONES_CAP
from lottery.interval_markov import (
    bitmap_zone_hits,
    expand_kl8_decadic_mask,
    expand_mask_until_pickable,
    markov_next_bitmap,
    mask_to_allowed_balls,
    max_pickable_with_mask,
)


def test_bitmap_zone_hits():
    balls = [1, 7, 18]
    m = bitmap_zone_hits(balls, DLT_FRONT_ZONES_CAP)
    assert m & 1
    assert m & (1 << 1)
    assert m & (1 << 3)


def test_expand_mask_until_pickable_dlt_front():
    mask = 1
    m2 = expand_mask_until_pickable(mask, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE, 5)
    assert max_pickable_with_mask(m2, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE) >= 5


def test_markov_short_history_fallback():
    draws = [[1, 2, 3, 4, 5]]
    s_last, s_pred, p, row, fb = markov_next_bitmap(draws, DLT_FRONT_ZONES_CAP)
    assert fb is True
    assert p == 1.0
    assert row == 0


def test_kl8_expand_satisfies_twenty_and_four_zones():
    m = expand_kl8_decadic_mask(0, KL8_PICK_ZONES_CAP, 20, 5)
    assert bin(m).count("1") >= 4
    assert max_pickable_with_mask(m, KL8_PICK_ZONES_CAP, 5) >= 20
    s = mask_to_allowed_balls(m, KL8_PICK_ZONES_CAP)
    assert len(s) >= 20


def test_expand_kl8_truncates_high_bits():
    m = expand_kl8_decadic_mask(1 << 20, KL8_PICK_ZONES_CAP, 20, 5)
    assert 0 <= m <= (1 << len(KL8_PICK_ZONES_CAP)) - 1
