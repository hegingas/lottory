# Lottery 工具与 Agent 配置

本仓库用于 **大乐透、双色球、快乐八** 相关的数据与分析工作流，核心是 **Cursor 下的多角色 Agent（Subagent）、Skills 与 Rules**。业务代码与数据目录可按需逐步补充。

## 重要说明

彩票开奖具有随机性，仓库内任何统计、预测或组合方案 **均不构成投资建议或中奖保证**，仅供学习与娱乐用途。请遵守法律法规与官方玩法规则。

## 推荐工作流（总控 + 专精多对话）

1. **`lottery-manager`**：解析意图、**盘点**当前目录内真实数据、输出 **分阶段计划与移交清单**（下一步应选哪个 Subagent、建议提示词）。总控 **不** 代为做历史统计报表、预测结论、采集落盘或组号（见职责隔离）。
2. 按清单 **分别新开对话** 选择：`lottery-draw-sync`（补数）→ `lottery-history-analysis`（分析）→ `lottery-prediction`（预测）等；每个 Agent **只** 做本角色工作。
3. 需要文字汇总时可再开 `**lottery-manager`**，**不得**要求总控重复计算专精结果。

**职责隔离** 全文见 `[.cursor/rules/lottery-core.mdc](.cursor/rules/lottery-core.mdc)` 中的表格。

**当前数据基线**（随仓库变化；总控每次任务会重新核对）：

- **快乐八**：以 `data/processed/kl8_draws.csv` 是否存在及行数为准。  
- **大乐透、双色球**：以 `dlt_draws.csv` / `ssq_draws.csv` 与 `manifest.json` 为准；缺口由 `lottery-draw-*` 或手工补 CSV。

细则与流程图见 `[AGENTS.md](AGENTS.md)`。

## 仓库结构概览


| 路径                          | 作用                                                                                                                                                                                           |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `[AGENTS.md](AGENTS.md)`    | 各角色职责、与 Skills 的对应关系、在 Cursor 中点选 Subagent 的说明                                                                                                                                               |
| [`path-b-checklist.md`](path-b-checklist.md) | **路径 B**（分析 + 预测 + 可选组号）固定检查表：分阶段勾选与产出核对                                                                                                                                 |
| `.cursor/agents/*.md`       | **独立可点选 Agent（Subagent）**：YAML（`name`、`description`）+ 系统提示词正文                                                                                                                                |
| `.cursor/skills/*/SKILL.md` | **项目技能**：细分流程、口径与约束，可用 `@` 引用进对话                                                                                                                                                             |
| `.cursor/rules/*.mdc`       | **项目规则**：`lottery-core` 默认全局生效；`lottery-stats-prediction-extended` 扩展统计与预测口径；`lottery-data` 在编辑 `data/`** 时生效；`lottery-history-storage` / `lottery-prediction-storage` 约定 `history/` 分析与预测归档 |
| `data/`                     | `raw/` 原始抓取（可选）；`processed/` **主数据**（`dlt_draws.csv` / `ssq_draws.csv` / `kl8_draws.csv`，**不含开奖日期列**，仅期号+号码）                                                                                                     |
| `history/`                  | 分析 / 预测：`daletou_*`、`shuangseqiu_*`、`kuaileba_*`（可由 `regenerate-history` 按**三彩种同一默认窗口**批量刷新，或由对应 Agent 维护）                                                                               |
| `src/scripts/`              | **`lottery.py`**：统一用 `regenerate-history` + `--only` 刷新 `history/`（`all` / `kl8` / `dlt-ssq`，默认近 30 期）；`regenerate-kl8-prediction` 为兼容别名；另保留 `regenerate_history_archives.py`                          |
| `src/lottery/`              | 盘点与校验逻辑（供 `lottery.py` 与后续测试复用）                          |
| `requirements.txt`          | Python 依赖：`pandas`、`numpy`（用于 `regenerate_history_archives.py`）                                                                                                                                                        |


## Subagent 一览

在 Cursor 的 Agent / Subagent 界面中，按配置里的 `**name`** 选用即可：


| `name`                     | 用途简述                                               |
| -------------------------- | -------------------------------------------------- |
| `lottery-manager`          | 任务编排、目录约定、多角色衔接                                    |
| `lottery-history-analysis` | 历史开奖描述性统计与数据质量                                     |
| `lottery-prediction`       | 基于明确统计口径的冷热 / 常见号参考（须声明随机性）                        |
| `lottery-combo-optimize`   | 默认 **10～30 元/期** 组合；大乐透/双色球支持单式、复式、胆拖（倍投仅当用户要求）；快乐八 **仅选十 + 11 码复式** |
| `lottery-draw-dlt-ssq`     | **仅**大乐透 + 双色球开奖数据更新（`processed` CSV / manifest）   |
| `lottery-draw-sync`        | **三彩种（含快乐八）**开奖数据采集、解析、校验与落盘                       |


更完整的表格与使用建议见 `[AGENTS.md](AGENTS.md)`。

## 在 Cursor 中的推荐用法

1. **全流程**：先 **`lottery-manager`** 拿移交清单，再 **切换** 各专精 Subagent 独立完成任务；各 Agent **禁止**做其他角色专属工作。
2. **仅历史分析 / 仅预测 / 仅补数 / 仅组号**：可直接打开对应 `name`，但仍须遵守职责隔离。
3. **补上下文**：在输入框 **@** 引用技能或 `@AGENTS.md`。
4. **全局规则**：`.cursor/rules/lottery-core.mdc`（含职责隔离表）；编辑 `data/`** 时另见 `.cursor/rules/lottery-data.mdc`。

## 数据与安全约定

- 建议：`data/raw/` 存不可随意覆盖的原始抓取；`data/processed/` 存清洗后的结构化数据。
- API 密钥、Cookie 等放在 **环境变量** 或 `.env`（已在 `.gitignore` 中忽略），勿提交到 Git。

## 扩展本项目

新增脚本或数据管道时，尽量保持与 `lottery-manager` 技能中的目录约定一致，并更新相关 Skill 中的口径说明，避免 Agent 与文档脱节。