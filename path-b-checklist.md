# 路径 B：分析 + 预测 +（可选）组号 — 固定检查表

> **适用**：需要书面分析归档、预测归档（含**明确号码**），以及可选的 **10～30 元** 组号附录。  
> **前提**：数据在 `data/processed/`，本仓库不依赖 xlsx。  
> **用法**：按顺序勾选；每步完成后在「产出核对」打勾。

---

## 阶段 0：意图与盘点

| # | 任务 | 执行者 | 产出核对 |
|---|------|--------|----------|
| 0.1 | 确认彩种与范围：大乐透 / 双色球 / 快乐八；是否要预测、是否要 combo 附录 | 用户 / `lottery-manager` | ☐ |
| 0.2 | 仓库根执行：`python src/scripts/lottery.py inventory` | 用户 / 终端 | ☐ 已保存或已查看 JSON 输出 |
| 0.3 | 总控输出**移交清单**（下一步 Subagent、`name`、提示词要点） | `lottery-manager` | ☐ 清单已拿到 |

---

## 阶段 1：数据与门禁（若 processed 有更新或存疑）

| # | 任务 | 执行者 | 产出核对 |
|---|------|--------|----------|
| 1.1 | 仅大乐透+双色球补数 → `lottery-draw-dlt-ssq`；含快乐八 → `lottery-draw-sync` | 专精 Agent | ☐ `dlt_draws.csv` / `ssq_draws.csv` /（如需）`kl8_draws.csv` 已更新 |
| 1.2 | 同步更新 `data/processed/manifest.json`（溯源、rows_out、期号范围等） | 同上 | ☐ manifest 与 CSV 一致 |
| 1.3 | 仓库根执行：`python src/scripts/lottery.py validate` | 用户 / 终端 | ☐ 退出码 **0**，JSON 中 `ok: true` |

---

## 阶段 2：历史分析（书面归档）

| # | 任务 | 执行者 | 产出核对 |
|---|------|--------|----------|
| 2.1 | 新开对话 → `lottery-history-analysis`，按清单附数据路径与彩种 | 专精 Agent | ☐ 对话已切换 |
| 2.2 | 大乐透分析落盘 | 同上 | ☐ `history/daletou_analysis.md` 已整文件更新 |
| 2.3 | 双色球分析落盘 | 同上 | ☐ `history/shuangseqiu_analysis.md` 已整文件更新 |
| 2.4 | 快乐八分析落盘（若做快乐八） | 同上 | ☐ `history/kuaileba_analysis.md` 已整文件更新 |

---

## 阶段 3：统计预测（书面归档 + 强制明确号码）

| # | 任务 | 执行者 | 产出核对 |
|---|------|--------|----------|
| 3.1 | 新开对话 → `lottery-prediction`，附 `processed` 路径与口径（如近 N 期） | 专精 Agent | ☐ 对话已切换 |
| 3.2 | 正文须含：**口径说明 → 结果摘要 → 明确号码输出（强制）→ 使用说明/随机性声明** | 同上 | ☐ 三节齐全，**非**仅热冷文字 |
| 3.3 | 大乐透：至少 **1 注** 前区 5 + 后区 2 | 同上 | ☐ `history/daletou_prediction.md` |
| 3.4 | 双色球：至少 **1 注** 红 6 + 蓝 1 | 同上 | ☐ `history/shuangseqiu_prediction.md` |
| 3.5 | 快乐八：至少 **选十参考 11 码（升序）** | 同上 | ☐ `history/kuaileba_prediction.md` |

---

## 阶段 3b（可选）：组合优化附录

| # | 任务 | 执行者 | 产出核对 |
|---|------|--------|----------|
| B.1 | 需要 **10～30 元**（DLT/SSQ，默认带）或 11 码复式（快乐八）时 → `lottery-combo-optimize` | 专精 Agent | ☐ 已切换对话 |
| B.2 | 输出须含：**投注原因**（目标函数 + 依据文件/章节） | 同上 | ☐ 非只给号码表 |
| B.3 | 附录写入对应 `history/*_prediction.md` 文末（或约定路径） | 同上 | ☐ 注数、金额、校验式已写清 |

---

## 阶段 4（可选）：Python 一键刷新正文

> **警告**：以下命令会**覆盖**对应 md **全文**；若已完成 **B.3 附录**，运行后须**重新追加附录**。

| # | 任务 | 执行者 | 产出核对 |
|---|------|--------|----------|
| 4.1 | **统一命令**：`python src/scripts/lottery.py regenerate-history`，按任务加 `--only`：`all`（默认，含 kl8 时写满至多 6 个 md）、`kl8`（仅快乐八分析+预测）、`dlt-ssq`（仅大乐透+双色球四文件） | 用户 / 终端 | ☐ 终端 JSON `ok: true` 且 `wrote` 与预期一致 |
| 4.1b | 若曾做 B.3：**重新粘贴/生成** 预测 md 的 combo 附录（DLT/SSQ/KL8 按需） | 用户 / combo Agent | ☐ 附录已恢复 |

---

## 阶段 5（可选）：总控汇总

| # | 任务 | 执行者 | 产出核对 |
|---|------|--------|----------|
| 5.1 | 再开 `lottery-manager`，只做文字汇总与一致性检查（不重算） | `lottery-manager` | ☐ 汇总已交付 |

---

## 一键核对（路径 B 最小闭环）

```
☐ inventory
☐ validate（exit 0）
☐ 三份 *_analysis.md（按彩种）
☐ 三份 *_prediction.md（含明确号码）
☐ （可选）combo 附录 + 投注原因
☐ （可选）`regenerate-history` 后预测附录已补回
```

---

## 相关文档

- 角色与数据流：`AGENTS.md`  
- 预测落盘规则：`.cursor/rules/lottery-prediction-storage.mdc`  
- Python 子命令说明：`AGENTS.md` 中「Agent 与 Python 协作」表及 `README.md`
