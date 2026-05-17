"""分析/预测 Markdown 构建器：大乐透、双色球、快乐八、排列5、七星彩的分析与预测归档生成。"""

from __future__ import annotations

from pathlib import Path

# ── 仓库路径常量 ──────────────────────────────────────────────
# __init__.py 在 src/lottery/builders/ 下，parents[3] 回到仓库根目录

REPO = Path(__file__).resolve().parents[3]
PROC = REPO / "data" / "processed"
HIST = REPO / "history"
MANIFEST = PROC / "manifest.json"

# ── 通用辅助 ──────────────────────────────────────────────────
# ── 分析构建 ──────────────────────────────────────────────────
from ._analysis import (  # noqa: E402
    build_dlt_analysis,
    build_kl8_analysis,
    build_pl5_analysis,
    build_qxc_analysis,
    build_ssq_analysis,
)

# ── 兼容旧接口 ────────────────────────────────────────────────
from ._compat import (  # noqa: E402
    dlt_explicit_from_patterns,
    ssq_explicit_from_patterns,
)

# ── 预测构建 ──────────────────────────────────────────────────
from ._prediction import (  # noqa: E402
    _kl8_collect_one_path_outputs,
    _kl8_collect_one_path_outputs_b,
    prediction_block_dlt,
    prediction_block_kl8,
    prediction_block_pl5,
    prediction_block_qxc,
    prediction_block_ssq,
)
from ._utils import (  # noqa: E402
    _kl8_draw_rows,
    _norm_df,
    _pl5_markov_blended,
    _pl5_markov_probs,
    _pl5_markov_probs_2nd,
    _pl5_norm01,
    _qstats,
    format_ac_top,
)

__all__ = [
    # path constants
    "REPO",
    "PROC",
    "HIST",
    "MANIFEST",
    # _utils
    "_norm_df",
    "_qstats",
    "format_ac_top",
    "_kl8_draw_rows",
    "_pl5_norm01",
    "_pl5_markov_probs",
    "_pl5_markov_probs_2nd",
    "_pl5_markov_blended",
    # _compat
    "dlt_explicit_from_patterns",
    "ssq_explicit_from_patterns",
    # _analysis
    "build_dlt_analysis",
    "build_ssq_analysis",
    "build_kl8_analysis",
    "build_pl5_analysis",
    "build_qxc_analysis",
    # _prediction
    "prediction_block_dlt",
    "prediction_block_ssq",
    "_kl8_collect_one_path_outputs",
    "_kl8_collect_one_path_outputs_b",
    "prediction_block_kl8",
    "prediction_block_pl5",
    "prediction_block_qxc",
]
