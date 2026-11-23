# Claude Code repository guide

PlotPilot（墨枢）是面向长篇 AI 创作的叙事引擎。本文只保留 Agent 开工所需的约束与命令；产品说明见 [README.md](README.md)，分层与数据流见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，全部维护文档见 [docs/README.md](docs/README.md)。不要在这里复制完整架构清单，以免与代码和正式文档漂移。

## Commands

```bash
# Backend — start API server (port 8005)
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload

# CLI entry point
python cli.py serve --reload

# Frontend — dev server (port 3000, proxies /api → 8005)
# `predev` hook auto-runs scripts/sync-builtin-taxonomy.mjs first
cd frontend && npm run dev

# Frontend — type-check (vue-tsc) + build
cd frontend && npm run build

# Frontend — Tauri desktop client
cd frontend && npm run tauri:dev
cd frontend && npm run tauri:build

# Tests — all
pytest tests/ -v

# Tests — unit / integration only
pytest tests/unit -v
pytest tests/integration -v

# Tests with coverage
pytest tests/ --cov=. --cov-report=term-missing

# Install dependencies
pip install -r requirements.txt           # core (lightweight)
pip install -r requirements-local.txt     # + local embedding models
```

## Architecture boundaries

- `domain/` contains business rules and must not depend on infrastructure or interfaces.
- `application/` orchestrates use cases through ports; do not import concrete persistence or provider internals across bounded contexts.
- `engine/` owns the production runtime and chapter pipeline.
- `infrastructure/` implements storage, AI providers, export and runtime adapters.
- `interfaces/` exposes FastAPI and process boundaries; `frontend/` is Vue 3 + Tauri.
- All SQLite writes must go through the single-writer dispatch path. Direct writes are limited to explicit migration/test tooling.

## Working rules

- Solve root causes instead of accumulating compatibility patches.
- Keep changes scoped and preserve unrelated user edits in a dirty worktree.
- Add or update tests for behavior changes. Run the narrowest relevant tests first, then broader checks proportional to risk.
- Keep `VERSION` as the release version source; use `scripts/sync_release_version.py` rather than editing generated version fields independently.
- Never commit `.env`, keys, local databases, logs, model files or build artifacts.
- Frontend source uses the `@/` alias for `frontend/src/`; built-in taxonomy changes must pass `npm run check:shared-config --prefix frontend`.

## Environment Variables

Copy `.env.example` to `.env` and configure at least one supported LLM provider. Treat `.env.example` as the authoritative variable inventory rather than duplicating it here.

## Local data

- SQLite DB: `data/plotpilot.db` (auto-created; falls back from old `aitext.db`)
- Vector store: `data/chromadb/`
- App logs: `logs/plotpilot.log`
- `.env` is gitignored; never commit secrets
