"""彩票项目全局常量与配置（从 `regenerate_history_archives.py` 迁移）。"""

from __future__ import annotations

import random
import numpy as np

# 仓库根与数据路径（保留给非 paths 模块直接引用场景）
DEFAULT_RANDOM_SEED = 20260430
_ACTIVE_RANDOM_SEED = DEFAULT_RANDOM_SEED

# 默认统计窗口（期末尾连续 N 期）
DEFAULT_STATS_WINDOW = 30

# 近 K 期密度因子所用期数
PATTERN_RECENT_K = 5
KL8_PATTERN_RECENT_K = PATTERN_RECENT_K

# 8 项因子独立权重（合计 1.0）—— 马尔可夫转移为最大权重
# 以下为原始硬编码值（保留作参考）；实际使用请通过 get_weights(lottery_type) 获取优化后权重
PATTERN_W_MARKOV  = 0.25
PATTERN_W_MISS    = 0.18
PATTERN_W_FREQ    = 0.14
PATTERN_W_ZONE    = 0.12
PATTERN_W_RECENCY = 0.10
PATTERN_W_PARITY  = 0.08
PATTERN_W_SIZE    = 0.08
PATTERN_W_SUM     = 0.05

# 默认 8 因子权重字典（大乐透/双色球/快乐八），key 与 _weighted_composite 参数对应
DEFAULT_8F_WEIGHTS: dict[str, float] = {
    "markov": PATTERN_W_MARKOV,
    "miss": PATTERN_W_MISS,
    "freq": PATTERN_W_FREQ,
    "zone": PATTERN_W_ZONE,
    "recency": PATTERN_W_RECENCY,
    "parity": PATTERN_W_PARITY,
    "size": PATTERN_W_SIZE,
    "sum": PATTERN_W_SUM,
}

# ── 各彩种优化权重（Dirichlet 采样 + 回测搜索，2026-05-17） ──

# 大乐透 8 因子优化权重（基于 hits 目标：avg_front*10 + avg_back）
DLT_8F_WEIGHTS: dict[str, float] = {
    "markov": 0.059, "miss": 0.014, "freq": 0.006, "zone": 0.007,
    "recency": 0.086, "parity": 0.082, "size": 0.230, "sum": 0.517,
}

# 大乐透 8 因子优化权重（基于 prize 目标：九等奖及以上比例）
DLT_8F_WEIGHTS_PRIZE: dict[str, float] = {
    "markov": 0.011, "miss": 0.066, "freq": 0.009, "zone": 0.216,
    "recency": 0.221, "parity": 0.016, "size": 0.012, "sum": 0.450,
}

# 双色球 8 因子优化权重（基于 hits 目标）
SSQ_8F_WEIGHTS: dict[str, float] = {
    "markov": 0.054, "miss": 0.087, "freq": 0.287, "zone": 0.004,
    "recency": 0.359, "parity": 0.004, "size": 0.194, "sum": 0.012,
}

# 双色球 8 因子优化权重（基于 prize 目标）
SSQ_8F_WEIGHTS_PRIZE: dict[str, float] = {
    "markov": 0.063, "miss": 0.013, "freq": 0.183, "zone": 0.017,
    "recency": 0.565, "parity": 0.087, "size": 0.047, "sum": 0.026,
}

# 快乐八 8 因子优化权重（基于 overlap 目标）
KL8_8F_WEIGHTS: dict[str, float] = {
    "markov": 0.269, "miss": 0.103, "freq": 0.028, "zone": 0.090,
    "recency": 0.016, "parity": 0.207, "size": 0.220, "sum": 0.067,
}

# 默认 4 因子权重字典（排列5/七星彩）
DEFAULT_4F_WEIGHTS: dict[str, float] = {
    "markov": 0.40,
    "miss": 0.20,
    "freq": 0.20,
    "recency": 0.20,
}

# 排列5 4 因子优化权重（基于 pos 目标）
PL5_4F_WEIGHTS: dict[str, float] = {
    "markov": 0.094, "miss": 0.445, "freq": 0.436, "recency": 0.025,
}

# 七星彩 4 因子优化权重（基于 pos 目标）
QXC_4F_WEIGHTS: dict[str, float] = {
    "markov": 0.701, "miss": 0.087, "freq": 0.180, "recency": 0.032,
}

# ── 彩种 → 优化权重映射 ──

_OPTIMIZED_8F: dict[str, dict[str, float]] = {
    "dlt": DLT_8F_WEIGHTS,
    "ssq": SSQ_8F_WEIGHTS,
    "kl8": KL8_8F_WEIGHTS,
}

_OPTIMIZED_4F: dict[str, dict[str, float]] = {
    "pl5": PL5_4F_WEIGHTS,
    "qxc": QXC_4F_WEIGHTS,
}


def get_optimized_weights(lottery_type: str) -> dict[str, float] | None:
    """返回指定彩种的优化权重字典，无优化数据时返回 None。"""
    if lottery_type in _OPTIMIZED_8F:
        return dict(_OPTIMIZED_8F[lottery_type])
    if lottery_type in _OPTIMIZED_4F:
        return dict(_OPTIMIZED_4F[lottery_type])
    return None

# 马尔可夫链阶数混合权重（1 阶 + 2 阶，合计 1.0）
MARKOV_1ST_ORDER_WEIGHT = 0.40
MARKOV_2ND_ORDER_WEIGHT = 0.60

# 快乐八取 20/11：8 个十码段约束（全表 01–80）；活跃段由「区间命中掩码马尔可夫 + 展开」确定，仅在并集内取号
KL8_MIN_PER_PICK_ZONE = 1
KL8_MAX_PER_PICK_ZONE = 5
KL8_PICK_ZONES_CAP = [(1, 10), (11, 20), (21, 30), (31, 40), (41, 50), (51, 60), (61, 70), (71, 80)]

# 大乐透前区：每 5 号一区间（7 段），每段至多 2 个
DLT_FRONT_ZONES_CAP = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 35)]
DLT_FRONT_MAX_PER_ZONE = 2
# 大乐透后区：4 段（每段 3 个号），每段至多 2 个
DLT_BACK_ZONES_CAP = [(1, 3), (4, 6), (7, 9), (10, 12)]
DLT_BACK_MAX_PER_ZONE = 2

# 双色球红球：每 5 号一区间（7 段），每段至多 2 个
SSQ_RED_ZONES_CAP = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 33)]
SSQ_RED_MAX_PER_ZONE = 2
# 双色球蓝球：每 4 号一区间（4 段），每段至多 2 个
SSQ_BLUE_ZONES_CAP = [(1, 4), (5, 8), (9, 12), (13, 16)]
SSQ_BLUE_MAX_PER_ZONE = 2

# 掩码活跃段上限（球数有限，不可能 n 个球覆盖 >n 个区段）
DLT_FRONT_MAX_ACTIVE_ZONES = 5   # 前区 5 球
DLT_BACK_MAX_ACTIVE_ZONES = 2    # 后区 2 球
SSQ_RED_MAX_ACTIVE_ZONES = 6     # 红球 6 球
SSQ_BLUE_MAX_ACTIVE_ZONES = 1    # 蓝球 1 球
KL8_MAX_ACTIVE_ZONES = 8         # 20 球远超 8 段，无上限约束

# 预算带
DEFAULT_COMBO_BUDGET_MIN_YUAN = 10
DEFAULT_COMBO_BUDGET_MAX_YUAN = 30
DEFAULT_COMBO_BUDGET_YUAN = DEFAULT_COMBO_BUDGET_MAX_YUAN

# 预测单式注数
PREDICTION_SINGLE_LINES = 5

# 选号算法硬编码参数（常量化）
TICKET_COLLECT_MAX_ITER = 2000
TICKET_COLLECT_PENALTY_INIT = 0.09
TICKET_COLLECT_FALLBACK_MAX = 400000
# 贪心与「按分洗牌」仍无法凑满互异单式时，随机合法采样兜底（每尝试 1 次计 1）
TICKET_COLLECT_RANDOM_PHASE_MAX = 800_000
# 主循环：压低最新一期已出球综合分，缓解「高分号与最新期高度重合」导致的死锁
TICKET_COLLECT_LATEST_SCORE_PENALTY = 0.28
MARKOV_LAPLACE_ALPHA = 1.0
KL8_ELEVEN_RANDOM_TRIES = 8000
KL8_ELEVEN_OVERLAP_MAX = 4   # 直选 11 码与最新期 20 码重合上限

# ── 七星彩 ────────────────────────────────────────────────────
QXC_FRONT_POSITIONS = 6
QXC_FRONT_DIGITS = 10      # 每位 0–9
QXC_BACK_MAX = 14           # 后区 0–14
# 七星彩分位评分权重（与排列5一致）—— 马尔可夫转移为最大权重
QXC_W_MARKOV = 0.40
QXC_W_MISS   = 0.20
QXC_W_FREQ   = 0.20
QXC_W_RECENCY = 0.20

# 校验错误截断阈值
VALIDATE_MAX_ERRORS = 40


def _fmt2(n: int) -> str:
    return f"{int(n):02d}"


def _set_random_seed(seed: int | None) -> int:
    global _ACTIVE_RANDOM_SEED
    s = DEFAULT_RANDOM_SEED if seed is None else int(seed)
    random.seed(s)
    np.random.seed(s % (2**32 - 1))
    _ACTIVE_RANDOM_SEED = s
    return s
