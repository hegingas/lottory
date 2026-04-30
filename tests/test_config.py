"""测试 config 模块常量一致性。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lottery.config import (
    PATTERN_W_MISS,
    PATTERN_W_FREQ,
    PATTERN_W_ZONE,
    PATTERN_W_RECENCY,
    PATTERN_W_PARITY,
    PATTERN_W_SIZE,
    PATTERN_W_SUM,
    PATTERN_W_MARKOV,
    DEFAULT_COMBO_BUDGET_MIN_YUAN,
    DEFAULT_COMBO_BUDGET_MAX_YUAN,
    DLT_FRONT_ZONES_CAP,
    DLT_BACK_ZONES_CAP,
    SSQ_RED_ZONES_CAP,
    SSQ_BLUE_ZONES_CAP,
    KL8_PICK_ZONES_CAP,
    DLT_FRONT_MAX_PER_ZONE,
    DLT_BACK_MAX_PER_ZONE,
    SSQ_RED_MAX_PER_ZONE,
    SSQ_BLUE_MAX_PER_ZONE,
    KL8_MIN_PER_PICK_ZONE,
    KL8_MAX_PER_PICK_ZONE,
    DEFAULT_STATS_WINDOW,
    PATTERN_RECENT_K,
)


def test_weights_sum_to_one():
    total = (
        PATTERN_W_MISS
        + PATTERN_W_FREQ
        + PATTERN_W_ZONE
        + PATTERN_W_RECENCY
        + PATTERN_W_PARITY
        + PATTERN_W_SIZE
        + PATTERN_W_SUM
        + PATTERN_W_MARKOV
    )
    assert abs(total - 1.0) < 1e-9, f"权重之和应为 1.0，实际 {total}"


def test_budget_constants():
    assert DEFAULT_COMBO_BUDGET_MIN_YUAN <= DEFAULT_COMBO_BUDGET_MAX_YUAN
    assert DEFAULT_COMBO_BUDGET_MIN_YUAN >= 0


def test_dlt_front_zones_cover_all():
    covered = set()
    for lo, hi in DLT_FRONT_ZONES_CAP:
        for i in range(lo, hi + 1):
            covered.add(i)
    assert covered == set(range(1, 36)), f"DLT 前区分区应覆盖 1-35，实际缺 {set(range(1, 36)) - covered}"


def test_dlt_back_zones_cover_all():
    covered = set()
    for lo, hi in DLT_BACK_ZONES_CAP:
        for i in range(lo, hi + 1):
            covered.add(i)
    assert covered == set(range(1, 13)), f"DLT 后区分区应覆盖 1-12"


def test_ssq_red_zones_cover_all():
    covered = set()
    for lo, hi in SSQ_RED_ZONES_CAP:
        for i in range(lo, hi + 1):
            covered.add(i)
    assert covered == set(range(1, 34)), f"SSQ 红球分区应覆盖 1-33"


def test_ssq_blue_zones_cover_all():
    covered = set()
    for lo, hi in SSQ_BLUE_ZONES_CAP:
        for i in range(lo, hi + 1):
            covered.add(i)
    assert covered == set(range(1, 17)), f"SSQ 蓝球分区应覆盖 1-16"


def test_kl8_zones_cover_all():
    covered = set()
    for lo, hi in KL8_PICK_ZONES_CAP:
        for i in range(lo, hi + 1):
            covered.add(i)
    assert covered == set(range(1, 81)), f"KL8 分区应覆盖 1-80"


def test_zone_caps_positive():
    assert DLT_FRONT_MAX_PER_ZONE > 0
    assert DLT_BACK_MAX_PER_ZONE > 0
    assert SSQ_RED_MAX_PER_ZONE > 0
    assert SSQ_BLUE_MAX_PER_ZONE > 0
    assert KL8_MIN_PER_PICK_ZONE >= 0
    assert KL8_MAX_PER_PICK_ZONE >= KL8_MIN_PER_PICK_ZONE


def test_window_constants():
    assert DEFAULT_STATS_WINDOW > 0
    assert PATTERN_RECENT_K > 0
    assert PATTERN_RECENT_K <= DEFAULT_STATS_WINDOW
