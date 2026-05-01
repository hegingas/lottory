"""测试 validate 模块数据校验函数。"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lottery.validate import validate_dlt, validate_ssq, validate_kl8, validate_pl5


def _make_dlt_df(rows):
    return pd.DataFrame(rows, columns=["lottery_type", "period_id", "front_1", "front_2", "front_3", "front_4", "front_5", "back_1", "back_2"])


def _make_ssq_df(rows):
    return pd.DataFrame(rows, columns=["lottery_type", "period_id", "red_1", "red_2", "red_3", "red_4", "red_5", "red_6", "blue"])


def _make_kl8_df(rows):
    cols = ["lottery_type", "period_id"] + [f"n{i:02d}" for i in range(1, 21)]
    return pd.DataFrame(rows, columns=cols)


def test_validate_dlt_valid():
    df = _make_dlt_df([["dlt", 26001, 1, 5, 10, 15, 20, 1, 12]])
    errs = validate_dlt(df)
    assert not errs


def test_validate_dlt_duplicate_front():
    df = _make_dlt_df([["dlt", 26001, 1, 1, 10, 15, 20, 1, 12]])
    errs = validate_dlt(df)
    assert any("重复" in e for e in errs)


def test_validate_dlt_out_of_range():
    df = _make_dlt_df([["dlt", 26001, 1, 5, 10, 15, 99, 1, 12]])
    errs = validate_dlt(df)
    assert any("越界" in e for e in errs)


def test_validate_dlt_wrong_type():
    df = _make_dlt_df([["ssq", 26001, 1, 5, 10, 15, 20, 1, 12]])
    errs = validate_dlt(df)
    assert any("lottery_type" in e for e in errs)


def test_validate_ssq_valid():
    df = _make_ssq_df([["ssq", 2026001, 1, 5, 10, 15, 20, 25, 5]])
    errs = validate_ssq(df)
    assert not errs


def test_validate_ssq_blue_out_of_range():
    df = _make_ssq_df([["ssq", 2026001, 1, 5, 10, 15, 20, 25, 99]])
    errs = validate_ssq(df)
    assert any("蓝球越界" in e for e in errs)


def test_validate_kl8_valid():
    row = ["kl8", 2026100] + list(range(1, 21))
    df = _make_kl8_df([row])
    errs = validate_kl8(df)
    assert not errs


def test_validate_kl8_not_sorted():
    row = ["kl8", 2026100] + [20, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    df = _make_kl8_df([row])
    errs = validate_kl8(df)
    assert any("升序" in e for e in errs)


def test_validate_kl8_duplicate():
    row = ["kl8", 2026100] + [1] * 20
    df = _make_kl8_df([row])
    errs = validate_kl8(df)
    assert any("重复" in e for e in errs)


def _make_pl5_df(rows):
    return pd.DataFrame(rows, columns=["lottery_type", "period_id", "d1", "d2", "d3", "d4", "d5"])


def test_validate_pl5_valid():
    df = _make_pl5_df([["pl5", 26101, 3, 4, 5, 6, 7]])
    errs = validate_pl5(df)
    assert not errs


def test_validate_pl5_valid_with_repeats():
    df = _make_pl5_df([["pl5", 26101, 0, 0, 5, 5, 9]])
    errs = validate_pl5(df)
    assert not errs


def test_validate_pl5_out_of_range():
    df = _make_pl5_df([["pl5", 26101, 3, 4, 5, 6, 10]])
    errs = validate_pl5(df)
    assert any("越界" in e for e in errs)


def test_validate_pl5_wrong_type():
    df = _make_pl5_df([["dlt", 26101, 3, 4, 5, 6, 7]])
    errs = validate_pl5(df)
    assert any("lottery_type" in e for e in errs)
