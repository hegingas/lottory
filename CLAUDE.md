# 彩票选号项目

本仓库用于**大乐透、双色球、快乐八、排列5、七星彩**的 Dynamic Workflow 选号。每个彩种由独立 Skill 驱动，通过多人委员会对抗验证 Workflow 输出一注推荐号码。

## 合规与表述

- 彩票为随机游戏，历史统计**不能**保证未来结果。禁止「稳赚」「必中」「投资回报率」等误导表述。
- 输出预测或推荐组合时，必须声明：**娱乐目的、概率本质、过往统计仅供参考**。
- 不协助未成年人购彩；不协助规避监管或伪造开奖数据。

## 彩种与范围

| 彩种  | 主区               | 副区           | 玩法约束             |
| --- | ---------------- | ------------ | ---------------- |
| 大乐透 | 前区 5 枚，01–35     | 后区 2 枚，01–12 | 支持单式、复式、胆拖       |
| 双色球 | 红球 6 枚，01–33     | 蓝球 1 枚，01–16 | 支持单式、复式、胆拖       |
| 快乐八 | 每期 20 个开奖号，01–80 | 无            | **仅选十**，复式仅 11 码 |
| 排列5 | 5 位数字，0–9        | 无            | 每位独立 0–9，允许重复    |
| 七星彩 | 前区 6 位，0–9       | 后区 1 位，0–14 | 按位匹配，允许重复       |

## 选号方式

全部 5 个彩种通过 **Dynamic Workflow 委员会对抗验证** 选号：

| Skill | 彩种 | 委员会 | 入口 |
|-------|------|--------|------|
| `daletou-picker` | 大乐透 | 五人（trend-hunter, gap-judge, struct-master, pattern-spy, game-theorist） | `Workflow({scriptPath: ".claude/skills/daletou-picker/scripts/workflow.js"})` |
| `shuangseqiu-picker` | 双色球 | 五人（同上） | `Workflow({scriptPath: ".claude/skills/shuangseqiu-picker/scripts/workflow.js"})` |
| `kuaileba-picker` | 快乐八 | 四人（无 pattern-spy） | `Workflow({scriptPath: ".claude/skills/kuaileba-picker/scripts/workflow.js"})` |
| `pailie5-picker` | 排列5 | 四人（无 pattern-spy） | `Workflow({scriptPath: ".claude/skills/pailie5-picker/scripts/workflow.js"})` |
| `qixingcai-picker` | 七星彩 | 四人（无 pattern-spy） | `Workflow({scriptPath: ".claude/skills/qixingcai-picker/scripts/workflow.js"})` |

### Workflow 流程

1. **数据准备** — 单 Agent 读取对应 CSV，提取全历史 + 近 50 期统计
2. **独立提名** — 各委员并行分析，各自提名一注
3. **对抗验证** — 最多 5 轮：互审 → 自证 → 收敛检查
4. **首席裁定** — Opus 综合辩论记录输出最终一注

### 自定义 Agent

| Agent | 视角 | 适用范围 |
|-------|------|----------|
| `trend-hunter` | 四窗口频率曲线判定趋势方向 | 全部彩种 |
| `gap-judge` | 遗漏和历史极值，超跌回补 | 全部彩种 |
| `struct-master` | 奇偶/大小/和值框架选号 | 全部彩种 |
| `pattern-spy` | 连号/重号/区间形态 | 仅大乐透、双色球 |
| `game-theorist` | 反共识选号，回避过热号 | 全部彩种 |

## 目录结构

| 路径 | 作用 |
|------|------|
| `.claude/skills/*/SKILL.md` | Skill 定义与 Workflow 入口 |
| `.claude/skills/*/scripts/workflow.js` | Workflow 脚本 |
| `.claude/agents/*.md` | 自定义 Agent 定义 |
| `data/processed/` | **规范化主数据**（dlt/ssq/kl8/pl5/qxc CSV，不含开奖日期列） |
| `data/raw/` | 原始抓取副本，不可覆盖唯一原件 |

## 数据约定

- processed CSV 不含开奖日期列，仅 `lottery_type` + `period_id` + 号码列
- 写入数据前校验：号码区间、去重、期号单调性
- API Key / Cookie 放环境变量或 `.env`（已 `.gitignore`），禁止写入仓库明文
- 来源优先级：官方渠道 > 用户提供的可追溯文件 > 第三方交叉验证

## 时间戳口径

`最后更新`、`预测生成时间` 统一使用**北京时间** ISO-8601（`+08:00`）。
