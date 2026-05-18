#!/usr/bin/env python3
"""
统一入口：盘点 data、校验 processed、按范围重算 history 书面归档。

用法（在仓库根目录）：
  python src/scripts/cli.py inventory
  python src/scripts/cli.py validate
  python src/scripts/cli.py regenerate-history [--only all|kl8|dlt-ssq|pl5|qxc]

**唯一推荐的刷新路径**：`regenerate-history`，用 ``--only`` 按用户/任务要刷的彩种选择范围。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

# 确保 src/ 在 sys.path 中
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from lottery.inventory import print_inventory_json
from lottery.paths import processed_dir, repo_root
from lottery.validate import run_validate


def cmd_inventory() -> int:
    print_inventory_json()
    return 0


def cmd_validate() -> int:
    r = run_validate()
    print(json.dumps(r, ensure_ascii=True, indent=2))
    return 0 if r.get("ok") else 1


def cmd_regenerate_history(only_api: str, seed: int, use_mask: bool = True, auto_strategy: bool = False) -> int:
    from scripts.regenerate_history_archives import main as regen_main

    internal = {"all": "all", "kl8": "kl8", "dlt-ssq": "dlt_ssq", "pl5": "pl5", "qxc": "qxc"}[only_api]
    rc = int(regen_main(only=internal, seed=seed, use_mask=use_mask, auto_strategy=auto_strategy))
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


def _build_doctor_report() -> tuple[dict, Any]:
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
        "qxc": _latest_period_from_csv(proc / "qxc_draws.csv"),
    }
    history_latest = {
        "dlt": _latest_period_from_history(hist / "daletou_prediction.md"),
        "ssq": _latest_period_from_history(hist / "shuangseqiu_prediction.md"),
        "kl8": _latest_period_from_history(hist / "kuaileba_prediction.md"),
        "pl5": _latest_period_from_history(hist / "pailie5_prediction.md"),
        "qxc": _latest_period_from_history(hist / "qixingcai_prediction.md"),
    }
    history_analysis_latest = {
        "dlt": _latest_period_from_history(hist / "daletou_analysis.md"),
        "ssq": _latest_period_from_history(hist / "shuangseqiu_analysis.md"),
        "kl8": _latest_period_from_history(hist / "kuaileba_analysis.md"),
        "pl5": _latest_period_from_history(hist / "pailie5_analysis.md"),
        "qxc": _latest_period_from_history(hist / "qixingcai_analysis.md"),
    }
    sync = {
        k: (data_latest.get(k) is not None and data_latest.get(k) == history_latest.get(k))
        for k in ("dlt", "ssq", "kl8", "pl5", "qxc")
    }
    analysis_sync = {
        k: (data_latest.get(k) is not None and data_latest.get(k) == history_analysis_latest.get(k))
        for k in ("dlt", "ssq", "kl8", "pl5", "qxc")
    }
    optimized = {
        "dlt": cfg.get_optimized_weights("dlt"),
        "ssq": cfg.get_optimized_weights("ssq"),
        "kl8": cfg.get_optimized_weights("kl8"),
    }
    formula_weight = {
        "dlt": _extract_markov_formula_weight(hist / "daletou_prediction.md"),
        "ssq": _extract_markov_formula_weight(hist / "shuangseqiu_prediction.md"),
        "kl8": _extract_markov_formula_weight(hist / "kuaileba_prediction.md"),
    }
    formula_sync: dict[str, bool] = {}
    for k in ("dlt", "ssq", "kl8"):
        fw = formula_weight.get(k)
        ow = optimized.get(k)
        formula_sync[k] = (
            fw is not None
            and ow is not None
            and abs(float(fw) - float(ow.get("markov", -1))) < 0.01
        )
    suggest_cmds: list[str] = []
    if not bool(val.get("ok")):
        suggest_cmds.append("python src/scripts/cli.py validate")
    if not all(sync.values()) or not all(analysis_sync.values()) or not all(formula_sync.values()):
        suggest_cmds.append("python src/scripts/cli.py regenerate-history --only all --seed 20260430")
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
        "weights_legacy": {
            "miss": float(cfg.PATTERN_W_MISS),
            "freq": float(cfg.PATTERN_W_FREQ),
            "zone": float(cfg.PATTERN_W_ZONE),
            "recency": float(cfg.PATTERN_W_RECENCY),
            "parity": float(cfg.PATTERN_W_PARITY),
            "size": float(cfg.PATTERN_W_SIZE),
            "sum": float(cfg.PATTERN_W_SUM),
            "markov": float(cfg.PATTERN_W_MARKOV),
        },
        "weights_optimized": {k: {kk: round(float(vv), 4) for kk, vv in v.items()} for k, v in optimized.items() if v is not None},
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
        except Exception as exc:
            out["ok"] = False
            out["auto_fix_error"] = f"doctor --fix exception: {exc}"
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


def cmd_migrate_to_db() -> int:
    from lottery.db import get_row_count, migrate_csv_to_db

    result = migrate_csv_to_db()
    summary = {lt: get_row_count(lt) for lt in result}
    print(json.dumps({"ok": True, "migrated": result, "db_row_counts": summary}, ensure_ascii=True, indent=2))
    return 0


def cmd_db_status(as_json: bool = False) -> int:
    from lottery.db import get_row_count, verify_db_csv_consistency
    from lottery.paths import db_path

    db = db_path()
    if not db.is_file():
        print(json.dumps({"ok": False, "error": f"数据库文件不存在: {db}"}, ensure_ascii=True, indent=2))
        return 1

    status = verify_db_csv_consistency()
    row_counts = {lt: get_row_count(lt) for lt in status if lt != "all_synced"}

    if as_json:
        print(json.dumps({**status, "db_path": db.as_posix(), "db_row_counts": row_counts}, ensure_ascii=True, indent=2))
    else:
        all_ok = status.get("all_synced", False)
        print(f"DB path: {db}")
        print(f"All synced: {all_ok}")
        for lt in ["dlt", "ssq", "kl8", "pl5", "qxc"]:
            if lt in status:
                s = status[lt]
                mark = "OK" if s["synced"] else "MISMATCH"
                print(f"  {lt}: csv={s['csv_rows']} db={s['db_rows']} csv_max={s['csv_max_period']} db_max={s['db_max_period']} [{mark}]")
    return 0 if status.get("all_synced", False) else 1


def cmd_prediction_list(lottery_type: str | None = None, period_id: int | None = None, as_json: bool = False) -> int:
    from lottery.db import get_predictions

    preds = get_predictions(lottery_type=lottery_type, predicted_period_id=period_id)
    if not preds:
        print("（无匹配的预测记录）")
        return 0

    if as_json:
        print(json.dumps(preds, ensure_ascii=False, indent=2))
        return 0

    # 按彩种+期号分组输出
    groups: dict[tuple[str, int], list[dict]] = {}
    for p in preds:
        key = (p["lottery_type"], p["predicted_period_id"])
        groups.setdefault(key, []).append(p)

    for (lt, pid), items in sorted(groups.items()):
        first = items[0]
        print(f"\n{'='*60}")
        print(f"彩种: {lt}  |  预测目标期: {pid}")
        print(f"统计窗口: {first['data_window_start']} – {first['data_window_end']}")
        print(f"预测时间: {first['prediction_date']}")
        regulars = [i for i in items if i["ticket_type"] == "regular"]
        bests = [i for i in items if i["ticket_type"] == "best"]
        for r in sorted(regulars, key=lambda x: x["ticket_index"]):
            nums = r["numbers"]
            if lt in ("dlt",):
                f_str = ",".join(f"{x:02d}" for x in nums["front"])
                b_str = ",".join(f"{x:02d}" for x in nums["back"])
                print(f"  第{r['ticket_index']}注: 前区 [{f_str}] 后区 [{b_str}]")
            elif lt == "ssq":
                r_str = ",".join(f"{x:02d}" for x in nums["red"])
                print(f"  第{r['ticket_index']}注: 红球 [{r_str}] 蓝球 [{nums['blue']:02d}]")
            elif lt == "kl8":
                c_str = ",".join(f"{x:02d}" for x in nums["codes"])
                print(f"  参考11码: [{c_str}]")
            elif lt == "pl5":
                d_str = "".join(str(d) for d in nums["digits"])
                print(f"  第{r['ticket_index']}注: {d_str}")
            elif lt == "qxc":
                f_str = ",".join(str(d) for d in nums["front"])
                print(f"  第{r['ticket_index']}注: 前区 [{f_str}] + 后区 {nums['special']}")
        for b in bests:
            nums = b["numbers"]
            score_str = f"  总分={b['total_score']:.3f}" if b.get("total_score") is not None else ""
            if lt in ("dlt",):
                f_str = ",".join(f"{x:02d}" for x in nums["front"])
                b_str = ",".join(f"{x:02d}" for x in nums["back"])
                print(f"  单式优选: 前区 [{f_str}] 后区 [{b_str}] {score_str}")
            elif lt == "ssq":
                r_str = ",".join(f"{x:02d}" for x in nums["red"])
                print(f"  单式优选: 红球 [{r_str}] 蓝球 [{nums['blue']:02d}] {score_str}")
            elif lt == "kl8":
                c_str = ",".join(f"{x:02d}" for x in nums["codes"])
                print(f"  单式优选: [{c_str}] {score_str}")
            elif lt == "pl5":
                d_str = "".join(str(d) for d in nums["digits"])
                print(f"  单式优选: {d_str} {score_str}")
            elif lt == "qxc":
                f_str = ",".join(str(d) for d in nums["front"])
                print(f"  单式优选: 前区 [{f_str}] + 后区 {nums['special']} {score_str}")
    print()
    return 0


def cmd_prediction_accuracy(lottery_type: str, period_id: int, as_json: bool = False) -> int:
    from lottery.db import compute_accuracy

    result = compute_accuracy(lottery_type, period_id)
    if "error" in result:
        print(result["error"])
        return 1

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"\n{'='*60}")
    print(f"彩种: {result['lottery_type']}  |  目标期: {result['predicted_period_id']}")
    print(f"预测时间: {result.get('prediction_date', 'N/A')}")
    print(f"开奖数据: {'已入库' if result['has_actual_draw'] else '尚未入库'}")

    if not result["has_actual_draw"]:
        print(result.get("message", ""))
        return 0

    print("\n--- 5注单式 ---")
    for t in result.get("tickets", []):
        if lottery_type in ("dlt",):
            print(f"  第{t['ticket_index']}注: 前区中{t['front_matches']} 后区中{t['back_matches']} → {t['prize_level']}")
        elif lottery_type == "ssq":
            print(f"  第{t['ticket_index']}注: 红球中{t['red_matches']} 蓝球{'中' if t['blue_match'] else '不中'} → {t['prize_level']}")
        elif lottery_type == "kl8":
            print(f"  参考11码: 与开奖20码重合 {t['overlap_count']} 个 {'(合规≤4)' if t['overlap_ok'] else '(超出上限)'}")
        elif lottery_type == "pl5":
            print(f"  第{t['ticket_index']}注: 逐位命中 {t['position_matches']}/5 {'★全中' if t['all_matched'] else ''}")
        elif lottery_type == "qxc":
            print(f"  第{t['ticket_index']}注: 前区命中 {t['front_matches']}/6 后区{'命中' if t['special_match'] else '未命中'}")

    best = result.get("best")
    if best:
        print("\n--- 单式优选 ---")
        if lottery_type in ("dlt",):
            print(f"  前区中{best['front_matches']} 后区中{best['back_matches']} → {best['prize_level']}")
        elif lottery_type == "ssq":
            print(f"  红球中{best['red_matches']} 蓝球{'中' if best['blue_match'] else '不中'} → {best['prize_level']}")
        elif lottery_type == "kl8":
            print(f"  与开奖20码重合 {best['overlap_count']} 个")
        elif lottery_type == "pl5":
            print(f"  逐位命中 {best['position_matches']}/5")
        elif lottery_type == "qxc":
            print(f"  前区命中 {best['front_matches']}/6 后区{'命中' if best['special_match'] else '未命中'}")
    print()
    return 0


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
        choices=["all", "kl8", "dlt-ssq", "pl5", "qxc"],
        default="all",
        metavar="SCOPE",
        help="all：DLT+SSQ+PL5 六文件，kl8/qxc CSV 存在时追加对应文件；kl8：仅 KL8；dlt-ssq：仅 DLT+SSQ；pl5：仅排列5；qxc：仅七星彩",
    )
    p_rh.add_argument(
        "--seed",
        type=int,
        default=20260430,
        help="预测随机种子（默认 20260430，可复现）",
    )
    p_rh.add_argument(
        "--no-mask", action="store_true", dest="no_mask",
        help="不使用区间掩码马尔可夫约束（全号池开放；DLT/SSQ 回测中奖率更高）",
    )
    p_rh.add_argument(
        "--auto-strategy", action="store_true", dest="auto_strategy",
        help="自动回测对比 mask vs no-mask，择优预测（与 --no-mask 互斥）",
    )

    sub.add_parser("regenerate-kl8-prediction", help="[兼容] 等同 regenerate-history --only kl8")

    sub.add_parser("migrate-to-db", help="一次性将全部 CSV 导入 SQLite 数据库")
    p_dbs = sub.add_parser("db-status", help="显示数据库状态与 CSV 同步情况")
    p_dbs.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    p_plist = sub.add_parser("prediction-list", help="列出已保存的预测记录")
    p_plist.add_argument("--type", dest="pred_type", choices=["dlt","ssq","kl8","pl5","qxc"], default=None, metavar="TYPE", help="按彩种过滤")
    p_plist.add_argument("--period", type=int, default=None, help="按目标期号过滤")
    p_plist.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    p_pacc = sub.add_parser("prediction-accuracy", help="对比预测 vs 实际开奖，计算准确率")
    p_pacc.add_argument("--type", dest="pred_type", choices=["dlt","ssq","kl8","pl5","qxc"], required=True, metavar="TYPE", help="彩种")
    p_pacc.add_argument("--period", type=int, required=True, help="被预测的目标期号")
    p_pacc.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    p_bt = sub.add_parser("backtest", help="历史滑动窗口回测")
    p_bt.add_argument("--type", dest="bt_type", choices=["dlt","ssq","kl8","pl5","qxc"], required=True, metavar="TYPE", help="彩种")
    p_bt.add_argument("--periods", type=int, default=100, help="回测期数（默认 100）")
    p_bt.add_argument("--window", type=int, default=30, help="预测窗口大小（默认 30）")
    p_bt.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    p_bt.add_argument("--no-mask", action="store_true", dest="no_mask", help="不使用区间掩码马尔可夫约束（全号池开放）")
    p_bt.add_argument("--factors", type=int, choices=[4, 6], default=6, dest="bt_factors", help="因子数：4（旧4F）或 6（新6F，默认），仅 PL5/QXC 有效")

    p_btc = sub.add_parser("backtest-compare", help="对比回测：mask vs no-mask 双路径")
    p_btc.add_argument("--type", dest="btc_type", choices=["dlt","ssq","kl8","pl5","qxc"], required=True, metavar="TYPE", help="彩种")
    p_btc.add_argument("--periods", type=int, default=100, help="回测期数（默认 100）")
    p_btc.add_argument("--window", type=int, default=30, help="预测窗口大小（默认 30）")
    p_btc.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    p_btf = sub.add_parser("backtest-factors", help="单因子独立回测 + 可选权重推导与对比")
    p_btf.add_argument("--type", dest="btf_type", choices=["dlt","ssq","kl8","pl5","qxc"], required=True, metavar="TYPE", help="彩种")
    p_btf.add_argument("--periods", type=int, default=100, help="回测期数（默认 100）")
    p_btf.add_argument("--window", type=int, default=30, help="预测窗口大小（默认 30）")
    p_btf.add_argument("--no-mask", action="store_true", dest="btf_no_mask", help="不使用区间掩码马尔可夫约束")
    p_btf.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    p_btf.add_argument("--derive", action="store_true", dest="btf_derive", help="基于单因子表现自动推导新权重并对比回测")

    args = p.parse_args()
    if args.command == "inventory":
        return cmd_inventory()
    if args.command == "validate":
        return cmd_validate()
    if args.command == "doctor":
        return cmd_doctor(as_json=args.json, auto_fix=args.fix)
    if args.command == "regenerate-history":
        return cmd_regenerate_history(args.only_scope, args.seed, use_mask=not args.no_mask, auto_strategy=args.auto_strategy)
    if args.command == "regenerate-kl8-prediction":
        return cmd_regenerate_history("kl8", 20260430, use_mask=True)
    if args.command == "migrate-to-db":
        return cmd_migrate_to_db()
    if args.command == "db-status":
        return cmd_db_status(as_json=args.json)
    if args.command == "prediction-list":
        return cmd_prediction_list(args.pred_type, args.period, as_json=args.json)
    if args.command == "prediction-accuracy":
        return cmd_prediction_accuracy(args.pred_type, args.period, as_json=args.json)
    if args.command == "backtest":
        return cmd_backtest(args.bt_type, args.periods, args.window, as_json=args.json, use_mask=not args.no_mask, factors=getattr(args, 'bt_factors', 6))
    if args.command == "backtest-compare":
        return cmd_backtest_compare(args.btc_type, args.periods, args.window, as_json=args.json)
    if args.command == "backtest-factors":
        return cmd_backtest_factors(args.btf_type, args.periods, args.window, use_mask=not args.btf_no_mask, as_json=args.json, derive=args.btf_derive)
    return 1


def cmd_backtest(lottery_type: str, periods: int = 100, window: int = 30, as_json: bool = False, use_mask: bool = True, factors: int = 6) -> int:
    from lottery.config import get_optimized_weights
    from lottery.db import run_backtest

    def progress(current, total, pid):
        pct = current * 100 // total
        bar = "#" * (pct // 4) + "-" * (25 - pct // 4)
        print(f"\r  [{bar}] {current}/{total} 期 (当前: {pid})", end="", flush=True)

    mask_label = "启用区间掩码" if use_mask else "全号池（无掩码）"
    factor_label = f"{factors}F" if lottery_type in ("pl5", "qxc") else ""
    header_extra = f"  |  {factor_label}" if factor_label else ""
    print(f"\n{'='*60}")
    print(f"彩种: {lottery_type}  |  回测范围: 近 {periods} 期  |  窗口: {window} 期  |  {mask_label}{header_extra}")
    print(f"{'='*60}")

    kwargs: dict = {"periods": periods, "window": window, "progress_callback": progress, "use_mask": use_mask}
    if lottery_type in ("pl5", "qxc"):
        kwargs["weights"] = get_optimized_weights(lottery_type, n_factors=factors)
    result = run_backtest(lottery_type, **kwargs)
    print("\n")

    if not result.get("ok"):
        print(f"回测失败: {result.get('error')}")
        return 1

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    s = result.get("summary", {})
    tested = result.get("periods_tested", 0)
    saved = result.get("saved", 0)
    print(f"回测完成: {tested} 期, 入库 {saved} 条\n")

    _print_backtest_summary(lottery_type, s)
    return 0


def cmd_backtest_compare(lottery_type: str, periods: int = 100, window: int = 30, as_json: bool = False) -> int:
    from lottery.db import run_backtest

    if lottery_type in ("pl5", "qxc"):
        print(f"\n{lottery_type} 本身不使用区间掩码，跳过对比回测。")
        return 0

    def progress(current, total, pid):
        pct = current * 100 // total
        bar = "#" * (pct // 4) + "-" * (25 - pct // 4)
        print(f"\r  [{bar}] {current}/{total} 期 (当前: {pid})", end="", flush=True)

    print(f"\n{'='*60}")
    print(f"彩种: {lottery_type}  |  对比回测: mask vs no-mask")
    print(f"回测范围: 近 {periods} 期  |  窗口: {window} 期")
    print(f"{'='*60}")

    print("\n--- 路径 1/2: 启用区间掩码 ---")
    r_mask = run_backtest(lottery_type, periods=periods, window=window, progress_callback=progress, use_mask=True)
    print("\n")

    print("--- 路径 2/2: 全号池（无区间掩码）---")
    r_nomask = run_backtest(lottery_type, periods=periods, window=window, progress_callback=progress, use_mask=False)
    print("\n")

    if not r_mask.get("ok") or not r_nomask.get("ok"):
        print(f"回测失败: mask={r_mask.get('error')} nomask={r_nomask.get('error')}")
        return 1

    if as_json:
        print(json.dumps({
            "lottery_type": lottery_type,
            "periods": periods,
            "window": window,
            "mask": {"saved": r_mask["saved"], "summary": r_mask["summary"]},
            "nomask": {"saved": r_nomask["saved"], "summary": r_nomask["summary"]},
        }, ensure_ascii=False, indent=2))
        return 0

    _print_backtest_comparison(lottery_type, r_mask, r_nomask)
    return 0


def _print_backtest_comparison(lottery_type: str, r_mask: dict, r_nomask: dict) -> None:
    s_m = r_mask.get("summary", {})
    s_n = r_nomask.get("summary", {})

    print(f"{'='*70}")
    print(f"对比结果: {lottery_type.upper()}")
    print(f"{'='*70}")
    print(f"{'指标':<32} {'mask (启用)':>18} {'no-mask (全池)':>18}")
    print(f"{'-'*32} {'-'*18} {'-'*18}")

    def _get(d, key, default="-"):
        return d.get(key, default) if d else default

    if lottery_type == "dlt":
        rm_reg = s_m.get("regular", {})
        rn_reg = s_n.get("regular", {})
        print(f"{'前区平均命中(/5)':<32} {str(_get(rm_reg, 'avg_front', '-')):>18} {str(_get(rn_reg, 'avg_front', '-')):>18}")
        print(f"{'后区平均命中(/2)':<32} {str(_get(rm_reg, 'avg_back', '-')):>18} {str(_get(rn_reg, 'avg_back', '-')):>18}")

        bm_reg = s_m.get("best", {})
        bn_reg = s_n.get("best", {})
        print(f"{'优选-前区平均命中(/5)':<32} {str(_get(bm_reg, 'avg_front', '-')):>18} {str(_get(bn_reg, 'avg_front', '-')):>18}")
        print(f"{'优选-后区平均命中(/2)':<32} {str(_get(bm_reg, 'avg_back', '-')):>18} {str(_get(bn_reg, 'avg_back', '-')):>18}")

        pm = rm_reg.get("prize_dist", {})
        pn = rn_reg.get("prize_dist", {})
        _print_prize_rate(pm, pn)

    elif lottery_type == "ssq":
        rm_reg = s_m.get("regular", {})
        rn_reg = s_n.get("regular", {})
        print(f"{'红球平均命中(/6)':<32} {str(_get(rm_reg, 'avg_red', '-')):>18} {str(_get(rn_reg, 'avg_red', '-')):>18}")
        print(f"{'蓝球命中率':<32} {str(_get(rm_reg, 'avg_blue', '-')):>18} {str(_get(rn_reg, 'avg_blue', '-')):>18}")

        bm_reg = s_m.get("best", {})
        bn_reg = s_n.get("best", {})
        print(f"{'优选-红球平均命中(/6)':<32} {str(_get(bm_reg, 'avg_red', '-')):>18} {str(_get(bn_reg, 'avg_red', '-')):>18}")
        print(f"{'优选-蓝球命中率':<32} {str(_get(bm_reg, 'avg_blue', '-')):>18} {str(_get(bn_reg, 'avg_blue', '-')):>18}")

        pm = rm_reg.get("prize_dist", {})
        pn = rn_reg.get("prize_dist", {})
        _print_prize_rate(pm, pn)

    elif lottery_type == "kl8":
        rm_reg = s_m.get("regular", {})
        rn_reg = s_n.get("regular", {})
        print(f"{'11码vs20码平均重合':<32} {str(_get(rm_reg, 'avg_overlap', '-')):>18} {str(_get(rn_reg, 'avg_overlap', '-')):>18}")

        bm_reg = s_m.get("best", {})
        bn_reg = s_n.get("best", {})
        print(f"{'优选-11码vs20码平均重合':<32} {str(_get(bm_reg, 'avg_overlap', '-')):>18} {str(_get(bn_reg, 'avg_overlap', '-')):>18}")

    # Stability
    sm_stab = s_m.get("regular", {}).get("stability", {})
    sn_stab = s_n.get("regular", {}).get("stability", {})
    def _fmt_rate(v):
        return f"{float(v):.2%}" if isinstance(v, (int, float)) else str(v)
    print(f"{'最大连续不中期数':<32} {str(_get(sm_stab, 'max_drawdown', '-')):>18} {str(_get(sn_stab, 'max_drawdown', '-')):>18}")
    print(f"{'平均中奖间隔':<32} {str(_get(sm_stab, 'prize_gap_avg', '-')):>18} {str(_get(sn_stab, 'prize_gap_avg', '-')):>18}")

    print()


def _print_prize_rate(pm: dict, pn: dict) -> None:
    def _rate(pd):
        if not pd:
            return "-"
        total = sum(pd.values())
        won = sum(v for k, v in pd.items() if k != "未中奖")
        return f"{won/total:.2%}" if total > 0 else "-"

    print(f"{'中奖率':<32} {_rate(pm):>18} {_rate(pn):>18}")


def _print_backtest_summary(lottery_type: str, s: dict) -> None:
    reg = s.get("regular", {})
    best = s.get("best", {})

    if lottery_type in ("dlt",):
        if reg:
            print("--- 5注单式 ---")
            print(f"  共 {reg.get('count', 0)} 注, 前区均值 {reg.get('avg_front', '-')}/5, 后区均值 {reg.get('avg_back', '-')}/2")
            pd = reg.get("prize_dist", {})
            if pd:
                print(f"  奖级分布: {', '.join(f'{k}:{v}' for k,v in pd.items())}")
            bh = reg.get("best_hit", {})
            if bh:
                print(f"  最优注: 第{bh.get('ticket_index','?')}注 前区中{bh.get('front_matches','?')} 后区中{bh.get('back_matches','?')} → {bh.get('prize_level','?')}")
        if best:
            print("\n--- 单式优选 ---")
            print(f"  共 {best.get('count', 0)} 期, 前区均值 {best.get('avg_front', '-')}/5, 后区均值 {best.get('avg_back', '-')}/2")
            pd = best.get("prize_dist", {})
            if pd:
                print(f"  奖级分布: {', '.join(f'{k}:{v}' for k,v in pd.items())}")

    elif lottery_type == "ssq":
        if reg:
            print("--- 5注单式 ---")
            print(f"  共 {reg.get('count', 0)} 注, 红球均值 {reg.get('avg_red', '-')}/6, 蓝球命中率 {reg.get('avg_blue', '-')}")
            pd = reg.get("prize_dist", {})
            if pd:
                print(f"  奖级分布: {', '.join(f'{k}:{v}' for k,v in pd.items())}")
            bh = reg.get("best_hit", {})
            if bh:
                print(f"  最优注: 第{bh.get('ticket_index','?')}注 红球中{bh.get('red_matches','?')} 蓝球{'中' if bh.get('blue_match') else '不中'} → {bh.get('prize_level','?')}")
        if best:
            print("\n--- 单式优选 ---")
            print(f"  共 {best.get('count', 0)} 期, 红球均值 {best.get('avg_red', '-')}/6, 蓝球命中率 {best.get('avg_blue', '-')}")
            pd = best.get("prize_dist", {})
            if pd:
                print(f"  奖级分布: {', '.join(f'{k}:{v}' for k,v in pd.items())}")

    elif lottery_type == "kl8":
        if reg:
            print("--- 选十参考11码 ---")
            print(f"  共 {reg.get('count', 0)} 期, 与开奖20码平均重合 {reg.get('avg_overlap', '-')} 个")
        if best:
            print("\n--- 单式优选 ---")
            print(f"  共 {best.get('count', 0)} 期, 与开奖20码平均重合 {best.get('avg_overlap', '-')} 个")

    elif lottery_type == "pl5":
        if reg:
            print("--- 5注单式 ---")
            print(f"  共 {reg.get('count', 0)} 注, 平均逐位命中 {reg.get('avg_pos', '-')}/5, 全中 {reg.get('all_matched', 0)} 次")
            pmd = reg.get("pos_match_dist", {})
            if pmd:
                print(f"  命中分布: {' '.join(f'{k}位:{v}' for k,v in pmd.items())}")
            ppa = reg.get("per_pos_accuracy", [])
            if ppa and len(ppa) == 5:
                print(f"  逐位准确率: {' '.join(f'd{i+1}={ppa[i]:.3f}' for i in range(5))}")
            mge = reg.get("match_ge_3_rate")
            if mge is not None:
                print(f"  >=3中率: {mge*100:.1f}%  单注最高: {reg.get('max_pos_hit', '-')} 位")
        if best:
            print("\n--- 单式优选 ---")
            print(f"  共 {best.get('count', 0)} 期, 平均逐位命中 {best.get('avg_pos', '-')}/5")

    elif lottery_type == "qxc":
        if reg:
            print("--- 5注单式 ---")
            print(f"  共 {reg.get('count', 0)} 注, 前区均值 {reg.get('avg_front', '-')}/6, 后区命中率 {reg.get('avg_special', '-')}")
            fd = reg.get("front_dist", {})
            if fd:
                print(f"  前区命中分布: {' '.join(f'{k}位:{v}' for k,v in fd.items())}")
            ppa = reg.get("per_pos_front_accuracy", [])
            if ppa and len(ppa) == 6:
                print(f"  逐位准确率: {' '.join(f'd{i+1}={ppa[i]:.3f}' for i in range(6))}")
            ch = reg.get("combined_hit_rate")
            if ch is not None:
                print(f"  前>=3+后中率: {ch*100:.1f}%  单注最高前区: {reg.get('max_front_hit', '-')} 位")
        if best:
            print("\n--- 单式优选 ---")
            print(f"  共 {best.get('count', 0)} 期, 前区均值 {best.get('avg_front', '-')}/6, 后区命中率 {best.get('avg_special', '-')}")
    print()


def cmd_backtest_factors(lottery_type: str, periods: int = 100, window: int = 30, use_mask: bool = True, as_json: bool = False, derive: bool = False) -> int:
    from lottery.config import get_optimized_weights, DEFAULT_8F_WEIGHTS, DLT_8F_WEIGHTS, SSQ_8F_WEIGHTS, KL8_8F_WEIGHTS
    from lottery.config import DEFAULT_PL5_6F_WEIGHTS, DEFAULT_QXC_6F_WEIGHTS
    from lottery.db import run_backtest
    from lottery.factor_evaluator import (
        factor_keys,
        derive_weights_from_single_factor,
        run_multi_weight_backtest,
    )

    mask_label = "启用区间掩码" if use_mask else "全号池（无掩码）"
    print(f"\n{'='*60}")
    print(f"单因子回测: {lottery_type}  |  范围: 近 {periods} 期  |  窗口: {window} 期  |  {mask_label}")
    print(f"{'='*60}")

    keys = factor_keys(lottery_type)
    n_total = len(keys)

    def progress(current, total, pid):
        pct = current * 100 // total
        bar = "#" * (pct // 4) + "-" * (25 - pct // 4)
        print(f"\r  [{bar}] {current}/{total} 期 (当前: {pid})", end="", flush=True)

    # 逐因子回测
    results = {}
    for idx, factor in enumerate(keys, 1):
        print(f"\n--- 因子 {idx}/{n_total}: {factor} ---")
        weights = {k: 1.0 if k == factor else 0.0 for k in keys}
        bt = run_backtest(
            lottery_type=lottery_type,
            periods=periods,
            window=window,
            use_mask=use_mask,
            weights=weights,
            progress_callback=progress,
        )
        print()
        results[factor] = {
            "weights": weights,
            "summary": bt.get("summary", {}),
            "periods_tested": bt.get("periods_tested", 0),
        }

    if as_json:
        print(json.dumps({
            "lottery_type": lottery_type, "periods": periods, "window": window,
            "use_mask": use_mask, "factors": results,
        }, ensure_ascii=False, indent=2))
        return 0

    # 打印单因子排名
    _print_single_factor_table(lottery_type, results, keys)

    if not derive:
        print()
        return 0

    # 推导新权重
    print(f"\n{'='*60}")
    print("自动推导新权重（proportional 方法）")
    print(f"{'='*60}")
    derived_weights = derive_weights_from_single_factor(results, lottery_type, method="proportional")

    # 获取现有权重做对比
    if lottery_type in ("dlt", "ssq", "kl8"):
        default_w = DEFAULT_8F_WEIGHTS
        optimized_w = {"dlt": DLT_8F_WEIGHTS, "ssq": SSQ_8F_WEIGHTS, "kl8": KL8_8F_WEIGHTS}[lottery_type]
    else:
        default_w = {"pl5": DEFAULT_PL5_6F_WEIGHTS, "qxc": DEFAULT_QXC_6F_WEIGHTS}[lottery_type]
        optimized_w = get_optimized_weights(lottery_type) or default_w

    print(f"\n{'权重对比':>12}  {'default':>10}  {'optimized':>10}  {'derived':>10}")
    for k in keys:
        print(f"  {k:>10}: {default_w.get(k, 0):>10.4f}  {optimized_w.get(k, 0):>10.4f}  {derived_weights.get(k, 0):>10.4f}")

    # 三组权重对比回测
    print(f"\n{'='*60}")
    print("三组权重对比回测:")
    print(f"{'='*60}")

    compare = run_multi_weight_backtest(
        lottery_type=lottery_type,
        weight_sets={
            "default (硬编码)": default_w,
            "optimized (Dirichlet)": optimized_w,
            "derived (单因子推导)": derived_weights,
        },
        periods=periods,
        window=window,
        use_mask=use_mask,
        progress_callback=progress,
    )
    print()

    _print_multi_weight_comparison(lottery_type, compare)

    print()
    return 0


def _print_single_factor_table(lottery_type: str, results: dict, keys: list[str]) -> None:
    """打印单因子回测结果排名表。"""
    from lottery.factor_evaluator import extract_score

    rows = []
    for factor in keys:
        r = results.get(factor, {})
        s = r.get("summary", {})
        score = extract_score(lottery_type, s)
        rows.append((factor, score, s))

    ranked = sorted(rows, key=lambda x: -x[1])

    if lottery_type == "dlt":
        print(f"\n{'因子':>10}  {'综合分':>8}  {'前区命中(/5)':>12}  {'后区命中(/2)':>12}  {'中奖率':>8}")
        for factor, score, s in ranked:
            reg = s.get("regular", {})
            pd = reg.get("prize_dist", {})
            total = sum(pd.values()) if pd else 0
            won = sum(v for k, v in pd.items() if k != "未中奖") if pd else 0
            prize_rate = f"{won/total*100:.1f}%" if total > 0 else "-"
            print(f"  {factor:>10}  {score:>8.4f}  {reg.get('avg_front', '-'):>12}  {reg.get('avg_back', '-'):>12}  {prize_rate:>8}")
    elif lottery_type == "ssq":
        print(f"\n{'因子':>10}  {'综合分':>8}  {'红球命中(/6)':>12}  {'蓝球命中率':>10}  {'中奖率':>8}")
        for factor, score, s in ranked:
            reg = s.get("regular", {})
            pd = reg.get("prize_dist", {})
            total = sum(pd.values()) if pd else 0
            won = sum(v for k, v in pd.items() if k != "未中奖") if pd else 0
            prize_rate = f"{won/total*100:.1f}%" if total > 0 else "-"
            print(f"  {factor:>10}  {score:>8.4f}  {reg.get('avg_red', '-'):>12}  {reg.get('avg_blue', '-'):>10}  {prize_rate:>8}")
    elif lottery_type == "kl8":
        print(f"\n{'因子':>10}  {'综合分':>8}  {'平均重合(/11)':>13}")
        for factor, score, s in ranked:
            reg = s.get("regular", {})
            print(f"  {factor:>10}  {score:>8.4f}  {reg.get('avg_overlap', '-'):>13}")
    elif lottery_type == "pl5":
        print(f"\n{'因子':>10}  {'综合分':>8}  {'逐位命中(/5)':>12}  {'全中':>6}  {'>=3位率':>8}")
        for factor, score, s in ranked:
            reg = s.get("regular", {})
            mge = reg.get("match_ge_3_rate", 0) or 0
            print(f"  {factor:>10}  {score:>8.4f}  {reg.get('avg_pos', '-'):>12}  {reg.get('all_matched', 0):>6}  {mge*100:>7.1f}%")
    elif lottery_type == "qxc":
        print(f"\n{'因子':>10}  {'综合分':>8}  {'前区命中(/6)':>12}  {'后区命中率':>10}")
        for factor, score, s in ranked:
            reg = s.get("regular", {})
            print(f"  {factor:>10}  {score:>8.4f}  {reg.get('avg_front', '-'):>12}  {reg.get('avg_special', '-'):>10}")


def _print_multi_weight_comparison(lottery_type: str, compare: dict) -> None:
    """打印多组权重对比回测结果。"""
    labels = list(compare.keys())

    if lottery_type == "dlt":
        print(f"\n{'指标':<32}  " + "  ".join(f"{lbl:>22}" for lbl in labels))
        print(f"{'-'*32}  " + "  ".join(f"{'-'*22}" for _ in labels))
        for metric, field, fmt in [
            ("前区平均命中(/5)", "avg_front", lambda v: f"{float(v):.4f}"),
            ("后区平均命中(/2)", "avg_back", lambda v: f"{float(v):.4f}"),
        ]:
            vals = "  ".join(f"{fmt(compare[lbl]['summary'].get('regular', {}).get(field, '-')):>22}" for lbl in labels)
            print(f"  {metric:<30}  {vals}")
        for metric, field, fmt in [
            ("中奖率", None, None),
        ]:
            def _prize_rate(lbl):
                pd = compare[lbl]["summary"].get("regular", {}).get("prize_dist", {})
                total = sum(pd.values()) if pd else 0
                won = sum(v for k, v in pd.items() if k != "未中奖") if pd else 0
                return f"{won/total*100:.1f}%" if total > 0 else "-"
            vals = "  ".join(f"{_prize_rate(lbl):>22}" for lbl in labels)
            print(f"  {metric:<30}  {vals}")

    elif lottery_type == "ssq":
        print(f"\n{'指标':<32}  " + "  ".join(f"{lbl:>22}" for lbl in labels))
        print(f"{'-'*32}  " + "  ".join(f"{'-'*22}" for _ in labels))
        for metric, field, fmt in [
            ("红球平均命中(/6)", "avg_red", lambda v: f"{float(v):.4f}"),
            ("蓝球命中率", "avg_blue", lambda v: f"{float(v):.4f}"),
        ]:
            vals = "  ".join(f"{fmt(compare[lbl]['summary'].get('regular', {}).get(field, '-')):>22}" for lbl in labels)
            print(f"  {metric:<30}  {vals}")
        def _ssq_prize_rate(lbl):
            pd = compare[lbl]["summary"].get("regular", {}).get("prize_dist", {})
            total = sum(pd.values()) if pd else 0
            won = sum(v for k, v in pd.items() if k != "未中奖") if pd else 0
            return f"{won/total*100:.1f}%" if total > 0 else "-"
        vals = "  ".join(f"{_ssq_prize_rate(lbl):>22}" for lbl in labels)
        print(f"  {'中奖率':<30}  {vals}")

    elif lottery_type == "kl8":
        print(f"\n{'指标':<32}  " + "  ".join(f"{lbl:>22}" for lbl in labels))
        print(f"{'-'*32}  " + "  ".join(f"{'-'*22}" for _ in labels))
        metric = "平均重合(/11)"
        field = "avg_overlap"
        vals = "  ".join(f"{float(compare[lbl]['summary'].get('regular', {}).get(field, 0)):.4f}".rjust(22) for lbl in labels)
        print(f"  {metric:<30}  {vals}")

    elif lottery_type == "pl5":
        print(f"\n{'指标':<32}  " + "  ".join(f"{lbl:>22}" for lbl in labels))
        print(f"{'-'*32}  " + "  ".join(f"{'-'*22}" for _ in labels))
        for metric, field, fmt in [
            ("平均逐位命中(/5)", "avg_pos", lambda v: f"{float(v):.4f}"),
            ("全中次数", "all_matched", lambda v: str(int(v))),
        ]:
            vals = "  ".join(f"{fmt(compare[lbl]['summary'].get('regular', {}).get(field, 0)):>22}" for lbl in labels)
            print(f"  {metric:<30}  {vals}")
        def _pl5_ge3(lbl):
            mge = compare[lbl]["summary"].get("regular", {}).get("match_ge_3_rate", 0) or 0
            return f"{mge*100:.1f}%"
        vals = "  ".join(f"{_pl5_ge3(lbl):>22}" for lbl in labels)
        print(f"  {'>=3位率':<30}  {vals}")

    elif lottery_type == "qxc":
        print(f"\n{'指标':<32}  " + "  ".join(f"{lbl:>22}" for lbl in labels))
        print(f"{'-'*32}  " + "  ".join(f"{'-'*22}" for _ in labels))
        for metric, field, fmt in [
            ("前区平均命中(/6)", "avg_front", lambda v: f"{float(v):.4f}"),
            ("后区命中率", "avg_special", lambda v: f"{float(v):.4f}"),
        ]:
            vals = "  ".join(f"{fmt(compare[lbl]['summary'].get('regular', {}).get(field, 0)):>22}" for lbl in labels)
            print(f"  {metric:<30}  {vals}")


if __name__ == "__main__":
    raise SystemExit(main())
