---
name: 同步彩票数据
description: 同步最新彩票开奖数据到本地CSV。当用户说"同步数据"、"更新开奖"、"拉最新开奖"、"sync lottery"、"数据最新吗"、"补全开奖数据"时使用。
---

# 同步彩票开奖数据

从官方源（中彩网 zhcw.com / 中福彩 cwl.gov.cn API）拉取缺失期号，更新 `data/processed/*.csv` 和 manifest。

## 执行

```bash
# 全量同步（5个彩种）
for s in scripts/_sync_ssq_gap.py scripts/_sync_dlt_gap.py scripts/_sync_kl8_gap.py scripts/_sync_pl5_gap.py scripts/_sync_qxc_gap.py; do
  echo "=== $s ===" && python "$s"
done

# 单彩种
python scripts/_sync_ssq_gap.py   # 双色球
python scripts/_sync_dlt_gap.py   # 大乐透
python scripts/_sync_kl8_gap.py   # 快乐八
python scripts/_sync_pl5_gap.py   # 排列5
python scripts/_sync_qxc_gap.py   # 七星彩
```

## 同步源

| 彩种 | 来源 | 方式 |
|------|------|------|
| 双色球/快乐八 | cwl.gov.cn API | API JSON |
| 大乐透/排列5/七星彩 | zhcw.com | Playwright 页面抓取 |

## 输出

- `data/processed/<type>_draws.csv` 追加缺失期号
- `data/raw/<type>_fetch_<timestamp>.json` 原始备份
- `data/processed/manifest.json` 更新行数和最新期号
- 打印新增期号明细
