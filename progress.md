# Progress Log

## Session: 2026-05-17

### Phase 1: Requirements & Discovery
- **Status:** complete
- **Started:** 2026-05-17
- Actions taken:
  - 盘点了 config.py 中所有权重常量和分区配置
  - 盘点了 scoring.py 中评分函数调用链和 `_weighted_composite` 实现
  - 盘点了 db.py 中 `run_backtest` 回测框架的完整流程
  - 盘点了 builders.py 中 prediction_block_* 函数签名
  - 确认了权重从 config → scoring → builders → backtest 的完整传递路径
  - 确认了三个关键决策：目标函数两种都跑、各彩种独立优化、30期粗筛+100期验证
- Files created/modified:
  - task_plan.md (created)
  - findings.md (created)
  - progress.md (created)

### Phase 2: 权重参数化改造
- **Status:** complete
- **Started:** 2026-05-17
- Actions taken:
  - config.py: 添加 DEFAULT_8F_WEIGHTS / DEFAULT_4F_WEIGHTS 字典
  - scoring.py: `_weighted_composite` 及所有 `_*_scores()` 函数支持 weights 参数
  - builders.py: 5 个 prediction_block_* 函数支持 weights 参数和透传
  - db.py: `run_backtest` 支持 weights 参数
  - 验证默认 weights=None 时向后兼容
  - 烟雾测试通过（DLT/SSQ/PL5 各 3 期回测）
- Files created/modified:
  - src/lottery/config.py (modified)
  - src/lottery/scoring.py (modified)
  - src/lottery/builders.py (modified)
  - src/lottery/db.py (modified)

### Phase 3: 优化引擎实现
- **Status:** complete
- **Started:** 2026-05-17
- Actions taken:
  - 实现 Dirichlet 权重采样器（8F/4F）
  - 实现多目标函数（hits/prize/overlap/pos）
  - 实现两阶段搜索主循环（粗筛+精细验证）
  - 实现结果格式化报告
  - 验证端到端流程
- Files created/modified:
  - src/lottery/weight_optimizer.py (created)

### Phase 4: 执行优化 & 结果分析
- **Status:** complete
- **Started:** 2026-05-17
- Actions taken:
  - DLT: 80 组粗筛 + 14 组精细验证，hits +9.1%, prize +50%
  - SSQ: 80 组粗筛 + 17 组精细验证，hits +6.2%, prize +23%
  - KL8: 80 组粗筛 + 10 组精细验证，overlap +1.6%
  - PL5: 40 组粗筛 + 8 组精细验证，pos +12%
  - QXC: 40 组粗筛 + 8 组精细验证，pos +2.4%
  - 发现：马尔可夫权重在 DLT/SSQ/PL5 中被严重高估
  - 发现：不同彩种最优因子结构完全不同
  - 发现：QXC 马尔可夫权重反涨（0.40→0.70）
- Files created/modified:
  - findings.md (updated with optimization results)

### Phase 5: 收敛 & 归档
- **Status:** complete
- Actions taken:
  - config.py: 添加所有彩种优化权重常量和 get_optimized_weights() 查询函数
  - builders.py: 所有 prediction_block_* 默认使用优化权重
  - 执行 regenerate-history --only all 刷新全部 10 个归档文件
  - 验证 optimization 权重默认生效
- Files created/modified:
  - src/lottery/config.py (modified: 添加优化权重)
  - src/lottery/builders.py (modified: 默认使用优化权重)
  - history/*.md (全部 10 个文件已刷新)

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Import check | import all modules | OK | OK | ✓ |
| Default weights backtest | DLT/SSQ/KL8/PL5/QXC 3期 | No crash | OK | ✓ |
| Custom weights backtest | DLT custom_w 3期 | Use custom w | OK | ✓ |
| Optimizer pipeline | DLT n_coarse=3 | End-to-end OK | OK | ✓ |
| DLT full optimization | 80 coarse + 14 fine | Improve over baseline | hits +9.1%, prize +50% | ✓ |
| SSQ full optimization | 80 coarse + 17 fine | Improve over baseline | hits +6.2%, prize +23% | ✓ |
| KL8 full optimization | 80 coarse + 10 fine | Improve over baseline | overlap +1.6% | ✓ |
| PL5 full optimization | 40 coarse + 8 fine | Improve over baseline | pos +12% | ✓ |
| QXC full optimization | 40 coarse + 8 fine | Improve over baseline | pos +2.4% | ✓ |
| regenerate-history | --only all | All 10 files refreshed | OK | ✓ |
| Optimized weights as default | run_backtest without weights | Uses optimized | OK | ✓ |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-05-17 | Edit: 2 matches found for DLT scoring call | 1 | Added surrounding context for uniqueness |
| 2026-05-17 | Edit: string not found for SSQ function | 1 | Used exact source text from Read output |
| 2026-05-17 | Edit: string not found for KL8 function | 1 | Used exact source text from Read output |

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | 任务 3 完成，任务 4 待做 |
| Where am I going? | 区间马尔可夫升二阶（任务 4） |
| What's the goal? | 快乐八模型从单层直接选号重构为 20→11 两阶段 ✓ |
| What have I learned? | Path B 20→11 重排位 +3.7%，0-hit 从 8 降到 2；瓶颈在结构非权重 |
| What have I done? | 新增 _kl8_eleven_from_twenty_rerank + Path B 收集函数 + 回测 20 码命中率指标 |

## Session: 2026-05-17 (任务 3: 快乐八模型重构)

### Phase 1: 现状盘点 & 路径设计
- **Status:** complete
- Actions taken:
  - 盘点 _kl8_twenty_from_patterns（已实现但闲置）与 _kl8_eleven_zone_capped_from_twenty（已实现但未接入主流程）
  - 确认当前 prediction_block_kl8 直接从 80 码跳到 11 码，跳过 20 码中间层
  - 设计 Path A（直接 11 码）、Path B（20→11）、Path C（频次基线）三条路径
  - 快速 benchmark 确定 20→11 最优策略：完整多因子重排位 > 贪心 > 随机 > 加权采样
- Key findings:
  - Path B_score_rerank: avg 2.737 vs Path A 2.638 (+3.8%)
  - Path B_greedy (_kl8_eleven_zone_capped_from_twenty): 实际倒退 -5.7%（因为用简单排名代替多因子分）
  - Path C 纯频次: 2.388（最差基线）

### Phase 2: Path B 实现 & 接入
- **Status:** complete
- Actions taken:
  - selection.py: 新增 `_kl8_eleven_from_twenty_rerank`（在 20 码池内用完整多因子分数贪心取 11 码）
  - builders.py: 新增 `_kl8_collect_one_path_outputs_b`，`prediction_block_kl8` 支持 `path` 参数（默认 "B"）
  - builders.py: 新增 Path B 专有的 20 码中间层输出（twenty_fmt, twenty_hit, twenty_block）
  - db.py: `run_backtest` 新增 `kl8_path` 参数 + 20 码命中率自动收集

### Phase 3: 回测对比
- **Status:** complete
- Actions taken:
  - 100 期 Path A vs B vs C: A=2.690, B=2.790 (+3.7%), C=2.510
  - Head-to-head: A胜=22, B胜=31, 平=47
  - Paired t-test: t=-1.119, p=0.266（不显著但方向明确）
  - B 路径 0-hit 仅 2 次 vs A 的 8 次（-75%）
  - 20 码中间层预测 avg 4.66/20 hit

### Phase 4: 收敛 & 归档
- **Status:** complete
- Actions taken:
  - 默认路径设为 "B"（20→11 重排位）
  - regenerate-history --only kl8 刷新 history/kuaileba_analysis.md + history/kuaileba_prediction.md
  - validate 确认 CSV ↔ DB 全部同步
  - task_plan.md 更新任务 3 为完成

### 改动文件
- `src/lottery/selection.py`: +`_kl8_eleven_from_twenty_rerank`
- `src/lottery/builders.py`: +`_kl8_collect_one_path_outputs_b`, `prediction_block_kl8` path 参数
- `src/lottery/db.py`: `run_backtest` +kl8_path +20码命中率指标
- `history/kuaileba_prediction.md`: 已刷新（默认 Path B）
- `history/kuaileba_analysis.md`: 已刷新
- `task_plan.md`: 更新状态

### Test Results (任务 3)
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Import check | all new functions | OK | OK | ✓ |
| Smoke test Path A | prediction_block_kl8 path='A' | No crash | OK | ✓ |
| Smoke test Path B | prediction_block_kl8 path='B' | No crash + twenty_hit in pred_data | OK | ✓ |
| 100期 Path A backtest | run_backtest kl8_path='A' | Baseline | avg=2.690 | ✓ |
| 100期 Path B backtest | run_backtest kl8_path='B' | Better than A | avg=2.790 (+3.7%) | ✓ |
| 20码命中率指标 | run_backtest kl8_path='B' | twenty_hit in summary | avg=4.66 | ✓ |
| regenerate-history | --only kl8 | Both files refreshed | OK | ✓ |
| validate | all data | No errors | all_synced=true | ✓ |
