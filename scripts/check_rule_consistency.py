#!/usr/bin/env python3
"""规则一致性快速检查：对比 CLAUDE.md 与 .cursor/rules/*.mdc 之间的关键约束。

用法：
  python scripts/check_rule_consistency.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLAUDE = REPO / "CLAUDE.md"
CURSOR_RULES = REPO / ".cursor" / "rules"


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def check_keywords() -> list[str]:
    """检查关键约束词是否在两套规则中都存在。"""
    issues: list[str] = []

    claude_text = load_text(CLAUDE)
    rule_files = sorted(CURSOR_RULES.glob("*.mdc")) if CURSOR_RULES.is_dir() else []
    rule_text = "\n".join(load_text(f) for f in rule_files)

    if not rule_files:
        return [f".cursor/rules/ 目录不存在或为空 ({CURSOR_RULES})"]

    # 关键约束词列表
    keywords = [
        (r"DEFAULT_STATS_WINDOW", "默认统计窗口"),
        (r"DEFAULT_COMBO_BUDGET", "组号金额带"),
        (r"去核心化", "反集中约束"),
        (r"防重合", "防止与历史重合"),
        (r"区间掩码马尔可夫", "区间掩码马尔可夫"),
        (r"多因子加权", "多因子加权规则"),
        (r"最新期强制重算", "最新期强制重算"),
        (r"analysis.*同步刷新", "analysis 强制同步刷新"),
        (r"七星彩", "七星彩支持"),
        (r"排列5", "排列5支持"),
    ]

    for pattern, desc in keywords:
        in_claude = bool(re.search(pattern, claude_text, re.IGNORECASE))
        in_cursor = bool(re.search(pattern, rule_text, re.IGNORECASE))
        if not (in_claude and in_cursor):
            issues.append(
                f"[{desc}] 仅在 {'CLAUDE.md' if in_claude else '.cursor/rules/'} 中找到，另一方缺失"
            )

    return issues


def main() -> int:
    print("=" * 60)
    print("规则一致性检查")
    print(f"  CLAUDE.md: {CLAUDE}")
    print(f"  .cursor/rules/: {CURSOR_RULES}")
    print("=" * 60)

    issues = check_keywords()

    if issues:
        print(f"\n发现 {len(issues)} 个不一致项：")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        print("\n建议：手动同步两套规则，确保关键约束一致。")
        return 1
    else:
        print("\n所有关键约束在两套规则中均存在，一致性检查通过。")
        return 0


if __name__ == "__main__":
    sys.exit(main())
