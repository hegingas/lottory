"""测试 scoring 模块核心统计算法。"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lottery.scoring import (
    ac_value,
    freq_miss_from_draws,
    topk,
    _minmax01_ball,
    _markov_next_probabilities,
    _dlt_front_scores,
    _dlt_back_scores,
    _ssq_red_scores,
    _ssq_blue_scores,
)


def test_ac_value_basic():
    assert ac_value([1, 2, 3, 4, 5]) == 0  # 全连续，D=4, AC=4-(5-1)=0
    assert ac_value([1, 3, 5, 7, 9]) == 0  # 等差2，D=4, AC=4-(5-1)=0
    assert ac_value([1, 10, 20, 30, 35]) == 5  # 分散：D=9, AC=9-(5-1)=5


def test_freq_miss_from_draws_empty():
    freq, cur, avg = freq_miss_from_draws([], [], 10)
    assert freq.sum() == 0
    assert (cur == 0).all()


def test_freq_miss_from_draws_basic():
    draws = [[1, 2, 3], [2, 3, 4]]
    freq, cur, _ = freq_miss_from_draws(draws, [], 5)
    assert freq[1] == 1
    assert freq[2] == 2
    assert freq[3] == 2
    assert freq[4] == 1
    assert freq[5] == 0
    assert cur[1] == 1  # 第0期出现后第1期没出现，current miss = 2-1-0 = 1
    assert cur[2] == 0  # 第1期出现
    assert cur[4] == 0  # 第1期出现


def test_topk_high():
    freq = np.zeros(11, dtype=int)
    freq[1] = 5
    freq[2] = 3
    freq[3] = 1
    top = topk(freq, 2, high=True)
    assert top[0] == (1, 5)
    assert top[1] == (2, 3)


def test_topk_low():
    freq = np.zeros(11, dtype=int)
    freq[1] = 5
    freq[2] = 3
    freq[3] = 1
    top = topk(freq, 2, high=False)
    assert top[0][1] <= top[1][1]


def test_minmax01_ball_uniform():
    raw = np.zeros(6, dtype=float)
    raw[1] = raw[2] = raw[3] = raw[4] = raw[5] = 1.0
    out = _minmax01_ball(raw, 5)
    assert abs(out[1] - 0.5) < 1e-9


def test_minmax01_ball_range():
    raw = np.zeros(6, dtype=float)
    raw[1] = 0.0
    raw[2] = 10.0
    raw[3] = 5.0
    out = _minmax01_ball(raw, 5)
    assert abs(out[1] - 0.0) < 1e-9
    assert abs(out[2] - 1.0) < 1e-9
    assert abs(out[3] - 0.5) < 1e-9


def test_markov_empty():
    out = _markov_next_probabilities([], 10)
    assert abs(out[1] - 0.5) < 1e-9


def test_markov_single_draw():
    out = _markov_next_probabilities([[1, 2]], 5)
    assert abs(out[1] - 0.5) < 1e-9


def test_markov_probabilities_in_range():
    draws = [[1, 2, 3], [2, 3, 4], [3, 4, 5], [4, 5, 6], [5, 6, 7]]
    out = _markov_next_probabilities(draws, 10)
    for i in range(1, 11):
        assert 0.0 <= out[i] <= 1.0, f"概率 {out[i]} 超出 [0,1]"


def test_dlt_front_scores_shape():
    draws = [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]]
    fq, fcur, _ = freq_miss_from_draws(draws, [], 35)
    mk = _markov_next_probabilities(draws, 35)
    scores = _dlt_front_scores(draws, fq, fcur, mk)
    assert scores.shape == (36,)  # 1-indexed, 0 unused


def test_dlt_back_scores_shape():
    draws = [[1, 2], [3, 4]]
    fq, fcur, _ = freq_miss_from_draws(draws, [], 12)
    mk = _markov_next_probabilities(draws, 12)
    scores = _dlt_back_scores(draws, fq, fcur, mk)
    assert scores.shape == (13,)  # 1-indexed


def test_ssq_red_scores_shape():
    draws = [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]
    fq, fcur, _ = freq_miss_from_draws(draws, [], 33)
    mk = _markov_next_probabilities(draws, 33)
    scores = _ssq_red_scores(draws, fq, fcur, mk)
    assert scores.shape == (34,)


def test_ssq_blue_scores_shape():
    blues = [1, 5, 10]
    bq, bcur, _ = freq_miss_from_draws([[b] for b in blues], [], 16)
    mk = _markov_next_probabilities([[b] for b in blues], 16)
    scores = _ssq_blue_scores(blues, bq, bcur, mk)
    assert scores.shape == (17,)
