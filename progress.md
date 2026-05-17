# Progress Log

## Session: 2026-05-17（锐评整改轮）

### Phase 0: 项目盘点与问题诊断
- **Status:** complete
- **Started:** 2026-05-17
- Actions taken:
  - 完整盘点项目文件结构、源码行数、测试覆盖、依赖管理、CI 配置
  - 输出锐评：发现 8 个工程短板（2 个怪兽文件 + 零 CI/CD + 零 lint + 依赖不全 + raw 空 + 规则冗余 + 测试薄）
  - 确认上一轮 7 个统计优化任务已全部完成
  - 创建本轮优化 task_plan.md（7 个新任务）
  - 更新 findings.md（锐评发现 + 本轮策略）
- Files created/modified:
  - task_plan.md (重写)
  - findings.md (重写)
  - progress.md (重写)

### Phase 5: 数据治理 + 规则收敛
- **Status:** complete
- Actions taken:
  - data/raw/README.md: 数据来源说明 + raw 层设计说明 + 未来计划
  - CLAUDE.md: 新增冲突声明（以 .cursor/rules/ 为准）
  - scripts/check_rule_consistency.py: 关键约束跨文件一致性检查脚本
  - 检查结果: 1 个不一致项（多因子加权规则仅在 CLAUDE.md）
- Files created/modified:
  - data/raw/README.md (created)
  - CLAUDE.md (modified)
  - scripts/check_rule_consistency.py (created)

### Phase 4: 测试覆盖补强
- **Status:** complete
- Actions taken:
  - test_builders.py: 12 个烟雾测试（5 个 analysis + 5 个 prediction + 2 个 adaptive/path）
  - test_weight_optimizer.py: 10 个测试（keys, dirichlet sampling, reproducibility, objective functions）
  - test_markdown_utils.py: 8 个测试（_fmt2, now_cn_iso, _pattern_weight_md_line, budget_rules, kl8_bet, appendix lines）
  - test_web_app.py: 26 个测试（routes + helpers + parsers）
  - 测试总数: 68 → 128 (+60)
  - 修复: prediction_block_* 返回 tuple 不是 str, API key 是 "period" 不是 "period_id"
- Files created/modified:
  - tests/test_builders.py (created)
  - tests/test_weight_optimizer.py (created)
  - tests/test_markdown_utils.py (created)
  - tests/test_web_app.py (created)

### Phase 3: web_app.py 模块化
- **Status:** complete
- Actions taken:
  - web_app.py (1336行) → web/ 包（4个文件）
  - __init__.py: create_app() 工厂 + 注册蓝图
  - _helpers.py (~900行): 所有辅助函数
  - routes_main.py (~50行): 2 个页面路由 (/, /<lt>)
  - routes_api.py (~400行): 11 个 API 路由
  - route 装饰器从 @app → @main / @api (Flask Blueprint)
  - lottery_web.py 导入更新: lottery.web_app → lottery.web
- Files created/modified:
  - src/lottery/web/__init__.py (created)
  - src/lottery/web/_helpers.py (created)
  - src/lottery/web/routes_main.py (created)
  - src/lottery/web/routes_api.py (created)
  - src/lottery/web_app.py (deleted)
  - src/scripts/lottery_web.py (updated import)
  - pyproject.toml (updated C401 per-file-ignore)

### Phase 2: builders.py 拆分
- **Status:** complete
- Actions taken:
  - 原 `builders.py` (1658行) → `builders/` 包 (5个文件)
  - `__init__.py`: 路径常量 (REPO/PROC/HIST/MANIFEST) + 全部 re-export
  - `_utils.py` (~160行): _norm_df, _qstats, format_ac_top, _kl8_draw_rows, _pl5_* 辅助函数
  - `_compat.py` (~60行): dlt_explicit_from_patterns, ssq_explicit_from_patterns
  - `_analysis.py` (~600行): 5个 build_*_analysis 函数
  - `_prediction.py` (~680行): 5个 prediction_block_* + _kl8_collect_* 辅助函数
  - 子模块导入从 `from .scoring` 升级为 `from ..scoring`（多一层目录）
  - REPO 从 `parents[2]` 改为 `parents[3]`（__init__.py 在 builders/ 内）
  - 修复: `lottery.py` → `cli.py`（脚本名与包名冲突导致导入失败）
  - CLAUDE.md 中所有 `lottery.py` 引用更新为 `cli.py`
  - 更新 ruff per-file-ignore: builders.py → builders/_prediction.py
  - 外部消费者验证: validate.py, db.py, regenerate_history_archives.py 全部正常导入
  - All 16 public exports verified
  - regenerate-history --only qxc 端到端通过
- Files created/modified:
  - src/lottery/builders/__init__.py (created)
  - src/lottery/builders/_utils.py (created)
  - src/lottery/builders/_compat.py (created)
  - src/lottery/builders/_analysis.py (created)
  - src/lottery/builders/_prediction.py (created)
  - src/lottery/builders.py (deleted)
  - src/scripts/lottery.py → src/scripts/cli.py (renamed)
  - CLAUDE.md (updated script references)
  - pyproject.toml (updated per-file-ignore)

### Phase 1: CI/CD + lint + 依赖管理
- **Status:** complete
- Actions taken:
  - 修复 test_schema_version: 硬编码 v=1 → 引用 CURRENT_SCHEMA_VERSION
  - 修复 pyproject.toml: build-backend `setuptools.backends._legacy` → `setuptools.build_meta`
  - pyproject.toml 补全: [tool.ruff], [tool.ruff.lint], [tool.ruff.lint.isort], [tool.ruff.format], [tool.mypy], [tool.pytest.ini_options]
  - pyproject.toml 补全依赖: flask, pytest, ruff, mypy 加入 [project.optional-dependencies] dev
  - per-file-ignores: scripts E402 (sys.path), scoring.py N806/N803 (math notation), builders/web_app C401
  - 全局 ignore: SIM103 (guard clause style), SIM108 (if-else clarity)
  - 新增 .github/workflows/ci.yml: push/PR → ruff + mypy(non-blocking) + pytest
  - ruff --fix 自动修复 62 个问题
  - 手动修复: 未用变量 (specials_all, s_pred/p_pred, n_pos, n_nums, m_count), zip without strict, unused loop var
  - 删除 requirements.txt, pyproject.toml 为唯一依赖源
  - ruff: 0 errors (from 91)
  - tests: 68 passed (from 67+1 fail)
  - mypy: 52 pre-existing errors (non-blocking in CI)
- Files created/modified:
  - pyproject.toml (rewritten)
  - .github/workflows/ci.yml (created)
  - tests/test_db.py (fixed schema version + import order)
  - src/lottery/builders.py (unused var removed)
  - src/lottery/interval_markov.py (unused var removed)
  - src/lottery/web_app.py (unused vars removed)
  - src/lottery/weight_optimizer.py (zip strict)
  - requirements.txt (deleted)

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | 锐评整改轮，Phase 0 完成，7 个任务待开始 |
| Where am I going? | 按优先级：先 CI/lint，再依赖规范，再文件拆分 |
| What's the goal? | 从"能跑就行"升级到"能维护、能部署、能协作" |
| What have I learned? | 8 个工程短板，统计算法已到位，基础设施拖后腿 |
| What have I done? | 全项目盘点 + 锐评 + 新 plan/findings/progress 就绪 |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| — | — | — | — |
