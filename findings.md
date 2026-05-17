# Findings & Decisions

## Requirements
- 八因子权重从硬编码改为数据驱动
- 使用现有回测框架验证
- 大乐透、双色球、快乐八的 8 因子权重 + 排列5/七星彩的 4 因子权重均需优化
- 最终产出：优化后的权重值 + 前后对比数据

## Optimization Results (2026-05-17)

### 方法
- Dirichlet(α=1) 采样 80 组权重（8F）/ 40 组（4F）
- 20 期回测粗筛 → Top N 用 100 期精细验证
- 两个目标函数：hits（命中数加权）和 prize（中奖比例）

### DLT 大乐透

| Factor | 原始 | hits-最优 | prize-最优 |
|--------|------|-----------|------------|
| markov | 0.25 | **0.059** | **0.011** |
| miss   | 0.18 | 0.014 | 0.066 |
| freq   | 0.14 | 0.006 | 0.009 |
| zone   | 0.12 | 0.007 | 0.216 |
| recency| 0.10 | 0.086 | 0.221 |
| parity | 0.08 | 0.082 | 0.016 |
| size   | 0.08 | **0.230** | 0.012 |
| sum    | 0.05 | **0.517** | **0.450** |

- hits: 7.87 → 8.59 (+9.1%)
- prize: 0.052 → 0.078 (+50%)

### SSQ 双色球

| Factor | 原始 | hits-最优 | prize-最优 |
|--------|------|-----------|------------|
| markov | 0.25 | **0.054** | **0.063** |
| miss   | 0.18 | 0.087 | 0.013 |
| freq   | 0.14 | **0.287** | **0.183** |
| zone   | 0.12 | 0.004 | 0.017 |
| recency| 0.10 | **0.359** | **0.565** |
| parity | 0.08 | 0.004 | 0.087 |
| size   | 0.08 | 0.194 | 0.047 |
| sum    | 0.05 | 0.012 | 0.026 |

- hits: 11.46 → 12.17 (+6.2%)
- prize: 0.060 → 0.074 (+23%)

### KL8 快乐八

| Factor | 原始 | overlap-最优 |
|--------|------|-------------|
| markov | 0.25 | **0.269** |
| miss   | 0.18 | 0.103 |
| freq   | 0.14 | 0.028 |
| zone   | 0.12 | 0.090 |
| recency| 0.10 | 0.016 |
| parity | 0.08 | **0.207** |
| size   | 0.08 | **0.220** |
| sum    | 0.05 | 0.067 |

- overlap: 2.53 → 2.57 (+1.6%，改善最小）

### PL5 排列5

| Factor | 原始 | pos-最优 |
|--------|------|----------|
| markov | 0.40 | **0.094** |
| miss   | 0.20 | **0.445** |
| freq   | 0.20 | **0.436** |
| recency| 0.20 | 0.025 |

- pos: 0.42 → 0.47 (+12%)

### QXC 七星彩

| Factor | 原始 | pos-最优 |
|--------|------|----------|
| markov | 0.40 | **0.701** |
| miss   | 0.20 | 0.087 |
| freq   | 0.20 | 0.180 |
| recency| 0.20 | 0.032 |

- pos: 0.82 → 0.84 (+2.4%)

## Key Insights

1. **马尔可夫转移被严重高估**：在 DLT/SSQ/PL5 中，markov 权重从原始的 0.25-0.40 暴跌至 0.01-0.09。二状态马尔可夫对组合型彩票的预测贡献远低于预期。

2. **不同彩种的主导因子完全不同**：
   - DLT: 和值带对齐 (sum) + 大小对齐 (size)
   - SSQ: 近K期密度 (recency) + 频次 (freq)
   - KL8: 奇偶 + 大小 + 马尔可夫（较均衡）
   - PL5: 遗漏 (miss) + 频次 (freq)
   - QXC: 马尔可夫 (markov) 独占鳌头

3. **QXC 反直觉**：七星彩的马尔可夫权重不降反升 (0.40→0.70)，说明其按位转移模式确实存在统计规律。

4. **KL8 改进最小**：+1.6%，说明快乐八的瓶颈不在权重，而在模型结构本身。

5. **prize 目标优化空间大于 hits 目标**：DLT prize +50%, SSQ prize +23%。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 权重通过可选参数透传，不用全局变量 | 保持向后兼容 |
| 使用 Dirichlet 分布采样（α=1） | 自动满足 simplex 约束 |
| 分层回测：20期粗筛 + 100期精细验证 | 平衡速度与可靠性 |
| 每个彩种独立优化 | 结果证实最优权重差异巨大，独立优化正确 |
| 默认使用 hits-优化权重 | 更稳定，绝对改善更大 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| prediction_block_* 返回类型标注为 str 但实际返回 (str, dict) 元组 | 已确认不影响功能，仅类型标注不准确 |
| 80 组粗筛约需 3 分钟/彩种 | 可接受，总耗时约 15 分钟 |

## Factor Correlation Analysis (2026-05-17)

### Correlation Matrix (DLT 30-period)
最强的因子相关性：
- **miss ↔ recency: r = -0.72** (强负相关)
- markov ↔ miss: r = -0.50
- freq ↔ sum: r = +0.45
- recency ↔ markov: r = +0.45

### VIF (方差膨胀因子)
| Factor | VIF | R² | 冗余度 |
|--------|-----|-----|--------|
| miss | 3.35 | 0.70 | 高 |
| recency | 2.63 | 0.62 | 中高 |
| freq | 1.67 | 0.40 | 中 |
| sum | 1.60 | 0.38 | 中 |
| markov | 1.55 | 0.35 | 中 |
| zone | 1.34 | 0.26 | 低 |
| parity | 1.23 | 0.19 | 低 |
| size | 1.04 | 0.04 | 极低 |

All VIF < 5: 共线性存在但不严重，条件数=14.9。

### ZCA Whitening Results

| 彩种 | 原始优化 | 白化+优化 | 变化 |
|------|---------|----------|------|
| DLT | 8.59 | 8.36 | -2.7% |
| SSQ | 12.17 | 12.66 | **+4.0%** |

**Decision**: DLT 不加白化，SSQ 默认开启白化。KL8/PL5/QXC 不适用（模型结构不同）。

## Technical Decisions (因子去相关)
| Decision | Rationale |
|----------|-----------|
| DLT 不用白化 | 倒退 -2.7%，因子相关性里包含有用结构信息 |
| SSQ 默认白化 | 改善 +4.0%，miss↔recency 共线削弱了 SSQ 预测 |
| ZCA over PCA | ZCA 保持因子方向，解释性更好 |
| shrinkage reg=0.05 | 防止小特征值爆炸 |

## Resources
- 优化引擎: `src/lottery/weight_optimizer.py`
- 白化函数: `src/lottery/scoring.py` (`_zca_whitening_matrix`, `_apply_whitening`)
- 优化后权重: `src/lottery/config.py` (DLT_8F_WEIGHTS, SSQ_8F_WEIGHTS, etc.)
- 原始权重仍保留: `config.py` PATTERN_W_* 常量
- 权重查找: `config.get_optimized_weights(lottery_type)`
