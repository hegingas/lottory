# 彩票项目 Agent 分工说明

## 统一入口：管理总控（`lottery-manager`）

**默认由 `lottery-manager` 接单**，负责：解析用户意图（大乐透 / 双色球 / 快乐八 × 分析 / 预测）、**盘点本仓库数据文件与期号覆盖**、判断阻塞、**输出分阶段计划与移交清单**（建议下一步应打开的 Subagent 及可复制提示词）。

总控 **不得** 代替其他 Agent 产出其专属交付物（详见 `.cursor/rules/lottery-core.mdc` 中的职责隔离表）。

## Agent 独立运行与禁止越界

- **每个 Agent 在各自对话中独立运行**，只完成本角色「专属」工作。
- **禁止**在对话中完成其他 Agent 专属内容（例如：`lottery-history-analysis` 不得给出预测推荐；`lottery-prediction` 不得编写采集脚本与落盘；`lottery-draw-sync` 不得做统计分析或组号）。
- 需要下一阶段时：由 **`lottery-manager` 在移交清单中写明**「请新开对话并选择 Subagent：`name`」，用户切换后再继续。

## 当前仓库数据基线（总控盘点用）

历史数据位于**当前项目目录**（总控须 **列出并读取** 实际数据文件，勿假设路径）：

| 彩种 | 当前状态（约定描述） |
|------|----------------------|
| **快乐八** | 以 `data/processed/kl8_draws.csv` 为准；行数少或来源为第三方时，移交中须提示与官方核对。 |
| **大乐透** | 以 `dlt_draws.csv` + `manifest` 为准；有缺口时移交 `lottery-draw-dlt-ssq` 或手工补录。 |
| **双色球** | 以 `ssq_draws.csv` + `manifest` 为准；同上。 |

基线随仓库变更；**每次任务**总控应重新盘点。

## 总控接收的典型用户输入

- 大乐透 / 双色球 / 快乐八：仅分析 / 仅预测 / 分析 + 预测（由总控拆阶段并移交）。

## 在 Cursor 里点选独立 Agent（Subagent）

路径：`.cursor/agents/*.md`。

| 点选用 `name` | 文件 |
|---------------|------|
| `lottery-manager` | `.cursor/agents/lottery-manager.md` |
| `lottery-history-analysis` | `.cursor/agents/lottery-history-analysis.md` |
| `lottery-prediction` | `.cursor/agents/lottery-prediction.md` |
| `lottery-combo-optimize` | `.cursor/agents/lottery-combo-optimize.md` |
| `lottery-draw-sync` | `.cursor/agents/lottery-draw-sync.md` |
| `lottery-draw-dlt-ssq` | `.cursor/agents/lottery-draw-dlt-ssq.md` |

**分析与预测类**：先 **`lottery-manager`** 拿计划与移交清单；再按清单 **分别** 打开 `lottery-draw-dlt-ssq` 或 `lottery-draw-sync`（若需补数）、`lottery-history-analysis`（分析）、`lottery-prediction`（预测）。仅组号时用 `lottery-combo-optimize`。

## 角色一览

| 角色 | 主要职责 | 关联技能 |
|------|-----------|----------|
| **管理总控** | 编排、数据盘点摘要、移交清单与建议提示词 | `@.cursor/skills/lottery-manager` |
| **历史数据分析** | 三彩种描述性统计与数据质量 | `@.cursor/skills/lottery-history-analysis` |
| **统计预测** | 冷热 / 常见号等（须声明随机性） | `@.cursor/skills/lottery-prediction` |
| **10～30 元组合优化** | 默认金额带内投注组合 | `@.cursor/skills/lottery-combo-optimize` |
| **大乐透+双色球开奖更新** | 仅两彩种采集/导入与 processed 更新 | `@.cursor/skills/lottery-draw-dlt-ssq` |
| **开奖数据更新（全彩种）** | 含快乐八的三彩种抓取、解析、校验、落盘 | `@.cursor/skills/lottery-draw-sync` |

## 标准流程（多 Agent、多对话）

```
用户 → lottery-manager（意图 + 数据盘点 + 移交清单）
    → [按需] 用户切换 lottery-draw-dlt-ssq（仅大乐透+双色球）或 lottery-draw-sync（含快乐八）补数
    → [按需] 用户切换 lottery-history-analysis 做分析
    → [按需] 用户切换 lottery-prediction 做预测（可附分析摘要或数据路径）
    → [可选] 用户再开 lottery-manager 仅做阶段汇总（不重复专精计算）
```

## 数据流（推荐）

1. **`lottery-draw-dlt-ssq`**（仅大乐透/双色球）或 **`lottery-draw-sync`**（三彩种）：权威源 → `data/raw/`（不可随意覆盖唯一原件）→ 校验合并 → **`data/processed/`**（规范化主数据，推荐为分析与预测的**单一事实源**）。  
2. **`lottery-history-analysis`**：优先读 `data/processed/`；若无则 `data/raw/` 或用户指定路径（**本仓库约定不存放 xlsx**）；输出 → `history/*_analysis.md`。  
3. **`lottery-prediction`**：同样优先 `data/processed/`；输出 → `history/*_prediction.md`。**强制**：每个彩种归档须含 **「明确号码输出」** 节（大乐透、双色球各 **5 注单式** 且逐号说明原因 + **预测生成时间**；快乐八至少选十参考 **11 码升序**），规则见 `lottery-prediction-storage` 与对应 Skill。  
4. **`lottery-combo-optimize`**：只组号；若对齐预测须引用 `history/*_prediction.md` 或用户粘贴摘要，**不重算**统计预测。

### Agent 与 Python 协作（必须知晓）

仓库提供**统一 CLI**（在仓库根执行）：

| 子命令 | 作用 | 建议由谁触发 |
|--------|------|----------------|
| `python src/scripts/lottery.py inventory` | 列出 `data/` 下文件（UTF-8 JSON） | **`lottery-manager`** 盘点、任意 Agent 核对路径 |
| `python src/scripts/lottery.py validate` | 校验 `dlt/ssq/kl8` CSV 列、号码区间、去重、与 `manifest` 行数是否一致；失败时 exit code 1 | **`lottery-draw-dlt-ssq` / `lottery-draw-sync`** 写入或追加 CSV **之后**；**`lottery-history-analysis`** 若怀疑脏数据可先跑 |
| `python src/scripts/lottery.py regenerate-history`（可选 `--only all` / `kl8` / `dlt-ssq`） | **唯一推荐的机械刷新入口**。调用 `regenerate_history_archives.py`：`--only all`（默认）写大乐透+双色球四文件，且存在 `kl8_draws.csv` 时再写快乐八两文件；`--only kl8` **仅**快乐八分析与预测；`--only dlt-ssq` **仅**大乐透+双色球四文件（不写快乐八）。均为**期末尾近 30 期**（`DEFAULT_STATS_WINDOW`） | **validate 通过**后按任务选择 `--only`；**会覆盖**本次涉及的 `history/*.md` 全文；预测若有 combo 附录须事后补回 |
| `python src/scripts/lottery.py regenerate-kl8-prediction` | **[兼容别名]**，等同 `regenerate-history --only kl8` | 旧脚本或习惯用法；新流程请统一用上一行 |

**配合原则**：专精 Agent **不替代**脚本做大规模逐行校验（易错）；脚本 **不替代** Agent 写归档解读与随机性声明。改数 → **先 `validate` 再分析与预测**；批量重算正文 → **`regenerate-history`**（用 `--only` 限定范围）。

### 明确投注号码（项目约定 / 用户要求时）

当任务要求**产出可打票的明确号码**（在统计参考之外）：

- **须**在统计规律（含 `regenerate-history` 机械参考）输出完成后，给出至少一套 **合计 10～30 元（含端点）/ 期** 的投注推荐；默认**上限仍为 30 元/期**，**下限 10 元**（单价以官方为准）。  
- **须**在 `lottery-prediction` 归档定稿后，按 **`lottery-combo-optimize`** 技能构造或核验方案，使**合计金额落在上述区间内**（不得仅以 2 元单注作为唯一推荐收尾，除非用户明确只要参考号）。  
- **大乐透、双色球**：各给出合计 **10～30 元** 的一套或混合方案（单式 / 复式 / 胆拖等；**倍投**仅当用户明确要求），表格列出**具体号码**、注数公式、小计与校验。  
- **快乐八**：在**选十**下给出 **1 组 11 码复式**（C(11,10)=11 注，通常 **22 元**，已落在 10～30 元带内），除非用户另行放开档位。  
- **投注原因（强制）**：与号码一并输出时，**必须**说明投注理由（目标函数 + 依据：`history/*_prediction.md` / 用户约束等），详见 **`lottery-combo-optimize`** 技能「输出清单」。禁止只给号码表。  
- 将结果写入对应 **`history/*_prediction.md` 附录**（或单独 `history/` 文件），并含随机性与娱乐声明。  
- 运行 `regenerate_history_archives.py` 会**重算预测正文**，若需保留附录，应在脚本之后**重新追加**组合附录或改为脚本外维护。

### 从 processed 刷新书面归档（可选）

在仓库根执行（与直接跑 `regenerate_history_archives.py` 等价）：

`python src/scripts/lottery.py regenerate-history [--only all|kl8|dlt-ssq]`

或：`python src/scripts/regenerate_history_archives.py [--only kl8]`（参数与上一致）。

写入规则与 `--only` 含义见上表 CLI 说明。**本仓库不包含 xlsx**，更新开奖请用 `lottery-draw-dlt-ssq` / `lottery-draw-sync` 或直接维护 CSV 与 `manifest.json`。

## 异常数据闭环

当历史分析发现**期号/行级数据异常**（重复号、非法区间等）：  
`lottery-draw-dlt-ssq`（仅大乐透/双色球）或 `lottery-draw-sync`（含快乐八）修正源或重建 `data/processed/` → `lottery-history-analysis`（重跑并更新 `history/*_analysis.md`）→ 按需 `lottery-prediction`（重跑并更新 `history/*_prediction.md`）。

## 使用建议

1. **先 `lottery-manager`**，再 **按移交清单切换**专精 Agent。  
2. 遵守 `.cursor/rules/lottery-core.mdc` 的合规与 **职责隔离**。  
3. **快乐八**：组合优化仍仅 **选十 + 11 码复式**；无数据时先补数再分析。  
4. **扩展统计与预测口径**（时间聚合、衍生指标、多窗口、随机基准对照、约束下频次等）：见 `.cursor/rules/lottery-stats-prediction-extended.mdc`，由历史分析 / 预测 Agent 在职责范围内选用。

## 路径 B 固定检查表（分析 + 预测 + 可选组号）

可打印或复制使用的勾选清单见仓库根文件：**[`path-b-checklist.md`](path-b-checklist.md)**（分阶段任务、产出核对、一键闭环摘要）。

## 数据与代码放置（约定）

- `data/raw/`、`data/processed/`、`src/`；若历史文件在根目录其它路径，以盘点为准并在移交清单中写明。
- **历史分析书面归档**：`history/daletou_analysis.md`（大乐透）、`history/shuangseqiu_analysis.md`（双色球）、`history/kuaileba_analysis.md`（快乐八）。**机械统计正文**由 `regenerate-history` + `--only`（`all` / `kl8` / `dlt-ssq`）按**同一默认窗口**刷新对应文件；深度解读与增补由 **`lottery-history-analysis`** 维护；规则见 `.cursor/rules/lottery-history-storage.mdc`。
- **预测参考书面归档**：`history/daletou_prediction.md`、`history/shuangseqiu_prediction.md`、`history/kuaileba_prediction.md`。由同一 `regenerate-history` 命令按 `--only` 覆盖相应预测 md；专精任务后由 **`lottery-prediction`** 定稿或手写覆盖；规则见 `.cursor/rules/lottery-prediction-storage.mdc`。
