# Topic Idea Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the topic idea pool from cards with scattered fields into a lightweight structured incubation report.

**Architecture:** Keep topic data independent from formal novel, Bible, chapter, graph, and workflow data. Add two weak-structured JSON fields on `TopicIdea`: `development_notes` for立项案内容 and `evaluation` for评估维度. Deepen/evaluate can fill these fields, while existing adopt flow still only creates a Novel through the current setup wizard.

**Tech Stack:** Python 3, FastAPI, SQLite, pytest, Vue 3, TypeScript, Naive UI, Vite.

---

## File Structure

- Modify `domain/topic/entities.py`: normalize `development_notes` and `evaluation` dictionaries.
- Modify `application/topic/dtos.py`: expose the two dictionaries in `TopicIdeaDTO`.
- Modify `application/topic/services/topic_idea_service.py`: ask LLM/fallback to populate structured report data.
- Modify `infrastructure/persistence/database/schema.sql`: add `development_notes_json` and `evaluation_json` columns.
- Modify `infrastructure/persistence/database/sqlite_topic_idea_repository.py`: persist and load the new JSON fields.
- Modify `interfaces/api/v1/topic/topic_ideas.py`: allow manual PATCH of the two dictionaries.
- Modify `frontend/src/api/topic.ts`: add the new fields to `TopicIdea`.
- Modify `frontend/src/components/topic/TopicIdeaPanel.vue`: render立项案 and评估维度 in cards.
- Update topic tests in `tests/unit/domain/topic/`, `tests/unit/infrastructure/database/`, `tests/unit/application/services/`, and `tests/unit/interfaces/api/`.

## Task 1: Backend Structured Report Fields

**Files:**
- Modify `domain/topic/entities.py`
- Modify `application/topic/dtos.py`
- Modify `application/topic/services/topic_idea_service.py`
- Modify `infrastructure/persistence/database/schema.sql`
- Modify `infrastructure/persistence/database/sqlite_topic_idea_repository.py`
- Modify `interfaces/api/v1/topic/topic_ideas.py`
- Test `tests/unit/domain/topic/test_topic_idea.py`
- Test `tests/unit/infrastructure/database/test_sqlite_topic_idea_repository.py`
- Test `tests/unit/application/services/test_topic_idea_service.py`
- Test `tests/unit/interfaces/api/test_topic_ideas.py`

- [ ] **Step 1: Add tests for report fields**

Add assertions that `TopicIdea` keeps dictionary fields, SQLite persists them, `deepen()` fills `development_notes`, `evaluate()` fills `evaluation`, and PATCH accepts both fields.

- [ ] **Step 2: Implement minimal backend support**

Add `development_notes: dict[str, Any]` and `evaluation: dict[str, Any]` to the domain entity, DTO, repository, schema, service editable/enrichment fields, and PATCH request.

- [ ] **Step 3: Preserve existing behavior**

Ensure existing generate/list/update/adopt/compare contracts still pass unchanged; do not make topic ideas depend on Novel/Bible/chapters before adoption.

- [ ] **Step 4: Verify backend**

Run:

```bash
uv run --with-requirements requirements.txt --with pytest python -m pytest tests/unit/domain/topic/test_topic_idea.py tests/unit/infrastructure/database/test_sqlite_topic_idea_repository.py tests/unit/application/services/test_topic_idea_service.py tests/unit/interfaces/api/test_topic_ideas.py -q
python3 -m compileall -q domain/topic application/topic infrastructure/persistence/database/sqlite_topic_idea_repository.py interfaces/api/v1/topic interfaces/main.py interfaces/api/dependencies.py
```

## Task 2: Frontend Report Rendering

**Files:**
- Modify `frontend/src/api/topic.ts`
- Modify `frontend/src/components/topic/TopicIdeaPanel.vue`

- [ ] **Step 1: Add typed report fields**

Add `development_notes: Record<string, unknown>` and `evaluation: Record<string, unknown>` to `TopicIdea`.

- [ ] **Step 2: Render structured report sections**

In each topic card, show a compact “立项案” block when `development_notes` has content and a compact “评估维度” block when `evaluation` has content. Render arrays as vertical list rows and scalar values as readable key-value rows.

- [ ] **Step 3: Keep layout stable**

Reuse existing card styling, keep border radius at 8px, avoid nested card-in-card UI, and keep mobile layout readable.

- [ ] **Step 4: Verify frontend**

Run:

```bash
cd frontend && npm run build
```

## Task 3: Final Review And Cleanup

**Files:**
- Update `agent_memory/progress.md`

- [ ] **Step 1: Run final targeted verification**

Run backend topic tests, compileall, and frontend build.

- [ ] **Step 2: Clean generated files**

Remove `uv.lock` if `uv run` generated it, and remove topic-related `__pycache__` directories.

- [ ] **Step 3: Update progress memory**

Record that the topic idea pool now supports structured incubation reports, with the latest verification status.
