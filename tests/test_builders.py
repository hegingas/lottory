"""builders 包烟雾测试：验证所有核心函数可正常执行并返回预期结构。"""

import pytest

from lottery.builders import (
    build_dlt_analysis,
    build_kl8_analysis,
    build_pl5_analysis,
    build_qxc_analysis,
    build_ssq_analysis,
    prediction_block_dlt,
    prediction_block_kl8,
    prediction_block_pl5,
    prediction_block_qxc,
    prediction_block_ssq,
)
from lottery.db import get_draws


@pytest.fixture(scope="module")
def dlt_df():
    return get_draws("dlt")


@pytest.fixture(scope="module")
def ssq_df():
    return get_draws("ssq")


@pytest.fixture(scope="module")
def kl8_df():
    return get_draws("kl8")


@pytest.fixture(scope="module")
def pl5_df():
    return get_draws("pl5")


@pytest.fixture(scope="module")
def qxc_df():
    return get_draws("qxc")


# ── 分析函数 ──────────────────────────────────────────────────


def test_build_dlt_analysis(dlt_df):
    result = build_dlt_analysis(dlt_df, manifest_excluded=[], analysis_window=30)
    assert isinstance(result, str)
    assert "大乐透" in result


def test_build_ssq_analysis(ssq_df):
    result = build_ssq_analysis(ssq_df, analysis_window=30)
    assert isinstance(result, str)
    assert "双色球" in result


def test_build_kl8_analysis(kl8_df):
    result = build_kl8_analysis(kl8_df, analysis_window=30)
    assert isinstance(result, str)
    assert "快乐八" in result


def test_build_pl5_analysis(pl5_df):
    result = build_pl5_analysis(pl5_df, analysis_window=30)
    assert isinstance(result, str)
    assert "排列5" in result


def test_build_qxc_analysis(qxc_df):
    result = build_qxc_analysis(qxc_df, analysis_window=30)
    assert isinstance(result, str)
    assert "七星彩" in result


# ── 预测函数 (返回 tuple[str, dict]) ─────────────────────────


def test_prediction_block_dlt(dlt_df):
    md, data = prediction_block_dlt(dlt_df, n_last=30)
    assert isinstance(md, str)
    assert isinstance(data, dict)
    assert "单式优选" in md


def test_prediction_block_ssq(ssq_df):
    md, data = prediction_block_ssq(ssq_df, n_last=30)
    assert isinstance(md, str)
    assert isinstance(data, dict)
    assert "单式优选" in md


def test_prediction_block_kl8(kl8_df):
    md, data = prediction_block_kl8(kl8_df, n_last=30, path="B")
    assert isinstance(md, str)
    assert isinstance(data, dict)
    assert "选十参考" in md


def test_prediction_block_pl5(pl5_df):
    md, data = prediction_block_pl5(pl5_df, n_last=30)
    assert isinstance(md, str)
    assert isinstance(data, dict)


def test_prediction_block_qxc(qxc_df):
    md, data = prediction_block_qxc(qxc_df, n_last=30)
    assert isinstance(md, str)
    assert isinstance(data, dict)


# ── 自适应窗口 ────────────────────────────────────────────────


def test_prediction_dlt_adaptive_window(dlt_df):
    md, data = prediction_block_dlt(dlt_df)  # n_last=None → adaptive
    assert isinstance(md, str)
    assert isinstance(data, dict)


# ── 快乐八 Path A 兼容 ───────────────────────────────────────


def test_prediction_block_kl8_path_a(kl8_df):
    md, data = prediction_block_kl8(kl8_df, n_last=30, path="A")
    assert isinstance(md, str)
    assert isinstance(data, dict)
    assert "选十参考" in md
