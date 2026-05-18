#!/usr/bin/env python3
"""
基于 data/processed/*.csv 重算并写入 history 下归档（N 默认见 `DEFAULT_STATS_WINDOW`，当前为 30）。

运行（在仓库根，统一入口）：
  python src/scripts/cli.py regenerate-history [--only all|kl8|dlt-ssq|pl5|qxc]
  # 或直接：python src/scripts/regenerate_history_archives.py [--only kl8]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

# 确保 src/ 在 sys.path 中以便直接运行脚本
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from lottery.builders import (
    HIST,
    MANIFEST,
    PROC,
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
from lottery.config import DEFAULT_RANDOM_SEED, _set_random_seed
from lottery.db import save_predictions_batch


def _load_draws(lottery_type: str) -> pd.DataFrame:
    """从 DB 优先读取，若 DB 为空或不可用则回退 CSV。"""
    import pandas as pd
    try:
        from lottery.db import get_draws
        df = get_draws(lottery_type)
        if len(df) > 0:
            return df
    except Exception:
        pass
    csv_path = PROC / f"{lottery_type}_draws.csv"
    if not csv_path.exists():
        raise SystemExit(f"缺少 data/processed/{lottery_type}_draws.csv")
    return pd.read_csv(csv_path, encoding="utf-8-sig")


def _normalize_only(only: str) -> str:
    o = (only or "all").strip().lower().replace("-", "_")
    if o == "dltssq":
        return "dlt_ssq"
    if o == "qxc":
        return "qxc"
    return o


def _save_prediction_to_db(lottery_type: str, pred_data: dict) -> dict[str, int]:
    """将单期预测结构化数据写入数据库。predicted_period_id = window_end + 1。"""
    return save_predictions_batch(
        lottery_type=lottery_type,
        predicted_period_id=pred_data["window_end"] + 1,
        tickets=pred_data["tickets"],
        best=pred_data.get("best"),
        prediction_date=pred_data["prediction_date"],
        data_window_start=pred_data["window_start"],
        data_window_end=pred_data["window_end"],
    )


def _auto_select_strategies(only_n: str) -> dict[str, bool]:
    """快速回测对比，自动选取最优策略。返回 {lottery_type: use_mask}。"""
    from lottery.db import run_backtest

    candidates = []
    if only_n in ("all", "dlt_ssq"):
        candidates.extend(["dlt", "ssq"])
    if only_n in ("all", "kl8"):
        candidates.append("kl8")
    # PL5/QXC 没有区间掩码，不参与

    if not candidates:
        return {}

    result: dict[str, bool] = {}
    for lt in candidates:
        r_mask = run_backtest(lt, periods=min(30, _available_periods(lt)), window=30, use_mask=True)
        r_nomask = run_backtest(lt, periods=min(30, _available_periods(lt)), window=30, use_mask=False)

        if not r_mask.get("ok") or not r_nomask.get("ok"):
            result[lt] = True  # fallback to default
            continue

        sm = r_mask.get("summary", {}).get("regular", {})
        sn = r_nomask.get("summary", {}).get("regular", {})

        if lt in ("dlt", "ssq"):
            # 以 prize_dist 中奖率判断
            pm = sm.get("prize_dist", {})
            pn = sn.get("prize_dist", {})
            wr_m = _win_rate(pm)
            wr_n = _win_rate(pn)
            better = wr_n > wr_m
        elif lt == "kl8":
            better = sm.get("avg_overlap", 0) > sn.get("avg_overlap", 0)
        else:
            better = True  # default

        result[lt] = not better  # better=False means no-mask won → use_mask=False

    return result


def _win_rate(prize_dist: dict) -> float:
    if not prize_dist:
        return 0.0
    total = sum(prize_dist.values())
    won = sum(v for k, v in prize_dist.items() if k != "未中奖")
    return won / total if total > 0 else 0.0


def _available_periods(lottery_type: str) -> int:
    """返回该彩种可用于回测的最大期数。"""
    try:
        df = _load_draws(lottery_type)
        return max(0, len(df) - 30)
    except Exception:
        return 0


def main(only: str = "all", seed: int | None = DEFAULT_RANDOM_SEED, use_mask: bool = True, auto_strategy: bool = False) -> int:
    only_n = _normalize_only(only)
    used_seed = _set_random_seed(seed)
    if only_n not in ("all", "kl8", "dlt_ssq", "pl5", "qxc"):
        print(
            json.dumps(
                {"ok": False, "error": f"invalid only={only!r}; use all | kl8 | dlt-ssq | pl5 | qxc"},
                ensure_ascii=True,
            )
        )
        return 1

    # ── 自动策略选择 ──
    strategy_override: dict[str, bool] = {}
    if auto_strategy:
        _set_random_seed(seed)
        strategy_override = _auto_select_strategies(only_n)
        print(json.dumps({"auto_strategy": strategy_override}, ensure_ascii=True))

    HIST.mkdir(parents=True, exist_ok=True)
    wrote: list[str] = []
    saved: dict[str, dict] = {}

    manifest_excl: list[dict] = []
    if MANIFEST.exists():
        try:
            m = json.loads(MANIFEST.read_text(encoding="utf-8"))
            for block in m.get("outputs", []):
                if block.get("lottery_type") == "dlt":
                    manifest_excl.extend(block.get("excluded", []))
        except (json.JSONDecodeError, OSError) as e:
            print(
                json.dumps(
                    {"ok": False, "error": f"读取 manifest.json 失败：{e}"},
                    ensure_ascii=True,
                )
            )
            return 1

    if only_n in ("all", "dlt_ssq"):
        dlt_path = PROC / "dlt_draws.csv"
        ssq_path = PROC / "ssq_draws.csv"
        if not dlt_path.exists() or not ssq_path.exists():
            raise SystemExit(
                "缺少 data/processed/dlt_draws.csv 或 ssq_draws.csv；请补全 CSV 或使用 lottery-draw-dlt-ssq / lottery-draw-sync。"
            )
        try:
            dlt = _load_draws("dlt")
            ssq = _load_draws("ssq")
        except Exception as e:
            print(
                json.dumps(
                    {"ok": False, "error": f"读取 DLT/SSQ CSV 失败：{e}"},
                    ensure_ascii=True,
                )
            )
            return 1

        (HIST / "daletou_analysis.md").write_text(build_dlt_analysis(dlt, manifest_excl), encoding="utf-8")
        (HIST / "shuangseqiu_analysis.md").write_text(build_ssq_analysis(ssq), encoding="utf-8")

        dlt_pred_md, dlt_pred_data = prediction_block_dlt(dlt, use_mask=strategy_override.get("dlt", use_mask))
        (HIST / "daletou_prediction.md").write_text(dlt_pred_md, encoding="utf-8")
        saved["dlt"] = _save_prediction_to_db("dlt", dlt_pred_data)

        ssq_pred_md, ssq_pred_data = prediction_block_ssq(ssq, use_mask=strategy_override.get("ssq", use_mask))
        (HIST / "shuangseqiu_prediction.md").write_text(ssq_pred_md, encoding="utf-8")
        saved["ssq"] = _save_prediction_to_db("ssq", ssq_pred_data)

        wrote.extend(
            [
                "history/daletou_analysis.md",
                "history/shuangseqiu_analysis.md",
                "history/daletou_prediction.md",
                "history/shuangseqiu_prediction.md",
            ]
        )

    if only_n in ("all", "kl8"):
        kl8_path = PROC / "kl8_draws.csv"
        if not kl8_path.is_file():
            if only_n == "kl8":
                raise SystemExit("缺少 data/processed/kl8_draws.csv；请先补数或使用 lottery-draw-sync。")
        else:
            try:
                kl8 = _load_draws("kl8")
            except Exception as e:
                print(
                    json.dumps(
                        {"ok": False, "error": f"读取 KL8 数据失败：{e}"},
                        ensure_ascii=True,
                    )
                )
                return 1
            (HIST / "kuaileba_analysis.md").write_text(build_kl8_analysis(kl8), encoding="utf-8")

            kl8_pred_md, kl8_pred_data = prediction_block_kl8(kl8, use_mask=strategy_override.get("kl8", use_mask))
            (HIST / "kuaileba_prediction.md").write_text(kl8_pred_md, encoding="utf-8")
            saved["kl8"] = _save_prediction_to_db("kl8", kl8_pred_data)

            wrote.extend(["history/kuaileba_analysis.md", "history/kuaileba_prediction.md"])

    if only_n in ("all", "pl5"):
        pl5_path = PROC / "pl5_draws.csv"
        if not pl5_path.is_file():
            if only_n == "pl5":
                raise SystemExit("缺少 data/processed/pl5_draws.csv；请先补数。")
        else:
            try:
                pl5 = _load_draws("pl5")
            except Exception as e:
                print(
                    json.dumps(
                        {"ok": False, "error": f"读取 PL5 数据失败：{e}"},
                        ensure_ascii=True,
                    )
                )
                return 1
            (HIST / "pailie5_analysis.md").write_text(build_pl5_analysis(pl5), encoding="utf-8")

            pl5_pred_md, pl5_pred_data = prediction_block_pl5(pl5)
            (HIST / "pailie5_prediction.md").write_text(pl5_pred_md, encoding="utf-8")
            saved["pl5"] = _save_prediction_to_db("pl5", pl5_pred_data)

            wrote.extend(["history/pailie5_analysis.md", "history/pailie5_prediction.md"])

    if only_n in ("all", "qxc"):
        qxc_path = PROC / "qxc_draws.csv"
        if not qxc_path.is_file():
            if only_n == "qxc":
                raise SystemExit("缺少 data/processed/qxc_draws.csv；请先补数。")
        else:
            try:
                qxc = _load_draws("qxc")
            except Exception as e:
                print(
                    json.dumps(
                        {"ok": False, "error": f"读取 QXC 数据失败：{e}"},
                        ensure_ascii=True,
                    )
                )
                return 1
            (HIST / "qixingcai_analysis.md").write_text(build_qxc_analysis(qxc), encoding="utf-8")

            qxc_pred_md, qxc_pred_data = prediction_block_qxc(qxc)
            (HIST / "qixingcai_prediction.md").write_text(qxc_pred_md, encoding="utf-8")
            saved["qxc"] = _save_prediction_to_db("qxc", qxc_pred_data)

            wrote.extend(["history/qixingcai_analysis.md", "history/qixingcai_prediction.md"])

    if not wrote:
        print(
            json.dumps(
                {"ok": False, "error": "未写入任何文件；检查 --only 与 processed CSV 是否存在"},
                ensure_ascii=True,
            )
        )
        return 1

    print(
        json.dumps(
            {"ok": True, "only": only_n, "seed": used_seed, "wrote": wrote, "predictions_saved": saved},
            ensure_ascii=True,
        )
    )
    return 0


def regenerate_kl8_prediction() -> int:
    return main(only="kl8")


def _cli_args_from_argv(argv: list[str]) -> tuple[str, int]:
    only = "all"
    seed = DEFAULT_RANDOM_SEED
    i = 0
    while i < len(argv):
        if argv[i] == "--only" and i + 1 < len(argv):
            only = argv[i + 1]
            i += 2
        elif argv[i] == "--seed" and i + 1 < len(argv):
            seed = int(argv[i + 1])
            i += 2
        else:
            i += 1
    return only, seed


if __name__ == "__main__":
    _only, _seed = _cli_args_from_argv(sys.argv[1:])
    raise SystemExit(main(only=_only, seed=_seed))
