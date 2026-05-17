"""数据库模块测试（使用临时文件隔离）。"""

import pandas as pd
import pytest

from lottery.db import (
    _CSV_COLUMNS,
    _LOTTERY_META,
    CURRENT_SCHEMA_VERSION,
    get_connection,
    get_draws,
    get_latest_period,
    get_row_count,
    get_schema_version,
    init_db,
    insert_draws,
    verify_db_csv_consistency,
)


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    return str(tmp_path_factory.mktemp("db") / "test.db")


def test_init_db_creates_tables(db_path):
    init_db(db_path)
    with get_connection(db_path) as conn:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r["name"] for r in cur.fetchall()]
        assert "schema_version" in tables
        for _lt, (table, _) in _LOTTERY_META.items():
            assert table in tables, f"table {table} missing"


def test_init_db_idempotent(db_path):
    init_db(db_path)
    init_db(db_path)
    with get_connection(db_path) as conn:
        cur = conn.execute("SELECT COUNT(*) AS n FROM dlt_draws")
        assert cur.fetchone()["n"] == 0


def test_insert_and_get_draws_dlt(db_path):
    rows = [
        {"lottery_type": "dlt", "period_id": 26001, "front_1": 1, "front_2": 5, "front_3": 10, "front_4": 15, "front_5": 20, "back_1": 1, "back_2": 12},
        {"lottery_type": "dlt", "period_id": 26002, "front_1": 2, "front_2": 6, "front_3": 11, "front_4": 16, "front_5": 21, "back_1": 2, "back_2": 11},
    ]
    n = insert_draws("dlt", rows, path=db_path)
    assert n == 2
    df = get_draws("dlt", path=db_path)
    assert len(df) == 2
    assert list(df.columns) == _CSV_COLUMNS["dlt"]
    assert df["period_id"].tolist() == [26001, 26002]


def test_insert_ignore_duplicate(db_path):
    rows = [{"period_id": 26001, "front_1": 1, "front_2": 5, "front_3": 10, "front_4": 15, "front_5": 20, "back_1": 3, "back_2": 9}]
    n = insert_draws("dlt", rows, path=db_path)
    assert n == 0
    assert get_row_count("dlt", path=db_path) == 2


def test_insert_from_dataframe(db_path):
    df_in = pd.DataFrame([{
        "lottery_type": "ssq", "period_id": 2026001,
        "red_1": 1, "red_2": 5, "red_3": 10, "red_4": 15, "red_5": 20, "red_6": 25,
        "blue": 8,
    }])
    n = insert_draws("ssq", df_in, path=db_path)
    assert n == 1
    df_out = get_draws("ssq", path=db_path)
    assert len(df_out) == 1
    assert int(df_out["blue"].iloc[0]) == 8


def test_get_latest_period(db_path):
    assert get_latest_period("dlt", path=db_path) == 26002
    assert get_latest_period("kl8", path=db_path) is None


def test_get_empty_draws(db_path):
    df = get_draws("kl8", path=db_path)
    assert len(df) == 0
    assert list(df.columns) == _CSV_COLUMNS["kl8"]


def test_insert_all_types(db_path):
    samples = {
        "dlt": {"period_id": 26999, "front_1": 1, "front_2": 2, "front_3": 3, "front_4": 4, "front_5": 5, "back_1": 1, "back_2": 2},
        "ssq": {"period_id": 2099999, "red_1": 1, "red_2": 2, "red_3": 3, "red_4": 4, "red_5": 5, "red_6": 6, "blue": 1},
        "kl8": {"period_id": 2099999, **{f"n{i:02d}": i for i in range(1, 21)}},
        "pl5": {"period_id": 99999, "d1": 0, "d2": 1, "d3": 2, "d4": 3, "d5": 4},
        "qxc": {"period_id": 99999, "d1": 0, "d2": 1, "d3": 2, "d4": 3, "d5": 4, "d6": 5, "special": 0},
    }
    for lt, row in samples.items():
        n = insert_draws(lt, [row], path=db_path)
        assert n == 1, f"insert {lt} failed"
        df = get_draws(lt, path=db_path)
        assert list(df.columns) == _CSV_COLUMNS[lt], f"{lt} columns mismatch"


def test_get_row_count(db_path):
    assert get_row_count("dlt", path=db_path) == 3


def test_schema_version(db_path):
    v = get_schema_version(path=db_path)
    assert v == CURRENT_SCHEMA_VERSION


def test_verify_consistency(db_path):
    result = verify_db_csv_consistency(path=db_path)
    assert "all_synced" in result
    assert "dlt" in result


def test_get_connection_commit(db_path):
    with get_connection(db_path) as conn:
        conn.execute("INSERT INTO dlt_draws(lottery_type,period_id,front_1,front_2,front_3,front_4,front_5,back_1,back_2) VALUES('dlt',26199,1,2,3,4,5,1,2)")
    df = get_draws("dlt", path=db_path)
    assert 26199 in df["period_id"].values


def test_get_connection_rollback(db_path):
    try:
        with get_connection(db_path) as conn:
            conn.execute("INSERT INTO dlt_draws(lottery_type,period_id,front_1,front_2,front_3,front_4,front_5,back_1,back_2) VALUES('dlt',26200,1,2,3,4,5,1,2)")
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass
    df = get_draws("dlt", path=db_path)
    assert 26200 not in df["period_id"].values
