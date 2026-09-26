# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PlotPilot (墨枢) is an open-source **narrative engine kernel** for long-form AI-assisted fiction writing. It is not a chatbot — it is a systems-engineering approach to maintaining character consistency, causal chain integrity, and foreshadowing closure across hundreds of thousands of words via structured narrative state management.

The LLM is treated as a stateless prose generator; all continuity lives in engine-managed state (Bible, chapter summary chains, narrative events, story-line DAG, foreshadowing registry) assembled into a context window per chapter.

## Commands

```bash
# Backend — API server (port 8005). Run from the repo root.
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload

# Autopilot daemon — standalone production entry (writes to the same DB/log)
python scripts/start_daemon.py

# Frontend — dev server (port 3000, proxies /api → 127.0.0.1:8005)
# `predev`/`prebuild` hooks auto-run the shared-taxonomy sync first
cd frontend && npm run dev

# Frontend — type-check + build (vue-tsc is the ONLY type check; there is no ESLint)
cd frontend && npm run build

# Frontend — verify generated taxonomy bundles match shared/ sources
cd frontend && npm run check:shared-config

# Tauri desktop client
cd frontend && npm run tauri:dev
cd frontend && npm run tauri:build

# Tests
pytest tests/ -v
pytest tests/unit -v              # 272 files — what CI runs
pytest tests/integration -v       # 31 files
pytest tests/dag -v               # 9 files

# Single test file / single test
pytest tests/unit/application/foo/test_bar.py -q
pytest tests/unit/application/foo/test_bar.py::TestBar::test_baz -q

# Coverage
pytest tests/ --cov=. --cov-report=term-missing

# Apply DB migrations (also runs automatically on startup)
python scripts/run_migrations.py
```

**There is no Python linter or formatter configured** (no ruff/black/flake8/pre-commit) and no frontend linter. Do not invent lint commands; `npm run build` is the frontend gate.

### uv equivalents

The repo ships `pyproject.toml` + `uv.lock` (requires Python ≥ 3.14; `uv` downloads it if missing). Any command above that assumes an activated venv has a 1:1 `uv run` form — no manual activation needed:

```bash
uv sync                                        # replaces `python -m venv .venv` + `pip install -r requirements.txt`
uv pip install -r requirements-local.txt       # local vector models (not in the lockfile, uses pip-compat layer)
uv run uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
uv run python scripts/start_daemon.py
uv run python scripts/run_migrations.py
uv run pytest tests/unit -v
```

### Entry-point gotchas

- `python cli.py serve` and `python -m cli serve` **both fail** with `ImportError: attempted relative import with no known parent package` — `cli.py` uses relative imports because the repo root is itself a package (root `__init__.py`, `__main__.py`). The working form is `python -m PlotPilot serve` **from the parent directory** (`D:\WorkSpace\projects`). Note it kills whatever process holds port 8005 before binding.
- `python interfaces/main.py` binds **`0.0.0.0:8000`**, not 8005. Use the `uvicorn` command above.
- `scripts/setup/start_daemon.py` is a **stale duplicate** that imports the deprecated `AutopilotDaemon`, uses an old `data/novels.db`, and a simplified `ContextBuilder`. Always use `scripts/start_daemon.py`.

## Architecture

DDD four layers, plus a fifth sibling package (`engine/`) that holds the production runtime.

```
domain/           # Pure business models. Zero external deps. Changing this is rare (19/200 recent commits).
application/      # Use-case orchestration. Highest churn (622/200 recent commits).
infrastructure/   # Replaceable tech: LLM clients, vector stores, SQLite repos, exporters.
interfaces/       # FastAPI boundary + DI factories + daemon process management.
engine/           # The production runtime kernel — daemon, chapter pipeline, genre pipelines.
frontend/         # Official workbench: Vue 3 + TS + Naive UI + Tauri shell.
shared/           # Cross-cutting taxonomy YAML (SSOT for generated frontend JSON).
```

`domain/`, `application/`, `infrastructure/`, `interfaces/` are all importable as **top-level** modules (`import application.paths`) thanks to `pythonpath = .` in `pytest.ini`. A few entry points instead use package-relative imports (`PlotPilot.*`). Both styles coexist — check the file you are editing.

### `engine/` — the production kernel

This is the most important package and is separate from `application/engine/` (a normal DDD application package with no special status):

```
engine/runtime/     # EngineDaemon, StoryPipelineRunner (runner.py), daemon_host.py, daemon_loop.py,
                    # stage delegates (macro_planning / act_planning / writing / legacy_writing / audit),
                    # novel_lifecycle.py, policy_validator.py, quality_guardrails/, plot_state_machine/
engine/pipeline/    # BaseStoryPipeline (base.py) — the 12-step chapter pipeline; context, steps,
                    # beat_contracts, generation_prompt_builder, prose_composer, recovery, telemetry
engine/pipelines/   # Genre registry (registry.py → PipelineRegistry). Only "wuxia" is registered;
                    # unknown genres fall back to ThemedStoryPipeline.
engine/core/        # Engine-side entities, ports (LLMPort/PersistencePort/EventPort/TracePort), VOs
engine/infrastructure/  # event_bus, engine-side memory (character_psyche/soul, echo_recall), checkpoint & trace stores
engine/application/ # DEPRECATED shim re-exporting engine.runtime.* ("will be removed in v4.0")
```

### Production daemon chain

```
scripts/start_daemon.py :: build_daemon()
    → reuses interfaces.api.dependencies factories (so daemon and API share one config)
    → builds repos, BackgroundTaskService, ContinuousPlanningService,
      ChapterAftermathPipeline, CircuitBreaker
    → EngineDaemon(...)  [engine/runtime/engine_daemon.py]  — "统一生产入口"
            → StoryPipelineRunner [engine/runtime/runner.py]
                    → BaseStoryPipeline [engine/pipeline/base.py]
```

`interfaces/daemon_manager.py:175` does `from scripts.start_daemon import build_daemon` — the API and the standalone daemon construct the daemon through the *same* factory. When adding a dependency to the daemon, add it there.

`PLOTPILOT_USE_STORY_PIPELINE` is read in `engine/runtime/writing_delegate.py`: unset / `writing` / `1` / `full` / `engine` → StoryPipeline; `off` / `legacy` → legacy beat writing (emergency rollback path).

**The pipeline has 12 steps, not ten** (`grep 'def _step_' engine/pipeline/base.py`): `find_next_chapter`, `prepare_governance`, `build_context`, `prepare_chapter_plan`, `generate`, `generate_with_composer`, `validate_content`, `save_chapter`, `validate_voice`, `run_post_commit`, `score_tension`, `finalize`. README and `docs/ARCHITECTURE.md` both say "十步" — they are wrong.

## Engine Subsystems

Each is a bounded context in `application/` with one public service. Cross-importing internals is **convention only — not enforced** (there is no import-linter config or boundary test; cross-engine imports do occur).

| Engine | Path | Public entry point |
|--------|------|--------------------|
| **Evolution** | `application/evolution/` + `domain/evolution/` | `EvolutionGateService` (gate_service.py); domain side has `contracts.py`, `models.py`, `reducer.py` |
| **Governance** | `application/governance/` | `NarrativeGovernanceService` (service.py) |
| **Memory** | `application/memory/` + `domain/memory/` | `CharacterContextCompiler` (character_context_compiler.py) |
| **Chronicles (Codex)** | `application/codex/chronicles_service.py` | Module-level functions, no class: `infer_chapter_from_texts`, `build_chronicles_rows` |
| **Snapshot** | `application/snapshot/services/snapshot_service.py` | `SnapshotService` |
| **Checkpoint** | `application/checkpoint/services/unified_checkpoint_service.py` | `UnifiedCheckpointService` |
| **DAG Engine** | `application/engine/dag/` | LangGraph-style DAG executor; compiles `DAGDefinition` → StateGraph |
| **Narrative Engine** | `application/narrative_engine/` | `NarrativeEngineReadFacade` (read_facade.py) — a **read-only BFF facade**, not a generator. `NarrativeLens` enum (catalog.py) defines the 10 lens dimensions. |

`application/narrative_engine/` route nuance: only `GET /api/v1/narrative-engine/surface-catalog` lives under that prefix (`surface_router`). The other endpoints hang off `GET /api/v1/novels/{novel_id}/narrative-engine/...`.

## Cross-Cutting Mechanisms

These require reading several files to understand — get them right before touching related code.

### Write Dispatch (single-writer router)

SQLite writes are serialized through a queue. This is **transparent at the connection layer**: repositories call `db.execute()` / `db.transaction()` normally and never import the dispatcher.

- `infrastructure/persistence/database/write_dispatch.py` — the dispatcher.
- `infrastructure/persistence/database/connection.py` is where routing happens: `execute()` checks `sql_is_mutating(sql) and not allow_direct_sqlite_writes() and not is_sqlite_writer_thread()` and enqueues onto the `persistence_queue`; `transaction()` from a non-writer thread collects SQL in a `TxnCollectingConnection` and flushes it as one `EXECUTE_SQL_TXN_BATCH`.

**Rule:** never open a raw `sqlite3` connection in application/interfaces code — always go through the `DatabaseConnection` wrapper so writes reach the queue. `write_dispatch.py` must not read `os.getenv` (a test enforces this). Escape hatches are narrow and intentional: `sqlite_writes_bypass_queue()`, `startup_sqlite_writes_bypass_queue()`, and `PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES=1` — which `tests/conftest.py::pytest_configure` sets for the whole test suite.

### Dependency injection

There is no DI container. Dependencies are module-level factory functions in **`interfaces/api/dependencies.py`** (plus `interfaces/api/container.py` for store selection), wrapped with caching. Both FastAPI routes and `scripts/start_daemon.py` call these same factories — that is the mechanism keeping the daemon and API on one configuration. Add new wiring there, not ad hoc.

### LLM providers

- Port: `domain/ai/services/llm_service.py` (`LLMService`, `GenerationConfig`, `GenerationResult`).
- Implementations: `infrastructure/ai/providers/` — `anthropic_provider.py`, `openai_provider.py`, `gemini_provider.py`, `mock_provider.py`.
- Selection is by **protocol string**, not class name, in `infrastructure/ai/provider_factory.py`: `"anthropic"` → `AnthropicProvider`, `"gemini"` → `GeminiProvider`, **anything else → `OpenAIProvider`**. Ark/Doubao is *not* a separate provider class — it is the OpenAI-compatible path. A missing key or model falls back to `MockProvider`.
- Runtime entry is `DynamicLLMService` (same file), which caches providers per profile and hot-swaps on profile change.
- To add a provider: implement `LLMService`, add a branch in `LLMProviderFactory.create_from_profile`, register a profile with the new `protocol`.

### Prompt strategy (CPMS)

"Prompt injection points" are CPMS **node keys**. The real count is **76**, not "20+".

- `infrastructure/ai/prompt_keys.py` — the single source of truth. Business code must import constants from here rather than hardcoding strings.
- `infrastructure/ai/prompt_packages/nodes/<node_key>/` — seed content: `package.yaml` (metadata + `variables`), `system.md`, `user.md`, optional `extras.json`. `bundle_meta.yaml` carries the version.
- `PromptManager.ensure_seeded()` (`infrastructure/ai/prompt_manager.py`) imports the YAML into SQLite (`prompt_templates` / `prompt_nodes` / `prompt_versions`). A `bundle_meta.yaml` **version bump** triggers incremental sync; rows with `created_by=user` are never overwritten.
- **The YAML directory is the release/seed source; per-user overrides live in the DB** (the 提示词广场 UI), not in YAML. Editing YAML alone does not change runtime behaviour for an existing install until the bundle version is bumped.
- Rendering goes through `infrastructure/ai/prompt_gateway.py` (`PromptGateway` — "CPMS-only prompt rendering entry"). Callers hold a `PromptContract` (`infrastructure/ai/prompt_contract.py`) defined in `infrastructure/ai/prompt_contracts/*.py` and call `get_prompt_gateway().render(CONTRACT, {...})` then `.validate_output(...)`.

### Vector retrieval (two parallel indexes)

Both live in `application/analyst/services/` and are wired in `interfaces/api/dependencies.py`:

1. **Chapter content index** — `chapter_indexing_service.py` (`ChapterIndexingService`), collection `novel_{novel_id}_chunks`; payload `kind` is `chapter_summary` or `bible_snippet`.
2. **Triple index** — `triple_indexing_service.py` (`TripleIndexingService`), queried via `sync_search(...)`; consumed by `application/world/services/knowledge_service.py::search_knowledge` using vector-first with fuzzy-text fallback and auto-indexing when empty.

Store selection is `interfaces/api/container.py::get_vector_store`: `VECTOR_STORE_TYPE=qdrant` → `infrastructure/ai/qdrant_vector_store.py`, otherwise `chromadb_vector_store.py` (default). A store init failure degrades to disabled rather than crashing. **There is no FAISS implementation** despite README/`docs/ARCHITECTURE.md` mentioning it. Embeddings: `local_embedding_service.py` (sentence-transformers) or `openai_embedding_service.py`.

### Database migrations

Plain `.sql` files in `infrastructure/persistence/database/migrations/` (32 today), applied idempotently by `infrastructure/persistence/database/migration_runner.py` and tracked in a `migrations_applied` table. Newest files use `NNN_name.sql`; older ones use `add_*.sql`. Add a migration by dropping in a new `.sql` file — do not edit applied ones. The PR template requires a migration note whenever you add a table or column.

### Frontend taxonomy sync

`shared/taxonomy/*.yaml` is the **authoritative** source; `frontend/scripts/sync-builtin-taxonomy.mjs` compiles it to JSON bundles (`frontend/src/domain/taxonomy/builtin_cn_v1.bundle.json`, `frontend/src/domain/worldbuilding/contract.bundle.json`) for static TS import. It also enforces a banned-phrase list (anti-cliché guard) and fails if any leak in.

`predev`/`prebuild` regenerate the bundles automatically, so **drift is silently repaired at build time** — `npm run check:shared-config` is the only thing that fails on drift, and it is **not wired into GitHub CI**. Run it manually when you touch `shared/taxonomy/`. Edit the YAML, never the generated JSON.

## Conventions

- **Layer placement is a review gate.** The PR template asks which layer a new file belongs to (`domain` / `application` / `infrastructure` / `interfaces` / `frontend` / `scripts`) and why. Adding a DB table/field requires a migration note; changing an API contract must be called out.
- **Import boundaries are aspirational, not enforced.** `domain/` is meant to have zero external deps, but `domain/engine/dag/repositories/dag_version_repository.py` already imports from `application/engine/dag/models` (a domain→application inversion). Don't add more.
- `docs/ARCHITECTURE.md` is itself out of date (its `domain/` tree omits `cast/`, `character/`, `evolution/`, `engine/`, `structure/`, `worldbuilding/`; its `application/` tree lists 9 of ~30 packages). Trust the code.
- Tests mirror the layer structure: `tests/unit/{application,domain,engine,infrastructure,interfaces}/`. CI runs only `pytest tests/unit -q --tb=short` with placeholder API keys.
- Frontend uses the `@/` alias for `frontend/src/`. Vite manual chunks: `naive-ui`, `echarts`, `vue-runtime`, `vendor`. The `/api` proxy sets `timeout: 0` for SSE — keep it.

## Environment Variables

Copy `.env.example` to `.env` (loaded by `load_env.py` / `python-dotenv`) and set at least one LLM key.

| Variable | Notes |
|---|---|
| `LLM_PROVIDER` | Optional default provider |
| `ANTHROPIC_API_KEY` / `ARK_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | At least one required |
| `<PROVIDER>_BASE_URL` / `<PROVIDER>_MODEL` | Per-provider endpoint and model |
| `EMBEDDING_SERVICE` | `openai` (default) or `local` (needs `requirements-local.txt`) |
| `EMBEDDING_API_KEY` / `_BASE_URL` / `_MODEL` | Falls back to `OPENAI_API_KEY` when empty |
| `EMBEDDING_MODEL_PATH` / `EMBEDDING_USE_GPU` | Local model path / GPU toggle |
| `VECTOR_STORE_TYPE` | `chromadb` (default) or `qdrant` |
| `PLOTPILOT_USE_STORY_PIPELINE` | `off`/`legacy` rolls back to legacy writing |
| `PLOTPILOT_PROD_DATA_DIR` | Overrides the data directory (legacy alias `AITEXT_PROD_DATA_DIR` still works); `PLOTPILOT_FORCE_PROD_DATA` forces production mode |
| `PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES` | `1` bypasses the write queue — tests set this; don't use it in app code |
| `PLOTPILOT_DEFAULT_CHAPTERS` / `PLOTPILOT_DEFAULT_WORDS_PER_CHAPTER` / `PLOTPILOT_SUMMARY_MAX_CHAPTERS` | Default planning knobs |
| `DISABLE_AUTO_DAEMON` | `1` = do not auto-start the daemon when the API boots |
| `LLM_PROVIDER` / `CORS_ORIGINS` / `LOG_LEVEL` / `LOG_FILE` | Read from code, not shown in `.env.example` (`LLM_PROVIDER` in `infrastructure/ai/llm_environment.py`, `CORS_ORIGINS` in `interfaces/api/settings.py`) |

## Data

- SQLite: `data/plotpilot.db` (path resolved by `application.paths.DATA_DIR`; `get_db_path()` falls back to the legacy `aitext.db`)
- Vector store: `data/chromadb/`
- Logs: `logs/plotpilot.log`
- `.env` is gitignored. Never commit `data/`, `logs/`, databases, or secrets — see the security section in README.md.

## Runtime gotchas

- **Don't run `python interfaces/main.py`** — it binds `0.0.0.0:8000` and conflicts with nothing but confuses the 8005 default.
- The API can **auto-start the autopilot daemon** at boot; use `DISABLE_AUTO_DAEMON=1` when you want a clean API-only process.
- `application/engine/services/autopilot_daemon.py` is a **deprecated shim** emitting `DeprecationWarning`; it re-delegates into `engine.runtime.*`. Same for `engine/application/`. Write new code against `engine/runtime/`.
- The repo root is a package (`__init__.py` + `__main__.py`), so both `import application.x` and `PlotPilot.application.x` resolve — importing the same module under two names creates duplicate module state. Prefer the top-level form used by the file you're editing.
- Always call `.validate_output(...)` on gateway renders rather than trusting raw LLM JSON — that is what the `PromptContract.output_schema` is for.
- Windows is the primary dev platform (`tools/plotpilot.bat` launcher, Tauri desktop, `SIGBREAK` handler in `interfaces/main.py`).
