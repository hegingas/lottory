"""校验 `data/processed/*.csv` 与 `manifest.json` 行数及号码规则。

- 大乐透/双色球：前区/红球、后区/蓝球仅检查 **互异 + 区间合法**；列顺序可为摇出顺序，不要求列内升序。
- 快乐八：`n01`–`n20` 须 **升序且 20 个互异**（与 schema 约定一致）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .paths import manifest_path, processed_dir, schema_path


def _norm_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).lstrip("\ufeff").strip() for c in df.columns]
    return df


def _load_csv(path: Path) -> pd.DataFrame:
    return _norm_columns(pd.read_csv(path, encoding="utf-8-sig"))


def validate_dlt(df: pd.DataFrame) -> list[str]:
    errs: list[str] = []
    need = {
        "lottery_type",
        "period_id",
        "front_1",
        "front_2",
        "front_3",
        "front_4",
        "front_5",
        "back_1",
        "back_2",
    }
    missing = need - set(df.columns)
    if missing:
        errs.append(f"dlt: 缺列 {sorted(missing)}")
        return errs
    if not (df["lottery_type"].astype(str).str.strip() == "dlt").all():
        errs.append("dlt: lottery_type 须全为 dlt")
    dup = df["period_id"].duplicated()
    if dup.any():
        errs.append(f"dlt: 重复 period_id 共 {int(dup.sum())} 行")
    for _, row in df.iterrows():
        if len(errs) >= 40:
            errs.append("dlt: 错误过多，已截断")
            break
        pid = row["period_id"]
        fronts = [int(row[f"front_{i}"]) for i in range(1, 6)]
        backs = [int(row["back_1"]), int(row["back_2"])]
        if len(set(fronts)) != 5:
            errs.append(f"dlt period {pid}: 前区有重复")
        if len(set(backs)) != 2:
            errs.append(f"dlt period {pid}: 后区有重复")
        for x in fronts:
            if not (1 <= x <= 35):
                errs.append(f"dlt period {pid}: 前区越界 {x}")
        for x in backs:
            if not (1 <= x <= 12):
                errs.append(f"dlt period {pid}: 后区越界 {x}")
    return errs


def validate_ssq(df: pd.DataFrame) -> list[str]:
    errs: list[str] = []
    need = {
        "lottery_type",
        "period_id",
        "red_1",
        "red_2",
        "red_3",
        "red_4",
        "red_5",
        "red_6",
        "blue",
    }
    missing = need - set(df.columns)
    if missing:
        errs.append(f"ssq: 缺列 {sorted(missing)}")
        return errs
    if not (df["lottery_type"].astype(str).str.strip() == "ssq").all():
        errs.append("ssq: lottery_type 须全为 ssq")
    dup = df["period_id"].duplicated()
    if dup.any():
        errs.append(f"ssq: 重复 period_id 共 {int(dup.sum())} 行")
    for _, row in df.iterrows():
        if len(errs) >= 40:
            errs.append("ssq: 错误过多，已截断")
            break
        pid = row["period_id"]
        reds = [int(row[f"red_{i}"]) for i in range(1, 7)]
        blue = int(row["blue"])
        if len(set(reds)) != 6:
            errs.append(f"ssq period {pid}: 红球重复")
        for x in reds:
            if not (1 <= x <= 33):
                errs.append(f"ssq period {pid}: 红球越界 {x}")
        if not (1 <= blue <= 16):
            errs.append(f"ssq period {pid}: 蓝球越界 {blue}")
    return errs


def validate_kl8(df: pd.DataFrame) -> list[str]:
    errs: list[str] = []
    ncols = [f"n{i:02d}" for i in range(1, 21)]
    need = {"lottery_type", "period_id", *ncols}
    missing = need - set(df.columns)
    if missing:
        errs.append(f"kl8: 缺列 {sorted(missing)}")
        return errs
    if not (df["lottery_type"].astype(str).str.strip() == "kl8").all():
        errs.append("kl8: lottery_type 须全为 kl8")
    dup = df["period_id"].duplicated()
    if dup.any():
        errs.append(f"kl8: 重复 period_id 共 {int(dup.sum())} 行")
    for _, row in df.iterrows():
        if len(errs) >= 40:
            errs.append("kl8: 错误过多，已截断")
            break
        pid = row["period_id"]
        nums = [int(row[c]) for c in ncols]
        if nums != sorted(nums):
            errs.append(f"kl8 period {pid}: 须升序")
        if len(set(nums)) != 20:
            errs.append(f"kl8 period {pid}: 开奖号重复或不足 20")
        for x in nums:
            if not (1 <= x <= 80):
                errs.append(f"kl8 period {pid}: 越界 {x}")
    return errs


def _manifest_row_counts(manifest: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for block in manifest.get("outputs", []):
        lt = block.get("lottery_type")
        if lt in ("dlt", "ssq", "kl8"):
            out[lt] = {
                "rows_out": block.get("rows_out"),
                "period_id_min": block.get("period_id_min"),
                "period_id_max": block.get("period_id_max"),
            }
    return out


def run_validate() -> dict[str, Any]:
    proc = processed_dir()
    result: dict[str, Any] = {"ok": True, "errors": [], "manifest_check": {}, "row_counts": {}}

    if not schema_path().exists():
        result["ok"] = False
        result["errors"].append("缺少 data/processed/schema.json")
        return result

    manifest: dict = {}
    if manifest_path().exists():
        manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
        result["manifest_check"] = _manifest_row_counts(manifest)

    all_errs: list[str] = []

    dlt_p = proc / "dlt_draws.csv"
    if dlt_p.is_file():
        dlt = _load_csv(dlt_p)
        result["row_counts"]["dlt_csv"] = len(dlt)
        e = validate_dlt(dlt)
        all_errs.extend(e)
        ro = result["manifest_check"].get("dlt", {}).get("rows_out")
        if ro is not None and int(ro) != len(dlt):
            all_errs.append(f"manifest dlt rows_out={ro} 与 CSV 行数 {len(dlt)} 不一致")
    else:
        all_errs.append("缺少 dlt_draws.csv")

    ssq_p = proc / "ssq_draws.csv"
    if ssq_p.is_file():
        ssq = _load_csv(ssq_p)
        result["row_counts"]["ssq_csv"] = len(ssq)
        all_errs.extend(validate_ssq(ssq))
        ro = result["manifest_check"].get("ssq", {}).get("rows_out")
        if ro is not None and int(ro) != len(ssq):
            all_errs.append(f"manifest ssq rows_out={ro} 与 CSV 行数 {len(ssq)} 不一致")
    else:
        all_errs.append("缺少 ssq_draws.csv")

    kl8_p = proc / "kl8_draws.csv"
    if kl8_p.is_file():
        kl8 = _load_csv(kl8_p)
        result["row_counts"]["kl8_csv"] = len(kl8)
        all_errs.extend(validate_kl8(kl8))
        ro = result["manifest_check"].get("kl8", {}).get("rows_out")
        if ro is not None and int(ro) != len(kl8):
            all_errs.append(f"manifest kl8 rows_out={ro} 与 CSV 行数 {len(kl8)} 不一致")
    else:
        result["row_counts"]["kl8_csv"] = 0

    result["errors"] = all_errs
    result["ok"] = len(all_errs) == 0
    return result
