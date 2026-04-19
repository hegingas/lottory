#!/usr/bin/env python3
"""
统一入口：盘点 data、校验 processed、按范围重算 history 书面归档。

用法（在仓库根目录）：
  python src/scripts/lottery.py inventory
  python src/scripts/lottery.py validate
  python src/scripts/lottery.py regenerate-history [--only all|kl8|dlt-ssq]

**唯一推荐的刷新路径**：`regenerate-history`，用 ``--only`` 按用户/任务要刷的彩种选择范围（见子命令 help）。

- ``--only all``（默认）：大乐透+双色球四个 md；若存在 ``kl8_draws.csv`` 再写快乐八分析与预测两个 md。
- ``--only kl8``：仅 ``kuaileba_analysis.md`` + ``kuaileba_prediction.md``。
- ``--only dlt-ssq``：仅大乐透+双色球四个 md（不写快乐八）。

``regenerate-kl8-prediction`` 为兼容别名，等同 ``regenerate-history --only kl8``。

Agent 协作：改 CSV / manifest 后应先 ``validate``；通过后再 ``regenerate-history``。
注意：被选中写入的 md 会**整文件覆盖**；预测中的 combo 附录须在命令后按需补回。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cmd_inventory() -> int:
    sys.path.insert(0, str(_repo_root() / "src"))
    from lottery.inventory import print_inventory_json

    print_inventory_json()
    return 0


def cmd_validate() -> int:
    sys.path.insert(0, str(_repo_root() / "src"))
    from lottery.validate import run_validate

    r = run_validate()
    print(json.dumps(r, ensure_ascii=True, indent=2))
    return 0 if r.get("ok") else 1


def _load_regen_module():
    root = _repo_root()
    script = root / "src" / "scripts" / "regenerate_history_archives.py"
    spec = importlib.util.spec_from_file_location("_regen", script)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cmd_regenerate_history(only_api: str) -> int:
    mod = _load_regen_module()
    if mod is None:
        print(json.dumps({"ok": False, "error": "cannot load regenerate script"}, ensure_ascii=True))
        return 1
    internal = {"all": "all", "kl8": "kl8", "dlt-ssq": "dlt_ssq"}[only_api]
    return int(mod.main(only=internal))


def main() -> int:
    p = argparse.ArgumentParser(description="彩票仓库统一 Python 工具（盘点 / 校验 / 重算 history）")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("inventory", help="列出 data/ 下文件（UTF-8 JSON）")
    sub.add_parser("validate", help="校验 processed CSV 与 manifest rows_out")

    p_rh = sub.add_parser(
        "regenerate-history",
        help="统一刷新 history 分析/预测归档（默认近 30 期，见脚本 DEFAULT_STATS_WINDOW）",
        description="根据 --only 选择写入范围；为三彩种唯一推荐的机械重算入口。",
    )
    p_rh.add_argument(
        "--only",
        dest="only_scope",
        choices=["all", "kl8", "dlt-ssq"],
        default="all",
        metavar="SCOPE",
        help="all：DLT+SSQ 四文件，且存在 kl8 CSV 时追加 KL8 两文件；kl8：仅 KL8 分析+预测；dlt-ssq：仅 DLT+SSQ 四文件",
    )

    sub.add_parser(
        "regenerate-kl8-prediction",
        help="[兼容] 等同 regenerate-history --only kl8",
    )

    args = p.parse_args()
    if args.command == "inventory":
        return cmd_inventory()
    if args.command == "validate":
        return cmd_validate()
    if args.command == "regenerate-history":
        return cmd_regenerate_history(args.only_scope)
    if args.command == "regenerate-kl8-prediction":
        return cmd_regenerate_history("kl8")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
