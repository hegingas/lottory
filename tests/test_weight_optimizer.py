"""weight_optimizer 烟雾测试：验证 Dirichlet 采样和目标函数。"""

import numpy as np
import pytest

from lottery.weight_optimizer import (
    _KEYS_4F,
    _KEYS_8F,
    _weights_to_dict,
    objective_dlt_hits,
    objective_dlt_prize,
    sample_dirichlet_4f,
    sample_dirichlet_8f,
)


def test_keys_8f():
    assert len(_KEYS_8F) == 8
    assert "markov" in _KEYS_8F
    assert "miss" in _KEYS_8F


def test_keys_4f():
    assert len(_KEYS_4F) == 4
    assert all(k in ["markov", "miss", "freq", "recency"] for k in _KEYS_4F)


def test_weights_to_dict():
    vec = np.array([0.25, 0.25, 0.25, 0.25])
    d = _weights_to_dict(["a", "b", "c", "d"], vec)
    assert d == {"a": 0.25, "b": 0.25, "c": 0.25, "d": 0.25}
    assert abs(sum(d.values()) - 1.0) < 0.001


def test_sample_dirichlet_8f_shape():
    samples = sample_dirichlet_8f(10)
    assert len(samples) == 10
    for s in samples:
        assert set(s.keys()) == set(_KEYS_8F)
        assert abs(sum(s.values()) - 1.0) < 0.001


def test_sample_dirichlet_4f_shape():
    samples = sample_dirichlet_4f(10)
    assert len(samples) == 10
    for s in samples:
        assert set(s.keys()) == set(_KEYS_4F)
        assert abs(sum(s.values()) - 1.0) < 0.001


def test_sample_dirichlet_reproducible():
    rng = np.random.default_rng(42)
    a = sample_dirichlet_8f(5, rng=rng)
    rng2 = np.random.default_rng(42)
    b = sample_dirichlet_8f(5, rng=rng2)
    for i in range(5):
        for k in _KEYS_8F:
            assert a[i][k] == b[i][k]


def test_objective_dlt_hits():
    summary = {"regular": {"avg_front": 2.5, "avg_back": 0.5}}
    score = objective_dlt_hits(summary)
    assert score == pytest.approx(2.5 * 10 + 0.5)


def test_objective_dlt_hits_no_regular():
    summary = {}
    score = objective_dlt_hits(summary)
    assert score == 0.0


def test_objective_dlt_prize_empty():
    summary = {"regular": {"prize_dist": {}}}
    score = objective_dlt_prize(summary)
    assert score == 0.0


def test_objective_dlt_prize_all_won():
    summary = {"regular": {"prize_dist": {"九等奖": 3, "未中奖": 7}}}
    score = objective_dlt_prize(summary)
    assert score == pytest.approx(3 / 10)
