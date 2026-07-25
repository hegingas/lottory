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

全部 5 个彩种通过 **漏斗 + 对抗验证** 选号：

| Skill | 彩种 | 漏斗层数 | 审查员 | 入口 |
|-------|------|:--:|:--:|------|
| `shuangseqiu-picker` | 双色球 | 四层（预筛选→结构→形态→精选） | 5 人 | `Workflow({scriptPath: ".claude/skills/shuangseqiu-picker/scripts/workflow.js"})` |
| `daletou-picker` | 大乐透 | 三层（结构→形态→精选，深冻/热冷无效） | 5 人 | `Workflow({scriptPath: ".claude/skills/daletou-picker/scripts/workflow.js"})` |
| `kuaileba-picker` | 快乐八 | 四层（预筛选→结构→形态→精选） | 4 人 | `Workflow({scriptPath: ".claude/skills/kuaileba-picker/scripts/workflow.js"})` |
| `pailie5-picker` | 排列5 | 三层（按位结构→跨位形态→精选） | 4 人 | `Workflow({scriptPath: ".claude/skills/pailie5-picker/scripts/workflow.js"})` |
| `qixingcai-picker` | 七星彩 | 四层（预筛选→按位结构→跨位形态→精选） | 4 人 | `Workflow({scriptPath: ".claude/skills/qixingcai-picker/scripts/workflow.js"})` |

### Workflow 流程

1. **数据准备** — Haiku Agent 读取对应 CSV，提取全历史 + 近 50 期统计
2. **漏斗选号** — 单 Agent 按彩种专属漏斗逐层过滤，产出复式 + 单式推荐
3. **对抗验证** — 审查员并行审查漏斗产出，各自从专业视角挑刺给改进建议
4. **首席裁定** — Sonnet 综合漏斗产出 + 审查意见，输出最终号码

### 自定义 Agent（对抗审查员）

| Agent | 审查视角 | 适用范围 |
|-------|----------|----------|
| `trend-hunter` | 四窗口频率曲线：审查号码趋势方向是否正确 | 全部彩种 |
| `gap-judge` | 遗漏状态：标记深冻/过热/超跌，给替换建议 | 全部彩种 |
| `struct-master` | 结构合规：检查奇偶/大小/和值/012路是否在历史高频区间 | 全部彩种 |
| `pattern-spy` | 形态细节：检查连号/重号/区间/跨度/同尾 | 仅双色球、大乐透 |
| `game-theorist` | 反共识度：检查是否过热、太大众化，给反共识替换建议 | 全部彩种 |

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
