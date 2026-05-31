# Chapter BeatCard Pipeline - Design Spec

**Date:** 2026-05-31
**Status:** Approved (brainstorming complete, awaiting implementation plan)
**Scope:** Minimal architectural change to fix three long-form generation pains: too many characters, plot fragmentation, chapter-to-chapter discontinuity.

## 1. Problem Statement

Current symptoms during autopilot generation:

- **Too many characters**: LLM introduces new characters chapter-by-chapter; no per-chapter cast budget.
- **Plot fragmentation**: governance only post-warns about `storyline_inflation`; no pre-chapter forcing of which storyline must advance.
- **Chapter discontinuity**: MemoryEngine writes back state, but the next chapter has no explicit, structured hooks carrying unresolved threads forward.

Existing assets we reuse:
- `ContextBudgetAllocator` (POV firewall by `reveal_chapter`)
- `GovernanceService` (canonical storylines, reveal budgets)
- `MemoryEngine` (fact_lock injection, emotional_residue)
- `post_process_generated_chapter` workflow

## 2. Solution Overview

Three additive components, no DDD layer restructuring:

1. **BeatCardComposer** (application/blueprint) - synthesizes a per-chapter `ChapterBeatCard` before generation starts.
2. **BeatCardEnforcer** (application/engine/services) - inside ContextBuilder, hard-filters character roster and injects highest-priority directive into the prompt.
3. **CarryOverExtractor** (application/workflows/extractors) - end of post-chapter pipeline, distills 3-5 forward-pointing hooks and seeds the next chapter's BeatCard row.

Soft-failure throughout: if any stage produces no data, downstream consumers pass through unchanged.

## 3. Data Model

### Value Object
File: `domain/engine/value_objects/chapter_beat_card.py`

```python
@dataclass(frozen=True)
class ChapterBeatCard:
    novel_id: str
    chapter_number: int
    pov_whitelist: list[str]            # <=3 character ids
    cast_budget: list[str]              # <=5 character ids (POV included)
    storyline_must_advance: list[str]   # <=2 storyline ids
    beat_goals: list[str]               # from act-beats
    carry_over_from_prev: list[str]     # 3-5 hooks from prior chapter
    forbidden_elements: list[str]       # from reveal budget
    notes: str
    generated_at: datetime
    source: str                         # auto | manual | auto+edited | carry_over_seed | auto-fallback
```

### SQLite Table
Append to `infrastructure/persistence/database/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS chapter_beat_cards (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    pov_whitelist TEXT NOT NULL,
    cast_budget TEXT NOT NULL,
    storyline_must_advance TEXT NOT NULL,
    beat_goals TEXT NOT NULL,
    carry_over_from_prev TEXT NOT NULL,
    forbidden_elements TEXT NOT NULL DEFAULT '[]',
    notes TEXT DEFAULT '',
    source TEXT NOT NULL DEFAULT 'auto',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE(novel_id, chapter_number, version)
);
CREATE INDEX IF NOT EXISTS idx_beat_cards_active
    ON chapter_beat_cards(novel_id, chapter_number, is_active);
```

Migration file: `scripts/migrations/20260531_add_chapter_beat_cards.sql`

### Repository
File: `infrastructure/persistence/repositories/beat_card_repository.py`

Operations (all writes via Write Dispatch):
- `save(card)` - inserts new row, marks prior versions `is_active=0`.
- `get_active(novel_id, chapter_number)` - single active card or `None`.
- `upsert_carry_over_seed(novel_id, next_chapter, hooks)` - creates a `source=carry_over_seed` empty-shell row if no card exists, else updates `carry_over_from_prev` on the seed row only.


## 4. Component: BeatCardComposer

File: `application/blueprint/composers/beat_card_composer.py`

```python
class BeatCardComposer:
    def compose(self, novel_id: str, chapter_number: int) -> ChapterBeatCard
```

Invocation: `engine/runtime/writing_delegate.py:run_writing`, after `_find_next_unwritten_chapter_async` returns, before ContextBuilder is invoked.

Idempotency:
- If `get_active(...)` returns a card with `source in {auto, manual, auto+edited}`, return it as-is (respects manual edits).
- If the active card has `source=carry_over_seed`, treat it as a partial card: preserve `carry_over_from_prev`, fill remaining fields, save with `source=auto` and `is_active=1`, old seed row becomes inactive.

Field synthesis rules:

| Field | Source | Rule |
|---|---|---|
| `beat_goals` | act-beats (governance/blueprint) | Take beats covering this chapter, truncate to <=5 |
| `storyline_must_advance` | governance canonical storylines | "Most overdue" first (by last-advance chapter), <=2 |
| `pov_whitelist` | prior-chapter evolution + main-storyline-bound protagonists | Carry unresolved POV hooks; fill to <=3 |
| `cast_budget` | POV union storyline-related chars union chars mentioned in carry_over | Dedupe, importance sort, <=5 |
| `carry_over_from_prev` | seed-row value if present, else empty | Direct copy |
| `forbidden_elements` | governance reveal budget + characters with `reveal_chapter > current` | Named entities to block |
| `notes` | auto-generated synthesis trace | Debug-only |

Soft-fallback: any data-source failure -> empty card with `source=auto-fallback`. Enforcer treats empty card as pass-through.

## 5. Component: BeatCardEnforcer

File: `application/engine/services/beat_card_enforcer.py`

Injection point: `application/engine/services/context_builder.py`, immediately after `self.budget_allocator.allocate(...)` returns `BudgetAllocation`, before the allocation is consumed by the prompt builder.

```python
class BeatCardEnforcer:
    def enforce(
        self,
        allocation: BudgetAllocation,
        card: ChapterBeatCard | None,
    ) -> BudgetAllocation
```

Two-step hard-clamp:

1. **Character roster filter**: drop characters not in `cast_budget` from `allocation.character_section`. Replace dropped entries with placeholder lines like `<name> - not present this chapter` (anti-hallucination guard).
2. **Directive injection**: prepend a `chapter_beat_card` section at priority 0 (highest), rendered from `infrastructure/ai/prompt_packages/nodes/beat_card_directive.yaml`.

Directive template (YAML-overridable):

```
[Chapter Hard Constraints - BeatCard]
POV (only): {pov_names}
Allowed cast: {cast_names} (others MUST NOT appear)
Storylines to advance: {storyline_titles_with_progress}
Beat goals: {beat_goals}
Carry-over hooks (must address): {carry_over_from_prev}
Forbidden (premature reveals): {forbidden_elements}
```

Soft-failure: `card is None` or `card.cast_budget == []` -> return allocation unchanged.

`BudgetAllocation` minimal extensions (avoid refactor):
- `with_characters(filtered_list)` - immutable replace
- `with_prepended_section(name, content, priority)` - immutable prepend
- `enforcement_log: dict` - records dropped chars + injected sections (for tests)

## 6. Component: CarryOverExtractor

File: `application/workflows/extractors/carry_over_extractor.py`

Invocation: `application/workflows/auto_novel_generation_workflow.py:post_process_generated_chapter` (line 521), appended as **step 7**, after MemoryEngine write-back.

```python
class CarryOverExtractor:
    def extract_and_persist(
        self,
        novel_id: str,
        chapter_number: int,
        chapter_content: str,
        evolution_events: list[EvolutionEvent],
        emotional_residue: dict | None,
    ) -> list[str]   # 3-5 hooks
```

Distillation rules (deterministic first, LLM fallback):

| Signal | Rule | Sample hook |
|---|---|---|
| `evolution_events.type=dialogue_open` | direct extract | "Li Ming's question to Wang Fang remains unanswered" |
| `evolution_events.type=item_in_transit` | item + holder | "The jade pendant is still with Zhao Wu, undelivered" |
| `emotional_residue` intensity >= threshold | char + emotion | "Zhou Lin's anger at her father is unresolved" |
| `evolution_events.type=fact_revealed_to_subset` | POV info gap | "Sun Qi knows the truth but has not told the team" |
| Fallback | if <3 hooks, prompt LLM on chapter tail | (via existing LLM client) |

Priority sort: `dialogue_open > item_in_transit > emotional_residue > fact_subset`. Take top 5.

Persistence: call `BeatCardRepository.upsert_carry_over_seed(novel_id, chapter_number + 1, hooks)`.

Soft-failure: any exception is logged and swallowed; main pipeline unaffected.

## 7. Integration Flow

```
[autopilot writing_delegate.run_writing]
        |
        v  determine next unwritten chapter N
[BeatCardComposer.compose(novel_id, N)]
        |       reads: act-beats / governance / prior-chapter evolution
        |       reads: existing seed row (if any) and merges carry_over_from_prev
        v
[BeatCardRepository.save(card)]   -- via Write Dispatch
        |
        v
[ContextBuilder.build_context]
        |  budget_allocator.allocate(...) -> BudgetAllocation
        v
[BeatCardEnforcer.enforce(allocation, card)]
        |  hard-filter character roster; prepend directive at priority 0
        v
[GenerationPromptBuilder] -> LLM call -> chapter content
        |
        v
[post_process_generated_chapter]   step 1..6 unchanged
        v
[step 7: CarryOverExtractor.extract_and_persist]
        |  distill 3-5 hooks
        v
[BeatCardRepository.upsert_carry_over_seed(novel_id, N+1, hooks)]
        |  creates source=carry_over_seed shell for chapter N+1
        v
   (next loop iteration: Composer for N+1 merges seed -> auto)
```

## 8. Configuration

`.env.example` additions:

```
BEATCARD_ENABLED=true
BEATCARD_ENFORCEMENT_MODE=hard       # hard | soft | off
BEATCARD_POV_LIMIT=3
BEATCARD_CAST_LIMIT=5
BEATCARD_STORYLINE_LIMIT=2
```

Rollback: `BEATCARD_ENABLED=false` short-circuits Composer/Enforcer/Extractor; legacy path unchanged.

## 9. File Manifest

**New:**
- `domain/engine/value_objects/chapter_beat_card.py`
- `application/blueprint/composers/__init__.py`
- `application/blueprint/composers/beat_card_composer.py`
- `application/engine/services/beat_card_enforcer.py`
- `application/workflows/extractors/__init__.py`
- `application/workflows/extractors/carry_over_extractor.py`
- `infrastructure/persistence/repositories/beat_card_repository.py`
- `infrastructure/ai/prompt_packages/nodes/beat_card_directive.yaml`
- `scripts/migrations/20260531_add_chapter_beat_cards.sql`

**Modified:**
- `infrastructure/persistence/database/schema.sql` (+CREATE TABLE)
- `application/engine/services/context_builder.py` (+Enforcer wiring; +`BudgetAllocation.with_characters/with_prepended_section/enforcement_log` if not already present)
- `application/workflows/auto_novel_generation_workflow.py` (+step 7)
- `engine/runtime/writing_delegate.py` (+Composer wiring)
- `.env.example` (+config keys)

**Tests:**
- `tests/unit/domain/test_chapter_beat_card.py`
- `tests/unit/blueprint/test_beat_card_composer.py`
- `tests/unit/engine/test_beat_card_enforcer.py`
- `tests/unit/workflows/test_carry_over_extractor.py`
- `tests/integration/test_beat_card_pipeline.py`
- `tests/integration/test_beat_card_persistence.py`

## 10. Test Strategy

| Test | Type | Key cases |
|---|---|---|
| `test_chapter_beat_card.py` | unit | immutability; POV subset of cast; field length caps |
| `test_beat_card_composer.py` | unit | mocked data sources; empty-data fallback; idempotency; seed-row merge upgrade |
| `test_beat_card_enforcer.py` | unit | character hard-filter correctness; empty-card pass-through; directive prepended at priority 0 |
| `test_carry_over_extractor.py` | unit | each signal source; priority sort; forward write to N+1; LLM fallback path |
| `test_beat_card_pipeline.py` | integration | chapter N done -> carry_over persisted -> chapter N+1 Composer merges -> Enforcer injects -> end-to-end |
| `test_beat_card_persistence.py` | integration | Write Dispatch path; multi-version is_active uniqueness; seed -> auto promotion |

## 11. Out of Scope

- Frontend BeatCard editor (deferred; manual override only via DB / API)
- Cross-chapter rollback semantics (covered by existing snapshot manager)
- Per-novel preset (planet-scale cast vs intimate-cast) - first ship hardcoded defaults
- Documentation page under `docs/` for end-users - separate task

## 12. Risk and Mitigation

| Risk | Mitigation |
|---|---|
| Composer mis-bounds storylines, blocking valid narrative | `BEATCARD_ENFORCEMENT_MODE=soft` flag downgrades hard-filter to advisory directive |
| Cast budget too tight causes LLM to violate constraint repeatedly | governance can detect ratio of violations and auto-relax via subsequent BeatCard versions (future) |
| Carry-over hooks accumulate stale entries | hooks not addressed within 2 chapters are dropped by Composer (rule: carry_over has TTL=2) |
| Write Dispatch contention | reuses existing single-writer path; no new contention surface |

## 13. Approval

Brainstorming approved 2026-05-31. Ready for implementation plan via writing-plans skill.
