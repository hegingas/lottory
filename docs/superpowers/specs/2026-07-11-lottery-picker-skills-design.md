# 彩票选号独立 Skill 设计文档

**日期**: 2026-07-11  
**状态**: 设计中 → 待评审  
**作者**: 用户需求，Claude Code 起草  

---

## 1. 目标

创建 5 个**三位一体**（历史分析 + 号码预测 + 投注组号）的独立 Skill，每种彩种一个，替代日常使用场景下对 `lottery-prediction` + `lottery-history-analysis` + `lottery-combo-optimize` 三个独立 Skill 的分别调用。

---

## 2. Skill 清单

| 目录路径 | name (触发词) | 彩种 | 数据文件 |
|---|---|---|---|
| `.claude/skills/daletou-picker/SKILL.md` | 选大乐透 | 大乐透 | `dlt_draws.csv` |
| `.claude/skills/shuangseqiu-picker/SKILL.md` | 选双色球 | 双色球 | `ssq_draws.csv` |
| `.claude/skills/kuaileba-picker/SKILL.md` | 选快乐八 | 快乐八 | `kl8_draws.csv` |
| `.claude/skills/pailie5-picker/SKILL.md` | 选排列5 | 排列5 | `pl5_draws.csv` |
| `.claude/skills/qixingcai-picker/SKILL.md` | 选七星彩 | 七星彩 | `qxc_draws.csv` |

存放位置：项目级 `.claude/skills/`，目录用英文，触发词用中文。

---

## 3. 职责范围（三位一体）

每个 Skill 按顺序执行三步：

### 3.1 历史分析

- 频次、冷热、遗漏统计（默认近 30 期窗口）
- 奇偶比、大小比、和值区间、AC 值等结构分析
- 数据质量检查
- 对应归档：更新 `history/<lottery>_analysis.md`

### 3.2 号码预测

- 区间掩码马尔可夫 + 多因子加权选号（与现有 CLAUDE.md 规则一致）
- 去核心化约束、防重合约束
- 强制输出：5 注单式 + 1 注最优单式
- 对应归档：更新 `history/<lottery>_prediction.md`

### 3.3 投注组号

- 10 ~ 30 元金额带
- 单式/复式/胆拖方案
- 注数金额明细表

---

## 4. 与现有 Skill 的关系

| 现有 Skill | 处理方式 |
|---|---|
| `lottery-prediction` | **保留**，作备用/总入口 |
| `lottery-history-analysis` | **保留**，作跨彩种对比等用 |
| `lottery-combo-optimize` | **保留**，作独立组号用 |
| `lottery-manager` | 不动 |
| `lottery-draw-sync` / `lottery-draw-dlt-ssq` | 不动 |

新增 5 个 Skill 为日常主力，现有 Skill 保留备用。

---

## 5. SKILL.md 结构设计

每个 SKILL.md 包含以下章节：

```markdown
---
name: <中文触发词>
description: <一句话描述，含触发场景>
---

# <彩种名>选号参考

## 核心规则（引用 CLAUDE.md 中该彩种的特有约束）
## 数据来源
## 执行流程（分析 → 预测 → 组号）
## 输出模板
## 落盘约定
## 职责隔离
```

**复用策略**：各 Skill 内部规则引用 CLAUDE.md 中已有约束（多因子权重、区间掩码、去核心化等），不重复粘贴，避免规则分叉。

---

## 6. 创建方式

使用 `skill-creator` skill 逐个创建，每创建一个验证一个。

---

## 7. 验收标准

- [ ] 5 个 SKILL.md 文件存在于 `.claude/skills/<name>/` 下
- [ ] 每个 Skill 的 `name` 字段中文可触发
- [ ] 每个 Skill 独立执行：分析 → 出号 → 组方案 全流程
- [ ] 各 Skill 规则与 CLAUDE.md 无冲突
- [ ] `python src/scripts/cli.py validate` 通过
