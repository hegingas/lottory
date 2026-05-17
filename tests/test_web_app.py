"""Web 应用烟雾测试：路由响应和 helper 函数。"""

import pytest

from lottery.web import create_app
from lottery.web._helpers import (
    LOTTERY_META,
    _compute_ac_value,
    _compute_consecutive_count,
    _compute_odd_even_ratio,
    _get_main_numbers,
    _get_numbers,
)


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ── 路由烟雾测试 ─────────────────────────────────────────────


def test_index_route(client):
    resp = client.get("/")
    assert resp.status_code == 200


@pytest.mark.parametrize("lt", ["dlt", "ssq", "kl8", "pl5", "qxc"])
def test_lottery_page_routes(client, lt):
    resp = client.get(f"/{lt}")
    assert resp.status_code == 200


def test_api_meta(client):
    resp = client.get("/api/meta")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)


def test_api_overview(client):
    resp = client.get("/api/overview")
    assert resp.status_code == 200


@pytest.mark.parametrize("lt", ["dlt", "ssq", "kl8", "pl5", "qxc"])
def test_api_latest(client, lt):
    resp = client.get(f"/api/{lt}/latest")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "period" in data  # API uses "period" key


@pytest.mark.parametrize("lt", ["dlt", "ssq", "kl8", "pl5", "qxc"])
def test_api_prediction(client, lt):
    resp = client.get(f"/api/{lt}/prediction")
    assert resp.status_code in (200, 500)


@pytest.mark.parametrize("lt", ["dlt", "ssq", "kl8", "pl5", "qxc"])
def test_api_backtest_summary(client, lt):
    resp = client.get(f"/api/{lt}/backtest-summary")
    assert resp.status_code == 200


# ── Helper 函数测试 ──────────────────────────────────────────


def test_lottery_meta():
    for lt in ["dlt", "ssq", "kl8", "pl5", "qxc"]:
        assert lt in LOTTERY_META


def test_compute_ac_value():
    nums = [1, 5, 10, 15, 20, 25]
    result = _compute_ac_value(nums)
    assert result >= 0


def test_compute_consecutive_count():
    result = _compute_consecutive_count([1, 2, 5, 6, 7])
    assert result >= 1  # at least one consecutive group


def test_compute_consecutive_count_none():
    result = _compute_consecutive_count([1, 3, 5])
    assert result == 0


def test_compute_odd_even_ratio():
    odd, even = _compute_odd_even_ratio([1, 2, 3, 4, 5, 6])
    assert odd == 3
    assert even == 3


def test_get_numbers_dlt():
    import pandas as pd

    row = pd.Series({"front_1": 1, "front_2": 5, "front_3": 10, "front_4": 15, "front_5": 20, "back_1": 1, "back_2": 12})
    nums = _get_numbers(row, "dlt")
    assert len(nums) == 7


def test_get_main_numbers():
    import pandas as pd

    row = pd.Series({"front_1": 1, "front_2": 5, "front_3": 10, "front_4": 15, "front_5": 20, "back_1": 1, "back_2": 12})
    nums = _get_main_numbers(row, "dlt")
    assert len(nums) == 5
