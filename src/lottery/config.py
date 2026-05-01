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

# 8 项因子独立权重（合计 1.0）
PATTERN_W_MISS    = 0.22
PATTERN_W_FREQ    = 0.16
PATTERN_W_ZONE    = 0.15
PATTERN_W_RECENCY = 0.13
PATTERN_W_PARITY  = 0.09
PATTERN_W_SIZE    = 0.09
PATTERN_W_SUM     = 0.04
PATTERN_W_MARKOV  = 0.12

# 快乐八取 20/11：8 个十码段约束
KL8_MIN_PER_PICK_ZONE = 1
KL8_MAX_PER_PICK_ZONE = 5
KL8_PICK_ZONES_CAP = [(1, 10), (11, 20), (21, 30), (31, 40), (41, 50), (51, 60), (61, 70), (71, 80)]

# 大乐透前区：每 5 号一区间（7 段），每段至多 2 个
DLT_FRONT_ZONES_CAP = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 35)]
DLT_FRONT_MAX_PER_ZONE = 2
# 大乐透后区：每 4 号一区间（3 段），每段至多 2 个
DLT_BACK_ZONES_CAP = [(1, 4), (5, 8), (9, 12)]
DLT_BACK_MAX_PER_ZONE = 2

# 双色球红球：每 5 号一区间（7 段），每段至多 2 个
SSQ_RED_ZONES_CAP = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 33)]
SSQ_RED_MAX_PER_ZONE = 2
# 双色球蓝球：每 4 号一区间（4 段），每段至多 2 个
SSQ_BLUE_ZONES_CAP = [(1, 4), (5, 8), (9, 12), (13, 16)]
SSQ_BLUE_MAX_PER_ZONE = 2

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
