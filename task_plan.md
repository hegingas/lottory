# Task Plan: 工程质量与架构优化（锐评整改）

## Goal
基于锐评发现的工程短板，从代码拆分、CI/CD、测试覆盖、数据治理、规则收敛五个维度提升项目工程质量，从"能跑就行"升级到"能维护、能部署、能协作"。

## 总览

| # | 任务 | 状态 | 优先级 | 预计收益 | 复杂度 |
|---|------|------|--------|---------|--------|
| 1 | builders.py 拆分 | ✅ 完成 | 🔴 高 | 可维护性翻倍 | 高 |
| 2 | web_app.py 模块化 | ✅ 完成 | 🔴 高 | 可扩展性提升 | 中 |
| 3 | CI/CD + lint/type-check | ✅ 完成 | 🔴 高 | 自动化质量门 | 低 |
| 4 | 依赖管理规范化 | ✅ 完成 | 🟡 中 | 可复现构建 | 低 |
| 5 | 测试覆盖补强 | ✅ 完成 | 🟡 中 | 回归保护 | 中 |
| 6 | 数据治理（raw层） | ✅ 完成 | 🟢 低 | 数据血缘清晰 | 低 |
| 7 | 规则文件收敛 | ✅ 完成 | 🟢 低 | 维护一致性 | 低 |

---

## Current Phase
🎉 全部 7 个任务已完成

---

## 任务 1: builders.py 拆分 🔴

### 问题
`src/lottery/builders.py` 1658 行，22 个函数，包揽了分析生成、预测生成、Markdown 拼接、号码输出、预算推荐等所有上层逻辑。

### 方案
按职责拆成 4 个模块：

```
src/lottery/
  builders/
    __init__.py          # 统一 re-export，保持向下兼容
    _analysis.py         # *_analysis_block 系列（DLT/SSQ/KL8/PL5/QXC 各 1 个 ≈ 5 函数）
    _prediction.py       # *_prediction_block 系列（DLT/SSQ/KL8/PL5/QXC 各 1 个 ≈ 5 函数）
    _formatting.py       # Markdown 格式化工具 + 号码格式化 + 预算推荐
    _collectors.py       # 内部收集函数（_collect_* 系列）
```

### 关键约束
- `from src.lottery.builders import prediction_block_dlt` 等所有现有导入不能断
- `builders/__init__.py` 做 `from ._analysis import *` + `from ._prediction import *` re-export
- 拆分后每个文件控制在 500 行以内

### 改动文件
- `src/lottery/builders.py` → `src/lottery/builders/` (拆分)
- `src/lottery/__init__.py` (如有导出需更新)

---

## 任务 2: web_app.py 模块化 🔴

### 问题
`src/lottery/web_app.py` 1336 行，38 个路由/函数，Flask 应用全部堆一个文件，没有蓝图、没有模板继承。

### 方案
按功能拆成蓝图结构：

```
src/lottery/
  web/
    __init__.py          # create_app() 工厂函数
    routes/
      __init__.py
      main.py            # 首页、走势图、通用路由
      analysis.py        # 分析相关路由
      prediction.py      # 预测相关路由
      backtest.py        # 回测相关路由
    templates/           # (现有 templates 移到这或保持原位置)
    static/              # (现有 static 保持)
```

### 关键约束
- `lottery_web.py` 入口脚本保持可用（一行 `create_app().run()`）
- 蓝图 URL 前缀保持与现有路由一致
- 每个蓝图文件控制在 300 行以内

### 改动文件
- `src/lottery/web_app.py` → `src/lottery/web/` (拆分)
- `src/scripts/lottery_web.py` (更新导入)

---

## 任务 3: CI/CD + lint/type-check 🔴

### 问题
- 没有 `.github/workflows/`，push 后零自动化
- `pyproject.toml` 只有 build-system 段，没有 `[tool.ruff]`、`[tool.mypy]`、`[tool.pytest.ini_options]`
- 8000+ 行 Python 全靠自觉

### 方案

**3a. pyproject.toml 补全：**
```toml
[tool.ruff]
line-length = 120
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]

[tool.mypy]
python_version = "3.10"
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**3b. GitHub Actions workflow：**
```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: ruff check src/ tests/
      - run: pytest -v
```

### 改动文件
- `pyproject.toml` (新增配置段)
- `.github/workflows/ci.yml` (新建)

---

## 任务 4: 依赖管理规范化 🟡

### 问题
- `requirements.txt` 只有 3 行（pandas, numpy, flask），不完整
- `pyproject.toml` 的 `dependencies` 也只有 2 行
- 没有 dev dependencies（pytest, ruff, mypy 等）
- 两份依赖清单可能不同步

### 方案
- `pyproject.toml` 作为唯一依赖声明源
  - `dependencies` → 运行时依赖
  - `[project.optional-dependencies]` → dev/test
- 删除 `requirements.txt` 或用 `pip-compile` 从 pyproject.toml 生成锁定文件
- 补全缺失依赖：`flask`, `matplotlib`(如 Web 走势图用), `pytest`, `ruff`, `mypy`

### 改动文件
- `pyproject.toml` (补全依赖)
- `requirements.txt` (删除或改为锁定文件)

---

## 任务 5: 测试覆盖补强 🟡

### 问题
- 692 行测试 vs 8125 行源码，测试比 8.5%
- 缺少以下关键模块的测试：`builders.py`(1658行, 0测试), `web_app.py`(1336行, 0测试), `weight_optimizer.py`(289行, 0测试), `markdown_utils.py`(362行, 0测试)

### 方案
优先补覆盖最大的风险点（不追求全覆盖）：

| 模块 | 当前测试 | 目标 | 说明 |
|------|---------|------|------|
| builders | 0 | test_builders.py (~200行) | prediction_block_* 烟雾测试 |
| weight_optimizer | 0 | test_weight_optimizer.py (~100行) | Dirichlet 采样+目标函数 |
| markdown_utils | 0 | test_markdown_utils.py (~80行) | 格式化函数 |
| web_app | 0 | test_web_app.py (~100行) | 路由响应烟雾测试 |

### 改动文件
- `tests/test_builders.py` (新增)
- `tests/test_weight_optimizer.py` (新增)
- `tests/test_markdown_utils.py` (新增)
- `tests/test_web_app.py` (新增)

---

## 任务 6: 数据治理（raw层） 🟢

### 问题
`data/raw/` 只有 `.gitkeep`，数据直接进 `processed/`，数据血缘丢失。

### 方案
- 不改现有流程，仅做最小补强
- 在 `data/raw/` 下新增 `README.md` 说明当前数据来源（哪个官方站、抓取时间、抓取脚本）
- 在 `data/processed/CHANGELOG.md` 补一条说明：processed CSV 是手动维护源，raw 层暂未启用
- **不强制**把所有 processed 数据回溯 raw（工程量大且收益低）

### 改动文件
- `data/raw/README.md` (新增数据溯源说明)
- `data/processed/CHANGELOG.md` (如存在则追加说明)

---

## 任务 7: 规则文件收敛 🟢

### 问题
CLAUDE.md (3000+ 字) ↔ .cursor/rules/*.mdc (5 文件, ~26000 字) ↔ AGENTS.md ↔ .cursor/agents/*.md，四套规则体系手动同步，迟早不一致。

### 方案
- 不改 .cursor/ 体系（它是 Cursor IDE 的规范源），仅做声明收敛
- CLAUDE.md 末尾明确声明：**"当本文件与 .cursor/rules/*.mdc 冲突时，以 .cursor/rules/ 为准，并在发现后同步 CLAUDE.md"**
- 新增 `scripts/check_rule_consistency.py` 做规则一致性快速检查（对比关键约束是否在两套文件中都存在）
- 不做大改——规则体系的根源问题是双 IDE 导致的双轨制，要么全切 Claude Code、要么全切 Cursor，暂时维持现状只加护栏

### 改动文件
- `CLAUDE.md` (新增冲突声明)
- `scripts/check_rule_consistency.py` (新增)

---

## Key Questions
1. 任务 1 builders.py 拆分：拆太细会导致导入链复杂，保持 4 个文件是否合适？
2. 任务 2 web_app 是否值得拆？Web UI 目前只有你一个人用，拆了主要是练手价值
3. 任务 5 测试补多少合适？builder 烟雾测试 vs 完整断言？

## Notes
- 本轮优化聚焦**工程基础设施**，不碰统计算法（算法在上一轮已优化完毕）
- 任务 3（CI + lint）收益最大成本最低，建议第一个做
- 任务 1+2（拆分怪兽文件）工作量最大，但长期收益最高
- 任务 6+7（数据治理+规则收敛）优先级最低，属于锦上添花
