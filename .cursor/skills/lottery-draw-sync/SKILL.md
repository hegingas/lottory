---
name: lottery-draw-sync
description: 从可信来源更新大乐透、双色球、快乐八开奖数据，完成抓取、解析、校验与落盘（当前不含排列5）。当用户要同步最新期、修复历史缺口、对比官方公告或编写采集脚本时使用；若用户明确只要大乐透+双色球且不含快乐八，可优先使用 lottery-draw-dlt-ssq。
---

# 开奖数据更新（三彩种，当前不含排列5）

> **范围**：大乐透 + 双色球 + 快乐八。若任务**仅**涉及大乐透与双色球，请改用专精 Agent **`lottery-draw-dlt-ssq`** 与本技能并行不冲突；快乐八必须由本技能或总控移交本技能处理。排列5 数据当前无专用 draw Agent，需按 `data/processed/pl5_draws.csv` 规范（`d1`–`d5`，0–9，允许重复）手工补录并更新 `manifest.json`。

## 数据来源优先级

1. 用户指定的 **官方公告页面或官方授权接口**（体彩 / 福彩）。  
2. 用户提供的 **已下载文件**（须记录文件名与日期）。  
3. 第三方聚合站点：仅可作为辅助交叉验证，**不可**作为唯一权威源。

## 流程

1. **拉取或接收文件**：保留 `data/raw/` 下不可变副本（时间戳命名）。  
2. **解析**：编码、分隔符、期号格式统一；快乐八注意 20 个号码排序存储。  
3. **校验**：号码区间、去重、期号未重复写入；与上一期日期逻辑粗检。  
4. **合并**：写入 `data/processed/`，主键建议 `(lottery_type, period_id)`。此处为下游分析与预测的**推荐单一事实源**；若用户仅有 Excel，由本 Agent 读取并转为规范化 CSV 写入 `processed/`，并在 `manifest.json` 记录来源说明（本仓库**不**内置 xlsx 批处理脚本）。  
5. **记录**：来源 URL、抓取 UTC 时间、校验人/脚本版本（可用 JSON 元数据文件）。  
6. **落盘后**：在仓库根执行 `python src/scripts/lottery.py validate`（exit 0 表示与 `manifest` 行数及号码规则自洽）。  
7. 若更新了快乐八 `kl8_draws.csv` 且用户需要同步分析 + 预测正文：执行 `python src/scripts/lottery.py regenerate-history --only kl8`（会覆盖 `history/kuaileba_analysis.md` 与 `history/kuaileba_prediction.md`；预测 combo 附录需按需补回）。

## 字段建议（processed）

- `lottery_type`: `dlt` | `ssq` | `kl8`  
- `period_id`: 与官方期号一致（CSV 中可用字符串或数值，下游统一解析）  
- **大乐透/双色球 CSV（本仓库约定）**：**不写 `draw_date` 列**，仅 `lottery_type`、`period_id` 与分区号码列；时间信息如需保留请放 `data/raw/` 或 manifest 备注。  
- `numbers`（若用 JSON/宽表以外格式）：分区存储，例如 `front`, `back` / `red`, `blue` / `drawn_20`；快乐八等可另行包含 `draw_date` 若你有统一宽表方案。

## 安全

- API Key、Cookie 放环境变量或 `.env`（已加入 `.gitignore`），禁止写入仓库明文。

## 职责隔离（禁止越界）

本 Skill 仅服务 **`lottery-draw-sync`**。**禁止**：历史描述性统计与数据质量报告（属 `lottery-history-analysis`）；冷热/常见号预测（属 `lottery-prediction`）；投注组合（属 `lottery-combo-optimize`）；全流程编排（属 `lottery-manager`）。完成后仅提示用户可将新期号范围交给分析 Agent。

## 完成后 handoff

通知用户或下游：`data/processed/` 中**主文件名**、期号起止、字段说明；以便 **`lottery-history-analysis`** 以 processed 为优先输入重跑统计；若刚修正异常行，提示**先**重跑分析归档再进入预测。
