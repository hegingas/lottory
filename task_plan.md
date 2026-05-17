# Task Plan: 八因子权重调优

## Goal
通过回测框架对八因子评分模型的权重进行数据驱动的优化，用网格搜索/随机采样找到使回测命中率最大化的权重组合，替代当前硬编码的 `(0.25, 0.18, 0.14, 0.12, 0.10, 0.08, 0.08, 0.05)`。

## Current Phase
Phase 5 — **全部完成** ✓

## Phases

### Phase 1: Requirements & Discovery
- [ ] 理清权重在调用链中的传递路径（config → scoring → builders → backtest）
- [ ] 确定优化目标函数（各彩种的命中数指标）
- [ ] 确定搜索空间与方法（Dirichlet 采样 vs 网格搜索）
- [ ] 确定回测规模（期数、窗口）以平衡速度与可靠性
- [ ] 评估一次完整回测的耗时
- **Status:** in_progress

### Phase 2: 权重参数化改造
- [ ] 在 `scoring.py` 中使 `_weighted_composite` 及各彩种评分函数支持外部传入权重
- [ ] 在 `builders.py` 中各 `prediction_block_*` 支持权重透传
- [ ] 在 `db.py` 中 `run_backtest` 支持权重透传
- [ ] 确保不改权重时行为与现状完全一致（向后兼容）
- **Status:** pending

### Phase 3: 优化引擎实现
- [ ] 实现权重向量采样器（Dirichlet 分布，保证 simplex 约束）
- [ ] 实现目标函数计算（单次回测 → 汇总指标）
- [ ] 实现搜索主循环（采样 → 回测 → 记录最优）
- [ ] 加入早停或自适应采样
- **Status:** pending

### Phase 4: 执行优化 & 结果分析
- [ ] 对大乐透执行权重搜索
- [ ] 对双色球执行权重搜索
- [ ] 对比优化前后回测指标
- [ ] 分析哪些因子权重变化最大、是否跨彩种一致
- [ ] 记录 findings
- **Status:** pending

### Phase 5: 收敛 & 归档
- [ ] 将最优权重更新到 `config.py`
- [ ] 用新权重重新生成 history/*_prediction.md
- [ ] 用新权重重新生成 history/*_analysis.md
- [ ] 清理临时/调试代码
- **Status:** pending

## Key Questions
1. 目标函数怎么定？DLT 前区匹配数优先还是奖级优先？不同彩种是否用不同目标？
2. 回测用多少期？100 期太慢，30 期可能噪声太大——折中选多少？
3. 是否所有彩种共用一套权重，还是每个彩种独立优化？
4. 排列5/七星彩的 4 因子权重要不要一起优化？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 等 Phase 1 盘完再定 |  |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
|       |         |            |

## Notes
- 当前权重向量: `(markov=0.25, miss=0.18, freq=0.14, zone=0.12, recency=0.10, parity=0.08, size=0.08, sum=0.05)`
- 回测框架已存在：`db.run_backtest()` 滑动窗口，结果存 `backtest_results` 表
- 排列5/七星彩用独立的 4 因子体系（markov=0.40, miss=0.20, freq=0.20, recency=0.20），本次一并优化
