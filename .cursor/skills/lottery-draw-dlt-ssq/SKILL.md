---
name: lottery-draw-dlt-ssq
description: 仅更新大乐透与双色球开奖数据：权威源抓取或接收文件、解析校验、写入 data/raw 与 data/processed（dlt_draws.csv、ssq_draws.csv、manifest 元数据）。当用户只要同步/补全大乐透与双色球、不涉及快乐八时使用；快乐八须转交 lottery-draw-sync。
---

# 大乐透 / 双色球 开奖数据更新（专精）

## 范围（强制）

- **仅**大乐透（`dlt`）、双色球（`ssq`）。  
- **不做**快乐八（`kl8`）任何采集或落盘；用户提到快乐八时，明确移交 `lottery-draw-sync`。

## 数据来源优先级

与 `lottery-draw-sync` 一致：用户指定 **官方/授权渠道** > 用户提供的可追溯文件 > 第三方仅作交叉验证。

## 落盘约定（本仓库）

1. **原始层**：新抓取或新导出写入 `data/raw/`，时间戳文件名，**不覆盖**既有唯一原件。  
2. **规范化层**：合并/追加后更新  
   - `data/processed/dlt_draws.csv`  
   - `data/processed/ssq_draws.csv`  
   列定义见 `data/processed/schema.json`（**不含 `draw_date`**）；期号、号码区间、去重、主键 `(lottery_type, period_id)` 须校验。  
3. **元数据**：更新或合并写入 `data/processed/manifest.json` 中与 `dlt`/`ssq` 相关的 `outputs` 块（注明 `generated_at`、源 SHA256、剔除行、period_id_min/max）；避免与快乐八条目互相覆盖——采用读-改-写整文件并保留 `kl8` 段（若存在）。  
4. 本仓库**不包含** xlsx→CSV 批处理脚本；无论用户提供 xlsx、csv 或网页抓取结果，均由本 Agent **解析校验后**直接写入/追加 `data/processed/*.csv` 与 `manifest.json`，并与 `schema.json` 列约定一致（可先复制到 `data/raw/` 留痕）。  
5. **写入后须跑校验**：在仓库根执行 `python src/scripts/lottery.py validate`（exit 0 方可认为 processed 自洽）。

## 完成后移交

- 提示用户（可选）`python src/scripts/lottery.py validate` 已通过的前提下，运行 `python src/scripts/lottery.py regenerate-history --only dlt-ssq`（**仅**大乐透+双色球四文件，避免误触快乐八）或 `--only all` 全量；亦可打开 `lottery-history-analysis` 做增量解读。

## 职责隔离

**禁止**：历史 EDA、统计预测、10～30 元组号、总控编排；**禁止**修改 `history/*` 分析/预测正文（除非用户明确要求由本角色代写，默认仍交给对应 Agent）。
