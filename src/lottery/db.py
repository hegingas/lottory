"""SQLite 数据库层：开奖数据的读优化镜像。

CSV 仍是维护源；本模块提供 DB 优先读取，分析/预测默认走 DB。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from .paths import db_path as _default_db_path
from .paths import processed_dir

CURRENT_SCHEMA_VERSION = 3

# lottery_type -> (table_name, [number_columns])
_LOTTERY_META: dict[str, tuple[str, list[str]]] = {
    "dlt": ("dlt_draws", ["front_1", "front_2", "front_3", "front_4", "front_5", "back_1", "back_2"]),
    "ssq": ("ssq_draws", ["red_1", "red_2", "red_3", "red_4", "red_5", "red_6", "blue"]),
    "kl8": ("kl8_draws", ["n01", "n02", "n03", "n04", "n05", "n06", "n07", "n08", "n09", "n10",
                          "n11", "n12", "n13", "n14", "n15", "n16", "n17", "n18", "n19", "n20"]),
    "pl5": ("pl5_draws", ["d1", "d2", "d3", "d4", "d5"]),
    "qxc": ("qxc_draws", ["d1", "d2", "d3", "d4", "d5", "d6", "special"]),
}

# DataFrame 列序（与 CSV header 完全一致）
_CSV_COLUMNS: dict[str, list[str]] = {
    "dlt": ["lottery_type", "period_id", "front_1", "front_2", "front_3", "front_4", "front_5", "back_1", "back_2"],
    "ssq": ["lottery_type", "period_id", "red_1", "red_2", "red_3", "red_4", "red_5", "red_6", "blue"],
    "kl8": ["lottery_type", "period_id", "n01", "n02", "n03", "n04", "n05", "n06", "n07", "n08", "n09", "n10",
            "n11", "n12", "n13", "n14", "n15", "n16", "n17", "n18", "n19", "n20"],
    "pl5": ["lottery_type", "period_id", "d1", "d2", "d3", "d4", "d5"],
    "qxc": ["lottery_type", "period_id", "d1", "d2", "d3", "d4", "d5", "d6", "special"],
}

_DDL = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);

CREATE TABLE IF NOT EXISTS dlt_draws (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lottery_type TEXT NOT NULL DEFAULT 'dlt',
    period_id    INTEGER NOT NULL UNIQUE,
    front_1      INTEGER NOT NULL CHECK (front_1 BETWEEN 1 AND 35),
    front_2      INTEGER NOT NULL CHECK (front_2 BETWEEN 1 AND 35),
    front_3      INTEGER NOT NULL CHECK (front_3 BETWEEN 1 AND 35),
    front_4      INTEGER NOT NULL CHECK (front_4 BETWEEN 1 AND 35),
    front_5      INTEGER NOT NULL CHECK (front_5 BETWEEN 1 AND 35),
    back_1       INTEGER NOT NULL CHECK (back_1 BETWEEN 1 AND 12),
    back_2       INTEGER NOT NULL CHECK (back_2 BETWEEN 1 AND 12),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dlt_period ON dlt_draws(period_id);

CREATE TABLE IF NOT EXISTS ssq_draws (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lottery_type TEXT NOT NULL DEFAULT 'ssq',
    period_id    INTEGER NOT NULL UNIQUE,
    red_1        INTEGER NOT NULL CHECK (red_1 BETWEEN 1 AND 33),
    red_2        INTEGER NOT NULL CHECK (red_2 BETWEEN 1 AND 33),
    red_3        INTEGER NOT NULL CHECK (red_3 BETWEEN 1 AND 33),
    red_4        INTEGER NOT NULL CHECK (red_4 BETWEEN 1 AND 33),
    red_5        INTEGER NOT NULL CHECK (red_5 BETWEEN 1 AND 33),
    red_6        INTEGER NOT NULL CHECK (red_6 BETWEEN 1 AND 33),
    blue         INTEGER NOT NULL CHECK (blue BETWEEN 1 AND 16),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ssq_period ON ssq_draws(period_id);

CREATE TABLE IF NOT EXISTS kl8_draws (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lottery_type TEXT NOT NULL DEFAULT 'kl8',
    period_id    INTEGER NOT NULL UNIQUE,
    n01 INTEGER NOT NULL CHECK (n01 BETWEEN 1 AND 80),
    n02 INTEGER NOT NULL CHECK (n02 BETWEEN 1 AND 80),
    n03 INTEGER NOT NULL CHECK (n03 BETWEEN 1 AND 80),
    n04 INTEGER NOT NULL CHECK (n04 BETWEEN 1 AND 80),
    n05 INTEGER NOT NULL CHECK (n05 BETWEEN 1 AND 80),
    n06 INTEGER NOT NULL CHECK (n06 BETWEEN 1 AND 80),
    n07 INTEGER NOT NULL CHECK (n07 BETWEEN 1 AND 80),
    n08 INTEGER NOT NULL CHECK (n08 BETWEEN 1 AND 80),
    n09 INTEGER NOT NULL CHECK (n09 BETWEEN 1 AND 80),
    n10 INTEGER NOT NULL CHECK (n10 BETWEEN 1 AND 80),
    n11 INTEGER NOT NULL CHECK (n11 BETWEEN 1 AND 80),
    n12 INTEGER NOT NULL CHECK (n12 BETWEEN 1 AND 80),
    n13 INTEGER NOT NULL CHECK (n13 BETWEEN 1 AND 80),
    n14 INTEGER NOT NULL CHECK (n14 BETWEEN 1 AND 80),
    n15 INTEGER NOT NULL CHECK (n15 BETWEEN 1 AND 80),
    n16 INTEGER NOT NULL CHECK (n16 BETWEEN 1 AND 80),
    n17 INTEGER NOT NULL CHECK (n17 BETWEEN 1 AND 80),
    n18 INTEGER NOT NULL CHECK (n18 BETWEEN 1 AND 80),
    n19 INTEGER NOT NULL CHECK (n19 BETWEEN 1 AND 80),
    n20 INTEGER NOT NULL CHECK (n20 BETWEEN 1 AND 80),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kl8_period ON kl8_draws(period_id);

CREATE TABLE IF NOT EXISTS pl5_draws (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lottery_type TEXT NOT NULL DEFAULT 'pl5',
    period_id    INTEGER NOT NULL UNIQUE,
    d1           INTEGER NOT NULL CHECK (d1 BETWEEN 0 AND 9),
    d2           INTEGER NOT NULL CHECK (d2 BETWEEN 0 AND 9),
    d3           INTEGER NOT NULL CHECK (d3 BETWEEN 0 AND 9),
    d4           INTEGER NOT NULL CHECK (d4 BETWEEN 0 AND 9),
    d5           INTEGER NOT NULL CHECK (d5 BETWEEN 0 AND 9),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pl5_period ON pl5_draws(period_id);

CREATE TABLE IF NOT EXISTS qxc_draws (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lottery_type TEXT NOT NULL DEFAULT 'qxc',
    period_id    INTEGER NOT NULL UNIQUE,
    d1           INTEGER NOT NULL CHECK (d1 BETWEEN 0 AND 9),
    d2           INTEGER NOT NULL CHECK (d2 BETWEEN 0 AND 9),
    d3           INTEGER NOT NULL CHECK (d3 BETWEEN 0 AND 9),
    d4           INTEGER NOT NULL CHECK (d4 BETWEEN 0 AND 9),
    d5           INTEGER NOT NULL CHECK (d5 BETWEEN 0 AND 9),
    d6           INTEGER NOT NULL CHECK (d6 BETWEEN 0 AND 9),
    special      INTEGER NOT NULL CHECK (special BETWEEN 0 AND 14),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_qxc_period ON qxc_draws(period_id);

CREATE TABLE IF NOT EXISTS predictions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    lottery_type        TEXT NOT NULL CHECK (lottery_type IN ('dlt','ssq','kl8','pl5','qxc')),
    predicted_period_id INTEGER NOT NULL,
    ticket_type         TEXT NOT NULL DEFAULT 'regular' CHECK (ticket_type IN ('regular','best')),
    ticket_index        INTEGER NOT NULL DEFAULT 0,
    numbers_json        TEXT NOT NULL,
    total_score         REAL,
    prediction_date     TEXT NOT NULL,
    data_window_start   INTEGER NOT NULL,
    data_window_end     INTEGER NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(lottery_type, predicted_period_id, ticket_type, ticket_index)
);
CREATE INDEX IF NOT EXISTS idx_pred_lt_period ON predictions(lottery_type, predicted_period_id);

CREATE TABLE IF NOT EXISTS backtest_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    lottery_type        TEXT NOT NULL CHECK (lottery_type IN ('dlt','ssq','kl8','pl5','qxc')),
    predicted_period_id INTEGER NOT NULL,
    data_window_start   INTEGER NOT NULL,
    data_window_end     INTEGER NOT NULL,
    ticket_type         TEXT NOT NULL DEFAULT 'regular' CHECK (ticket_type IN ('regular','best')),
    ticket_index        INTEGER NOT NULL DEFAULT 0,
    front_matches       INTEGER,
    back_matches        INTEGER,
    red_matches         INTEGER,
    blue_match          INTEGER,
    overlap_count       INTEGER,
    position_matches    INTEGER,
    all_matched         INTEGER,
    special_match       INTEGER,
    prize_level         TEXT,
    total_score         REAL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(lottery_type, predicted_period_id, ticket_type, ticket_index)
);
CREATE INDEX IF NOT EXISTS idx_bt_lt_period ON backtest_results(lottery_type, predicted_period_id);
"""


@contextmanager
def get_connection(path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    db = str(path) if path is not None else str(_default_db_path())
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: Path | str | None = None) -> None:
    with get_connection(path) as conn:
        conn.executescript(_DDL)
        cur = conn.execute("SELECT MAX(version) FROM schema_version")
        row = cur.fetchone()
        existing = row[0] if row and row[0] is not None else 0
        if existing < CURRENT_SCHEMA_VERSION:
            desc = {
                1: "initial schema: 5 lottery tables + schema_version",
                2: "add predictions table for accuracy tracking",
                3: "add backtest_results table for historical backtesting",
            }.get(CURRENT_SCHEMA_VERSION, f"schema v{CURRENT_SCHEMA_VERSION}")
            conn.execute(
                "INSERT OR REPLACE INTO schema_version(version, description) VALUES(?,?)",
                (CURRENT_SCHEMA_VERSION, desc),
            )


def _table_for(lt: str) -> str:
    return _LOTTERY_META[lt][0]


def _num_cols_for(lt: str) -> list[str]:
    return _LOTTERY_META[lt][1]


# ── CRUD ────────────────────────────────────────────────────────


def insert_draws(
    lottery_type: str,
    draws: list[dict] | pd.DataFrame,
    path: Path | str | None = None,
) -> int:
    table = _table_for(lottery_type)
    cols = _num_cols_for(lottery_type)
    placeholders = ", ".join(["?"] * (len(cols) + 2))
    col_names = ", ".join(["lottery_type", "period_id"] + cols)
    sql = f"INSERT OR IGNORE INTO {table}({col_names}) VALUES({placeholders})"

    if isinstance(draws, pd.DataFrame):
        rows: list[tuple] = []
        for _, row in draws.iterrows():
            lt = str(row.get("lottery_type", lottery_type))
            pid = int(row["period_id"])
            vals = tuple(int(row[c]) for c in cols)
            rows.append((lt, pid, *vals))
    else:
        rows = []
        for d in draws:
            lt = str(d.get("lottery_type", lottery_type))
            pid = int(d["period_id"])
            vals = tuple(int(d[c]) for c in cols)
            rows.append((lt, pid, *vals))

    init_db(path)
    with get_connection(path) as conn:
        cur = conn.executemany(sql, rows)
        return cur.rowcount


def get_draws(
    lottery_type: str,
    path: Path | str | None = None,
) -> pd.DataFrame:
    table = _table_for(lottery_type)
    csv_cols = _CSV_COLUMNS[lottery_type]
    select_cols = ", ".join(csv_cols)
    init_db(path)
    with get_connection(path) as conn:
        cur = conn.execute(f"SELECT {select_cols} FROM {table} ORDER BY period_id")
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=csv_cols)
    return pd.DataFrame([dict(r) for r in rows], columns=csv_cols)


def get_latest_period(
    lottery_type: str,
    path: Path | str | None = None,
) -> int | None:
    table = _table_for(lottery_type)
    init_db(path)
    with get_connection(path) as conn:
        cur = conn.execute(f"SELECT MAX(period_id) FROM {table}")
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else None


def get_row_count(
    lottery_type: str,
    path: Path | str | None = None,
) -> int:
    table = _table_for(lottery_type)
    init_db(path)
    with get_connection(path) as conn:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        row = cur.fetchone()
        return int(row[0]) if row else 0


# ── CSV ↔ DB 同步 ──────────────────────────────────────────────


def _read_csv(lottery_type: str) -> pd.DataFrame:
    proc = processed_dir()
    csv_path = proc / f"{lottery_type}_draws.csv"
    if not csv_path.is_file():
        return pd.DataFrame(columns=_CSV_COLUMNS[lottery_type])
    return pd.read_csv(csv_path, encoding="utf-8-sig")


def migrate_csv_to_db(path: Path | str | None = None) -> dict[str, int]:
    result: dict[str, int] = {}
    for lt in _LOTTERY_META:
        df = _read_csv(lt)
        if len(df) == 0:
            result[lt] = 0
            continue
        result[lt] = insert_draws(lt, df, path=path)
    return result


def sync_csv_to_db(
    lottery_type: str | None = None,
    path: Path | str | None = None,
) -> dict[str, int]:
    types = [lottery_type] if lottery_type else list(_LOTTERY_META)
    result: dict[str, int] = {}
    for lt in types:
        df = _read_csv(lt)
        if len(df) == 0:
            result[lt] = 0
            continue
        db_max = get_latest_period(lt, path=path)
        if db_max is not None:
            df["period_id_num"] = pd.to_numeric(df["period_id"], errors="coerce")
            df = df[df["period_id_num"] > db_max].drop(columns=["period_id_num"])
        if len(df) == 0:
            result[lt] = 0
            continue
        result[lt] = insert_draws(lt, df, path=path)
    return result


def verify_db_csv_consistency(
    lottery_type: str | None = None,
    path: Path | str | None = None,
) -> dict:
    types = [lottery_type] if lottery_type else list(_LOTTERY_META)
    all_synced = True
    result: dict[str, dict] = {}
    for lt in types:
        csv_rows = len(_read_csv(lt))
        db_rows = get_row_count(lt, path=path)
        csv_max = None
        db_max = get_latest_period(lt, path=path)
        df = _read_csv(lt)
        if len(df) > 0:
            csv_max = int(pd.to_numeric(df["period_id"], errors="coerce").max())
        synced = (csv_rows == db_rows and csv_max == db_max)
        if not synced:
            all_synced = False
        result[lt] = {
            "csv_rows": csv_rows,
            "db_rows": db_rows,
            "csv_max_period": csv_max,
            "db_max_period": db_max,
            "synced": synced,
        }
    result["all_synced"] = all_synced
    return result


def get_schema_version(path: Path | str | None = None) -> int:
    init_db(path)
    with get_connection(path) as conn:
        cur = conn.execute("SELECT MAX(version) FROM schema_version")
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0


# ── 预测入库 ────────────────────────────────────────────────────


def save_prediction(
    lottery_type: str,
    predicted_period_id: int,
    ticket_type: str,
    ticket_index: int,
    numbers: dict,
    prediction_date: str,
    data_window_start: int,
    data_window_end: int,
    total_score: float | None = None,
    path: Path | str | None = None,
) -> int:
    """保存一条预测记录，INSERT OR REPLACE。"""
    init_db(path)
    sql = """\
INSERT OR REPLACE INTO predictions(
    lottery_type, predicted_period_id, ticket_type, ticket_index,
    numbers_json, total_score, prediction_date,
    data_window_start, data_window_end
) VALUES(?,?,?,?,?,?,?,?,?)
"""
    with get_connection(path) as conn:
        cur = conn.execute(
            sql,
            (
                lottery_type,
                predicted_period_id,
                ticket_type,
                ticket_index,
                json.dumps(numbers, ensure_ascii=False, separators=(",", ":")),
                total_score,
                prediction_date,
                data_window_start,
                data_window_end,
            ),
        )
        return cur.rowcount


def save_predictions_batch(
    lottery_type: str,
    predicted_period_id: int,
    tickets: list[dict],
    best: dict | None,
    prediction_date: str,
    data_window_start: int,
    data_window_end: int,
    path: Path | str | None = None,
) -> dict[str, int]:
    """批量保存一个期次的全部预测（5 注 regular + 1 注 best）。

    tickets: [{"index": 1, "numbers": {...}}, ...]
    best: {"numbers": {...}, "score": 1.23} | None
    """
    regular_count = 0
    for t in tickets:
        regular_count += save_prediction(
            lottery_type=lottery_type,
            predicted_period_id=predicted_period_id,
            ticket_type="regular",
            ticket_index=t["index"],
            numbers=t["numbers"],
            prediction_date=prediction_date,
            data_window_start=data_window_start,
            data_window_end=data_window_end,
            path=path,
        )
    best_count = 0
    if best is not None:
        best_count = save_prediction(
            lottery_type=lottery_type,
            predicted_period_id=predicted_period_id,
            ticket_type="best",
            ticket_index=0,
            numbers=best["numbers"],
            total_score=best.get("score"),
            prediction_date=prediction_date,
            data_window_start=data_window_start,
            data_window_end=data_window_end,
            path=path,
        )
    return {"regular": regular_count, "best": best_count}


def get_predictions(
    lottery_type: str | None = None,
    predicted_period_id: int | None = None,
    path: Path | str | None = None,
) -> list[dict]:
    """查询已保存的预测。可按彩种和期号过滤。"""
    init_db(path)
    sql = "SELECT * FROM predictions WHERE 1=1"
    params: list = []
    if lottery_type is not None:
        sql += " AND lottery_type = ?"
        params.append(lottery_type)
    if predicted_period_id is not None:
        sql += " AND predicted_period_id = ?"
        params.append(predicted_period_id)
    sql += " ORDER BY lottery_type, predicted_period_id, ticket_type, ticket_index"
    with get_connection(path) as conn:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
    result: list[dict] = []
    for r in rows:
        d = dict(r)
        d["numbers"] = json.loads(d.pop("numbers_json"))
        result.append(d)
    return result


# ── 准确率计算 ──────────────────────────────────────────────────


def _dlt_prize(front_matches: int, back_matches: int) -> str:
    if front_matches == 5 and back_matches == 2:
        return "一等奖"
    if front_matches == 5 and back_matches == 1:
        return "二等奖"
    if front_matches == 5 and back_matches == 0:
        return "三等奖"
    if front_matches == 4 and back_matches == 2:
        return "四等奖"
    if front_matches == 4 and back_matches == 1:
        return "五等奖"
    if front_matches == 3 and back_matches == 2:
        return "六等奖"
    if front_matches == 4 and back_matches == 0:
        return "七等奖"
    if (front_matches == 3 and back_matches == 1) or (front_matches == 2 and back_matches == 2):
        return "八等奖"
    if (front_matches == 3 and back_matches == 0) or (front_matches == 2 and back_matches == 1) or (front_matches == 1 and back_matches == 2) or (front_matches == 0 and back_matches == 2):
        return "九等奖"
    return "未中奖"


def _ssq_prize(red_matches: int, blue_match: int) -> str:
    if red_matches == 6 and blue_match == 1:
        return "一等奖"
    if red_matches == 6 and blue_match == 0:
        return "二等奖"
    if red_matches == 5 and blue_match == 1:
        return "三等奖"
    if (red_matches == 5 and blue_match == 0) or (red_matches == 4 and blue_match == 1):
        return "四等奖"
    if (red_matches == 4 and blue_match == 0) or (red_matches == 3 and blue_match == 1):
        return "五等奖"
    if (red_matches == 2 and blue_match == 1) or (red_matches == 1 and blue_match == 1) or (red_matches == 0 and blue_match == 1):
        return "六等奖"
    return "未中奖"


def compute_accuracy(
    lottery_type: str,
    predicted_period_id: int,
    path: Path | str | None = None,
) -> dict:
    """对比预测 vs 实际开奖，返回准确率结果。"""
    predictions = get_predictions(lottery_type, predicted_period_id, path=path)
    if not predictions:
        return {"error": f"无预测记录: {lottery_type} period {predicted_period_id}"}

    table = _table_for(lottery_type)
    init_db(path)
    with get_connection(path) as conn:
        cur = conn.execute(
            f"SELECT * FROM {table} WHERE period_id = ?", (predicted_period_id,)
        )
        draw_row = cur.fetchone()

    if draw_row is None:
        return {
            "lottery_type": lottery_type,
            "predicted_period_id": predicted_period_id,
            "has_actual_draw": False,
            "message": f"开奖数据尚未入库: {lottery_type} {predicted_period_id}",
            "tickets": [],
            "best": None,
        }

    draw = dict(draw_row)
    tickets_result = []
    best_result = None

    for p in predictions:
        nums = p["numbers"]
        if lottery_type == "dlt":
            front_pred = set(nums["front"])
            back_pred = set(nums["back"])
            front_actual = {draw["front_1"], draw["front_2"], draw["front_3"], draw["front_4"], draw["front_5"]}
            back_actual = {draw["back_1"], draw["back_2"]}
            fm = len(front_pred & front_actual)
            bm = len(back_pred & back_actual)
            entry = {
                "ticket_type": p["ticket_type"],
                "ticket_index": p["ticket_index"],
                "front_matches": fm,
                "back_matches": bm,
                "prize_level": _dlt_prize(fm, bm),
            }
        elif lottery_type == "ssq":
            red_pred = set(nums["red"])
            red_actual = {draw["red_1"], draw["red_2"], draw["red_3"], draw["red_4"], draw["red_5"], draw["red_6"]}
            blue_pred = nums["blue"]
            blue_actual = draw["blue"]
            rm = len(red_pred & red_actual)
            bm = 1 if blue_pred == blue_actual else 0
            entry = {
                "ticket_type": p["ticket_type"],
                "ticket_index": p["ticket_index"],
                "red_matches": rm,
                "blue_match": bm,
                "prize_level": _ssq_prize(rm, bm),
            }
        elif lottery_type == "kl8":
            codes_pred = set(nums["codes"])
            codes_actual = {draw[f"n{i:02d}"] for i in range(1, 21)}
            overlap = len(codes_pred & codes_actual)
            entry = {
                "ticket_type": p["ticket_type"],
                "ticket_index": p["ticket_index"],
                "overlap_count": overlap,
                "overlap_ok": overlap <= 4,
            }
        elif lottery_type == "pl5":
            digits_pred = nums["digits"]
            digits_actual = [draw["d1"], draw["d2"], draw["d3"], draw["d4"], draw["d5"]]
            pos_matches = sum(1 for i in range(5) if digits_pred[i] == digits_actual[i])
            entry = {
                "ticket_type": p["ticket_type"],
                "ticket_index": p["ticket_index"],
                "position_matches": pos_matches,
                "all_matched": pos_matches == 5,
            }
        elif lottery_type == "qxc":
            front_pred = nums["front"]
            front_actual = [draw["d1"], draw["d2"], draw["d3"], draw["d4"], draw["d5"], draw["d6"]]
            special_pred = nums["special"]
            special_actual = draw["special"]
            fm = sum(1 for i in range(6) if front_pred[i] == front_actual[i])
            sm = 1 if special_pred == special_actual else 0
            entry = {
                "ticket_type": p["ticket_type"],
                "ticket_index": p["ticket_index"],
                "front_matches": fm,
                "special_match": sm,
            }
        else:
            entry = {"ticket_type": p["ticket_type"], "ticket_index": p["ticket_index"]}

        if p["ticket_type"] == "best":
            best_result = entry
        else:
            tickets_result.append(entry)

    return {
        "lottery_type": lottery_type,
        "predicted_period_id": predicted_period_id,
        "prediction_date": predictions[0]["prediction_date"] if predictions else None,
        "has_actual_draw": True,
        "tickets": tickets_result,
        "best": best_result,
    }


# ── 历史回测 ──────────────────────────────────────────────────

_lottery_prize = {
    "dlt": _dlt_prize,
    "ssq": _ssq_prize,
}


def save_backtest_result(
    lottery_type: str,
    predicted_period_id: int,
    data_window_start: int,
    data_window_end: int,
    ticket_type: str,
    ticket_index: int,
    match_data: dict,
    total_score: float | None = None,
    path: Path | str | None = None,
) -> int:
    """插入一条回测结果。match_data 来自 compute_accuracy 单条 entry 或 best。"""
    init_db(path)
    sql = """\
INSERT OR REPLACE INTO backtest_results(
    lottery_type, predicted_period_id, data_window_start, data_window_end,
    ticket_type, ticket_index,
    front_matches, back_matches, red_matches, blue_match,
    overlap_count, position_matches, all_matched, special_match,
    prize_level, total_score
) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""
    params = [
        lottery_type,
        predicted_period_id,
        data_window_start,
        data_window_end,
        ticket_type,
        ticket_index,
        match_data.get("front_matches"),
        match_data.get("back_matches"),
        match_data.get("red_matches"),
        match_data.get("blue_match"),
        match_data.get("overlap_count"),
        match_data.get("position_matches"),
        1 if match_data.get("all_matched") else None,
        match_data.get("special_match"),
        match_data.get("prize_level"),
        total_score,
    ]
    with get_connection(path) as conn:
        cur = conn.execute(sql, params)
        return cur.rowcount


def get_backtest_results(
    lottery_type: str | None = None,
    path: Path | str | None = None,
) -> list[dict]:
    """查询回测结果。"""
    init_db(path)
    sql = "SELECT * FROM backtest_results WHERE 1=1"
    params: list = []
    if lottery_type is not None:
        sql += " AND lottery_type = ?"
        params.append(lottery_type)
    sql += " ORDER BY lottery_type, predicted_period_id, ticket_type, ticket_index"
    with get_connection(path) as conn:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def run_backtest(
    lottery_type: str,
    periods: int = 100,
    window: int = 30,
    path: Path | str | None = None,
    progress_callback=None,
    weights: dict[str, float] | None = None,
    whiten: bool | None = None,
    kl8_path: str = "B",
) -> dict:
    """滑动窗口历史回测。

    Args:
        lottery_type: 彩种 (dlt/ssq/kl8/pl5/qxc)
        periods: 回测期数
        window: 预测窗口大小（默认 30）
        path: DB 路径
        progress_callback: 可选回调 f(current, total, period_id)
        kl8_path: 快乐八选号路径 "A"（直接11码）或 "B"（20→11重排位），默认 "B"

    Returns:
        {"ok": True, "summary": {...}, "total": N}
    """
    from .builders import (
        prediction_block_dlt,
        prediction_block_kl8,
        prediction_block_pl5,
        prediction_block_qxc,
        prediction_block_ssq,
    )

    builders = {
        "dlt": prediction_block_dlt,
        "ssq": prediction_block_ssq,
        "kl8": prediction_block_kl8,
        "pl5": prediction_block_pl5,
        "qxc": prediction_block_qxc,
    }
    builder = builders.get(lottery_type)
    if builder is None:
        return {"ok": False, "error": f"不支持的彩种: {lottery_type}"}

    init_db(path)

    # 读取全量数据
    df = get_draws(lottery_type, path=path)
    if df.empty:
        return {"ok": False, "error": "无开奖数据"}
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    df = df.sort_values("period_id").reset_index(drop=True)
    all_pids = df["period_id"].tolist()

    min_data_needed = window + 1  # 至少需要 window 期来预测，且目标期本身存在
    if len(all_pids) < min_data_needed:
        return {"ok": False, "error": f"数据不足（需至少 {min_data_needed} 期，当前 {len(all_pids)} 期）"}

    # 回测范围：从末尾向前 periods 期
    test_count = min(periods, len(all_pids) - window)
    if test_count <= 0:
        return {"ok": False, "error": "回测范围为空"}

    start_idx = len(all_pids) - test_count
    # 清除该彩种旧回测结果
    with get_connection(path) as conn:
        conn.execute("DELETE FROM backtest_results WHERE lottery_type = ?", (lottery_type,))
        conn.commit()

    saved_total = 0
    all_regular_entries: list[dict] = []
    all_best_entries: list[dict] = []
    twenty_hits: list[int] = []  # KL8 Path B 20码命中数

    from .config import DEFAULT_RANDOM_SEED, _set_random_seed

    for i in range(start_idx, len(all_pids)):
        target_pid = int(all_pids[i])
        window_end_idx = i - 1
        window_start_idx = max(0, window_end_idx - window + 1)

        # 取窗口数据
        win_df = df.iloc[window_start_idx : window_end_idx + 1].copy()
        win_pids = win_df["period_id"].tolist()
        if len(win_pids) < window:
            continue
        w_start = int(min(win_pids))
        w_end = int(max(win_pids))

        # 用固定种子保证每次独立可复现（基于目标期号）
        _set_random_seed(int(DEFAULT_RANDOM_SEED) + target_pid)

        try:
            kwargs = {"n_last": window}
            if weights is not None:
                kwargs["weights"] = weights
            if whiten is not None:
                kwargs["whiten"] = whiten
            if lottery_type == "kl8":
                kwargs["path"] = kl8_path
            _md, pred_data = builder(win_df, **kwargs)
        except Exception:
            continue

        # 对比实际开奖
        target_row = df[df["period_id"] == target_pid]
        if target_row.empty:
            continue
        target = target_row.iloc[0].to_dict()

        # 处理每注
        for t in pred_data.get("tickets", []):
            entry = _compare_one_ticket(lottery_type, t["numbers"], target)
            save_backtest_result(
                lottery_type, target_pid, w_start, w_end,
                "regular", t["index"], entry, path=path,
            )
            entry["ticket_index"] = t["index"]
            entry["ticket_type"] = "regular"
            all_regular_entries.append(entry)
            saved_total += 1

        # 处理单式优选
        if pred_data.get("best"):
            best_nums = pred_data["best"]["numbers"]
            best_score = pred_data["best"].get("score")
            best_entry = _compare_one_ticket(lottery_type, best_nums, target)
            save_backtest_result(
                lottery_type, target_pid, w_start, w_end,
                "best", 0, best_entry, total_score=best_score, path=path,
            )
            best_entry["ticket_type"] = "best"
            best_entry["ticket_index"] = 0
            all_best_entries.append(best_entry)
            saved_total += 1

        if progress_callback:
            progress_callback(i - start_idx + 1, test_count, target_pid)

        twenty_hit_val = pred_data.get("twenty_hit")
        if isinstance(twenty_hit_val, (int, float)):
            twenty_hits.append(int(twenty_hit_val))

    # 聚合
    summary = _aggregate_backtest(lottery_type, all_regular_entries, all_best_entries)
    if twenty_hits:
        import numpy as np
        summary["twenty_hit"] = {
            "count": len(twenty_hits),
            "avg": float(np.mean(twenty_hits)),
            "median": float(np.median(twenty_hits)),
            "max": int(max(twenty_hits)),
        }
    return {"ok": True, "lottery_type": lottery_type, "periods_tested": test_count, "window": window, "saved": saved_total, "summary": summary}


def _compare_one_ticket(lottery_type: str, numbers: dict, draw: dict) -> dict:
    """对比单注预测 vs 实际开奖。"""
    if lottery_type == "dlt":
        f_pred = set(numbers["front"])
        f_act = {draw["front_1"], draw["front_2"], draw["front_3"], draw["front_4"], draw["front_5"]}
        b_pred = set(numbers["back"])
        b_act = {draw["back_1"], draw["back_2"]}
        fm = len(f_pred & f_act)
        bm = len(b_pred & b_act)
        return {"front_matches": fm, "back_matches": bm, "prize_level": _dlt_prize(fm, bm)}
    elif lottery_type == "ssq":
        r_pred = set(numbers["red"])
        r_act = {draw["red_1"], draw["red_2"], draw["red_3"], draw["red_4"], draw["red_5"], draw["red_6"]}
        bp = int(numbers["blue"])
        ba = int(draw["blue"])
        rm = len(r_pred & r_act)
        bm = 1 if bp == ba else 0
        return {"red_matches": rm, "blue_match": bm, "prize_level": _ssq_prize(rm, bm)}
    elif lottery_type == "kl8":
        c_pred = set(numbers["codes"])
        c_act = {draw[f"n{i:02d}"] for i in range(1, 21)}
        overlap = len(c_pred & c_act)
        return {"overlap_count": overlap}
    elif lottery_type == "pl5":
        d_pred = numbers["digits"]
        d_act = [draw["d1"], draw["d2"], draw["d3"], draw["d4"], draw["d5"]]
        pm = sum(1 for i in range(5) if d_pred[i] == d_act[i])
        return {"position_matches": pm, "all_matched": pm == 5}
    elif lottery_type == "qxc":
        f_pred = numbers["front"]
        f_act = [draw["d1"], draw["d2"], draw["d3"], draw["d4"], draw["d5"], draw["d6"]]
        sp = numbers["special"]
        sa = draw["special"]
        fm = sum(1 for i in range(6) if f_pred[i] == f_act[i])
        sm = 1 if sp == sa else 0
        return {"front_matches": fm, "special_match": sm}
    return {}


def _aggregate_backtest(lottery_type: str, regulars: list[dict], bests: list[dict]) -> dict:
    """聚合回测统计（含最大回撤、中奖间隔分布等金融视角指标）。"""
    import numpy as np
    summary: dict = {}

    def _is_loss_dlt(e: dict) -> bool:
        return e.get("prize_level", "未中奖") == "未中奖"

    def _is_loss_ssq(e: dict) -> bool:
        return e.get("prize_level", "未中奖") == "未中奖"

    def _is_loss_kl8(e: dict) -> bool:
        return e.get("overlap_count", 0) == 0

    def _is_loss_pl5(e: dict) -> bool:
        return e.get("position_matches", 0) == 0

    def _is_loss_qxc(e: dict) -> bool:
        return e.get("front_matches", 0) == 0 and e.get("special_match", 0) == 0

    _loss_fn = {
        "dlt": _is_loss_dlt, "ssq": _is_loss_ssq, "kl8": _is_loss_kl8,
        "pl5": _is_loss_pl5, "qxc": _is_loss_qxc,
    }.get(lottery_type, lambda e: False)

    def _compute_stability(entries: list[dict]) -> dict:
        if not entries:
            return {}
        # 最大回撤：最长连续未中奖
        max_dd = 0
        cur_dd = 0
        gaps: list[int] = []
        since_last_win = 0
        for e in entries:
            if _loss_fn(e):
                cur_dd += 1
                since_last_win += 1
            else:
                if since_last_win > 0:
                    gaps.append(since_last_win)
                since_last_win = 0
                max_dd = max(max_dd, cur_dd)
                cur_dd = 0
        max_dd = max(max_dd, cur_dd)
        gap_avg = float(np.mean(gaps)) if gaps else 0.0
        gap_median = float(np.median(gaps)) if gaps else 0.0
        gap_max = int(max(gaps)) if gaps else 0
        win_rate = sum(1 for e in entries if not _loss_fn(e)) / len(entries)
        return {
            "max_drawdown": max_dd,
            "prize_gap_avg": round(gap_avg, 1),
            "prize_gap_median": round(gap_median, 1),
            "prize_gap_max": gap_max,
            "win_rate": round(win_rate, 4),
        }

    if lottery_type in ("dlt",):
        if regulars:
            fm_avg = sum(e.get("front_matches", 0) for e in regulars) / len(regulars)
            bm_avg = sum(e.get("back_matches", 0) for e in regulars) / len(regulars)
            summary["regular"] = {"count": len(regulars), "avg_front": round(fm_avg, 2), "avg_back": round(bm_avg, 2)}
            from collections import Counter
            prize_dist = Counter(e.get("prize_level", "未中奖") for e in regulars)
            summary["regular"]["prize_dist"] = dict(prize_dist.most_common())
            best_hit = max(regulars, key=lambda e: (e.get("front_matches", 0) * 10 + e.get("back_matches", 0)))
            summary["regular"]["best_hit"] = best_hit
            summary["regular"]["stability"] = _compute_stability(regulars)
        if bests:
            fm_avg = sum(e.get("front_matches", 0) for e in bests) / len(bests)
            bm_avg = sum(e.get("back_matches", 0) for e in bests) / len(bests)
            summary["best"] = {"count": len(bests), "avg_front": round(fm_avg, 2), "avg_back": round(bm_avg, 2)}
            from collections import Counter
            prize_dist = Counter(e.get("prize_level", "未中奖") for e in bests)
            summary["best"]["prize_dist"] = dict(prize_dist.most_common())
            summary["best"]["stability"] = _compute_stability(bests)

    elif lottery_type == "ssq":
        if regulars:
            rm_avg = sum(e.get("red_matches", 0) for e in regulars) / len(regulars)
            bm_avg = sum(e.get("blue_match", 0) for e in regulars) / len(regulars)
            summary["regular"] = {"count": len(regulars), "avg_red": round(rm_avg, 2), "avg_blue": round(bm_avg, 2)}
            from collections import Counter
            prize_dist = Counter(e.get("prize_level", "未中奖") for e in regulars)
            summary["regular"]["prize_dist"] = dict(prize_dist.most_common())
            best_hit = max(regulars, key=lambda e: (e.get("red_matches", 0) * 10 + e.get("blue_match", 0)))
            summary["regular"]["best_hit"] = best_hit
            summary["regular"]["stability"] = _compute_stability(regulars)
        if bests:
            rm_avg = sum(e.get("red_matches", 0) for e in bests) / len(bests)
            bm_avg = sum(e.get("blue_match", 0) for e in bests) / len(bests)
            summary["best"] = {"count": len(bests), "avg_red": round(rm_avg, 2), "avg_blue": round(bm_avg, 2)}
            from collections import Counter
            prize_dist = Counter(e.get("prize_level", "未中奖") for e in bests)
            summary["best"]["prize_dist"] = dict(prize_dist.most_common())
            summary["best"]["stability"] = _compute_stability(bests)

    elif lottery_type == "kl8":
        if regulars:
            ol_avg = sum(e.get("overlap_count", 0) for e in regulars) / len(regulars)
            summary["regular"] = {"count": len(regulars), "avg_overlap": round(ol_avg, 2)}
            summary["regular"]["stability"] = _compute_stability(regulars)
        if bests:
            ol_avg = sum(e.get("overlap_count", 0) for e in bests) / len(bests)
            summary["best"] = {"count": len(bests), "avg_overlap": round(ol_avg, 2)}
            summary["best"]["stability"] = _compute_stability(bests)

    elif lottery_type == "pl5":
        if regulars:
            pm_avg = sum(e.get("position_matches", 0) for e in regulars) / len(regulars)
            all_hit = sum(1 for e in regulars if e.get("all_matched"))
            summary["regular"] = {"count": len(regulars), "avg_pos": round(pm_avg, 2), "all_matched": all_hit}
            summary["regular"]["stability"] = _compute_stability(regulars)
        if bests:
            pm_avg = sum(e.get("position_matches", 0) for e in bests) / len(bests)
            summary["best"] = {"count": len(bests), "avg_pos": round(pm_avg, 2)}
            summary["best"]["stability"] = _compute_stability(bests)

    elif lottery_type == "qxc":
        if regulars:
            fm_avg = sum(e.get("front_matches", 0) for e in regulars) / len(regulars)
            sm_avg = sum(e.get("special_match", 0) for e in regulars) / len(regulars)
            summary["regular"] = {"count": len(regulars), "avg_front": round(fm_avg, 2), "avg_special": round(sm_avg, 2)}
            summary["regular"]["stability"] = _compute_stability(regulars)
        if bests:
            fm_avg = sum(e.get("front_matches", 0) for e in bests) / len(bests)
            sm_avg = sum(e.get("special_match", 0) for e in bests) / len(bests)
            summary["best"] = {"count": len(bests), "avg_front": round(fm_avg, 2), "avg_special": round(sm_avg, 2)}
            summary["best"]["stability"] = _compute_stability(bests)

    return summary


def compute_rolling_stability(
    lottery_type: str,
    periods: int = 200,
    window: int = 30,
    slice_size: int = 50,
    path: Path | str | None = None,
) -> dict:
    """滚动窗口稳定性：将全历史按 slice_size 拆分，各段独立回测，评估模型在不同时期的稳定性。"""
    import numpy as np

    init_db(path)
    df = get_draws(lottery_type, path=path)
    if df.empty:
        return {"ok": False, "error": "无开奖数据"}
    df["period_id"] = pd.to_numeric(df["period_id"], errors="coerce")
    df = df.sort_values("period_id").reset_index(drop=True)
    all_pids = df["period_id"].tolist()

    total = len(all_pids)
    slices = []
    start = max(0, total - periods)
    while start + window + 10 < total:
        end = min(start + slice_size, total)
        if end - start >= window + 10:
            slices.append((start, end))
        start += slice_size // 2  # 50% 重叠

    if len(slices) < 2:
        return {"ok": False, "error": f"数据不足以做滚动分析（需至少 2 段，当前 {len(slices)} 段）"}

    segment_results = []
    for seg_start, seg_end in slices:
        seg_pids = all_pids[seg_start:seg_end]
        seg_label = f"{int(min(seg_pids))}–{int(max(seg_pids))}"
        r = run_backtest(lottery_type, periods=min(50, seg_end - seg_start - window),
                         window=window, path=path)
        if r["ok"]:
            s = r["summary"]
            metric = None
            if lottery_type == "dlt":
                metric = s.get("regular", {}).get("avg_front", 0) + s.get("regular", {}).get("avg_back", 0)
            elif lottery_type == "ssq":
                metric = s.get("regular", {}).get("avg_red", 0)
            elif lottery_type == "kl8":
                metric = s.get("regular", {}).get("avg_overlap", 0)
            elif lottery_type == "pl5":
                metric = s.get("regular", {}).get("avg_pos", 0)
            elif lottery_type == "qxc":
                metric = s.get("regular", {}).get("avg_front", 0)
            segment_results.append({"segment": seg_label, "periods": r["periods_tested"], "metric": round(metric, 3) if metric else 0})

    if not segment_results:
        return {"ok": False, "error": "无有效回测段"}

    metrics = [s["metric"] for s in segment_results]
    return {
        "ok": True,
        "lottery_type": lottery_type,
        "total_segments": len(segment_results),
        "metric_mean": round(float(np.mean(metrics)), 3),
        "metric_std": round(float(np.std(metrics, ddof=1)), 3) if len(metrics) > 1 else 0.0,
        "metric_min": round(float(min(metrics)), 3),
        "metric_max": round(float(max(metrics)), 3),
        "cv": round(float(np.std(metrics, ddof=1)) / max(0.001, float(np.mean(metrics))), 4) if len(metrics) > 1 else 0.0,
        "segments": segment_results,
    }
