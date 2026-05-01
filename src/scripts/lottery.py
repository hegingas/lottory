#!/usr/bin/env python3
"""
统一入口：盘点 data、校验 processed、按范围重算 history 书面归档。

用法（在仓库根目录）：
  python src/scripts/lottery.py inventory
  python src/scripts/lottery.py validate
  python src/scripts/lottery.py regenerate-history [--only all|kl8|dlt-ssq|pl5]

**唯一推荐的刷新路径**：`regenerate-history`，用 ``--only`` 按用户/任务要刷的彩种选择范围。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# 确保 src/ 在 sys.path 中
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from lottery.paths import repo_root, processed_dir, manifest_path
from lottery.inventory import print_inventory_json
from lottery.validate import run_validate


def cmd_inventory() -> int:
    print_inventory_json()
    return 0


def cmd_validate() -> int:
    r = run_validate()
    print(json.dumps(r, ensure_ascii=True, indent=2))
    return 0 if r.get("ok") else 1


def cmd_regenerate_history(only_api: str, seed: int) -> int:
    from scripts.regenerate_history_archives import main as regen_main

    internal = {"all": "all", "kl8": "kl8", "dlt-ssq": "dlt_ssq", "pl5": "pl5"}[only_api]
    rc = int(regen_main(only=internal, seed=seed))
    if rc == 0:
        report, _ = _build_doctor_report()
        if isinstance(report, dict):
            post = {
                "ok": bool(report.get("ok", False)),
                "sync_ok": bool(report.get("sync_ok", False)),
                "analysis_sync_ok": bool(report.get("analysis_sync_ok", False)),
                "formula_sync_ok": bool(report.get("formula_sync_ok", False)),
            }
            print(json.dumps({"post_check": post}, ensure_ascii=True))
    return rc


def _latest_period_from_csv(path: Path) -> int | None:
    if not path.is_file():
        return None
    latest: int | None = None
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        for row in rd:
            try:
                pid = int(str(row.get("period_id", "")).strip())
            except ValueError:
                continue
            if latest is None or pid > latest:
                latest = pid
    return latest


def _latest_period_from_history(path: Path) -> int | None:
    if not path.is_file():
        return None
    txt = path.read_text(encoding="utf-8", errors="ignore")
    pairs = re.findall(r"`(\d+)`\s*(?:[–\-~]|至|到)\s*`(\d+)`", txt)
    if not pairs:
        return None
    latest: int | None = None
    for _, right in pairs:
        try:
            val = int(right)
        except ValueError:
            continue
        if latest is None or val > latest:
            latest = val
    return latest


def _extract_markov_formula_weight(path: Path) -> float | None:
    if not path.is_file():
        return None
    txt = path.read_text(encoding="utf-8", errors="ignore")
    m_old = re.search(r"C=([0-9]+(?:\.[0-9]+)?)\*N", txt)
    if m_old:
        return float(m_old.group(1))
    m_new = re.search(r"([0-9]+(?:\.[0-9]+)?)%\s*[×xX*]\s*马尔可夫", txt)
    if m_new:
        return float(m_new.group(1)) / 100.0
    return None


def _build_doctor_report() -> tuple[dict, object]:
    import lottery.config as cfg

    root = repo_root()
    proc = processed_dir()
    hist = root / "history"

    val = run_validate()
    from scripts.regenerate_history_archives import main as regen_main

    data_latest = {
        "dlt": _latest_period_from_csv(proc / "dlt_draws.csv"),
        "ssq": _latest_period_from_csv(proc / "ssq_draws.csv"),
        "kl8": _latest_period_from_csv(proc / "kl8_draws.csv"),
        "pl5": _latest_period_from_csv(proc / "pl5_draws.csv"),
    }
    history_latest = {
        "dlt": _latest_period_from_history(hist / "daletou_prediction.md"),
        "ssq": _latest_period_from_history(hist / "shuangseqiu_prediction.md"),
        "kl8": _latest_period_from_history(hist / "kuaileba_prediction.md"),
        "pl5": _latest_period_from_history(hist / "pailie5_prediction.md"),
    }
    history_analysis_latest = {
        "dlt": _latest_period_from_history(hist / "daletou_analysis.md"),
        "ssq": _latest_period_from_history(hist / "shuangseqiu_analysis.md"),
        "kl8": _latest_period_from_history(hist / "kuaileba_analysis.md"),
        "pl5": _latest_period_from_history(hist / "pailie5_analysis.md"),
    }
    sync = {
        k: (data_latest.get(k) is not None and data_latest.get(k) == history_latest.get(k))
        for k in ("dlt", "ssq", "kl8", "pl5")
    }
    analysis_sync = {
        k: (data_latest.get(k) is not None and data_latest.get(k) == history_analysis_latest.get(k))
        for k in ("dlt", "ssq", "kl8", "pl5")
    }
    expected_markov_weight = float(cfg.PATTERN_W_MARKOV)
    formula_weight = {
        "dlt": _extract_markov_formula_weight(hist / "daletou_prediction.md"),
        "ssq": _extract_markov_formula_weight(hist / "shuangseqiu_prediction.md"),
        "kl8": _extract_markov_formula_weight(hist / "kuaileba_prediction.md"),
    }
    formula_sync = {
        k: (
            formula_weight.get(k) is not None
            and abs(float(formula_weight.get(k)) - expected_markov_weight) < 1e-9
        )
        for k in ("dlt", "ssq", "kl8")
    }
    suggest_cmds: list[str] = []
    if not bool(val.get("ok")):
        suggest_cmds.append("python src/scripts/lottery.py validate")
    if not all(sync.values()) or not all(analysis_sync.values()) or not all(formula_sync.values()):
        suggest_cmds.append("python src/scripts/lottery.py regenerate-history --only all --seed 20260430")
    if not suggest_cmds:
        suggest_cmds.append("# 状态正常：当前无需修复命令")

    out = {
        "ok": bool(val.get("ok")) and all(sync.values()) and all(analysis_sync.values()) and all(formula_sync.values()),
        "sync_ok": all(sync.values()),
        "analysis_sync_ok": all(analysis_sync.values()),
        "formula_sync_ok": all(formula_sync.values()),
        "validate_ok": bool(val.get("ok")),
        "data_latest_period": data_latest,
        "history_latest_period": history_latest,
        "history_analysis_latest_period": history_analysis_latest,
        "sync": sync,
        "analysis_sync": analysis_sync,
        "formula_weight_in_history": formula_weight,
        "formula_sync": formula_sync,
        "seed": {
            "default_random_seed": int(cfg.DEFAULT_RANDOM_SEED),
            "active_random_seed": int(cfg._ACTIVE_RANDOM_SEED),
        },
        "weights": {
            "miss": float(cfg.PATTERN_W_MISS),
            "freq": float(cfg.PATTERN_W_FREQ),
            "zone": float(cfg.PATTERN_W_ZONE),
            "recency": float(cfg.PATTERN_W_RECENCY),
            "parity": float(cfg.PATTERN_W_PARITY),
            "size": float(cfg.PATTERN_W_SIZE),
            "sum": float(cfg.PATTERN_W_SUM),
            "markov": float(cfg.PATTERN_W_MARKOV),
        },
        "validate_errors": val.get("errors", []),
        "suggested_commands": suggest_cmds,
    }
    return out, regen_main


def cmd_doctor(as_json: bool = False, auto_fix: bool = False) -> int:
    out, regen_main = _build_doctor_report()

    if auto_fix and not out.get("ok", False):
        out["auto_fix_executed"] = True
        out["auto_fix_steps"] = []
        out["auto_fix_error"] = None
        try:
            v = run_validate()
            out["auto_fix_steps"].append({"step": "validate", "ok": bool(v.get("ok", False))})

            rc = int(regen_main(only="all", seed=20260430))
            out["auto_fix_steps"].append({"step": "regenerate-history", "exit_code": rc})
            if rc != 0:
                out["auto_fix_error"] = f"regenerate-history failed with exit_code={rc}"

            out2, _ = _build_doctor_report()
            out2["auto_fix_executed"] = True
            out2["auto_fix_steps"] = out["auto_fix_steps"]
            out2["auto_fix_error"] = out["auto_fix_error"]
            out = out2
        except Exception as e:
            out["ok"] = False
            out["auto_fix_error"] = f"doctor --fix exception: {e}"
    else:
        out["auto_fix_executed"] = False
        out["auto_fix_steps"] = []
        out["auto_fix_error"] = None

    if as_json:
        print(json.dumps(out, ensure_ascii=True, indent=2))
    else:
        print("=== Lottery Doctor ===")
        print(f"- overall_ok: {out['ok']}")
        print(f"- validate_ok: {out['validate_ok']}")
        print(f"- sync_ok: {out['sync_ok']}")
        print(f"- analysis_sync_ok: {out['analysis_sync_ok']}")
        print(f"- formula_sync_ok: {out['formula_sync_ok']}")
        print(f"- auto_fix_executed: {out['auto_fix_executed']}")
        if out["auto_fix_steps"]:
            print(f"- auto_fix_steps: {out['auto_fix_steps']}")
        if out["auto_fix_error"]:
            print(f"- auto_fix_error: {out['auto_fix_error']}")
        print(f"- data_latest_period: {out['data_latest_period']}")
        print(f"- history_latest_period: {out['history_latest_period']}")
        print(f"- history_analysis_latest_period: {out['history_analysis_latest_period']}")
        print(f"- sync: {out['sync']}")
        print(f"- analysis_sync: {out['analysis_sync']}")
        print(f"- formula_weight_in_history: {out['formula_weight_in_history']}")
        print(f"- formula_sync: {out['formula_sync']}")
        print(f"- seed: {out['seed']}")
        print(f"- weights: {out['weights']}")
        if out["validate_errors"]:
            print("- validate_errors:")
            for e in out["validate_errors"]:
                print(f"  - {e}")
        else:
            print("- validate_errors: []")
        print("- suggested_commands:")
        for c in out["suggested_commands"]:
            print(f"  - {c}")
    return 0 if out["ok"] else 1


def main() -> int:
    p = argparse.ArgumentParser(description="彩票仓库统一 Python 工具（盘点 / 校验 / 重算 history）")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("inventory", help="列出 data/ 下文件（UTF-8 JSON）")
    sub.add_parser("validate", help="校验 processed CSV 与 manifest rows_out")
    p_doctor = sub.add_parser("doctor", help="诊断 data/history/seed/weights 一致性")
    p_doctor.add_argument("--json", action="store_true", help="输出 JSON（默认输出可读摘要）")
    p_doctor.add_argument(
        "--fix",
        action="store_true",
        help="检测失败时自动执行修复：validate + regenerate-history --only all --seed 20260430",
    )

    p_rh = sub.add_parser(
        "regenerate-history",
        help="统一刷新 history 分析/预测归档（默认近 30 期）",
        description="根据 --only 选择写入范围；为仓库彩种统一推荐的机械重算入口。",
    )
    p_rh.add_argument(
        "--only",
        dest="only_scope",
        choices=["all", "kl8", "dlt-ssq", "pl5"],
        default="all",
        metavar="SCOPE",
        help="all：DLT+SSQ+PL5 六文件，且存在 kl8 CSV 时追加 KL8 两文件；kl8：仅 KL8 分析+预测；dlt-ssq：仅 DLT+SSQ 四文件；pl5：仅排列5分析+预测",
    )
    p_rh.add_argument(
        "--seed",
        type=int,
        default=20260430,
        help="预测随机种子（默认 20260430，可复现）",
    )

    sub.add_parser("regenerate-kl8-prediction", help="[兼容] 等同 regenerate-history --only kl8")

    args = p.parse_args()
    if args.command == "inventory":
        return cmd_inventory()
    if args.command == "validate":
        return cmd_validate()
    if args.command == "doctor":
        return cmd_doctor(as_json=args.json, auto_fix=args.fix)
    if args.command == "regenerate-history":
        return cmd_regenerate_history(args.only_scope, args.seed)
    if args.command == "regenerate-kl8-prediction":
        return cmd_regenerate_history("kl8", 20260430)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
