---
name: lottery-draw-sync
description: 从可信来源更新大乐透、双色球、快乐八开奖数据：抓取、解析、校验、落盘与溯源。适用三彩种全量同步。
---

# 开奖数据更新（三彩种）

## 范围

大乐透 + 双色球 + 快乐八。若任务仅涉及大乐透与双色球，建议用 `/lottery-draw-dlt-ssq`。

## 数据来源优先级

1. 用户指定的官方公告页面或官方授权接口（体彩/福彩）。
2. 用户提供的已下载文件（须记录文件名与日期）。
3. 第三方聚合站点：仅辅助交叉验证，不可作为唯一权威源。

## 流程

1. **拉取/接收**：保留 `data/raw/` 下不可变副本（时间戳命名）。
2. **解析**：编码、分隔符、期号统一；快乐八注意 20 个号码排序存储。
3. **校验**：号码区间、去重、期号不重复；与上一期日期逻辑粗检。
4. **合并**：写入 `data/processed/`（`dlt_draws.csv` / `ssq_draws.csv` / `kl8_draws.csv`）。用户提供 xlsx 时，转为规范化 CSV 写入并在 `manifest.json` 记录来源。
5. **记录元数据**：来源 URL、抓取时间、校验人。
6. **校验**：执行 `python src/scripts/lottery.py validate`（exit 0 方可认为自洽）。
7. **可选刷新**：若更新了快乐八且需要同步分析+预测，执行 `python src/scripts/lottery.py regenerate-history --only kl8`。

## CSV 列约定

- 大乐透：`lottery_type,period_id,front_1..front_5,back_1,back_2`（不含 draw_date）
- 双色球：`lottery_type,period_id,red_1..red_6,blue`
- 快乐八：`lottery_type,period_id,n01..n20`（升序）

列定义详见 `data/processed/schema.json`。

## 安全

API Key、Cookie 放环境变量或 `.env`，禁止写入仓库明文。

## 职责隔离

**禁止**：历史统计分析、预测推荐、投注组合、全流程编排。

## 完成后

通知用户：processed 主文件名、期号起止、字段说明；提示可运行 `validate` 和 `regenerate-history`。
