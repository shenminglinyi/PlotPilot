# AGENTS.md

PlotPilot（墨枢）— 开源剧情引擎内核，用结构化叙事状态管理在数十万字规模上保住人物一致性、因果链完整性与伏笔闭环。LLM 仅作 prose 生成器，续读由 `engine/runtime/` 下的运行时承载。

> 这份文件是面向所有 AI 编程 Agent 的项目总览。具体到本机 Claude Code 的工作约定见同目录 `CLAUDE.md`（比 `AGENTS.md` 更细，包括 entry-point 陷阱、运行时坑位、单一写者派发器等）。

## Setup commands

### 后端（Python 3.11+，SQLite，向量库默认 ChromaDB）

- 装核心依赖（秒级）：`pip install -r requirements.txt`；用 uv 则 `uv sync`（按 `pyproject.toml` + `uv.lock` 一步建 `.venv` 并装依赖，要求 Python ≥3.14，uv 会自动下载）
- 装本地向量模型（按需，不在 `uv.lock` 里）：`pip install -r requirements-local.txt`；用 uv 则 `uv pip install -r requirements-local.txt`
- 复制环境变量：`cp .env.example .env`，至少填一个 LLM key（`ANTHROPIC_API_KEY` / `ARK_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY`）
- 启动 API 服务（端口 8005）：`uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload`；用 uv 则 `uv run uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload`；加 `DISABLE_AUTO_DAEMON=1` 可禁止 API 启动时自动拉起守护进程
- 启动独立守护进程（与 API 同 DB/日志）：`python scripts/start_daemon.py` / `uv run python scripts/start_daemon.py`（`scripts/setup/start_daemon.py` 是过期副本，别用）
- 应用数据库迁移（启动时也会自动跑）：`python scripts/run_migrations.py` / `uv run python scripts/run_migrations.py`
- **uv 通用规则**：项目根下任何 `python` / `uvicorn` / `pytest` 命令加 `uv run` 前缀即等价切换，无需手动激活 `.venv`
- **Entry-point 陷阱**：`python cli.py serve` / `python -m cli serve` 会因相对导入失败（正确姿势是在上级目录 `python -m PlotPilot serve`）；`python interfaces/main.py` 绑的是 `0.0.0.0:8000` 而非 8005

### 前端（Vue 3 + TS + Naive UI + Vite，可选 Tauri 桌面壳）

- 装依赖：`cd frontend && npm ci`
- 开发服务器（端口 3000，`/api` 代理到 8005）：`npm run dev`
- 构建（**这是唯一的前端门禁**，包含 `vue-tsc` 类型检查）：`npm run build`
- Tauri 桌面：`npm run tauri:dev` / `npm run tauri:build`
- 校对前端 taxonomy 与 `shared/taxonomy/*.yaml` 不漂移：`npm run check:shared-config`（未接入 CI，改了 `shared/taxonomy/` 要手动跑）
- `predev`/`prebuild` 会自动重新生成 taxonomy JSON，漂移会被静默修复——只改 YAML 源，**绝不改生成的 JSON**

## Project layout

按 DDD 分层 + 一块独立的生产运行时内核：

- `domain/` — 纯业务模型，零外部依赖（**改这里最稀有**，约 19/200 次提交）
- `application/` — 用例编排（**最高频修改**，约 622/200 次提交）；内含 Evolution / Governance / Memory / DAG / Narrative Engine 等子系统
- `infrastructure/` — 可替换技术：LLM 客户端、向量库、SQLite 仓、导出器、CPMS
- `interfaces/` — FastAPI 边界 + DI 工厂 + 守护进程管理；新依赖都加在 `interfaces/api/dependencies.py`
- `engine/` — **生产运行时内核**，独立包；包含 `engine/runtime/`、`engine/pipeline/`、`engine/pipelines/`、`engine/core/`
- `frontend/` — 官方工作台：Vue 3 + TS + Naive UI + Tauri 壳
- `shared/taxonomy/` — 跨端分类学的 YAML（前端 JSON 是从这里生成的产物）
- `scripts/` — 工具脚本（守护进程、迁移、评估、安装器）
- `tests/` — 单测 / 集成 / DAG / E2E，镜像分层结构
- `docs/` — 长文档（`ARCHITECTURE.md`、`BUILD_INSTALLER.md` 等）；**部分内容已过时**（如章节 pipeline 实为 12 步而非"十步"、并无 FAISS 实现），以代码为准
- `tools/` — 启动器（`plotpilot.bat`）、嵌入模型下载说明

## Code style

- **没有 Python linter/formatter**（无 ruff/black/flake8/pre-commit）；不要发明 `python -m lint`
- **没有前端 ESLint**；`npm run build` 是前端唯一门禁
- **依赖边界是"约定"，不是强制的**：`domain/` 不应引入外部依赖；现有的越界（如 `domain/engine/dag/repositories/dag_version_repository.py` 引入 `application`）不要新增
- **分层位置是 PR 评审项**：新建文件先想清楚属于哪一层；加表/字段 PR 必须写迁移说明；改 API 契约必须显式说明
- **SQLite 写盘统一走单一写者派发器**：业务代码不要直接 `import sqlite3`，经 `infrastructure/persistence/database/connection.py` 的 `db.execute()` / `db.transaction()`；底层 `write_dispatch.py` 负责串行化
- **Prompt 注入字符串用常量**：`infrastructure/ai/prompt_keys.py` 是 CPMS 76 个节点键的唯一来源；新增模板放在 `infrastructure/ai/prompt_packages/nodes/<node_key>/` 并 bump `bundle_meta.yaml` 版本号
- **测试镜像分层**：`tests/unit/{application,domain,engine,infrastructure,interfaces}/`；CI 只跑 `pytest tests/unit -q --tb=short`
- **两种 import 风格并存**：仓库根自身是包（根 `__init__.py` + `__main__.py`），`import application.x` 与 `PlotPilot.application.x` 都能解析；跟随所改文件的既有风格，别混用（同模块双名加载会产生重复模块状态）
- **弃用 shim 不要续命**：`engine/application/` 与 `application/engine/services/autopilot_daemon.py` 都是转发到 `engine/runtime/` 的弃用层，新代码一律写向 `engine/runtime/`

## Testing instructions

- 单测（**CI 默认**）：`pytest tests/unit -v`（uv 环境：`uv run pytest tests/unit -v`，下同）
- 集成：`pytest tests/integration -v`
- DAG 专项：`pytest tests/dag -v`
- 全量：`pytest tests/ -v`
- 跑单个用例：`pytest <path>::<Class>::<test> -q`
- 前端类型 + 构建：`cd frontend && npm run build`
- 新行为必须有测试；与新文件同包的现有 `test_*.py` 是模板
- 测试需要占位 LLM key（已在 CI 配 `ANTHROPIC_API_KEY=test-placeholder`）

## PR & commit conventions

- 默认分支是 `master`；**永远不要直接 push 到 master**，先 fork 或拉分支
- 提交风格自由（项目本身不强制 conventional commits）
- PR 模板强制回答：新增文件在哪一层、为什么；新增表/字段的迁移说明；变更 API 契约的影响范围
- CI 绿后用 `gh pr create` 开 PR；远程：fork 是 `git@github.com:uwakeme/PlotPilot.git`、上游是 `git@github.com:shenminglinyi/PlotPilot.git`（本机 HTTPS 443 不通，SSH 22 通）

## Security

- **绝不要提交密钥**：`.env` 在 `.gitignore`；`data/`、`logs/`、数据库、向量库目录也全部 gitignore
- LLM key 至少配一个；缺 key 会落到 `MockProvider`，不代表能上线
- 写盘测试一律设 `PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES=1`；**应用代码不要设**，会绕开单一写者派发器
- Windows 是主要开发平台；桌面端走 Tauri；`tools/plotpilot.bat` 是统一启动器