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
| Where am I? | Phase 5 complete - 全部完成 |
| Where am I going? | 任务完成，可进入下一个优化（因子去相关） |
| What's the goal? | 用回测数据驱动权重优化，替代硬编码 ✓ |
| What have I learned? | 马尔可夫被严重高估；各彩种最优因子结构完全不同 |
| What have I done? | 全部 5 阶段完成，优化权重已设为默认并刷新归档 |
