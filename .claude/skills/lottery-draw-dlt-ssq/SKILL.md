---
name: lottery-draw-dlt-ssq
description: 专精更新大乐透与双色球开奖数据：抓取或导入、校验、写入 data/raw/ 与 data/processed/（dlt_draws.csv、ssq_draws.csv 及 manifest）。不涉及快乐八。
---

# 大乐透 / 双色球 开奖数据更新（专精）

## 范围（强制）

- **仅**大乐透（`dlt`）、双色球（`ssq`）。
- **不做**快乐八任何采集或落盘；用户提到快乐八时移交 `/lottery-draw-sync`。

## 数据来源优先级

与 `/lottery-draw-sync` 一致：用户指定官方/授权渠道 > 可追溯文件 > 第三方仅交叉验证。

## 落盘约定

1. **原始层**：新抓取写入 `data/raw/`，时间戳文件名，**不覆盖**既有原件。
2. **规范化层**：更新 `data/processed/dlt_draws.csv`、`data/processed/ssq_draws.csv`。列定义见 `data/processed/schema.json`（不含 `draw_date`）。
3. **元数据**：读-改-写 `data/processed/manifest.json` 中 dlt/ssq 相关 `outputs` 块（保留 kl8 段若存在）。注明 `generated_at`、源、剔除行、period_id_min/max。
4. **xlsx 处理**：由你解析校验后直接写入 CSV 与 manifest，可先复制到 `data/raw/` 留痕。
5. **写入后校验**：执行 `python src/scripts/lottery.py validate`（exit 0 方可认为自洽）。

## 完成后

- 提示运行 `python src/scripts/lottery.py regenerate-history --only dlt-ssq`（仅大乐透+双色球四文件）或 `--only all`。
- 或移交 `/lottery-history-analysis` 做增量解读。

## 职责隔离

**禁止**：历史 EDA、统计预测、投注组合、总控编排；**禁止**修改 `history/*` 分析/预测正文（除非用户明确要求）。
