"""SQLite 数据库层：开奖数据的读优化镜像。

CSV 仍是维护源；本模块提供 DB 优先读取，分析/预测默认走 DB。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from .paths import db_path as _default_db_path, processed_dir

CURRENT_SCHEMA_VERSION = 1

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
            conn.execute(
                "INSERT OR REPLACE INTO schema_version(version, description) VALUES(?,?)",
                (CURRENT_SCHEMA_VERSION, "initial schema: 5 lottery tables + schema_version"),
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
