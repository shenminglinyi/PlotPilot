# Chapter BeatCard Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-chapter BeatCard pipeline (Composer + Enforcer + CarryOverExtractor) that hard-bounds character roster, forces storyline progression, and persists cross-chapter continuity hooks.

**Architecture:** Three additive components in existing DDD packages, gated by `BEATCARD_ENABLED`. BeatCard is a frozen value object persisted in a new `chapter_beat_cards` SQLite table via Write Dispatch. Composer runs in autopilot before ContextBuilder; Enforcer runs inside ContextBuilder right after `budget_allocator.allocate()`; CarryOverExtractor runs as step 7 of `post_process_generated_chapter` and forward-writes a seed row for chapter N+1.

**Tech Stack:** Python 3.x, FastAPI, SQLite (via Write Dispatch single-writer), pytest, dataclasses, existing `infrastructure/ai/prompt_packages` YAML.

**Spec:** `docs/superpowers/specs/2026-05-31-chapter-beat-card-design.md`

---

## File Structure

| File | Role |
|---|---|
| `domain/engine/value_objects/chapter_beat_card.py` | Frozen dataclass `ChapterBeatCard`, field validation |
| `infrastructure/persistence/repositories/beat_card_repository.py` | `save/get_active/upsert_carry_over_seed`, JSON serialization |
| `infrastructure/persistence/database/schema.sql` | +CREATE TABLE `chapter_beat_cards` |
| `scripts/migrations/20260531_add_chapter_beat_cards.sql` | Standalone migration |
| `application/blueprint/composers/beat_card_composer.py` | Synthesizes BeatCard from act-beats / governance / prior-chapter evolution |
| `application/engine/services/beat_card_enforcer.py` | Filters character slots, prepends T0 directive |
| `application/engine/services/context_budget_models.py` | +helpers on `BudgetAllocation` |
| `application/engine/services/context_builder.py` | Wires Enforcer between `allocate()` and `get_final_context()` |
| `application/workflows/extractors/carry_over_extractor.py` | Distills 3-5 hooks, calls `upsert_carry_over_seed` |
| `application/workflows/auto_novel_generation_workflow.py` | +step 7 in `post_process_generated_chapter` |
| `engine/runtime/writing_delegate.py` | Calls Composer before ContextBuilder in `run_writing` |
| `infrastructure/ai/prompt_packages/nodes/beat_card_directive.yaml` | YAML-overridable directive template |
| `.env.example` | +5 BEATCARD_* keys |

---


## Task 1: ChapterBeatCard value object

**Files:**
- Create: `domain/engine/value_objects/chapter_beat_card.py`
- Test: `tests/unit/domain/test_chapter_beat_card.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/domain/test_chapter_beat_card.py
from datetime import datetime
import pytest
from domain.engine.value_objects.chapter_beat_card import ChapterBeatCard


def _card(**overrides):
    defaults = dict(
        novel_id="n1",
        chapter_number=5,
        pov_whitelist=["c1"],
        cast_budget=["c1", "c2"],
        storyline_must_advance=["s1"],
        beat_goals=["b1"],
        carry_over_from_prev=[],
        forbidden_elements=[],
        notes="",
        generated_at=datetime(2026, 5, 31),
        source="auto",
    )
    defaults.update(overrides)
    return ChapterBeatCard(**defaults)


def test_card_is_frozen():
    c = _card()
    with pytest.raises(Exception):
        c.notes = "mutated"


def test_pov_must_be_subset_of_cast():
    with pytest.raises(ValueError, match="pov_whitelist must be subset of cast_budget"):
        _card(pov_whitelist=["x"], cast_budget=["c1"])


def test_pov_limit_enforced():
    with pytest.raises(ValueError, match="pov_whitelist exceeds limit"):
        _card(pov_whitelist=["a", "b", "c", "d"], cast_budget=["a", "b", "c", "d"])


def test_cast_limit_enforced():
    with pytest.raises(ValueError, match="cast_budget exceeds limit"):
        _card(cast_budget=["a", "b", "c", "d", "e", "f"], pov_whitelist=["a"])


def test_storyline_limit_enforced():
    with pytest.raises(ValueError, match="storyline_must_advance exceeds limit"):
        _card(storyline_must_advance=["s1", "s2", "s3"])


def test_source_must_be_known():
    with pytest.raises(ValueError, match="unknown source"):
        _card(source="garbage")


def test_empty_card_factory():
    c = ChapterBeatCard.empty("n1", 5, source="auto-fallback")
    assert c.cast_budget == ()
    assert c.pov_whitelist == ()
    assert c.source == "auto-fallback"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/domain/test_chapter_beat_card.py -v`
Expected: ImportError / ModuleNotFoundError

- [ ] **Step 3: Implement value object**

```python
# domain/engine/value_objects/chapter_beat_card.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Tuple


_VALID_SOURCES = frozenset({
    "auto", "manual", "auto+edited", "carry_over_seed", "auto-fallback",
})


@dataclass(frozen=True)
class BeatCardLimits:
    pov: int = 3
    cast: int = 5
    storyline: int = 2


@dataclass(frozen=True)
class ChapterBeatCard:
    novel_id: str
    chapter_number: int
    pov_whitelist: Tuple[str, ...]
    cast_budget: Tuple[str, ...]
    storyline_must_advance: Tuple[str, ...]
    beat_goals: Tuple[str, ...]
    carry_over_from_prev: Tuple[str, ...]
    forbidden_elements: Tuple[str, ...]
    notes: str
    generated_at: datetime
    source: str

    LIMITS: ClassVar[BeatCardLimits] = BeatCardLimits()

    def __post_init__(self):
        for fname in ("pov_whitelist", "cast_budget", "storyline_must_advance",
                      "beat_goals", "carry_over_from_prev", "forbidden_elements"):
            object.__setattr__(self, fname, tuple(getattr(self, fname)))

        if self.source not in _VALID_SOURCES:
            raise ValueError(f"unknown source: {self.source}")
        if len(self.pov_whitelist) > self.LIMITS.pov:
            raise ValueError(f"pov_whitelist exceeds limit ({self.LIMITS.pov})")
        if len(self.cast_budget) > self.LIMITS.cast:
            raise ValueError(f"cast_budget exceeds limit ({self.LIMITS.cast})")
        if len(self.storyline_must_advance) > self.LIMITS.storyline:
            raise ValueError(f"storyline_must_advance exceeds limit ({self.LIMITS.storyline})")
        if not set(self.pov_whitelist).issubset(set(self.cast_budget)):
            raise ValueError("pov_whitelist must be subset of cast_budget")

    @classmethod
    def empty(cls, novel_id: str, chapter_number: int,
              source: str = "auto-fallback") -> "ChapterBeatCard":
        return cls(
            novel_id=novel_id, chapter_number=chapter_number,
            pov_whitelist=(), cast_budget=(), storyline_must_advance=(),
            beat_goals=(), carry_over_from_prev=(), forbidden_elements=(),
            notes="", generated_at=datetime.utcnow(), source=source,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/domain/test_chapter_beat_card.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add -f domain/engine/value_objects/chapter_beat_card.py tests/unit/domain/test_chapter_beat_card.py
git commit -m "feat(domain): add ChapterBeatCard value object with field constraints"
```


## Task 2: SQLite schema and migration

**Files:**
- Modify: `infrastructure/persistence/database/schema.sql` (append at end)
- Create: `scripts/migrations/20260531_add_chapter_beat_cards.sql`

- [ ] **Step 1: Inspect existing migrations to mirror style**

Run: `ls scripts/migrations/ | tail -5`
Read one recent migration file to confirm comment/format conventions.

- [ ] **Step 2: Append table to schema.sql**

Append at end of `infrastructure/persistence/database/schema.sql`:

```sql

-- =====================================================
-- Chapter BeatCards: per-chapter generation contracts
-- =====================================================
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

- [ ] **Step 3: Create standalone migration file**

```sql
-- scripts/migrations/20260531_add_chapter_beat_cards.sql
-- Migration: Add chapter_beat_cards table for per-chapter generation contracts.

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

- [ ] **Step 4: Verify schema applies on fresh DB**

```bash
python -c "
import sqlite3, os
os.makedirs('/tmp/bc_test', exist_ok=True)
db = '/tmp/bc_test/test.db'
if os.path.exists(db): os.remove(db)
conn = sqlite3.connect(db)
conn.executescript(open('infrastructure/persistence/database/schema.sql').read())
cur = conn.execute('SELECT name FROM sqlite_master WHERE type=\"table\" AND name=\"chapter_beat_cards\"')
print('found' if cur.fetchone() else 'missing')
conn.close()
"
```

Expected: `found`

- [ ] **Step 5: Commit**

```bash
git add infrastructure/persistence/database/schema.sql scripts/migrations/20260531_add_chapter_beat_cards.sql
git commit -m "feat(persistence): add chapter_beat_cards table"
```


## Task 3: BeatCard repository

**Files:**
- Create: `infrastructure/persistence/repositories/__init__.py` (if missing)
- Create: `infrastructure/persistence/repositories/beat_card_repository.py`
- Test: `tests/integration/test_beat_card_persistence.py`

- [ ] **Step 1: Ensure package init exists**

```bash
test -f infrastructure/persistence/repositories/__init__.py || touch infrastructure/persistence/repositories/__init__.py
```

- [ ] **Step 2: Write failing integration tests**

```python
# tests/integration/test_beat_card_persistence.py
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime

import pytest

from domain.engine.value_objects.chapter_beat_card import ChapterBeatCard


@pytest.fixture
def fresh_db(monkeypatch):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "bc.db")
    monkeypatch.setenv("PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES", "1")
    conn = sqlite3.connect(db_path)
    conn.executescript(open("infrastructure/persistence/database/schema.sql").read())
    # seed a novel row to satisfy FK
    conn.execute("INSERT INTO novels (id, title) VALUES (?, ?)", ("n1", "t"))
    conn.commit()
    conn.close()
    return db_path


def _direct_repo(db_path):
    from infrastructure.persistence.repositories.beat_card_repository import (
        BeatCardRepository,
    )
    return BeatCardRepository(db_path=db_path, direct=True)


def test_save_and_get_active(fresh_db):
    repo = _direct_repo(fresh_db)
    card = ChapterBeatCard(
        novel_id="n1", chapter_number=1,
        pov_whitelist=["c1"], cast_budget=["c1"],
        storyline_must_advance=["s1"], beat_goals=["b1"],
        carry_over_from_prev=(), forbidden_elements=(),
        notes="", generated_at=datetime(2026, 5, 31), source="auto",
    )
    repo.save(card)
    loaded = repo.get_active("n1", 1)
    assert loaded is not None
    assert loaded.cast_budget == ("c1",)
    assert loaded.source == "auto"


def test_save_creates_new_version_and_deactivates_old(fresh_db):
    repo = _direct_repo(fresh_db)
    base = dict(
        novel_id="n1", chapter_number=2,
        pov_whitelist=["c1"], cast_budget=["c1"],
        storyline_must_advance=(), beat_goals=(),
        carry_over_from_prev=(), forbidden_elements=(),
        notes="", generated_at=datetime(2026, 5, 31),
    )
    repo.save(ChapterBeatCard(**base, source="auto"))
    repo.save(ChapterBeatCard(**base, source="manual"))
    loaded = repo.get_active("n1", 2)
    assert loaded.source == "manual"
    # only one active row
    with sqlite3.connect(fresh_db) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM chapter_beat_cards WHERE novel_id=? AND chapter_number=? AND is_active=1",
            ("n1", 2),
        ).fetchone()[0]
        assert n == 1


def test_upsert_carry_over_seed_creates_shell(fresh_db):
    repo = _direct_repo(fresh_db)
    repo.upsert_carry_over_seed("n1", next_chapter=3, hooks=["hook A", "hook B"])
    loaded = repo.get_active("n1", 3)
    assert loaded is not None
    assert loaded.source == "carry_over_seed"
    assert loaded.carry_over_from_prev == ("hook A", "hook B")
    assert loaded.cast_budget == ()


def test_upsert_carry_over_seed_overwrites_existing_seed(fresh_db):
    repo = _direct_repo(fresh_db)
    repo.upsert_carry_over_seed("n1", 4, ["old"])
    repo.upsert_carry_over_seed("n1", 4, ["new1", "new2"])
    loaded = repo.get_active("n1", 4)
    assert loaded.carry_over_from_prev == ("new1", "new2")


def test_get_active_returns_none_when_absent(fresh_db):
    repo = _direct_repo(fresh_db)
    assert repo.get_active("n1", 99) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/integration/test_beat_card_persistence.py -v`
Expected: ImportError


- [ ] **Step 4: Implement repository**

```python
# infrastructure/persistence/repositories/beat_card_repository.py
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional

from domain.engine.value_objects.chapter_beat_card import ChapterBeatCard


class BeatCardRepository:
    """Persistence for ChapterBeatCard.

    `direct=True` writes via a private sqlite3 connection (tests, migrations).
    `direct=False` (default in production) routes writes through Write Dispatch.
    Reads always use a private read-only connection.
    """

    def __init__(self, db_path: Optional[str] = None, direct: bool = False):
        self._db_path = db_path or os.environ.get(
            "PLOTPILOT_DB_PATH", "data/plotpilot.db"
        )
        self._direct = direct

    # ---- writes ----
    def save(self, card: ChapterBeatCard) -> None:
        next_version = self._next_version(card.novel_id, card.chapter_number)
        new_id = str(uuid.uuid4())
        deactivate_sql = (
            "UPDATE chapter_beat_cards SET is_active=0 "
            "WHERE novel_id=? AND chapter_number=? AND is_active=1"
        )
        insert_sql = (
            "INSERT INTO chapter_beat_cards "
            "(id, novel_id, chapter_number, version, pov_whitelist, cast_budget, "
            "storyline_must_advance, beat_goals, carry_over_from_prev, "
            "forbidden_elements, notes, source, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)"
        )
        params = (
            new_id, card.novel_id, card.chapter_number, next_version,
            json.dumps(list(card.pov_whitelist), ensure_ascii=False),
            json.dumps(list(card.cast_budget), ensure_ascii=False),
            json.dumps(list(card.storyline_must_advance), ensure_ascii=False),
            json.dumps(list(card.beat_goals), ensure_ascii=False),
            json.dumps(list(card.carry_over_from_prev), ensure_ascii=False),
            json.dumps(list(card.forbidden_elements), ensure_ascii=False),
            card.notes, card.source,
        )
        self._exec(deactivate_sql, (card.novel_id, card.chapter_number))
        self._exec(insert_sql, params)

    def upsert_carry_over_seed(
        self, novel_id: str, next_chapter: int, hooks: List[str]
    ) -> None:
        existing = self.get_active(novel_id, next_chapter)
        if existing is not None and existing.source == "carry_over_seed":
            # overwrite hooks on the seed row only (no new version)
            self._exec(
                "UPDATE chapter_beat_cards SET carry_over_from_prev=? "
                "WHERE novel_id=? AND chapter_number=? AND is_active=1 "
                "AND source='carry_over_seed'",
                (json.dumps(hooks, ensure_ascii=False), novel_id, next_chapter),
            )
            return
        if existing is not None:
            # active card already promoted; do nothing
            return
        seed = ChapterBeatCard(
            novel_id=novel_id, chapter_number=next_chapter,
            pov_whitelist=(), cast_budget=(),
            storyline_must_advance=(), beat_goals=(),
            carry_over_from_prev=tuple(hooks), forbidden_elements=(),
            notes="", generated_at=datetime.utcnow(),
            source="carry_over_seed",
        )
        self.save(seed)

    # ---- reads ----
    def get_active(self, novel_id: str, chapter_number: int) -> Optional[ChapterBeatCard]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT pov_whitelist, cast_budget, storyline_must_advance, "
                "beat_goals, carry_over_from_prev, forbidden_elements, notes, "
                "source, created_at FROM chapter_beat_cards "
                "WHERE novel_id=? AND chapter_number=? AND is_active=1 LIMIT 1",
                (novel_id, chapter_number),
            ).fetchone()
        if row is None:
            return None
        return ChapterBeatCard(
            novel_id=novel_id, chapter_number=chapter_number,
            pov_whitelist=tuple(json.loads(row[0])),
            cast_budget=tuple(json.loads(row[1])),
            storyline_must_advance=tuple(json.loads(row[2])),
            beat_goals=tuple(json.loads(row[3])),
            carry_over_from_prev=tuple(json.loads(row[4])),
            forbidden_elements=tuple(json.loads(row[5])),
            notes=row[6], source=row[7],
            generated_at=datetime.fromisoformat(row[8]) if isinstance(row[8], str)
                         else (row[8] or datetime.utcnow()),
        )

    # ---- internals ----
    def _next_version(self, novel_id: str, chapter_number: int) -> int:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM chapter_beat_cards "
                "WHERE novel_id=? AND chapter_number=?",
                (novel_id, chapter_number),
            ).fetchone()
        return int(row[0]) + 1

    def _exec(self, sql: str, params) -> None:
        if self._direct:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(sql, params)
                conn.commit()
            return
        from infrastructure.persistence.database.write_dispatch import (
            enqueue_execute_sql,
        )
        ok = enqueue_execute_sql(sql, list(params))
        if not ok:
            raise RuntimeError("BeatCard write rejected: persistence queue not ready")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/integration/test_beat_card_persistence.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add -f infrastructure/persistence/repositories/beat_card_repository.py infrastructure/persistence/repositories/__init__.py tests/integration/test_beat_card_persistence.py
git commit -m "feat(persistence): add BeatCardRepository with version-aware save and seed upsert"
```

## Task 4: BudgetAllocation helpers

**Files:**
- Modify: `application/engine/services/context_budget_models.py`
- Test: `tests/unit/engine/test_budget_allocation_helpers.py`

Enforcer needs three primitives on `BudgetAllocation`: replace slot content, prepend a T0 slot at highest priority, record an enforcement log entry.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/engine/test_budget_allocation_helpers.py
from application.engine.services.context_budget_models import (
    BudgetAllocation, ContextSlot, PriorityTier,
)


def _alloc():
    a = BudgetAllocation()
    a.slots["characters"] = ContextSlot(
        name="characters", tier=PriorityTier.T0_CRITICAL,
        content="Alice: hero\nBob: sidekick\nCarol: extra",
        tokens=10, priority=5,
    )
    return a


def test_replace_character_slot_content():
    a = _alloc()
    a.replace_slot_content("characters", "Alice: hero\n[Bob, Carol - not present]")
    assert "[Bob, Carol - not present]" in a.slots["characters"].content
    assert "Bob: sidekick" not in a.slots["characters"].content


def test_replace_missing_slot_is_noop():
    a = _alloc()
    a.replace_slot_content("nonexistent", "x")
    assert "nonexistent" not in a.slots


def test_prepend_t0_slot_uses_max_priority():
    a = _alloc()
    a.prepend_t0_slot("chapter_beat_card", "DIRECTIVE TEXT")
    slot = a.slots["chapter_beat_card"]
    assert slot.tier == PriorityTier.T0_CRITICAL
    assert slot.priority > a.slots["characters"].priority


def test_enforcement_log_records_actions():
    a = _alloc()
    a.record_enforcement("dropped_characters", ["Bob", "Carol"])
    a.record_enforcement("injected", "chapter_beat_card")
    assert a.enforcement_log["dropped_characters"] == ["Bob", "Carol"]


def test_get_final_context_includes_prepended_directive():
    a = _alloc()
    a.prepend_t0_slot("chapter_beat_card", "MUST DO THIS")
    text = a.get_final_context()
    assert text.index("MUST DO THIS") < text.index("Alice: hero")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/engine/test_budget_allocation_helpers.py -v`
Expected: AttributeError for new methods.

- [ ] **Step 3: Add field and helpers**

In `application/engine/services/context_budget_models.py`, after `expired_foreshadows: List[str] = field(default_factory=list)` inside `class BudgetAllocation`, add:

```python
    enforcement_log: Dict[str, object] = field(default_factory=dict)
```

Add three methods above `get_final_context`:

```python
    def replace_slot_content(self, name: str, new_content: str) -> None:
        slot = self.slots.get(name)
        if slot is None:
            return
        slot.content = new_content

    def prepend_t0_slot(self, name: str, content: str) -> None:
        max_pri = max((s.priority for s in self.slots.values()), default=0)
        self.slots[name] = ContextSlot(
            name=name, tier=PriorityTier.T0_CRITICAL,
            content=content, tokens=0, priority=max_pri + 1000,
        )

    def record_enforcement(self, key: str, value) -> None:
        self.enforcement_log[key] = value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/engine/test_budget_allocation_helpers.py -v`
Expected: 5 passed

Run regression: `pytest tests/ -k budget -v` — all existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add application/engine/services/context_budget_models.py tests/unit/engine/test_budget_allocation_helpers.py
git commit -m "feat(engine): add BudgetAllocation slot-edit helpers"
```

## Task 5: BeatCardComposer

**Files:**
- Create: `application/blueprint/__init__.py` (if missing)
- Create: `application/blueprint/composers/__init__.py`
- Create: `application/blueprint/composers/beat_card_composer.py`
- Test: `tests/unit/blueprint/test_beat_card_composer.py`

Composer reads from three data sources, applies the rules from spec §4, and is heavily mock-driven. To keep it testable, the Composer takes its data sources as constructor-injected providers (callables), and we mock those in tests. Production wiring passes real lookups (touched later in Task 8).

- [ ] **Step 1: Ensure package inits exist**

```bash
test -f application/blueprint/__init__.py || touch application/blueprint/__init__.py
mkdir -p application/blueprint/composers
test -f application/blueprint/composers/__init__.py || touch application/blueprint/composers/__init__.py
mkdir -p tests/unit/blueprint
test -f tests/unit/blueprint/__init__.py || touch tests/unit/blueprint/__init__.py
```

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/blueprint/test_beat_card_composer.py
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from domain.engine.value_objects.chapter_beat_card import ChapterBeatCard
from application.blueprint.composers.beat_card_composer import (
    BeatCardComposer, ComposerProviders,
)


def _providers(**overrides):
    base = ComposerProviders(
        get_existing_active=MagicMock(return_value=None),
        get_beat_goals=MagicMock(return_value=["goal1"]),
        get_overdue_storylines=MagicMock(return_value=["s1"]),
        get_storyline_characters=MagicMock(return_value=["c2"]),
        get_main_pov_chars=MagicMock(return_value=["c1"]),
        get_forbidden_elements=MagicMock(return_value=["spoiler1"]),
        save_card=MagicMock(),
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_returns_existing_active_card_unchanged():
    existing = ChapterBeatCard.empty("n1", 5, source="manual")
    existing = ChapterBeatCard(
        novel_id="n1", chapter_number=5,
        pov_whitelist=("a",), cast_budget=("a",),
        storyline_must_advance=(), beat_goals=(),
        carry_over_from_prev=(), forbidden_elements=(),
        notes="", generated_at=datetime(2026, 5, 31), source="manual",
    )
    p = _providers(get_existing_active=MagicMock(return_value=existing))
    card = BeatCardComposer(p).compose("n1", 5)
    assert card is existing
    p.save_card.assert_not_called()


def test_synthesizes_card_when_none_exists():
    p = _providers()
    card = BeatCardComposer(p).compose("n1", 5)
    assert card.source == "auto"
    assert card.beat_goals == ("goal1",)
    assert card.storyline_must_advance == ("s1",)
    assert "c1" in card.cast_budget
    assert "c2" in card.cast_budget
    assert "c1" in card.pov_whitelist
    p.save_card.assert_called_once()


def test_merges_carry_over_seed_into_auto_card():
    seed = ChapterBeatCard(
        novel_id="n1", chapter_number=5,
        pov_whitelist=(), cast_budget=(),
        storyline_must_advance=(), beat_goals=(),
        carry_over_from_prev=("hook A",),
        forbidden_elements=(), notes="",
        generated_at=datetime(2026, 5, 31), source="carry_over_seed",
    )
    p = _providers(get_existing_active=MagicMock(return_value=seed))
    card = BeatCardComposer(p).compose("n1", 5)
    assert card.source == "auto"
    assert card.carry_over_from_prev == ("hook A",)
    assert card.beat_goals == ("goal1",)
    p.save_card.assert_called_once()


def test_returns_empty_fallback_on_provider_failure():
    p = _providers(get_beat_goals=MagicMock(side_effect=RuntimeError("boom")))
    card = BeatCardComposer(p).compose("n1", 5)
    assert card.source == "auto-fallback"
    assert card.cast_budget == ()
    p.save_card.assert_called_once()


def test_truncates_to_limits():
    p = _providers(
        get_main_pov_chars=MagicMock(return_value=["a", "b", "c", "d", "e"]),
        get_storyline_characters=MagicMock(return_value=["f", "g"]),
        get_overdue_storylines=MagicMock(return_value=["s1", "s2", "s3"]),
    )
    card = BeatCardComposer(p).compose("n1", 5)
    assert len(card.pov_whitelist) <= ChapterBeatCard.LIMITS.pov
    assert len(card.cast_budget) <= ChapterBeatCard.LIMITS.cast
    assert len(card.storyline_must_advance) <= ChapterBeatCard.LIMITS.storyline
    assert set(card.pov_whitelist).issubset(set(card.cast_budget))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/blueprint/test_beat_card_composer.py -v`
Expected: ImportError

- [ ] **Step 4: Implement Composer**

```python
# application/blueprint/composers/beat_card_composer.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional

from domain.engine.value_objects.chapter_beat_card import ChapterBeatCard

logger = logging.getLogger(__name__)


@dataclass
class ComposerProviders:
    """Injected data-source callables. Each returns a list[str] or appropriate type."""
    get_existing_active: Callable[[str, int], Optional[ChapterBeatCard]]
    get_beat_goals: Callable[[str, int], List[str]]
    get_overdue_storylines: Callable[[str, int], List[str]]
    get_storyline_characters: Callable[[str, List[str]], List[str]]
    get_main_pov_chars: Callable[[str, int], List[str]]
    get_forbidden_elements: Callable[[str, int], List[str]]
    save_card: Callable[[ChapterBeatCard], None]


class BeatCardComposer:
    def __init__(self, providers: ComposerProviders):
        self._p = providers

    def compose(self, novel_id: str, chapter_number: int) -> ChapterBeatCard:
        existing = self._p.get_existing_active(novel_id, chapter_number)
        if existing is not None and existing.source != "carry_over_seed":
            return existing

        carry_over = existing.carry_over_from_prev if existing is not None else ()

        try:
            card = self._synthesize(novel_id, chapter_number, carry_over)
        except Exception as exc:
            logger.warning("BeatCardComposer fallback: %s", exc)
            card = ChapterBeatCard.empty(
                novel_id, chapter_number, source="auto-fallback"
            )
            # preserve carry-over even in fallback
            if carry_over:
                card = ChapterBeatCard(
                    novel_id=novel_id, chapter_number=chapter_number,
                    pov_whitelist=(), cast_budget=(),
                    storyline_must_advance=(), beat_goals=(),
                    carry_over_from_prev=carry_over, forbidden_elements=(),
                    notes="composer fallback", generated_at=datetime.utcnow(),
                    source="auto-fallback",
                )

        self._p.save_card(card)
        return card

    def _synthesize(self, novel_id, chapter_number, carry_over) -> ChapterBeatCard:
        L = ChapterBeatCard.LIMITS

        beat_goals = list(self._p.get_beat_goals(novel_id, chapter_number))[:5]

        storylines = list(self._p.get_overdue_storylines(novel_id, chapter_number))[:L.storyline]

        pov = list(self._p.get_main_pov_chars(novel_id, chapter_number))[:L.pov]

        storyline_chars = list(self._p.get_storyline_characters(novel_id, storylines))
        cast = []
        for c in pov + storyline_chars:
            if c not in cast:
                cast.append(c)
            if len(cast) >= L.cast:
                break

        # ensure POV subset of cast (truncation may have dropped pov chars)
        pov = [c for c in pov if c in cast]

        forbidden = list(self._p.get_forbidden_elements(novel_id, chapter_number))

        return ChapterBeatCard(
            novel_id=novel_id, chapter_number=chapter_number,
            pov_whitelist=tuple(pov), cast_budget=tuple(cast),
            storyline_must_advance=tuple(storylines),
            beat_goals=tuple(beat_goals),
            carry_over_from_prev=tuple(carry_over),
            forbidden_elements=tuple(forbidden),
            notes=f"auto-composed from pov={len(pov)} cast={len(cast)} storylines={len(storylines)}",
            generated_at=datetime.utcnow(),
            source="auto",
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/blueprint/test_beat_card_composer.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add -f application/blueprint/composers/ application/blueprint/__init__.py tests/unit/blueprint/
git commit -m "feat(blueprint): add BeatCardComposer with provider injection and seed merge"
```

## Task 6: BeatCardEnforcer

**Files:**
- Create: `application/engine/services/beat_card_enforcer.py`
- Test: `tests/unit/engine/test_beat_card_enforcer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/engine/test_beat_card_enforcer.py
from datetime import datetime

import pytest

from application.engine.services.beat_card_enforcer import BeatCardEnforcer
from application.engine.services.context_budget_models import (
    BudgetAllocation, ContextSlot, PriorityTier,
)
from domain.engine.value_objects.chapter_beat_card import ChapterBeatCard


def _alloc(character_content="Alice (id=c1) - hero\nBob (id=c2) - sidekick\nCarol (id=c3) - extra"):
    a = BudgetAllocation()
    a.slots["characters"] = ContextSlot(
        name="characters", tier=PriorityTier.T0_CRITICAL,
        content=character_content, tokens=20, priority=5,
    )
    return a


def _card(pov=("c1",), cast=("c1", "c2"), **overrides):
    base = dict(
        novel_id="n1", chapter_number=5,
        pov_whitelist=pov, cast_budget=cast,
        storyline_must_advance=("s1",), beat_goals=("b1",),
        carry_over_from_prev=("hookA",), forbidden_elements=("spoilerX",),
        notes="", generated_at=datetime(2026, 5, 31), source="auto",
    )
    base.update(overrides)
    return ChapterBeatCard(**base)


def test_none_card_is_passthrough():
    a = _alloc()
    out = BeatCardEnforcer().enforce(a, None)
    assert out is a
    assert "chapter_beat_card" not in a.slots


def test_empty_card_is_passthrough():
    a = _alloc()
    card = _card(pov=(), cast=())
    out = BeatCardEnforcer().enforce(a, card)
    assert "chapter_beat_card" not in out.slots


def test_directive_slot_injected_at_highest_priority():
    a = _alloc()
    out = BeatCardEnforcer().enforce(a, _card())
    assert "chapter_beat_card" in out.slots
    directive_slot = out.slots["chapter_beat_card"]
    assert directive_slot.priority > a.slots["characters"].priority


def test_directive_contains_card_fields():
    a = _alloc()
    out = BeatCardEnforcer().enforce(a, _card())
    text = out.slots["chapter_beat_card"].content
    assert "c1" in text  # pov id appears
    assert "s1" in text  # storyline id appears
    assert "hookA" in text
    assert "spoilerX" in text


def test_characters_outside_cast_are_dropped():
    a = _alloc()
    out = BeatCardEnforcer().enforce(a, _card(cast=("c1", "c2")))
    content = out.slots["characters"].content
    # c3 (Carol) should not appear as detail; should appear as placeholder
    assert "Carol" not in content or "not present" in content


def test_enforcement_log_records_dropped_and_injected():
    a = _alloc()
    BeatCardEnforcer().enforce(a, _card(cast=("c1",)))
    assert a.enforcement_log.get("injected") == "chapter_beat_card"
    assert "dropped_character_lines" in a.enforcement_log
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/engine/test_beat_card_enforcer.py -v`
Expected: ImportError

- [ ] **Step 3: Implement Enforcer**

```python
# application/engine/services/beat_card_enforcer.py
from __future__ import annotations

import logging
from typing import Optional, Set

from application.engine.services.context_budget_models import BudgetAllocation
from domain.engine.value_objects.chapter_beat_card import ChapterBeatCard

logger = logging.getLogger(__name__)


_DIRECTIVE_TEMPLATE = (
    "[Chapter Hard Constraints - BeatCard]\n"
    "POV (only): {pov}\n"
    "Allowed cast: {cast} (others MUST NOT appear)\n"
    "Storylines to advance: {storylines}\n"
    "Beat goals: {goals}\n"
    "Carry-over hooks (must address): {carry_over}\n"
    "Forbidden (premature reveals): {forbidden}\n"
)


class BeatCardEnforcer:
    """Hard-clamps the assembled context to the BeatCard contract."""

    def __init__(self, character_slot_name: str = "characters"):
        self._slot_name = character_slot_name

    def enforce(
        self,
        allocation: BudgetAllocation,
        card: Optional[ChapterBeatCard],
    ) -> BudgetAllocation:
        if card is None or not card.cast_budget:
            return allocation

        dropped = self._filter_character_slot(allocation, set(card.cast_budget))
        directive = self._render_directive(card)
        allocation.prepend_t0_slot("chapter_beat_card", directive)

        allocation.record_enforcement("dropped_character_lines", dropped)
        allocation.record_enforcement("injected", "chapter_beat_card")
        return allocation

    def _filter_character_slot(
        self, allocation: BudgetAllocation, allowed_ids: Set[str]
    ) -> list:
        slot = allocation.slots.get(self._slot_name)
        if slot is None or not slot.content.strip():
            return []
        kept, dropped = [], []
        for line in slot.content.splitlines():
            if not line.strip():
                continue
            # heuristic: a line is "kept" if any allowed id is a substring
            if any(cid in line for cid in allowed_ids):
                kept.append(line)
            else:
                dropped.append(line)
        new_lines = kept[:]
        if dropped:
            new_lines.append(
                f"[{len(dropped)} other characters - not present this chapter]"
            )
        allocation.replace_slot_content(self._slot_name, "\n".join(new_lines))
        return dropped

    def _render_directive(self, card: ChapterBeatCard) -> str:
        return _DIRECTIVE_TEMPLATE.format(
            pov=", ".join(card.pov_whitelist) or "(none)",
            cast=", ".join(card.cast_budget) or "(none)",
            storylines=", ".join(card.storyline_must_advance) or "(none)",
            goals="; ".join(card.beat_goals) or "(none)",
            carry_over="; ".join(card.carry_over_from_prev) or "(none)",
            forbidden=", ".join(card.forbidden_elements) or "(none)",
        )
```

Note: the directive template can later be moved to a YAML override in Task 9 without breaking the API.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/engine/test_beat_card_enforcer.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add application/engine/services/beat_card_enforcer.py tests/unit/engine/test_beat_card_enforcer.py
git commit -m "feat(engine): add BeatCardEnforcer with character filter and T0 directive injection"
```

## Task 7: CarryOverExtractor

**Files:**
- Create: `application/workflows/extractors/__init__.py`
- Create: `application/workflows/extractors/carry_over_extractor.py`
- Test: `tests/unit/workflows/test_carry_over_extractor.py`

- [ ] **Step 1: Ensure package init**

```bash
mkdir -p application/workflows/extractors
test -f application/workflows/extractors/__init__.py || touch application/workflows/extractors/__init__.py
mkdir -p tests/unit/workflows
test -f tests/unit/workflows/__init__.py || touch tests/unit/workflows/__init__.py
```

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/workflows/test_carry_over_extractor.py
from unittest.mock import MagicMock

import pytest

from application.workflows.extractors.carry_over_extractor import CarryOverExtractor


def _mock_repo():
    repo = MagicMock()
    repo.upsert_carry_over_seed = MagicMock()
    return repo


def _event(event_type, **kw):
    defaults = dict(type=event_type, character_id="c1", detail="detail")
    defaults.update(kw)
    return defaults


def test_extracts_dialogue_open_hooks():
    repo = _mock_repo()
    ext = CarryOverExtractor(repo)
    events = [
        _event("dialogue_open", detail="question to Wang Fang"),
        _event("item_in_transit", detail="jade pendant with Zhao Wu"),
    ]
    hooks = ext.extract_and_persist("n1", 3, "chapter text", events, None)
    assert len(hooks) >= 2
    assert any("Wang Fang" in h for h in hooks)
    repo.upsert_carry_over_seed.assert_called_once()
    call_args = repo.upsert_carry_over_seed.call_args
    assert call_args[0][0] == "n1"
    assert call_args[0][1] == 4  # next chapter


def test_extracts_emotional_residue():
    repo = _mock_repo()
    ext = CarryOverExtractor(repo)
    residue = {"c1": {"emotion": "anger", "intensity": 0.9, "target": "father"}}
    hooks = ext.extract_and_persist("n1", 3, "text", [], residue)
    assert any("anger" in h.lower() or "c1" in h for h in hooks)


def test_truncates_to_five_hooks():
    repo = _mock_repo()
    ext = CarryOverExtractor(repo)
    events = [_event("dialogue_open", detail=f"q{i}") for i in range(10)]
    hooks = ext.extract_and_persist("n1", 3, "text", events, None)
    assert len(hooks) <= 5


def test_returns_empty_on_no_signals():
    repo = _mock_repo()
    ext = CarryOverExtractor(repo)
    hooks = ext.extract_and_persist("n1", 3, "text", [], None)
    assert hooks == []
    repo.upsert_carry_over_seed.assert_not_called()


def test_soft_failure_on_exception():
    repo = _mock_repo()
    repo.upsert_carry_over_seed.side_effect = RuntimeError("db down")
    ext = CarryOverExtractor(repo)
    # should not raise
    hooks = ext.extract_and_persist("n1", 3, "text", [_event("dialogue_open")], None)
    # hooks may still be returned, but persist failed gracefully
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/workflows/test_carry_over_extractor.py -v`
Expected: ImportError

- [ ] **Step 4: Implement CarryOverExtractor**

```python
# application/workflows/extractors/carry_over_extractor.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_HOOK_PRIORITY = {
    "dialogue_open": 0,
    "item_in_transit": 1,
    "emotional_residue": 2,
    "fact_revealed_to_subset": 3,
}
_MAX_HOOKS = 5
_EMOTION_THRESHOLD = 0.7


class CarryOverExtractor:
    """Distills forward-pointing hooks from evolution events and emotional residue."""

    def __init__(self, beat_card_repo):
        self._repo = beat_card_repo

    def extract_and_persist(
        self,
        novel_id: str,
        chapter_number: int,
        chapter_content: str,
        evolution_events: List[dict],
        emotional_residue: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        hooks = self._extract(evolution_events, emotional_residue)
        if not hooks:
            return []
        try:
            self._repo.upsert_carry_over_seed(
                novel_id, chapter_number + 1, hooks
            )
        except Exception:
            logger.exception("CarryOverExtractor persist failed for novel=%s ch=%d",
                             novel_id, chapter_number)
        return hooks

    def _extract(self, events, residue) -> List[str]:
        raw = []
        for ev in events:
            etype = ev.get("type", "")
            if etype == "dialogue_open":
                raw.append((0, f"{ev.get('character_id', '?')}: {ev.get('detail', 'unresolved dialogue')}"))
            elif etype == "item_in_transit":
                raw.append((1, f"Item: {ev.get('detail', 'item in transit')}"))
            elif etype == "fact_revealed_to_subset":
                raw.append((3, f"{ev.get('character_id', '?')} knows secret: {ev.get('detail', '')}"))

        if residue:
            for cid, info in residue.items():
                intensity = info.get("intensity", 0) if isinstance(info, dict) else 0
                if intensity >= _EMOTION_THRESHOLD:
                    emotion = info.get("emotion", "unresolved feeling")
                    raw.append((2, f"{cid}: {emotion} (intensity {intensity:.1f})"))

        raw.sort(key=lambda x: x[0])
        return [h for _, h in raw[:_MAX_HOOKS]]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/workflows/test_carry_over_extractor.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add -f application/workflows/extractors/ tests/unit/workflows/test_carry_over_extractor.py tests/unit/workflows/__init__.py
git commit -m "feat(workflows): add CarryOverExtractor for chapter continuity hooks"
```

## Task 8: Wire Enforcer into ContextBuilder

**Files:**
- Modify: `application/engine/services/context_builder.py`
- Test: `tests/integration/test_context_builder_with_enforcer.py`

Enforcer is wired as an **optional collaborator** via constructor injection (mirrors the existing pattern of `Optional` kwargs). When `beat_card_repo` and `beat_card_enforcer` are both provided, build_context fetches the active card and runs the Enforcer on the allocation before returning the final context.

The configuration check `BEATCARD_ENABLED` is intentionally NOT inside ContextBuilder — Task 9 short-circuits at the wiring layer in `writing_delegate` by simply not constructing the enforcer when the flag is off.

- [ ] **Step 1: Write failing integration test**

```python
# tests/integration/test_context_builder_with_enforcer.py
"""Verify ContextBuilder applies Enforcer when a card is available."""
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from application.engine.services.context_builder import ContextBuilder
from application.engine.services.context_budget_models import (
    BudgetAllocation, ContextSlot, PriorityTier,
)
from application.engine.services.beat_card_enforcer import BeatCardEnforcer
from domain.engine.value_objects.chapter_beat_card import ChapterBeatCard


def _seeded_allocation():
    a = BudgetAllocation()
    a.slots["characters"] = ContextSlot(
        name="characters", tier=PriorityTier.T0_CRITICAL,
        content="Alice (id=c1) - hero\nBob (id=c2) - sidekick",
        tokens=10, priority=5,
    )
    return a


def _card():
    return ChapterBeatCard(
        novel_id="n1", chapter_number=5,
        pov_whitelist=("c1",), cast_budget=("c1",),
        storyline_must_advance=("s1",), beat_goals=("b1",),
        carry_over_from_prev=("hookA",), forbidden_elements=(),
        notes="", generated_at=datetime(2026, 5, 31), source="auto",
    )


def test_enforcer_runs_when_repo_and_enforcer_provided():
    cb = ContextBuilder.__new__(ContextBuilder)
    cb.budget_allocator = MagicMock()
    cb.budget_allocator.allocate.return_value = _seeded_allocation()
    cb.beat_card_repo = MagicMock()
    cb.beat_card_repo.get_active.return_value = _card()
    cb.beat_card_enforcer = BeatCardEnforcer()

    ctx_text = cb.build_context(
        novel_id="n1", chapter_number=5,
        outline="o", max_tokens=1000, scene_director=None,
    )
    assert "Chapter Hard Constraints" in ctx_text
    assert "hookA" in ctx_text


def test_no_enforcer_path_is_unchanged():
    cb = ContextBuilder.__new__(ContextBuilder)
    cb.budget_allocator = MagicMock()
    cb.budget_allocator.allocate.return_value = _seeded_allocation()
    cb.beat_card_repo = None
    cb.beat_card_enforcer = None

    ctx_text = cb.build_context(
        novel_id="n1", chapter_number=5,
        outline="o", max_tokens=1000, scene_director=None,
    )
    assert "Chapter Hard Constraints" not in ctx_text


def test_missing_card_passes_through():
    cb = ContextBuilder.__new__(ContextBuilder)
    cb.budget_allocator = MagicMock()
    cb.budget_allocator.allocate.return_value = _seeded_allocation()
    cb.beat_card_repo = MagicMock()
    cb.beat_card_repo.get_active.return_value = None
    cb.beat_card_enforcer = BeatCardEnforcer()

    ctx_text = cb.build_context(
        novel_id="n1", chapter_number=5,
        outline="o", max_tokens=1000, scene_director=None,
    )
    assert "Chapter Hard Constraints" not in ctx_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_context_builder_with_enforcer.py -v`
Expected: AttributeError (`beat_card_repo` / `beat_card_enforcer` not set) OR enforcer not invoked.

- [ ] **Step 3: Add Enforcer injection points to ContextBuilder.__init__**

In `application/engine/services/context_builder.py`, add two new kwargs at the end of `__init__` (before the closing `):`). After the `evolution_repository=None,` line:

```python
        beat_card_repo=None,
        beat_card_enforcer=None,
```

Inside `__init__` body, after `self.evolution_repository = evolution_repository` (or the last `self.xxx = xxx` assignment), add:

```python
        self.beat_card_repo = beat_card_repo
        self.beat_card_enforcer = beat_card_enforcer
```

- [ ] **Step 4: Apply Enforcer in build_context**

Locate `build_context` (around line 170). Replace:

```python
        allocation = self.budget_allocator.allocate(
            novel_id=novel_id,
            chapter_number=chapter_number,
            outline=outline,
            total_budget=max_tokens,
            scene_director=scene_director,
        )
        
        return allocation.get_final_context()
```

With:

```python
        allocation = self.budget_allocator.allocate(
            novel_id=novel_id,
            chapter_number=chapter_number,
            outline=outline,
            total_budget=max_tokens,
            scene_director=scene_director,
        )

        if self.beat_card_enforcer is not None and self.beat_card_repo is not None:
            try:
                card = self.beat_card_repo.get_active(novel_id, chapter_number)
                allocation = self.beat_card_enforcer.enforce(allocation, card)
            except Exception:
                logger.exception("BeatCard enforcement failed (novel=%s ch=%d)",
                                 novel_id, chapter_number)

        return allocation.get_final_context()
```

Apply the same pattern to `build_structured_context` if it returns layered text (look at lines 199-235 and add the enforce call between `allocate(...)` and the return).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/integration/test_context_builder_with_enforcer.py -v`
Expected: 3 passed

Run regression: `pytest tests/ -k context_builder -v`
Expected: existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add application/engine/services/context_builder.py tests/integration/test_context_builder_with_enforcer.py
git commit -m "feat(engine): wire BeatCardEnforcer into ContextBuilder.build_context"
```

## Task 9: Wire CarryOverExtractor into post-chapter pipeline

**Files:**
- Modify: `application/workflows/auto_novel_generation_workflow.py`

The workflow's `__init__` already has many optional collaborators. We add `carry_over_extractor` and call it as step 7 in `post_process_generated_chapter`, right before the `return` at line 562.

- [ ] **Step 1: Add constructor arg**

In `application/workflows/auto_novel_generation_workflow.py`, find `class AutoNovelGenerationWorkflow.__init__`. Add a new kwarg after the last existing one:

```python
        carry_over_extractor=None,
```

Inside the body, add:

```python
        self.carry_over_extractor = carry_over_extractor
```

- [ ] **Step 2: Add step 7 in post_process_generated_chapter**

Before the `return {` block at line 562, insert:

```python
        # Step 7: CarryOverExtractor — distill hooks for next chapter
        carry_over_hooks = []
        if self.carry_over_extractor and os.environ.get("BEATCARD_ENABLED", "true").lower() not in ("false", "0", "off"):
            try:
                evolution_events_for_hooks = chapter_state.get("events", []) if isinstance(chapter_state, dict) else []
                emotional_residue = memory_delta.get("emotional_residue") if isinstance(memory_delta, dict) else None
                carry_over_hooks = self.carry_over_extractor.extract_and_persist(
                    novel_id=novel_id,
                    chapter_number=chapter_number,
                    chapter_content=content,
                    evolution_events=evolution_events_for_hooks,
                    emotional_residue=emotional_residue,
                )
                if carry_over_hooks:
                    logger.info("  🔗 CarryOver: %d hooks for chapter %d", len(carry_over_hooks), chapter_number + 1)
            except Exception as e:
                logger.warning("CarryOverExtractor failed: %s", e)
```

Also add `import os` at the top of the file if not already present.

Add `carry_over_hooks` to the return dict:

```python
            "carry_over_hooks": carry_over_hooks,
```

- [ ] **Step 3: Verify the file parses**

Run: `python -c "import ast; ast.parse(open('application/workflows/auto_novel_generation_workflow.py').read()); print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add application/workflows/auto_novel_generation_workflow.py
git commit -m "feat(workflows): wire CarryOverExtractor as step 7 in post-chapter pipeline"
```

## Task 10: Wire Composer into writing_delegate + config + YAML

**Files:**
- Modify: `engine/runtime/writing_delegate.py`
- Create: `infrastructure/ai/prompt_packages/nodes/beat_card_directive.yaml`
- Modify: `.env.example`

This is the production wiring task that connects the Composer to the autopilot writing loop, adds the config flags, and creates the YAML override file.

- [ ] **Step 1: Add config keys to .env.example**

Append at end of `.env.example`:

```
# Chapter BeatCard Pipeline
BEATCARD_ENABLED=true
BEATCARD_ENFORCEMENT_MODE=hard       # hard | soft | off
BEATCARD_POV_LIMIT=3
BEATCARD_CAST_LIMIT=5
BEATCARD_STORYLINE_LIMIT=2
```

- [ ] **Step 2: Create YAML override**

```yaml
# infrastructure/ai/prompt_packages/nodes/beat_card_directive.yaml
name: chapter_beat_card
tier: t0_critical
description: >
  Per-chapter hard constraints injected by the BeatCard pipeline.
  Overrides the default template in BeatCardEnforcer._DIRECTIVE_TEMPLATE.
template: |
  [Chapter Hard Constraints - BeatCard]
  POV (only): {pov}
  Allowed cast: {cast} (others MUST NOT appear)
  Storylines to advance: {storylines}
  Beat goals: {goals}
  Carry-over hooks (must address): {carry_over}
  Forbidden (premature reveals): {forbidden}
```

- [ ] **Step 3: Wire Composer in writing_delegate**

In `engine/runtime/writing_delegate.py`, inside `run_story_pipeline_writing`, before the `pipeline = get_pipeline_registry().create_pipeline(genre)` line (around line 153), insert the Composer call:

```python
    # BeatCard composition: synthesize per-chapter contract before generation
    if os.environ.get("BEATCARD_ENABLED", "true").lower() not in ("false", "0", "off"):
        try:
            from infrastructure.persistence.repositories.beat_card_repository import BeatCardRepository
            from application.blueprint.composers.beat_card_composer import BeatCardComposer, ComposerProviders

            bc_repo = BeatCardRepository()

            def _get_active(nid, ch):
                return bc_repo.get_active(nid, ch)
            def _save(card):
                bc_repo.save(card)

            # TODO: wire real governance/blueprint lookups when available
            providers = ComposerProviders(
                get_existing_active=_get_active,
                get_beat_goals=lambda nid, ch: [],
                get_overdue_storylines=lambda nid, ch: [],
                get_storyline_characters=lambda nid, sls: [],
                get_main_pov_chars=lambda nid, ch: [],
                get_forbidden_elements=lambda nid, ch: [],
                save_card=_save,
            )
            BeatCardComposer(providers).compose(novel_id, ctx.chapter_number)
        except Exception:
            logger.exception("BeatCard composition failed for novel=%s", novel_id)
```

Also add `import os` at the top if missing.

The provider lambdas are stubs returning empty lists for now — real governance/blueprint lookups will be wired once those services expose the needed query methods. The Composer's soft-fallback means it produces an `auto-fallback` card when data sources return empty, and the Enforcer passes through when the card has no `cast_budget`.

- [ ] **Step 4: Verify parse**

Run: `python -c "import ast; ast.parse(open('engine/runtime/writing_delegate.py').read()); print('OK')"`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add -f engine/runtime/writing_delegate.py infrastructure/ai/prompt_packages/nodes/beat_card_directive.yaml .env.example
git commit -m "feat(engine): wire BeatCardComposer in writing_delegate; add config and YAML override"
```

## Task 11: End-to-end integration test

**Files:**
- Create: `tests/integration/test_beat_card_pipeline.py`

This test walks the full pipeline: compose card -> enforce -> carry-over extraction, using in-memory SQLite and mock providers.

- [ ] **Step 1: Write the test**

```python
# tests/integration/test_beat_card_pipeline.py
"""End-to-end BeatCard pipeline: compose -> enforce -> carry-over -> next compose."""
import os
import sqlite3
import tempfile
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from domain.engine.value_objects.chapter_beat_card import ChapterBeatCard
from application.blueprint.composers.beat_card_composer import BeatCardComposer, ComposerProviders
from application.engine.services.beat_card_enforcer import BeatCardEnforcer
from application.engine.services.context_budget_models import (
    BudgetAllocation, ContextSlot, PriorityTier,
)
from application.workflows.extractors.carry_over_extractor import CarryOverExtractor
from infrastructure.persistence.repositories.beat_card_repository import BeatCardRepository


@pytest.fixture
def fresh_db():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "e2e.db")
    os.environ["PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES"] = "1"
    conn = sqlite3.connect(db_path)
    conn.executescript(open("infrastructure/persistence/database/schema.sql").read())
    conn.execute("INSERT INTO novels (id, title) VALUES (?, ?)", ("novel1", "Test"))
    conn.commit()
    conn.close()
    return db_path


def test_full_pipeline_chapter_5_to_6(fresh_db):
    repo = BeatCardRepository(db_path=fresh_db, direct=True)

    # --- Chapter 5: compose ---
    providers = ComposerProviders(
        get_existing_active=repo.get_active,
        get_beat_goals=lambda nid, ch: ["confront villain", "reveal secret"],
        get_overdue_storylines=lambda nid, ch: ["sl_main"],
        get_storyline_characters=lambda nid, sls: ["c2_villain"],
        get_main_pov_chars=lambda nid, ch: ["c1_hero"],
        get_forbidden_elements=lambda nid, ch: ["spoiler_identity"],
        save_card=repo.save,
    )
    card5 = BeatCardComposer(providers).compose("novel1", 5)
    assert card5.source == "auto"
    assert "c1_hero" in card5.pov_whitelist
    assert "c1_hero" in card5.cast_budget
    assert "c2_villain" in card5.cast_budget
    assert "sl_main" in card5.storyline_must_advance

    # --- Chapter 5: enforce ---
    alloc = BudgetAllocation()
    alloc.slots["characters"] = ContextSlot(
        name="characters", tier=PriorityTier.T0_CRITICAL,
        content="c1_hero - protagonist\nc2_villain - antagonist\nc3_side - bystander\nc4_extra - filler",
        tokens=30, priority=5,
    )
    enforcer = BeatCardEnforcer()
    enforced = enforcer.enforce(alloc, card5)
    assert "chapter_beat_card" in enforced.slots
    chars = enforced.slots["characters"].content
    assert "c3_side" not in chars or "not present" in chars

    # --- Chapter 5: carry-over extraction ---
    extractor = CarryOverExtractor(repo)
    events = [
        {"type": "dialogue_open", "character_id": "c1_hero", "detail": "question about the map"},
        {"type": "item_in_transit", "character_id": "c2_villain", "detail": "key in villain possession"},
    ]
    hooks = extractor.extract_and_persist("novel1", 5, "chapter 5 content", events, None)
    assert len(hooks) >= 2

    # --- Chapter 6: compose (should merge carry-over seed) ---
    card6 = BeatCardComposer(providers).compose("novel1", 6)
    assert card6.source == "auto"
    assert len(card6.carry_over_from_prev) >= 2
    assert any("map" in h for h in card6.carry_over_from_prev)

    # --- Chapter 6: enforce ---
    alloc6 = BudgetAllocation()
    alloc6.slots["characters"] = ContextSlot(
        name="characters", tier=PriorityTier.T0_CRITICAL,
        content="c1_hero - protagonist\nc2_villain - antagonist",
        tokens=20, priority=5,
    )
    enforced6 = enforcer.enforce(alloc6, card6)
    directive = enforced6.slots["chapter_beat_card"].content
    assert "carry" in directive.lower() or "hook" in directive.lower()
```

- [ ] **Step 2: Run the E2E test**

Run: `pytest tests/integration/test_beat_card_pipeline.py -v`
Expected: 1 passed

- [ ] **Step 3: Commit**

```bash
git add -f tests/integration/test_beat_card_pipeline.py
git commit -m "test(integration): add end-to-end BeatCard pipeline test"
```

## Task 12: Run full test suite and verify

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/unit/domain/test_chapter_beat_card.py tests/unit/engine/test_budget_allocation_helpers.py tests/unit/engine/test_beat_card_enforcer.py tests/unit/blueprint/test_beat_card_composer.py tests/unit/workflows/test_carry_over_extractor.py -v`
Expected: all pass

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/integration/test_beat_card_persistence.py tests/integration/test_context_builder_with_enforcer.py tests/integration/test_beat_card_pipeline.py -v`
Expected: all pass

- [ ] **Step 3: Run existing test suite regression**

Run: `pytest tests/ -x --timeout=120 -q`
Expected: no new failures introduced by BeatCard changes

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "chore: fix any test regressions from BeatCard pipeline"
```

