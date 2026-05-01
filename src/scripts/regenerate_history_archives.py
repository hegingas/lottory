#!/usr/bin/env python3
"""
基于 data/processed/*.csv 重算并写入 history 下归档（N 默认见 `DEFAULT_STATS_WINDOW`，当前为 30）。

运行（在仓库根，统一入口）：
  python src/scripts/lottery.py regenerate-history [--only all|kl8|dlt-ssq|pl5]
  # 或直接：python src/scripts/regenerate_history_archives.py [--only kl8]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 确保 src/ 在 sys.path 中以便直接运行脚本
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from lottery.config import DEFAULT_RANDOM_SEED, _set_random_seed
from lottery.builders import (
    HIST,
    MANIFEST,
    PROC,
    build_dlt_analysis,
    build_ssq_analysis,
    build_kl8_analysis,
    build_pl5_analysis,
    prediction_block_dlt,
    prediction_block_ssq,
    prediction_block_kl8,
    prediction_block_pl5,
)
from lottery.paths import repo_root  # noqa: E402


def _normalize_only(only: str) -> str:
    o = (only or "all").strip().lower().replace("-", "_")
    if o == "dltssq":
        return "dlt_ssq"
    return o


def main(only: str = "all", seed: int | None = DEFAULT_RANDOM_SEED) -> int:
    only_n = _normalize_only(only)
    used_seed = _set_random_seed(seed)
    if only_n not in ("all", "kl8", "dlt_ssq", "pl5"):
        print(
            json.dumps(
                {"ok": False, "error": f"invalid only={only!r}; use all | kl8 | dlt-ssq | pl5"},
                ensure_ascii=True,
            )
        )
        return 1

    HIST.mkdir(parents=True, exist_ok=True)
    wrote: list[str] = []

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
            import pandas as pd

            dlt = pd.read_csv(dlt_path, encoding="utf-8-sig")
            ssq = pd.read_csv(ssq_path, encoding="utf-8-sig")
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
        (HIST / "daletou_prediction.md").write_text(prediction_block_dlt(dlt), encoding="utf-8")
        (HIST / "shuangseqiu_prediction.md").write_text(prediction_block_ssq(ssq), encoding="utf-8")
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
                import pandas as pd

                kl8 = pd.read_csv(kl8_path, encoding="utf-8-sig")
            except Exception as e:
                print(
                    json.dumps(
                        {"ok": False, "error": f"读取 KL8 CSV 失败：{e}"},
                        ensure_ascii=True,
                    )
                )
                return 1
            (HIST / "kuaileba_analysis.md").write_text(build_kl8_analysis(kl8), encoding="utf-8")
            (HIST / "kuaileba_prediction.md").write_text(prediction_block_kl8(kl8), encoding="utf-8")
            wrote.extend(["history/kuaileba_analysis.md", "history/kuaileba_prediction.md"])

    if only_n in ("all", "pl5"):
        pl5_path = PROC / "pl5_draws.csv"
        if not pl5_path.is_file():
            if only_n == "pl5":
                raise SystemExit("缺少 data/processed/pl5_draws.csv；请先补数。")
        else:
            try:
                import pandas as pd

                pl5 = pd.read_csv(pl5_path, encoding="utf-8-sig")
            except Exception as e:
                print(
                    json.dumps(
                        {"ok": False, "error": f"读取 PL5 CSV 失败：{e}"},
                        ensure_ascii=True,
                    )
                )
                return 1
            (HIST / "pailie5_analysis.md").write_text(build_pl5_analysis(pl5), encoding="utf-8")
            (HIST / "pailie5_prediction.md").write_text(prediction_block_pl5(pl5), encoding="utf-8")
            wrote.extend(["history/pailie5_analysis.md", "history/pailie5_prediction.md"])

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
            {"ok": True, "only": only_n, "seed": used_seed, "wrote": wrote},
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
