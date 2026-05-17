# data/raw — 原始开奖数据副本

当前此目录为空（仅有此说明文件）。数据直接维护在 `data/processed/` 下。

## 数据来源

processed CSV 为手动维护的主数据源：

| 彩种 | 文件 | 来源 |
|------|------|------|
| 大乐透 | `dlt_draws.csv` | 官方渠道采集/用户提供 |
| 双色球 | `ssq_draws.csv` | 官方渠道采集/用户提供 |
| 快乐八 | `kl8_draws.csv` | 官方渠道采集/用户提供 |
| 排列5 | `pl5_draws.csv` | 官方渠道采集/用户提供 |
| 七星彩 | `qxc_draws.csv` | 官方渠道采集/用户提供 |

## 设计说明

- **当前状态**：raw 层未启用，processed CSV 兼具原始数据与加工后数据角色
- **未来计划**：若接入自动抓取，原始副本将存入此目录作为不可覆盖的溯源记录
- **数据血缘**：`data/processed/manifest.json` 记录各文件的期号范围与更新时间

## 相关文档

- 数据校验：`python src/scripts/cli.py validate`
- 数据约定：`CLAUDE.md` 中"数据约定"章节
