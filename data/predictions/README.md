# 预测记录归档

每个彩种的预测号码自动归档到对应 CSV，由 workflow 终裁后自动写入。

## 文件结构

| 文件 | 彩种 | 主号码列 |
|------|------|----------|
| `ssq_predictions.csv` | 双色球 | compound_red, compound_blue, s[1-3]_red, s[1-3]_blue |
| `dlt_predictions.csv` | 大乐透 | compound_front, compound_back, s[1-3]_front, s[1-3]_back |
| `kl8_predictions.csv` | 快乐八 | compound(选十10码), s[1-3] |
| `pl5_predictions.csv` | 排列5 | s[1-3]（5位数字空格分隔） |
| `qxc_predictions.csv` | 七星彩 | compound_front, compound_back, s[1-3]_front, s[1-3]_back |

## 公共列

| 列 | 说明 |
|------|------|
| `period_id` | 预测期号 |
| `pred_time` | 预测生成时间（ISO-8601 +08:00） |
| `notes` | 核心逻辑摘要 |

## 归档方式

1. **自动**：workflow 终裁后由"存档" agent 调用 `scripts/_archive_prediction.py` 自动写入
2. **手动**：`python scripts/_archive_prediction.py <彩种> '<JSON>'`
3. **去重**：同期号已存在则跳过，不会重复写入
