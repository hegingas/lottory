# 彩票数据分析项目

本仓库用于**大乐透、双色球、快乐八**的数据采集、历史分析、统计型预测参考与投注组合优化。

## 合规与表述

- 彩票为随机游戏，历史统计**不能**保证未来结果。禁止「稳赚」「必中」「投资回报率」等误导表述。
- 输出预测或推荐组合时，必须声明：**娱乐目的、概率本质、过往统计仅供参考**。
- 不协助未成年人购彩；不协助规避监管或伪造开奖数据。

## 彩种与范围

| 彩种 | 主区 | 副区 | 玩法约束 |
|------|------|------|----------|
| 大乐透 | 前区 5 枚，01–35 | 后区 2 枚，01–12 | 支持单式、复式、胆拖 |
| 双色球 | 红球 6 枚，01–33 | 蓝球 1 枚，01–16 | 支持单式、复式、胆拖 |
| 快乐八 | 每期 20 个开奖号，01–80 | 无 | **仅选十**，复式仅 11 码 |

## 默认统计窗口

未指定期数时，三彩种频率/冷热/遗漏等主体统计**默认仅对期末尾连续 30 期**（`DEFAULT_STATS_WINDOW`）。若用其他 N 须显式写明。

## 目录结构

| 路径 | 作用 |
|------|------|
| `data/raw/` | 原始抓取副本，不可覆盖唯一原件 |
| `data/processed/` | **规范化主数据**，分析与预测的单一事实源 |
| `history/` | 分析/预测书面归档（6 个 md） |
| `src/lottery/` | Python 库：路径、盘点、校验 |
| `src/scripts/` | CLI 入口 `lottery.py` |

## CLI 工具

| 命令 | 作用 |
|------|------|
| `python src/scripts/lottery.py inventory` | 列出 data/ 下文件（JSON） |
| `python src/scripts/lottery.py validate` | 校验 CSV 与 manifest 一致性 |
| `python src/scripts/lottery.py regenerate-history [--only all\|kl8\|dlt-ssq]` | **唯一推荐**的机械刷新入口，默认近 30 期，覆盖 history/*.md |

## 数据约定

- **processed CSV 不含开奖日期列**，仅 `lottery_type` + `period_id` + 号码列。
- 分析与预测 Agent **优先**读取 `data/processed/`；若不存在则回退 `data/raw/` 或用户指定路径。
- **本仓库不约定存放 xlsx**。用户提供 xlsx 时须由采集 Agent 转 CSV 写入 `processed/` 并在 `manifest.json` 记录来源。
- 写入数据前执行校验：号码区间、去重、期号单调性。
- API Key / Cookie 放环境变量或 `.env`（已 `.gitignore`），禁止写入仓库明文。
- Manifest 条目按 `lottery_type` 分块（dlt/ssq/kl8），更新整文件时保留其他块。

## 硬性规则（所有任务必须遵守）

### 最新期强制重算

每次「分析/预测/组号」请求，必须先以 `data/processed/*.csv` 的**最新期号**为基准重算。若归档末期小于 CSV 最新 `period_id`，必须先重算再输出。

### analysis 强制同步刷新

每次执行预测或分析任务时，必须在同一轮内同步刷新对应 `history/*_analysis.md`。禁止只更新 prediction 不更新 analysis。

### 去核心化选号

大乐透、双色球、快乐八预测禁止直接围绕最新窗口 Top 热号骨架拼注。必须加入反集中约束（分区均衡、过热惩罚、热温冷混合），并在正文写明"已执行去核心化约束"。

### 大乐透/双色球重合约束

① 任一预测单式不得与历史任一期开奖完全重合；② 任一预测单式与最新一期开奖重合号数 ≤ 3（全号码位 7 码计算）。

### 快乐八重合上限

预测"参考开奖 20 码"与最新一期真实开奖 20 码的重合数 ≤ 6。超出时按分数从低到高替换重合号，直至满足上限。

### 时间戳口径

`最后更新`、`预测生成时间` 统一使用**北京时间** ISO-8601（`+08:00`）。

### 组号金额带

统计规律输出完成后，配套至少一套**合计 10~30 元（含端点）/ 期**的投注推荐。不得仅以 2 元单注作为唯一收尾。

### 单式优选强制输出

预测"明确号码"之后，必须额外给出 1 注分数最高的单式（大乐透前 5+后 2，双色球红 6+蓝 1，快乐八候选前 11），含总分、关键因子与生成时间。

## AC 值（算术复杂度）

定义：号码排序后，所有两两差值去重个数 D，AC = D − (n−1)。

| 彩种 | 计算对象 | n | 公式 |
|------|----------|---|------|
| 双色球 | 红球 6 枚 | 6 | AC = D − 5 |
| 大乐透 | 前区 5 枚 | 5 | AC = D − 4 |
| 快乐八 | 20 开奖号（用户明确要求时） | 20 | AC = D − 19（非主流） |

## 历史分析归档

| 彩种 | 文件 |
|------|------|
| 大乐透 | `history/daletou_analysis.md` |
| 双色球 | `history/shuangseqiu_analysis.md` |
| 快乐八 | `history/kuaileba_analysis.md` |

每完成分析任务须更新对应文件（整文件覆盖），元数据含：最后更新、期号范围、所用数据路径。

## 预测参考归档

| 彩种 | 文件 |
|------|------|
| 大乐透 | `history/daletou_prediction.md` |
| 双色球 | `history/shuangseqiu_prediction.md` |
| 快乐八 | `history/kuaileba_prediction.md` |

每完成预测任务须更新对应文件，必须包含：口径说明、结果摘要、明确号码输出（强制）、使用说明/随机性声明。

## 职责隔离

本项目有 6 个 Skill（通过 `/skill-name` 调用），各司其职：

| Skill | 专属职能 | 禁止 |
|-------|----------|------|
| `lottery-manager` | 意图解析、数据盘点、移交清单、跨阶段汇总 | 统计报表、预测结论、采集落盘、投注方案 |
| `lottery-history-analysis` | 描述性统计、频次遗漏、数据质量报告 | 预测推荐、采集落盘、投注组合、全流程编排 |
| `lottery-prediction` | 冷热号/结构参考、明确号码输出 | 完整 EDA 替代、采集落盘、投注组合、全流程编排 |
| `lottery-draw-sync` | 三彩种数据采集、解析、校验、落盘 | 统计分析、预测推荐、投注组合、全流程编排 |
| `lottery-draw-dlt-ssq` | 仅大乐透+双色球数据同步 | 快乐八同步、统计分析、预测推荐、投注组合 |
| `lottery-combo-optimize` | 10~30 元内投注组合/注数/金额 | 历史 EDA、预测推荐、采集落盘、全流程编排 |

## 推荐工作流

```
/lottery-manager（盘点 + 移交清单）
    → /lottery-draw-sync 或 /lottery-draw-dlt-ssq（补数据）
    → validate（python src/scripts/lottery.py validate）
    → /lottery-history-analysis（分析 + 更新 history/*_analysis.md）
    → /lottery-prediction（预测 + 更新 history/*_prediction.md）
    → /lottery-combo-optimize（可选组号）
```

## 异常数据闭环

历史分析发现异常 → `/lottery-draw-sync` 修正源或重建 processed → `/lottery-history-analysis` 重跑 → 按需 `/lottery-prediction` 重跑。
