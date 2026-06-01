# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PlotPilot (墨枢) is an open-source **narrative engine kernel** for long-form AI-assisted fiction writing. It's not a chatbot — it's a systems-engineering approach to maintaining character consistency, causal chain integrity, and foreshadowing closure across hundreds of thousands of words via structured narrative state management.

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

## Architecture: DDD Four-Layer

```
domain/           # Domain layer — zero external deps, pure business logic
  novel/          # Novel aggregate, Chapter entity, Storyline, Foreshadowing registry
  bible/          # Story Bible aggregate root (composes cast/worldbuilding/structure)
  cast/           # Character roster (ensemble-level view, distinct from per-character model)
  character/      # Character entity model (POV firewall, frequency scheduling)
  worldbuilding/  # World setting triples, locations, factions
  structure/      # Macro structure (part/volume/act/chapter scaffolding)
  knowledge/      # Knowledge triples, story knowledge graph
  evolution/      # State change events — character status, item transfer, fact reveal
  memory/         # Per-character compiled context, arc projection
  prop/           # Props / items tracked across chapters
  engine/         # Engine-side domain types shared across application engines
  ai/             # LLM service interfaces, prompt value objects, token stats
  shared/         # Shared kernel (base classes, domain events, exceptions)

application/      # Application layer — use-case orchestration
  engine/         # AI generation service, autopilot daemon, DAG executor, context assembler
  blueprint/      # Macro planning (part-volume-act), act-level beat sheets
  world/          # Bible management, knowledge graph construction
  audit/          # Chapter review, macro restructuring, cliché scanner
  analyst/        # Style analysis, tension analysis, drift detection
  workflows/      # Post-chapter pipeline orchestration
  novel/          # Novel/chapter CRUD services
  narrative_engine/  # Story pipeline (10-step BaseStoryPipeline)
  narrative/      # Narrative-domain application services (shared by engines)
  manuscript/     # Manuscript-level read/write operations (chapter body, revisions)
  evolution/      # Evolution Engine — state-change tracking & gate validation
  governance/     # Governance Engine — narrative-contract enforcement
  memory/         # Memory Engine — character-context compilation
  codex/          # Chronicles (Codex) — dual-helix plot timeline + semantic snapshots
  snapshot/       # Snapshot manager (checkpoint create / rollback / HEAD)
  checkpoint/     # Checkpoint persistence primitives
  character/      # Character-level use cases
  prop/           # Prop/item use cases
  reader/         # Reader-facing read models
  workbench/      # Workbench-specific aggregation (frontend BFF helpers)
  ai/             # AI orchestration helpers (prompt assembly, retries)
  core/           # Cross-cutting application primitives
  services/       # Misc application services
  dtos/           # Cross-layer DTOs

infrastructure/   # Infrastructure layer — replaceable tech implementations
  ai/             # LLM clients, ChromaDB/Qdrant vector store, embedding services
    providers/    # anthropic_provider, openai_provider, gemini_provider, mock_provider
    prompt_packages/  # YAML-overridable prompt packs (20+ injection points)
    prompts/      # Raw prompt templates
  persistence/    # SQLite repositories, Write Dispatch (single-writer router)
  json_stream/    # Streaming JSON parsing utilities

interfaces/       # Interface layer — external boundaries
  api/v1/         # Versioned REST API (FastAPI), split by subdomain:
    core/ engine/ world/ blueprint/ audit/ analyst/ prop/ reader/ workbench/ meta/
    anti_ai.py    # Anti-AI-detection endpoints
    system.py     # System / health endpoints
```

## Engine Subsystems

PlotPilot contains multiple specialized engines, each with a distinct role in the narrative production pipeline:

| Engine | Layer | Role |
|--------|-------|------|
| **Autopilot Daemon** | `application/engine/services/` | Staged state machine driving full-novel generation: macro planning → act beats → chapter loop → post-chapter pipeline. Circuit breaker, SSE streaming, checkpoint snapshots. |
| **DAG Engine** | `application/engine/dag/` | LangGraph-based DAG executor with topological parallel execution. Compiles `DAGDefinition` → `StateGraph`, supports checkpoint/resume. Nodes split by concern: planning, context, execution, review, validation, gateway, anti-AI, props, world. |
| **Narrative Engine** | `application/narrative_engine/` | Novelist-facing **BFF read surface**. Aggregates read models across all domains via `NarrativeLens` dimensions (manuscript, macrocosm, plot structure, time/revision, subtext, persona/voice, craft/quality, knowledge graph, automation, platform). Exposed via `/api/v1/narrative-engine/`. |
| **Evolution Engine** | `application/evolution/` + `domain/evolution/` | Tracks story-world state changes across chapters: character status (alive/dead/missing), item transfers, fact reveals, storyline progress, emotional residue. Gate validation ensures state transitions are narratively coherent. |
| **Governance Engine** | `application/governance/` | Enforces narrative contracts: canonical storylines with alias merging, forbidden early payoffs, reveal budgets, theme anchors. Produces `GovernanceReport` with severity-ranked issues. |
| **Memory Engine** | `application/memory/` + `domain/memory/` | Compiles character-specific context across chapters, projects character arcs forward, imports legacy memory formats. |
| **Chronicles (Codex)** | `application/codex/` | Dual-helix chronicles: zipper-merges plot timeline with semantic snapshots by chapter index for time/revision queries. |
| **Snapshot Manager** | `application/snapshot/` | Checkpoint creation, rollback, and HEAD tracking for the autopilot state machine. |

## Key Design Decisions

- **All SQLite writes** go through a single-writer dispatcher (`Write Dispatch`) to eliminate concurrent write conflicts
- **LLM providers** are abstracted behind a unified interface; switching models doesn't touch business code. Providers: Anthropic, OpenAI-compatible, Ark (Doubao), Gemini
- **Prompt strategy**: 20+ independent prompt injection points, each overridable via YAML config in `infrastructure/ai/prompt_packages/`
- **Vector retrieval**: Two parallel indexes — chapter content (ChromaDB / Qdrant) and knowledge triples (structured + semantic hybrid query)
- **Autopilot daemon** drives full-novel generation as a staged state machine with circuit breaker protection, checkpoint snapshots, and SSE real-time streaming
- **Bible composition**: `domain/bible/` is the aggregate root; `cast/`, `character/`, `worldbuilding/`, `structure/` are sub-aggregates broken out for independent evolution. Don't reach across them — go through the bible aggregate or an application service.
- **Engines vs. application services**: The "Engines" in the table above (Evolution, Governance, Memory, Codex, Snapshot) each have their own `application/<name>/` package with a clear public service; treat them as bounded contexts and avoid cross-importing internals.
- **Frontend** uses `@/` alias for `frontend/src/`; chunk splitting: naive-ui, echarts, vue-runtime, vendor. Vue 3 + TypeScript + Vite + Pinia + Vue Router + Vue Flow (DAG viz) + ECharts. Tauri 2.x for desktop builds.

## Environment Variables

Copy `.env.example` to `.env` and configure at minimum one LLM key (`ANTHROPIC_API_KEY` or `ARK_API_KEY`). Key vars: `EMBEDDING_SERVICE` (openai/local), `VECTOR_STORE_TYPE` (chromadb), `LOG_LEVEL`, `LOG_FILE`, `CORS_ORIGINS`, `DISABLE_AUTO_DAEMON`.

## Data

- SQLite DB: `data/plotpilot.db` (auto-created; falls back from old `aitext.db`)
- Vector store: `data/chromadb/`
- App logs: `logs/plotpilot.log`
- `.env` is gitignored; never commit secrets
