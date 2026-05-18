"""单因子独立回测与权重推导。

提供逐因子独立回测评估（weight=1.0 单因子，其余=0.0），
基于回测结果推导新权重，以及对比不同权重组的回测表现。
"""

from __future__ import annotations

from typing import Any

from lottery.db import run_backtest

# 因子列表
_KEYS_8F = ["markov", "miss", "freq", "zone", "recency", "parity", "size", "sum"]
_KEYS_6F = ["markov", "miss", "freq", "recency", "parity", "size"]

_LOTTERY_SPEC: dict[str, dict] = {
    "dlt": {"n_factors": 8, "keys": _KEYS_8F},
    "ssq": {"n_factors": 8, "keys": _KEYS_8F},
    "kl8": {"n_factors": 8, "keys": _KEYS_8F},
    "pl5": {"n_factors": 6, "keys": _KEYS_6F},
    "qxc": {"n_factors": 6, "keys": _KEYS_6F},
}


def factor_keys(lottery_type: str) -> list[str]:
    return list(_LOTTERY_SPEC[lottery_type]["keys"])


def run_single_factor_backtests(
    lottery_type: str,
    periods: int = 100,
    window: int = 30,
    use_mask: bool = True,
    factors: list[str] | None = None,
    progress_callback: Any = None,
) -> dict:
    """逐因子独立回测。

    每个因子 weight=1.0，其余=0.0，独立跑一次回测。
    返回 {factor_name: {"weights": {...}, "summary": {...}}}。
    """
    keys = factors or factor_keys(lottery_type)
    results: dict[str, dict] = {}

    for factor in keys:
        weights = {k: 1.0 if k == factor else 0.0 for k in keys}

        bt_result = run_backtest(
            lottery_type=lottery_type,
            periods=periods,
            window=window,
            use_mask=use_mask,
            weights=weights,
            progress_callback=progress_callback,
        )

        results[factor] = {
            "weights": weights,
            "summary": bt_result.get("summary", {}),
            "periods_tested": bt_result.get("periods_tested", 0),
        }

    return results


def extract_score(lottery_type: str, summary: dict) -> float:
    """从回测 summary 中提取统一性能分（基于 regular 注）。"""
    lt = lottery_type
    reg = summary.get("regular", {})

    if lt == "dlt":
        avg_front = float(reg.get("avg_front", 0) or 0)
        avg_back = float(reg.get("avg_back", 0) or 0)
        return avg_front / 5 * 0.7 + avg_back / 2 * 0.3
    elif lt == "ssq":
        avg_red = float(reg.get("avg_red", 0) or 0)
        avg_blue = float(reg.get("avg_blue", 0) or 0)
        return avg_red / 6 * 0.85 + avg_blue * 0.15
    elif lt == "kl8":
        avg_overlap = float(reg.get("avg_overlap", 0) or 0)
        return avg_overlap / 11
    elif lt == "pl5":
        avg_pos = float(reg.get("avg_pos", 0) or 0)
        return avg_pos / 5
    elif lt == "qxc":
        avg_front = float(reg.get("avg_front", 0) or 0)
        avg_special = float(reg.get("avg_special", 0) or 0)
        return avg_front / 6 * 0.8 + avg_special * 0.2

    return 0.0


def derive_weights_from_single_factor(
    single_results: dict,
    lottery_type: str,
    method: str = "proportional",
    floor: float = 0.02,
) -> dict[str, float]:
    """从单因子回测结果推导新权重。

    Args:
        single_results: run_single_factor_backtests() 的返回值
        lottery_type: 彩种
        method: "proportional"（按性能比例）或 "rank"（按排名加权）
        floor: 权重下限，防止某因子权重为 0

    Returns:
        归一化到 1.0 的权重 dict
    """
    keys = factor_keys(lottery_type)

    scores: dict[str, float] = {}
    for factor in keys:
        if factor not in single_results:
            scores[factor] = 0.0
            continue
        summary = single_results[factor].get("summary", {})
        scores[factor] = extract_score(lottery_type, summary)

    if method == "proportional":
        total = sum(scores.values())
        if total > 0:
            raw = {k: v / total for k, v in scores.items()}
        else:
            raw = {k: 1.0 / len(keys) for k in keys}
    elif method == "rank":
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        n = len(ranked)
        rank_w = {k: float(n - i) for i, (k, _) in enumerate(ranked)}
        total = sum(rank_w.values())
        raw = {k: v / total for k, v in rank_w.items()}
    else:
        raise ValueError(f"未知推导方法: {method}")

    weights = {k: max(raw.get(k, 0.0), floor) for k in keys}
    total = sum(weights.values())
    weights = {k: round(v / total, 6) for k, v in weights.items()}

    return weights


def run_multi_weight_backtest(
    lottery_type: str,
    weight_sets: dict[str, dict[str, float]],
    periods: int = 100,
    window: int = 30,
    use_mask: bool = True,
    progress_callback: Any = None,
) -> dict:
    """多组权重对比回测。

    Args:
        weight_sets: {label: weights_dict} 多组权重

    Returns:
        {label: {"weights": ..., "summary": ..., "periods_tested": ...}}
    """
    results: dict[str, dict] = {}

    for label, weights in weight_sets.items():
        bt_result = run_backtest(
            lottery_type=lottery_type,
            periods=periods,
            window=window,
            use_mask=use_mask,
            weights=weights,
            progress_callback=progress_callback,
        )
        results[label] = {
            "weights": weights,
            "summary": bt_result.get("summary", {}),
            "periods_tested": bt_result.get("periods_tested", 0),
        }

    return results
