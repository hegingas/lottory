---
name: 选双色球
description: 双色球选号——Dynamic Workflow 编排五人委员会（trend-hunter/gap-judge/struct-master/pattern-spy/game-theorist），并行提名+交叉辩论+首席裁定，一注定乾坤。当用户说"选双色球"、"双色球选号"、"双色球预测"、"双色球推荐号码"、"帮我选双色球"、"双色球买什么"时使用。
---

# 双色球选号（五人委员会 · Dynamic Workflow · 一注定乾坤）

## 项目依赖限制

- **仅允许**读取 `data/processed/ssq_draws.csv`
- **禁止**使用 src/、scripts/、history/、config 等任何其他项目内容
- 所有分析逻辑由各 Agent 自行实现

## 原则

- 彩票为随机游戏，历史统计**不能**保证未来结果
- **只出一注**，不撒网
- 时间戳：北京时间 ISO-8601（`+08:00`）

---

## 架构

```
选双色球 Skill 触发
    │
    └─→ Workflow 脚本 (scripts/workflow.js)
           │
           ├─ Phase 1: 数据准备 (haiku, 快速)
           │
           ├─ Phase 2: parallel(5 Agent 独立提名)
           │    ├─ trend-hunter   (sonnet) 趋势猎手
           │    ├─ gap-judge      (sonnet) 遗漏判官
           │    ├─ struct-master  (sonnet) 结构大师
           │    ├─ pattern-spy    (sonnet) 形态侦探
           │    └─ game-theorist  (sonnet) 博弈鬼才
           │
           ├─ Phase 3: parallel(5 Agent 交叉辩论)
           │    每人点评一位对手 + 自辩
           │
           └─ Phase 4: 首席裁定 (opus, high effort)
                综合提名+辩论 → 最终一注
```

## 自定义 Agent 清单

| Agent 类型 | 文件 | 视角 | 工具 |
|---|---|---|---|
| `trend-hunter` | `.claude/agents/trend-hunter.md` | 四窗口频率趋势 | Read, Bash |
| `gap-judge` | `.claude/agents/gap-judge.md` | 超跌冷号回补 | Read, Bash |
| `struct-master` | `.claude/agents/struct-master.md` | 奇偶/大小/和值 | Read, Bash |
| `pattern-spy` | `.claude/agents/pattern-spy.md` | 连号/重号/区间 | Read, Bash |
| `game-theorist` | `.claude/agents/game-theorist.md` | 反共识博冷 | Read, Bash |

## 执行方式

**使用 Workflow 工具**，传入 skill 自带的脚本：
```
Workflow({ scriptPath: ".claude/skills/shuangseqiu-picker/scripts/workflow.js" })
```

Workflow 自动处理并行调度、结果收集和结构化输出。脚本位置：`.claude/skills/shuangseqiu-picker/scripts/workflow.js`

---

## 选号约束

- **连号**：至少一组连续号（如 14,15 或 28,29）
- **上期重叠**：与最新一期重叠 1-2 个号
- **去重**：不与历史任一期完全重合

---

## 输出模板

```markdown
## 双色球选号委员会 · Workflow 裁定

**期号范围**：… ~ …
**上期开奖**：红 … + 蓝 …

### Phase 1: 独立提名
| 委员 | 红球 | 蓝球 | 核心理由 |
|---|---|---|---|
| … | … | … | … |

### Phase 2: 交叉辩论
（各委员点评+自辩摘要）

### Phase 3: 首席裁定

**最终一注**：红球 … + 蓝球 …

| 号码 | 来源 | 裁定理由 |
|---|---|---|
| … | … | … |

- **连号**：… ✅
- **与上期重叠**：…个 ✅
- **生成时间**：…

### 🗳️ 贡献统计
| 委员 | 入选数 |
|---|---|
| … | … |

## ⚠️ 使用说明
以上为五人委员会基于历史统计的辩论裁定结果。双色球为独立随机游戏，历史统计不构成未来开奖保证。理性购彩，2元。
```

## 落盘

更新 `history/shuangseqiu_prediction.md` 和 `history/debate_log_ssq_<date>.md`

## 禁止

- 不得跳过 Workflow 直接出号
- 不得少于 5 人参与
- 不得输出多注
- 不得使用马尔可夫链/区间掩码等既存算法
