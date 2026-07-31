---
name: 赛后复盘
description: 开奖后自动分析：结构偏离度、预测命中率、参数健康度。当用户说"复盘"、"分析开奖"、"预测命中了吗"、"开奖结果怎么样"、"对比预测"、"post-draw"时使用。
---

# 赛后复盘分析

开奖后自动运行，对比预测存档与实际开奖结果，分析结构偏离度，检查参数是否需要调整。

## 执行

```bash
# 全彩种复盘
python scripts/post_draw.py all

# 单彩种最新期
python scripts/post_draw.py dlt
python scripts/post_draw.py ssq
python scripts/post_draw.py kl8

# 指定期号
python scripts/post_draw.py dlt 2026083
python scripts/post_draw.py ssq 2026084
```

## 输出内容

1. **开奖号码** — 主区+副区完整号码
2. **结构快照** — 奇偶比、大小比、和值、012路、质数、连号、同尾、区间
3. **结构正常度** — 0-100 分，偏离历史均值越多分越低
4. **重号** — 与上期重叠个数和具体号码
5. **预测命中** — 如果 `data/predictions/` 有存档，自动对比每注命中数
6. **参数建议** — 检测是否需要调整参数阈值
7. **下期提示** — 基于极端事件的回归建议

## 预测存档

Workflow 跑完后把结果保存到 `data/predictions/<type>_<period>_<timestamp>.json`：

```json
{
  "lottery_type": "dlt",
  "period": "2026083",
  "predicted_at": "2026-07-25T...",
  "bets": [
    {"main": ["03","08","17","19","28"], "sub": ["03","10"], "strategy": "冷回补"},
    ...
  ]
}
```
