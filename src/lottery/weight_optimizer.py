"""权重优化引擎：Dirichlet 采样 + 回测驱动搜索最优因子权重。

用法示例:
    from src.lottery.weight_optimizer import optimize_8f
    best, history = optimize_8f("dlt", n_coarse=80, n_fine=10)
"""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np

from .config import DEFAULT_4F_WEIGHTS, DEFAULT_8F_WEIGHTS
from .db import run_backtest

_KEYS_8F = ["markov", "miss", "freq", "zone", "recency", "parity", "size", "sum"]
_KEYS_4F = ["markov", "miss", "freq", "recency"]


def _weights_to_dict(keys: list[str], vec: np.ndarray) -> dict[str, float]:
    return {k: float(v) for k, v in zip(keys, vec, strict=False)}


# ── 采样 ──────────────────────────────────────────────────────────

def sample_dirichlet_8f(n: int, rng: np.random.Generator | None = None) -> list[dict[str, float]]:
    """从 Dirichlet(α=1) 采样 n 组 8 因子权重。"""
    rng = rng or np.random.default_rng()
    samples = rng.dirichlet(np.ones(8), size=n)
    return [_weights_to_dict(_KEYS_8F, s) for s in samples]


def sample_dirichlet_4f(n: int, rng: np.random.Generator | None = None) -> list[dict[str, float]]:
    """从 Dirichlet(α=1) 采样 n 组 4 因子权重。"""
    rng = rng or np.random.default_rng()
    samples = rng.dirichlet(np.ones(4), size=n)
    return [_weights_to_dict(_KEYS_4F, s) for s in samples]


# ── 目标函数 ──────────────────────────────────────────────────────

def objective_dlt_hits(summary: dict) -> float:
    """DLT 命中数：前区*10 + 后区（模拟奖级权重）。"""
    reg = summary.get("regular", {})
    return reg.get("avg_front", 0.0) * 10.0 + reg.get("avg_back", 0.0)


def objective_dlt_prize(summary: dict) -> float:
    """DLT 奖级：九等奖及以上比例。"""
    reg = summary.get("regular", {})
    dist = reg.get("prize_dist", {})
    total = sum(dist.values())
    if total == 0:
        return 0.0
    won = sum(v for k, v in dist.items() if k != "未中奖")
    return won / total


def objective_ssq_hits(summary: dict) -> float:
    """SSQ 命中数：红球*10 + 蓝球。"""
    reg = summary.get("regular", {})
    return reg.get("avg_red", 0.0) * 10.0 + reg.get("avg_blue", 0.0)


def objective_ssq_prize(summary: dict) -> float:
    """SSQ 奖级：六等奖及以上比例。"""
    reg = summary.get("regular", {})
    dist = reg.get("prize_dist", {})
    total = sum(dist.values())
    if total == 0:
        return 0.0
    won = sum(v for k, v in dist.items() if k != "未中奖")
    return won / total


def objective_pl5(summary: dict) -> float:
    """PL5：平均位置命中数。"""
    reg = summary.get("regular", {})
    return reg.get("avg_pos", 0.0)


def objective_qxc(summary: dict) -> float:
    """QXC：前区平均命中 + 后区*2。"""
    reg = summary.get("regular", {})
    return reg.get("avg_front", 0.0) + reg.get("avg_special", 0.0) * 2.0


def objective_kl8(summary: dict) -> float:
    """KL8：平均重合数（注意受 ≤4 约束影响，意义有限）。"""
    reg = summary.get("regular", {})
    return reg.get("avg_overlap", 0.0)


# ── 彩种 → (n_factors, sampler, objectives) 映射 ─────────────────

_LOTTERY_SPEC: dict[str, dict] = {
    "dlt": {
        "n_factors": 8,
        "sampler": sample_dirichlet_8f,
        "objectives": {"hits": objective_dlt_hits, "prize": objective_dlt_prize},
    },
    "ssq": {
        "n_factors": 8,
        "sampler": sample_dirichlet_8f,
        "objectives": {"hits": objective_ssq_hits, "prize": objective_ssq_prize},
    },
    "kl8": {
        "n_factors": 8,
        "sampler": sample_dirichlet_8f,
        "objectives": {"overlap": objective_kl8},
    },
    "pl5": {
        "n_factors": 4,
        "sampler": sample_dirichlet_4f,
        "objectives": {"pos": objective_pl5},
    },
    "qxc": {
        "n_factors": 4,
        "sampler": sample_dirichlet_4f,
        "objectives": {"pos": objective_qxc},
    },
}


# ── 搜索主循环 ───────────────────────────────────────────────────

def optimize(
    lottery_type: str,
    n_coarse: int = 80,
    n_fine: int = 10,
    periods_coarse: int = 20,
    periods_fine: int = 100,
    window: int = 30,
    rng: np.random.Generator | None = None,
    progress_callback: Callable[[str], None] | None = None,
    whiten: bool = False,
) -> dict:
    """对指定彩种执行两阶段权重优化。

    Returns:
        {"lottery_type": str,
         "default_weights": dict,
         "default_results": {obj_name: score},
         "coarse_best": [{weights, results}],
         "fine_best": [{weights, results}],
         "top_overall": {obj_name: {weights, score}}}  }
    """
    rng = rng or np.random.default_rng(42)
    spec = _LOTTERY_SPEC[lottery_type]
    sampler = spec["sampler"]
    objectives = spec["objectives"]
    obj_names = list(objectives.keys())

    def _log(msg: str):
        if progress_callback:
            progress_callback(msg)

    results: dict = {
        "lottery_type": lottery_type,
        "default_weights": DEFAULT_8F_WEIGHTS if spec["n_factors"] == 8 else DEFAULT_4F_WEIGHTS,
        "default_results": {},
        "coarse_best": [],
        "fine_best": [],
        "top_overall": {},
    }

    # ── 基线：默认权重 ──
    _log(f"[{lottery_type}] 基线回测 ({periods_fine} 期)...")
    t0 = time.time()
    default_r = run_backtest(lottery_type, periods=periods_fine, window=window, whiten=whiten)
    for oname, ofunc in objectives.items():
        results["default_results"][oname] = ofunc(default_r.get("summary", {}))
    _log(f"[{lottery_type}] 基线 {results['default_results']} ({time.time()-t0:.1f}s)")

    # ── 粗筛阶段 ──
    _log(f"[{lottery_type}] 粗筛 {n_coarse} 组 × {periods_coarse} 期...")
    samples = sampler(n_coarse, rng=rng)
    coarse_scores: list[tuple[dict, dict]] = []  # [(weights, {obj: score})]

    t0 = time.time()
    for idx, w in enumerate(samples):
        bt = run_backtest(lottery_type, periods=periods_coarse, window=window, weights=w, whiten=whiten)
        sm = bt.get("summary", {})
        scores = {oname: objectives[oname](sm) for oname in obj_names}
        coarse_scores.append((w, scores))

        if (idx + 1) % 20 == 0 or idx == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / max(elapsed, 0.1)
            eta = (n_coarse - idx - 1) / max(rate, 0.01)
            _log(f"[{lottery_type}] 粗筛 {idx+1}/{n_coarse}  rate={rate:.1f}/s ETA={eta:.0f}s")

    _log(f"[{lottery_type}] 粗筛完成 ({time.time()-t0:.1f}s)")

    # ── 按各目标排序，取 top N ──
    top_indices: set[int] = set()
    for oname in obj_names:
        sorted_idx = sorted(range(len(coarse_scores)), key=lambda i: coarse_scores[i][1][oname], reverse=True)
        top_indices.update(sorted_idx[:n_fine])

    _log(f"[{lottery_type}] 精细验证 {len(top_indices)} 组 × {periods_fine} 期...")
    t0 = time.time()
    fine_results: list[tuple[dict, dict]] = []
    for idx in top_indices:
        w = coarse_scores[idx][0]
        bt = run_backtest(lottery_type, periods=periods_fine, window=window, weights=w)
        sm = bt.get("summary", {})
        scores = {oname: objectives[oname](sm) for oname in obj_names}
        fine_results.append((w, scores))

    _log(f"[{lottery_type}] 精细验证完成 ({time.time()-t0:.1f}s)")

    # ── 排序存储 ──
    results["coarse_best"] = [
        {"weights": w, "results": s} for w, s in
        sorted(coarse_scores, key=lambda ws: max(ws[1].values()), reverse=True)[:n_fine]
    ]
    results["fine_best"] = [
        {"weights": w, "results": s} for w, s in
        sorted(fine_results, key=lambda ws: max(ws[1].values()), reverse=True)[:n_fine]
    ]

    # 每个目标最优
    for oname in obj_names:
        best_w, best_s = max(fine_results, key=lambda ws: ws[1][oname])
        results["top_overall"][oname] = {
            "weights": best_w,
            "score": best_s[oname],
            "vs_default": best_s[oname] - results["default_results"].get(oname, 0.0),
        }

    return results


def optimize_all(
    lottery_types: list[str] | None = None,
    n_coarse: int = 80,
    n_fine: int = 10,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, dict]:
    """批量优化多个彩种。"""
    types = lottery_types or list(_LOTTERY_SPEC)
    all_results: dict[str, dict] = {}
    for lt in types:
        all_results[lt] = optimize(
            lt,
            n_coarse=n_coarse,
            n_fine=n_fine,
            progress_callback=progress_callback,
        )
    return all_results


# ── 结果报告 ─────────────────────────────────────────────────────

def format_optimization_report(result: dict) -> str:
    """将优化结果格式化为可读报告。"""
    lt = result["lottery_type"]
    lines = [f"## {lt.upper()} 权重优化结果", ""]

    lines.append("### 默认权重基线")
    dw = result["default_weights"]
    lines.append("```")
    for k, v in dw.items():
        lines.append(f"  {k}: {v:.4f}")
    lines.append("```")
    lines.append(f"基线得分: {result['default_results']}")
    lines.append("")

    lines.append("### 各目标最优权重")
    for oname, info in result.get("top_overall", {}).items():
        lines.append(f"**{oname}**: 得分 {info['score']:.4f} (vs 默认 {info['vs_default']:+.4f})")
        lines.append("```")
        for k, v in info["weights"].items():
            default_v = dw.get(k, 0)
            delta = v - default_v
            lines.append(f"  {k}: {v:.4f}  (默认 {default_v:.4f}, {'+' if delta >= 0 else ''}{delta:.4f})")
        lines.append("```")
        lines.append("")

    lines.append("### Top 5 精细验证结果")
    for i, entry in enumerate(result.get("fine_best", [])[:5]):
        lines.append(f"**#{i+1}**: {entry['results']}")
        lines.append(f"  {', '.join(f'{k}={v:.3f}' for k, v in entry['weights'].items())}")
    lines.append("")

    return "\n".join(lines)
