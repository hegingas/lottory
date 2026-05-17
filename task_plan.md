# Task Plan: 统计模型系统性优化

## Goal
从权重、因子结构、模型架构、窗口策略、评估体系五个维度系统性提升彩票预测模型的统计质量。

## 总览

| # | 任务 | 状态 | 预计收益 | 复杂度 |
|---|------|------|---------|--------|
| 1 | 八因子权重调优 | ✅ 完成 | DLT +9%, SSQ +10%, PL5 +12% | 中 |
| 2 | 因子去相关 (ZCA白化) | ✅ 完成 | SSQ +4%, DLT 不适用 | 中 |
| 3 | 快乐八模型重构 | ✅ 完成 | 11码命中 +3.7%, 0-hit -75% | 中 |
| 4 | 区间马尔可夫升二阶 | ✅ 完成 | DLT后区 +6.3%, SSQ蓝球 +12.8% | 低 |
| 5 | 排列5/七星彩位间相关性 | ❌ 跳过 | 经验证无统计显著性 | 中 |
| 6 | 统计窗口自适应 | ⏳ 待做 | 待评估 | 中 |
| 7 | 回测评估体系完善 | ⏳ 待做 | 无直接收益/基础建设 | 中 |

---

## Current Phase
Phase 已完成 (下一个: 任务 6 统计窗口自适应)

---

## 任务 1: 八因子权重调优 ✅

### Goal
用 Dirichlet 采样 + 回测搜索替代硬编码权重 `(0.25, 0.18, 0.14, 0.12, 0.10, 0.08, 0.08, 0.05)`

### 关键发现
- 马尔可夫转移被严重高估：DLT 0.25→0.06, SSQ 0.25→0.05, PL5 0.40→0.09
- 不同彩种最优因子结构完全不同：DLT 和值+大小主导，SSQ 近期密度+频次主导
- QXC 马尔可夫反涨：0.40→0.70（按位转移确实有用）

### 改动文件
- `src/lottery/config.py`: 新增各彩种优化权重常量 + `get_optimized_weights()`
- `src/lottery/scoring.py`: `_weighted_composite` 及各 `_*_scores` 支持 `weights` 参数
- `src/lottery/builders.py`: 各 `prediction_block_*` 默认使用优化权重
- `src/lottery/db.py`: `run_backtest` 支持 `weights` 透传
- `src/lottery/weight_optimizer.py`: **新增** 优化引擎

---

## 任务 2: 因子去相关 (ZCA白化) ✅

### Goal
消除 8 因子间的共线性（最强: miss↔recency r=-0.72），避免同一信息源重复计分

### 关键发现
- 所有 VIF < 5，共线性存在但不严重（条件数 14.9）
- DLT 白化倒退 -2.7%（相关性里包含有用结构信息）
- SSQ 白化改善 +4.0%（默认开启）

### 改动文件
- `src/lottery/scoring.py`: 新增 `_zca_whitening_matrix()`, `_apply_whitening()`, `_weighted_composite` 支持 `whiten`
- `src/lottery/builders.py`: SSQ 默认 `whiten=True`, DLT 保持 `False`
- `src/lottery/db.py`: `run_backtest` 支持 `whiten` 透传
- `src/lottery/weight_optimizer.py`: `optimize()` 支持 `whiten`

---

## 任务 3: 快乐八模型重构 ✅

### Goal
修复当前"跳过 20 码中间层直接选 11 码"的流程缺陷，实现两阶段 20→11 选号，多路径回测对比

### 关键发现
- **Path B (20→11 重排位) 最优**：11 码命中 +3.7%，0-hit 从 8 降到 2（-75%）
- 20 码中间层预测 avg 4.66/20 hit，但贪心转换会丢失信息
- `_kl8_eleven_zone_capped_from_twenty` 用简单排名分数替代多因子分数是瓶颈
- 纯频次基线（Path C）最差 avg 2.51，验证了多因子评分的价值
- 改善幅度不大（+3.7%），验证了问题诊断：KL8 瓶颈在结构而非权重

### 改动文件
- `src/lottery/selection.py`: 新增 `_kl8_eleven_from_twenty_rerank`（20 码池内完整多因子重排位）
- `src/lottery/builders.py`: 新增 `_kl8_collect_one_path_outputs_b`（Path B 收集函数），`prediction_block_kl8` 支持 `path` 参数（默认 "B"）
- `src/lottery/db.py`: `run_backtest` 新增 `kl8_path` 参数 + 20 码命中率指标
- `history/kuaileba_prediction.md`: 已刷新，默认 Path B
- `history/kuaileba_analysis.md`: 已刷新

---

## 任务 4: 区间马尔可夫升二阶 ✅

### Goal
区间掩码马尔可夫从一阶升级为一阶+二阶混合（与按号马尔可夫方法论对齐）

### 关键发现
- **小区间数收益明显**：DLT 后区 Jaccard +6.3%，SSQ 蓝球 Jaccard +12.8%
- **大区间数中性**：DLT 前区/SSQ 红球/KL8 几乎无变化（状态空间太大，二阶稀疏）
- 二阶在状态空间小（4 段=16 状态）时能学到有用模式，7/8 段（128/256 状态）时退化
- 方法论对齐的价值大于预测增益：现在按号 + 区间两个层次都是 40/60 混合

### 改动范围
- `src/lottery/interval_markov.py`: 新增 `markov_next_bitmap_2nd_order`、`markov_next_bitmap_blended`、`_markov_prob_dist`
- `src/lottery/builders.py`: DLT/SSQ/KL8 全部 9 个调用点从 `markov_next_bitmap` 迁移到 `markov_next_bitmap_blended`，markdown 描述同步更新
- `history/*.md`: 全部 10 个归档文件已刷新

---

## 任务 5: 排列5/七星彩位间相关性 ❌ 跳过

### Goal
突破当前"各位独立评分"的简化假设，引入位间转移模式

### 快速验证结果
- **排列5**：4 对相邻位互信息 < 0.01 bits（理论上限 3.32），卡方 p 全部 > 0.10，完全不显著
- **七星彩**：6 对相邻位互信息 0.07-0.11 bits，d1→d2 最近接显著（p=0.056）但未过 0.05，解释熵不到 2%
- **决策**：跳过，位间独立假设对这两种彩种是合理的，额外因子只会增加噪声

### 改动文件
- （无代码改动）

---

## 任务 6: 统计窗口自适应 ⏳

### Goal
不同彩种、不同分析目的自动调整统计窗口，替代硬编码的 DEFAULT_STATS_WINDOW=30

### 问题诊断
- 所有彩种一刀切 30 期
- 大乐透全历史 3000+ 期，30 期覆盖不到 1%
- 排列5 每天开奖，30 期 ≈ 1 个月；大乐透每周 3 期，30 期 ≈ 2.5 个月

### 方案
- 冷热/频次分析：窗口 = min(30, 全历史 10%)
- 遗漏分析：窗口 = max(50, 全历史 20%)（遗漏需要更长窗口）
- 马尔可夫转移：全历史（已实现）
- 近期密度：固定 K=5（已合理）
- 或基于数据量自适应：窗口 = max(30, int(sqrt(全历史期数)))

### 改动范围
- `src/lottery/config.py`: 新增自适应窗口函数
- `src/lottery/builders.py`: 各 prediction/analysis block 调用自适应窗口

---

## 任务 7: 回测评估体系完善 ⏳

### Goal
在现有命中数统计基础上，加入经济学视角的评估指标

### 方案
- **预期收益率**: Σ(奖级概率 × 奖金额) / 投注成本
- **夏普比率**: (平均收益 - 无风险收益) / 收益标准差
- **最大回撤**: 连续未中奖期数
- **中奖间隔分布**: 中奖之间的期数分布
- **滚动窗口稳定性**: 在不同时间段上回测表现的稳定性
- **20 码命中率**（KL8 专用）: 预测 20 码与真实 20 码的 overlap

### 改动范围
- `src/lottery/db.py`: 新增 `compute_financial_metrics()` 等函数
- `history/*.md`: 分析归档中可选展示

---

## Key Questions (跨任务)
1. 任务 4/5/6 的优先级：先做哪个？（建议 4→5→6→7）
2. 任务 5 的位间相关性可能收益有限——要不要先快速验证再决定做不做？
3. 任务 7 需要奖金数据，目前 DB 中没有——需要手动录入奖级金额表？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 按 3→4→5→6→7 顺序执行 | 从易到难，先修明显缺陷再补基础设施 |
| 任务 5 先做快速验证 | 位间相关性可能对 QXC 有用但 PL5 收益有限 |
| 任务 7 最后做 | 基础建设，不影响预测质量 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
|       |         |            |

## Notes
- 已完成：任务 1 (权重调优) + 任务 2 (因子去相关)，已提交 `b78c317`
- 当前：任务 3 (快乐八模型重构) Phase 1
- 后续：确认任务 3 完成后按顺序推进
