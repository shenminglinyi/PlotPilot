# Style Bible Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a medium-scope writing-technique knowledge base that learns style, pacing, and craft rules from user-provided novel samples, saves them as editable style profiles, and injects selected profiles into chapter generation.

**Architecture:** Add a new `style_bible` bounded context that follows the existing DDD layout: `domain/style_bible`, `application/style_bible`, SQLite repository, FastAPI routes, and a Vue workbench panel. The system stores raw samples and chunks, computes deterministic metrics, optionally asks the active LLM to extract technique cards, then composes a compact prompt overlay for chapter generation.

**Tech Stack:** Python 3, FastAPI, SQLite, Vue 3 + TypeScript + Naive UI, existing LLM control/provider layer, existing prompt plaza and chapter workflow.

---

## Scope

### Included In MVP

- Paste text samples into a Style Bible panel.
- Store sample metadata: title, source type, genre, scene type, POV, permission to use in generation.
- Split samples into chapters, scenes, and paragraphs using deterministic rules.
- Compute style metrics: sentence length, paragraph length, dialogue ratio, action/psychology/environment ratio, hook positions, pacing markers, AI-cliche hits.
- Generate an editable style profile with technique cards, rhythm rules, and forbidden patterns.
- Select one style profile during chapter generation.
- Inject a compact `style-bible-chapter-overlay` prompt block.
- Score generated chapters against the selected profile at a basic metrics level.

### Explicitly Not Included In MVP

- Model fine-tuning or LoRA training.
- Copyright enforcement beyond local metadata and permission flags.
- Full-text sample retrieval into every generation request.
- Multi-profile blending.
- Automatic ingestion from external novel websites.

---

## File Map

### Domain

- Create `domain/style_bible/__init__.py`
- Create `domain/style_bible/entities.py`
  - `StyleSample`
  - `StyleSampleChunk`
  - `StyleProfile`
  - `StyleTechniqueCard`
  - `StyleRule`
- Create `domain/style_bible/repositories.py`
  - `StyleBibleRepository`

### Application

- Create `application/style_bible/__init__.py`
- Create `application/style_bible/dtos.py`
- Create `application/style_bible/services/text_splitter.py`
- Create `application/style_bible/services/style_metric_analyzer.py`
- Create `application/style_bible/services/style_profile_service.py`
- Create `application/style_bible/services/style_prompt_overlay_service.py`

### Infrastructure

- Create `infrastructure/persistence/database/sqlite_style_bible_repository.py`
- Modify `infrastructure/persistence/database/connection.py`
- Modify `infrastructure/persistence/database/schema.sql`
- Modify `infrastructure/ai/prompts/prompts_defaults.json`

### Interfaces

- Create `interfaces/api/v1/style_bible.py`
- Modify `interfaces/api/dependencies.py`
- Modify `interfaces/main.py`
- Modify `interfaces/api/v1/engine/generation.py`

### Frontend

- Create `frontend/src/api/styleBible.ts`
- Create `frontend/src/components/workbench/StyleBiblePanel.vue`
- Modify `frontend/src/components/workbench/SettingsPanel.vue`
- Modify `frontend/src/components/workbench/WorkArea.vue` if a top-level entry is needed.
- Modify the quick-generation modal or chapter generation request model to pass `style_profile_id`.

### Tests

- Create `tests/unit/domain/style_bible/test_style_bible_entities.py`
- Create `tests/unit/application/services/test_style_text_splitter.py`
- Create `tests/unit/application/services/test_style_metric_analyzer.py`
- Create `tests/unit/application/services/test_style_profile_service.py`
- Create `tests/unit/application/services/test_style_prompt_overlay_service.py`
- Create `tests/unit/infrastructure/database/test_sqlite_style_bible_repository.py`
- Create `tests/unit/interfaces/api/test_style_bible_api.py`
- Update `tests/unit/application/workflows/test_auto_novel_generation_workflow.py`

---

## Data Model

### `style_samples`

Purpose: original user-provided sample metadata and raw content.

Columns:

- `id TEXT PRIMARY KEY`
- `novel_id TEXT DEFAULT ''`
- `profile_id TEXT DEFAULT ''`
- `title TEXT NOT NULL`
- `source_type TEXT DEFAULT 'reference'`
- `genre TEXT DEFAULT ''`
- `scene_type TEXT DEFAULT ''`
- `pov TEXT DEFAULT ''`
- `allowed_for_generation INTEGER DEFAULT 0`
- `content TEXT NOT NULL`
- `content_hash TEXT NOT NULL`
- `char_count INTEGER DEFAULT 0`
- `created_at TEXT DEFAULT ''`
- `updated_at TEXT DEFAULT ''`

Index:

- `idx_style_samples_novel ON style_samples(novel_id, created_at)`
- `idx_style_samples_profile ON style_samples(profile_id)`
- unique soft guard in repository by `content_hash + novel_id`

### `style_sample_chunks`

Purpose: deterministic chunks for analysis and later retrieval.

Columns:

- `id TEXT PRIMARY KEY`
- `sample_id TEXT NOT NULL`
- `chunk_type TEXT NOT NULL`
- `chapter_number INTEGER DEFAULT 0`
- `sequence INTEGER NOT NULL`
- `title TEXT DEFAULT ''`
- `content TEXT NOT NULL`
- `char_count INTEGER DEFAULT 0`
- `metrics_json TEXT DEFAULT '{}'`
- `created_at TEXT DEFAULT ''`

Chunk types:

- `chapter`
- `scene`
- `paragraph`

### `style_profiles`

Purpose: editable style package used during generation.

Columns:

- `id TEXT PRIMARY KEY`
- `novel_id TEXT DEFAULT ''`
- `name TEXT NOT NULL`
- `description TEXT DEFAULT ''`
- `status TEXT DEFAULT 'active'`
- `profile_json TEXT DEFAULT '{}'`
- `metrics_json TEXT DEFAULT '{}'`
- `rules_json TEXT DEFAULT '[]'`
- `forbidden_patterns_json TEXT DEFAULT '[]'`
- `version INTEGER DEFAULT 1`
- `created_at TEXT DEFAULT ''`
- `updated_at TEXT DEFAULT ''`

### `style_technique_cards`

Purpose: actionable craft cards extracted from samples.

Columns:

- `id TEXT PRIMARY KEY`
- `profile_id TEXT NOT NULL`
- `title TEXT NOT NULL`
- `category TEXT DEFAULT ''`
- `scene_type TEXT DEFAULT ''`
- `rule_text TEXT NOT NULL`
- `example_summary TEXT DEFAULT ''`
- `prompt_instruction TEXT NOT NULL`
- `enabled INTEGER DEFAULT 1`
- `weight REAL DEFAULT 1.0`
- `created_at TEXT DEFAULT ''`
- `updated_at TEXT DEFAULT ''`

Categories:

- `pacing`
- `dialogue`
- `emotion`
- `conflict`
- `hook`
- `description`
- `anti_ai`

---

## Prompt Overlay Contract

Generated prompt block should be compact and deterministic:

```text
【写作手法库】
使用风格包：{profile_name}

节奏约束：
- 平均句长：{avg_sentence_length} 字附近，关键动作可短句单独成段
- 段落：每段 {paragraph_min}-{paragraph_max} 字为主，避免连续长段解释
- 场景推进：每 {beat_interval_chars} 字出现一次信息、关系或目标变化

技法卡：
- {card_1.prompt_instruction}
- {card_2.prompt_instruction}
- {card_3.prompt_instruction}

禁用项：
- {forbidden_pattern_1}
- {forbidden_pattern_2}

执行要求：
- 只学习写法和节奏，不复刻样本文字、角色、设定或专有表达。
- 本章必须服从当前小说 Bible、章节大纲和连续性约束。
```

Initial card limit: max 6 enabled cards, sorted by scene type match, weight, and recency.

---

## Task 1: Domain Entities And Repository Contract

**Files:**

- Create `domain/style_bible/__init__.py`
- Create `domain/style_bible/entities.py`
- Create `domain/style_bible/repositories.py`
- Test `tests/unit/domain/style_bible/test_style_bible_entities.py`

- [ ] **Step 1: Write failing entity tests**

Create tests for:

- sample rejects empty content
- sample computes `char_count`
- profile starts as version 1 active
- technique card can be disabled without deleting it

Run:

```bash
uv run --with-requirements requirements.txt --with pytest python -m pytest tests/unit/domain/style_bible/test_style_bible_entities.py -q
```

Expected: fails because modules do not exist.

- [ ] **Step 2: Implement minimal domain entities**

Use dataclasses, matching the project’s lightweight domain style. Do not introduce ORM models.

Required entity fields:

- `StyleSample(id, title, content, source_type, genre, scene_type, pov, allowed_for_generation, novel_id, profile_id, content_hash, char_count, created_at, updated_at)`
- `StyleSampleChunk(id, sample_id, chunk_type, chapter_number, sequence, title, content, char_count, metrics, created_at)`
- `StyleProfile(id, name, description, status, novel_id, profile, metrics, rules, forbidden_patterns, version, created_at, updated_at)`
- `StyleTechniqueCard(id, profile_id, title, category, scene_type, rule_text, example_summary, prompt_instruction, enabled, weight, created_at, updated_at)`

- [ ] **Step 3: Define repository protocol**

Required methods:

- `save_sample(sample, chunks)`
- `list_samples(novel_id=None, profile_id=None)`
- `get_sample(sample_id)`
- `save_profile(profile)`
- `list_profiles(novel_id=None, status=None)`
- `get_profile(profile_id)`
- `save_technique_cards(profile_id, cards)`
- `list_technique_cards(profile_id, enabled=None)`
- `update_technique_card(card)`

- [ ] **Step 4: Run tests**

Expected: entity tests pass.

- [ ] **Step 5: Commit**

```bash
git add domain/style_bible tests/unit/domain/style_bible
git commit -m "feat: add style bible domain model"
```

---

## Task 2: SQLite Persistence And Migrations

**Files:**

- Create `infrastructure/persistence/database/sqlite_style_bible_repository.py`
- Modify `infrastructure/persistence/database/connection.py`
- Modify `infrastructure/persistence/database/schema.sql`
- Test `tests/unit/infrastructure/database/test_sqlite_style_bible_repository.py`

- [ ] **Step 1: Write repository tests**

Cover:

- saving a sample with chunks
- duplicate `content_hash + novel_id` does not create duplicate samples
- saving and listing profiles
- saving, disabling, and listing technique cards
- old empty database creates tables on startup

Run:

```bash
uv run --with-requirements requirements.txt --with pytest python -m pytest tests/unit/infrastructure/database/test_sqlite_style_bible_repository.py -q
```

Expected: fail because repository does not exist.

- [ ] **Step 2: Add schema**

Add `CREATE TABLE IF NOT EXISTS` blocks for:

- `style_samples`
- `style_sample_chunks`
- `style_profiles`
- `style_technique_cards`

Add indexes listed in Data Model.

- [ ] **Step 3: Add startup migration guards**

In `connection.py`, add `_ensure_style_bible_tables(conn)` after existing topic and NovelPro table guards. It must be idempotent for old databases.

- [ ] **Step 4: Implement SQLite repository**

Use explicit JSON serialization for `metrics`, `profile`, `rules`, `forbidden_patterns`.

Repository must call `conn.commit()` after writes.

- [ ] **Step 5: Run repository tests**

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add infrastructure/persistence/database tests/unit/infrastructure/database/test_sqlite_style_bible_repository.py
git commit -m "feat: persist style bible samples and profiles"
```

---

## Task 3: Deterministic Text Splitting And Metrics

**Files:**

- Create `application/style_bible/services/text_splitter.py`
- Create `application/style_bible/services/style_metric_analyzer.py`
- Test `tests/unit/application/services/test_style_text_splitter.py`
- Test `tests/unit/application/services/test_style_metric_analyzer.py`

- [ ] **Step 1: Write splitter tests**

Cover:

- recognizes headings like `第十二章 标题`
- falls back to one chapter when no heading exists
- splits paragraphs by blank lines
- preserves original order and sequence

- [ ] **Step 2: Implement splitter**

Rules:

- Chapter heading regex: `第[一二三四五六七八九十百千万0-9]+章`
- Paragraph split: one or more blank lines first, then long paragraph fallback.
- Scene split MVP: paragraph groups of 1200-2500 Chinese chars, not semantic LLM split.

- [ ] **Step 3: Write metric tests**

Use a short Chinese fixture with narration, dialogue, action, psychology, and environment text.

Expected metrics:

- `avg_sentence_length > 0`
- `dialogue_ratio > 0`
- `paragraph_count`
- `cliche_hit_count`
- ratio keys exist: `action_ratio`, `psychology_ratio`, `environment_ratio`

- [ ] **Step 4: Implement metrics**

Use deterministic heuristics:

- Dialogue: Chinese quote pairs `“...”`, `「...」`, or lines containing `说/问/答/喊/低声`.
- Psychology: `想/觉得/意识到/心里/脑海/明白/害怕/犹豫`.
- Action: verbs such as `走/推/拉/抬/转/握/冲/停/看/拿`.
- Environment: `雨/风/灯/门/窗/街/夜/屋/楼/光/影`.
- AI cliches: reuse `ClicheScanner`.

- [ ] **Step 5: Run tests**

```bash
uv run --with-requirements requirements.txt --with pytest python -m pytest \
  tests/unit/application/services/test_style_text_splitter.py \
  tests/unit/application/services/test_style_metric_analyzer.py \
  -q
```

- [ ] **Step 6: Commit**

```bash
git add application/style_bible tests/unit/application/services/test_style_text_splitter.py tests/unit/application/services/test_style_metric_analyzer.py
git commit -m "feat: analyze style bible text samples"
```

---

## Task 4: Profile Service And Technique Card Extraction

**Files:**

- Create `application/style_bible/dtos.py`
- Create `application/style_bible/services/style_profile_service.py`
- Test `tests/unit/application/services/test_style_profile_service.py`

- [ ] **Step 1: Write service tests**

Cover:

- `import_sample` saves sample, chunks, metrics, and profile when requested.
- `generate_profile_from_samples` produces a profile with deterministic fallback cards when LLM is unavailable.
- LLM JSON fields are normalized when arrays/objects appear where strings are expected.
- disabled sample with `allowed_for_generation=False` can be analyzed but does not get selected by overlay service.

- [ ] **Step 2: Define DTOs**

Create:

- `StyleSampleImportRequestDTO`
- `StyleSampleDTO`
- `StyleChunkDTO`
- `StyleProfileDTO`
- `StyleTechniqueCardDTO`
- `StyleProfileGenerateRequestDTO`
- `StyleProfileMatchReportDTO`

- [ ] **Step 3: Implement service**

The service coordinates:

- hash content
- split text
- compute metrics per chunk and aggregate metrics
- save sample/chunks
- create or update profile
- generate fallback technique cards

Fallback cards must include:

- pacing card from paragraph/sentence metrics
- dialogue card from dialogue ratio
- anti-AI card from cliche hits
- hook card from chapter ending pattern

- [ ] **Step 4: Add optional LLM card extraction**

Use existing LLM provider dependency if available. Prompt must ask for JSON with:

```json
{
  "profile_summary": "string",
  "rhythm_rules": ["string"],
  "forbidden_patterns": ["string"],
  "technique_cards": [
    {
      "title": "string",
      "category": "pacing",
      "scene_type": "dialogue",
      "rule_text": "string",
      "example_summary": "string",
      "prompt_instruction": "string"
    }
  ]
}
```

If parsing fails, keep deterministic fallback.

- [ ] **Step 5: Run tests**

```bash
uv run --with-requirements requirements.txt --with pytest python -m pytest tests/unit/application/services/test_style_profile_service.py -q
```

- [ ] **Step 6: Commit**

```bash
git add application/style_bible tests/unit/application/services/test_style_profile_service.py
git commit -m "feat: generate style bible profiles"
```

---

## Task 5: Prompt Overlay And Chapter Generation Integration

**Files:**

- Create `application/style_bible/services/style_prompt_overlay_service.py`
- Modify `application/workflows/auto_novel_generation_workflow.py`
- Modify `infrastructure/ai/prompts/prompts_defaults.json`
- Modify `interfaces/api/v1/engine/generation.py`
- Test `tests/unit/application/services/test_style_prompt_overlay_service.py`
- Update `tests/unit/application/workflows/test_auto_novel_generation_workflow.py`

- [ ] **Step 1: Write overlay tests**

Cover:

- no selected profile returns empty overlay
- selected profile builds compact block
- disabled cards are excluded
- scene type matching ranks cards first
- overlay includes “do not copy sample text” safety instruction

- [ ] **Step 2: Implement overlay service**

Inputs:

- `novel_id`
- `style_profile_id`
- `scene_type`
- optional `max_cards=6`

Output:

- plain string prompt block
- profile metadata for UI/debug

- [ ] **Step 3: Add prompt plaza node**

Add `style-bible-chapter-overlay` to `prompts_defaults.json` with variables:

- `{style_overlay}` required
- `{scene_type}` optional

This node is not a standalone generator. It is a reusable prompt fragment.

- [ ] **Step 4: Wire chapter generation**

Extend request DTOs to accept:

- `style_profile_id?: string`
- `scene_type?: string`

Inject overlay into `context` or a dedicated runtime variable before prompt build.

- [ ] **Step 5: Run tests**

```bash
uv run --with-requirements requirements.txt --with pytest python -m pytest \
  tests/unit/application/services/test_style_prompt_overlay_service.py \
  tests/unit/application/workflows/test_auto_novel_generation_workflow.py::TestBuildPrompt \
  -q
python3 -m json.tool infrastructure/ai/prompts/prompts_defaults.json >/dev/null
```

- [ ] **Step 6: Commit**

```bash
git add application/style_bible application/workflows/auto_novel_generation_workflow.py infrastructure/ai/prompts/prompts_defaults.json interfaces/api/v1/engine/generation.py tests/unit/application/services/test_style_prompt_overlay_service.py tests/unit/application/workflows/test_auto_novel_generation_workflow.py
git commit -m "feat: inject style bible into chapter generation"
```

---

## Task 6: Style Bible API

**Files:**

- Create `interfaces/api/v1/style_bible.py`
- Modify `interfaces/api/dependencies.py`
- Modify `interfaces/main.py`
- Test `tests/unit/interfaces/api/test_style_bible_api.py`

- [ ] **Step 1: Write API tests**

Cover:

- import sample
- list samples
- create/generate profile
- list profiles
- get profile detail with cards
- update technique card enabled/rule text
- build overlay preview

- [ ] **Step 2: Add dependency constructors**

Add:

- `get_style_bible_repository`
- `get_style_profile_service`
- `get_style_prompt_overlay_service`

Reuse:

- active LLM provider service if already available
- `ClicheScanner`

- [ ] **Step 3: Add routes**

Routes:

```http
POST /api/v1/style-bible/samples
GET  /api/v1/style-bible/samples
GET  /api/v1/style-bible/samples/{sample_id}
POST /api/v1/style-bible/profiles
GET  /api/v1/style-bible/profiles
GET  /api/v1/style-bible/profiles/{profile_id}
PATCH /api/v1/style-bible/profiles/{profile_id}
PATCH /api/v1/style-bible/cards/{card_id}
POST /api/v1/style-bible/overlay/preview
```

- [ ] **Step 4: Register router**

In `interfaces/main.py`, include the router under `/api/v1`.

- [ ] **Step 5: Run tests**

```bash
uv run --with-requirements requirements.txt --with pytest python -m pytest tests/unit/interfaces/api/test_style_bible_api.py -q
```

- [ ] **Step 6: Commit**

```bash
git add interfaces/api/v1/style_bible.py interfaces/api/dependencies.py interfaces/main.py tests/unit/interfaces/api/test_style_bible_api.py
git commit -m "feat: expose style bible api"
```

---

## Task 7: Frontend Panel

**Files:**

- Create `frontend/src/api/styleBible.ts`
- Create `frontend/src/components/workbench/StyleBiblePanel.vue`
- Modify `frontend/src/components/workbench/SettingsPanel.vue`
- Modify chapter generation controls to select `style_profile_id`

- [ ] **Step 1: Add API client**

Types:

- `StyleSample`
- `StyleProfile`
- `StyleTechniqueCard`
- `StyleOverlayPreview`

Methods:

- `importSample`
- `listSamples`
- `listProfiles`
- `getProfile`
- `createProfile`
- `updateCard`
- `previewOverlay`

- [ ] **Step 2: Add panel layout**

Panel tabs:

- `样本`
- `画像`
- `技法卡`
- `注入预览`

Rules:

- No nested cards.
- Dense operational UI, not a landing page.
- Long text areas must have fixed min/max height.

- [ ] **Step 3: Add sample import form**

Fields:

- title required
- source type
- genre
- scene type
- POV
- allowed for generation checkbox
- content textarea

- [ ] **Step 4: Add profile/cards UI**

Allow:

- list profiles
- inspect metrics
- edit card instruction
- enable/disable cards
- preview overlay

- [ ] **Step 5: Wire generation selection**

In the quick generation area, add:

- style profile select
- scene type select/input

Pass values into generation request.

- [ ] **Step 6: Build frontend**

```bash
cd frontend
npm run build
```

Expected: build passes.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/styleBible.ts frontend/src/components/workbench/StyleBiblePanel.vue frontend/src/components/workbench/SettingsPanel.vue frontend/src
git commit -m "feat: add style bible workbench panel"
```

---

## Task 8: Match Report And Feedback Loop

**Files:**

- Extend `application/style_bible/services/style_metric_analyzer.py`
- Extend `application/style_bible/services/style_profile_service.py`
- Extend `interfaces/api/v1/style_bible.py`
- Extend `frontend/src/components/workbench/StyleBiblePanel.vue`
- Test `tests/unit/application/services/test_style_profile_service.py`

- [ ] **Step 1: Write match report tests**

Given generated text and a profile, assert report includes:

- overall score
- sentence length status
- paragraph rhythm status
- dialogue ratio status
- cliche hit status
- actionable suggestions

- [ ] **Step 2: Implement report**

Scoring MVP:

- sentence length within 20% -> full score for that dimension
- paragraph average within 25% -> full score
- dialogue ratio within 0.1 absolute -> full score
- cliche hits below threshold -> full score

- [ ] **Step 3: Add API**

```http
POST /api/v1/style-bible/profiles/{profile_id}/match
```

Body:

```json
{
  "content": "generated chapter text",
  "scene_type": "dialogue"
}
```

- [ ] **Step 4: Add UI**

Add match report action in `注入预览` tab.

- [ ] **Step 5: Run tests and build**

```bash
uv run --with-requirements requirements.txt --with pytest python -m pytest tests/unit/application/services/test_style_profile_service.py tests/unit/interfaces/api/test_style_bible_api.py -q
cd frontend && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add application/style_bible interfaces/api/v1/style_bible.py frontend/src/components/workbench/StyleBiblePanel.vue tests/unit/application/services/test_style_profile_service.py tests/unit/interfaces/api/test_style_bible_api.py
git commit -m "feat: score chapters against style bible profiles"
```

---

## Task 9: Documentation And Verification

**Files:**

- Modify `docs/NOVELPRO_README.md`
- Add `docs/style-bible-guide.md`
- Update this plan with final verification notes if behavior differs.

- [ ] **Step 1: Add user guide**

Guide must cover:

- What sample text is used for.
- Recommended sample size: 3-10 chapters for stable rhythm, 1 chapter for quick tests.
- Why generated prompt overlay does not copy original text.
- How to create a profile.
- How to edit cards.
- How to select profile in chapter generation.
- How to interpret match report.

- [ ] **Step 2: Add developer notes**

Include:

- schema tables
- API list
- prompt overlay contract
- test commands

- [ ] **Step 3: Run full focused verification**

```bash
python3 -m compileall -q domain/style_bible application/style_bible infrastructure/persistence/database/sqlite_style_bible_repository.py interfaces/api/v1/style_bible.py
uv run --with-requirements requirements.txt --with pytest python -m pytest \
  tests/unit/domain/style_bible \
  tests/unit/application/services/test_style_text_splitter.py \
  tests/unit/application/services/test_style_metric_analyzer.py \
  tests/unit/application/services/test_style_profile_service.py \
  tests/unit/application/services/test_style_prompt_overlay_service.py \
  tests/unit/infrastructure/database/test_sqlite_style_bible_repository.py \
  tests/unit/interfaces/api/test_style_bible_api.py \
  tests/unit/application/workflows/test_auto_novel_generation_workflow.py::TestBuildPrompt \
  -q
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add docs/NOVELPRO_README.md docs/style-bible-guide.md docs/superpowers/plans/2026-04-30-style-bible-implementation-plan.md
git commit -m "docs: document style bible workflow"
```

---

## Rollout Order

1. Local backend tests only.
2. Local frontend build.
3. Local API smoke test with one pasted chapter.
4. Deploy to Baota.
5. Run online smoke test:
   - create sample
   - generate profile
   - preview overlay
   - generate chapter with profile
   - run match report
6. Update memory with known issues and verification status.

---

## Risk Controls

- Do not put original sample text into every generation context.
- Prompt overlay must include “do not copy sample text, characters, settings, or proper nouns.”
- Keep raw sample storage local SQLite only.
- Do not expose raw samples through public unauthenticated endpoints beyond existing app access model.
- Keep LLM extraction optional; deterministic fallback must work without API key.
- Keep generation request backward compatible when `style_profile_id` is empty.

---

## Self-Review Notes

- Spec coverage: sample ingestion, analysis, profile/card storage, prompt injection, frontend, and match report are each mapped to implementation tasks.
- Placeholder scan: no intentionally deferred MVP requirements remain; non-MVP items are explicitly excluded.
- Type consistency: file names and service names use `style_bible` across domain, application, API, and frontend API client.
