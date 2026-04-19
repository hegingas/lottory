"""枚举 `data/` 下文件，供总控与 Agent 盘点（UTF-8 JSON 输出）。"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import data_dir, repo_root


def run_inventory() -> dict:
    root = repo_root()
    data = data_dir()
    out: dict = {
        "repo_root": str(root),
        "data_dir_exists": data.is_dir(),
        "files": [],
    }
    if not data.is_dir():
        return out

    for p in sorted(data.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        try:
            st = p.stat()
            out["files"].append({"path": rel, "size": int(st.st_size)})
        except OSError:
            out["files"].append({"path": rel, "size": None})
    return out


def print_inventory_json() -> None:
    print(json.dumps(run_inventory(), ensure_ascii=True, indent=2))
