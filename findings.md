# Findings & Decisions（锐评整改轮）

## 锐评核心发现 (2026-05-17)

### 工程短板盘点

1. **builders.py 1658 行** — 22 个函数塞一个文件，分析/预测/Markdown/预算全部堆在一起
2. **web_app.py 1336 行** — 38 个路由函数，零蓝图拆分，Flask 最佳实践全部绕过
3. **零 CI/CD** — 无 `.github/workflows/`，push 后无任何自动化
4. **零 lint/type-check 配置** — `pyproject.toml` 只有 build-system，没有 ruff/mypy/pytest 配置
5. **依赖管理不完整** — `requirements.txt` 仅 3 行，`pyproject.toml` 仅 2 个依赖，缺少 dev deps
6. **data/raw/ 空目录** — 数据血缘从 processed CSV 直接开始，无原始副本溯源
7. **规则四轨制** — CLAUDE.md / .cursor/rules/*.mdc / AGENTS.md / .cursor/agents/*.md 手动同步
8. **测试覆盖偏薄** — 692行测试 vs 8125行源码 (8.5%)，builders/web_app/weight_optimizer 零测试

### 不算问题的问题（锐评吐槽但不入计划）
- 统计算法方向性争议（彩票本质是随机）→ 这是练手项目，技术栈本身有价值
- Web UI 自娱自乐 → 同上，练 Flask 全栈是正经技能
- weight_optimizer 回测过拟合 → 工程上 Dirichlet + 回测框架本身是正确的

## 本轮优化策略

**不做的事：**
- 不改统计算法（上一轮已完成）
- 不改预测模型逻辑
- 不全量回溯 raw 数据
- 不统一 IDE 工具链（Cursor ↔ Claude Code 双轨暂时共存）

**优先做的事（按收益/成本排序）：**
1. CI + lint + type-check（成本最低收益最大）
2. 依赖管理规范化（顺手的事）
3. builders.py 拆分（大工程但值）
4. web_app.py 模块化（练手价值高）
5. 测试补强（builders 烟雾测试优先）
6. 数据治理 raw 层说明（敷衍一下但得做）
7. 规则文件收敛（加护栏不重构）
