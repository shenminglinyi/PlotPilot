# Topic Idea Incubation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight topic idea incubation pool that can generate, save, archive, restore, and adopt topic ideas into the existing novel setup flow.

**Architecture:** Add an independent `topic` slice with a small domain entity, SQLite repository, application service, FastAPI router, and Vue panel on the home page. Topic ideas stay separate from formal novel data until the user explicitly adopts one, at which point the service calls the existing `NovelService.create_novel`.

**Tech Stack:** Python 3, FastAPI, SQLite, pytest, Vue 3, TypeScript, Naive UI, Vite.

---

## File Structure

- Create `domain/topic/__init__.py`: exports topic domain types.
- Create `domain/topic/entities.py`: `TopicIdea` dataclass and status constants.
- Create `domain/topic/repositories.py`: repository protocol used by application service.
- Create `application/topic/__init__.py`: package marker.
- Create `application/topic/dtos.py`: request/response DTOs and normalization helpers.
- Create `application/topic/services/__init__.py`: package marker.
- Create `application/topic/services/topic_idea_service.py`: LLM prompt, parsing, fallback, list/update/adopt orchestration.
- Create `infrastructure/persistence/database/sqlite_topic_idea_repository.py`: SQLite CRUD and row mapping.
- Modify `infrastructure/persistence/database/schema.sql`: add `topic_ideas` table and indexes.
- Modify `interfaces/api/dependencies.py`: add `get_topic_idea_repository` and `get_topic_idea_service`.
- Create `interfaces/api/v1/topic/__init__.py`: package marker.
- Create `interfaces/api/v1/topic/topic_ideas.py`: FastAPI models and routes.
- Modify `interfaces/main.py`: import and include topic router.
- Create `frontend/src/api/topic.ts`: typed client for `/api/v1/topics`.
- Create `frontend/src/components/topic/TopicIdeaPanel.vue`: modal panel for generating and managing topic ideas.
- Modify `frontend/src/views/Home.vue`: add topic pool button, modal state, and adopt-to-wizard bridge.
- Create `tests/unit/domain/topic/test_topic_idea.py`: entity normalization tests.
- Create `tests/unit/infrastructure/database/test_sqlite_topic_idea_repository.py`: repository tests.
- Create `tests/unit/application/services/test_topic_idea_service.py`: generation, fallback, status, adopt idempotency tests.
- Create `tests/unit/interfaces/api/test_topic_ideas.py`: API route tests.

## Implementation Tasks

### Task 1: Domain Entity And DTOs

**Files:**
- Create: `domain/topic/__init__.py`
- Create: `domain/topic/entities.py`
- Create: `domain/topic/repositories.py`
- Create: `application/topic/__init__.py`
- Create: `application/topic/dtos.py`
- Test: `tests/unit/domain/topic/test_topic_idea.py`

- [ ] **Step 1: Write the failing entity tests**

Create `tests/unit/domain/topic/test_topic_idea.py`:

```python
from domain.topic.entities import TopicIdea, TopicIdeaStatus


def test_topic_idea_normalizes_lists_and_score():
    idea = TopicIdea(
        id="topic-1",
        title="  青铜旧神  ",
        genre="玄幻升级",
        world_preset="修仙风",
        length_tier="standard",
        logline="旧神复苏。",
        premise="少年发现宗门供奉的是敌人。",
        protagonist_hook="不能修炼，但能读懂神像裂纹。",
        core_conflict="少年 vs 伪装成祖师的旧神",
        opening_hook="祖师像在夜里流血。",
        selling_points=("升级爽", "宗门悬疑"),
        long_term_potential="从宗门谜案扩展到诸天旧神秩序。",
        risk_notes=("旧神设定容易空泛",),
        market_tags=("玄幻", "克系"),
        score=188,
        status="unknown",
        source_brief={"keywords": ["旧神"]},
    )

    assert idea.title == "青铜旧神"
    assert idea.selling_points == ["升级爽", "宗门悬疑"]
    assert idea.risk_notes == ["旧神设定容易空泛"]
    assert idea.market_tags == ["玄幻", "克系"]
    assert idea.score == 100
    assert idea.status == TopicIdeaStatus.DRAFT


def test_topic_idea_adopted_status_accepts_existing_novel_id():
    idea = TopicIdea(
        id="topic-2",
        title="霓虹斩妖人",
        genre="科幻赛博",
        world_preset="赛博朋克风",
        length_tier="short",
        logline="义体医生夜斩数据妖魔。",
        premise="义体医生卷入巨企养妖阴谋。",
        status=TopicIdeaStatus.ADOPTED,
        adopted_novel_id="novel-123",
    )

    assert idea.status == TopicIdeaStatus.ADOPTED
    assert idea.adopted_novel_id == "novel-123"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/domain/topic/test_topic_idea.py -q
```

Expected: FAIL during import with `ModuleNotFoundError: No module named 'domain.topic'`.

- [ ] **Step 3: Add the domain entity and repository protocol**

Create `domain/topic/entities.py`:

```python
"""Topic idea domain objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


class TopicIdeaStatus:
    DRAFT = "draft"
    ADOPTED = "adopted"
    ARCHIVED = "archived"

    ALL = {DRAFT, ADOPTED, ARCHIVED}

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        value = (raw or "").strip().lower()
        return value if value in cls.ALL else cls.DRAFT


def _str(value: Any) -> str:
    return str(value or "").strip()


def _str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Iterable):
        return [str(v).strip() for v in value if str(v or "").strip()]
    return []


def _score(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    return max(0, min(100, n))


@dataclass
class TopicIdea:
    id: str
    title: str
    genre: str = ""
    world_preset: str = ""
    length_tier: str = "standard"
    logline: str = ""
    premise: str = ""
    protagonist_hook: str = ""
    core_conflict: str = ""
    opening_hook: str = ""
    selling_points: List[str] = field(default_factory=list)
    long_term_potential: str = ""
    risk_notes: List[str] = field(default_factory=list)
    market_tags: List[str] = field(default_factory=list)
    score: int = 0
    status: str = TopicIdeaStatus.DRAFT
    adopted_novel_id: Optional[str] = None
    source_brief: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        self.id = _str(self.id)
        self.title = _str(self.title)
        self.genre = _str(self.genre)
        self.world_preset = _str(self.world_preset)
        self.length_tier = _str(self.length_tier) or "standard"
        self.logline = _str(self.logline)
        self.premise = _str(self.premise)
        self.protagonist_hook = _str(self.protagonist_hook)
        self.core_conflict = _str(self.core_conflict)
        self.opening_hook = _str(self.opening_hook)
        self.selling_points = _str_list(self.selling_points)
        self.long_term_potential = _str(self.long_term_potential)
        self.risk_notes = _str_list(self.risk_notes)
        self.market_tags = _str_list(self.market_tags)
        self.score = _score(self.score)
        self.status = TopicIdeaStatus.normalize(self.status)
        self.adopted_novel_id = _str(self.adopted_novel_id) or None
        self.source_brief = dict(self.source_brief or {})
        now = datetime.utcnow().isoformat()
        self.created_at = _str(self.created_at) or now
        self.updated_at = _str(self.updated_at) or self.created_at
```

Create `domain/topic/repositories.py`:

```python
"""Topic idea repository contracts."""
from __future__ import annotations

from typing import List, Optional, Protocol

from domain.topic.entities import TopicIdea


class TopicIdeaRepository(Protocol):
    def save(self, idea: TopicIdea) -> TopicIdea: ...
    def get_by_id(self, topic_id: str) -> Optional[TopicIdea]: ...
    def list(self, status: Optional[str] = None) -> List[TopicIdea]: ...
    def update_status(
        self,
        topic_id: str,
        status: str,
        adopted_novel_id: Optional[str] = None,
    ) -> TopicIdea: ...
```

Create `domain/topic/__init__.py`:

```python
from domain.topic.entities import TopicIdea, TopicIdeaStatus

__all__ = ["TopicIdea", "TopicIdeaStatus"]
```

Create `application/topic/__init__.py`:

```python
"""Topic idea incubation application package."""
```

- [ ] **Step 4: Add application DTOs**

Create `application/topic/dtos.py`:

```python
"""DTOs for topic idea incubation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from domain.topic.entities import TopicIdea


@dataclass
class TopicGenerateRequestDTO:
    genre: str = ""
    world_preset: str = ""
    keywords: List[str] = field(default_factory=list)
    desired_selling_points: List[str] = field(default_factory=list)
    avoid_patterns: List[str] = field(default_factory=list)
    length_tier: str = "standard"
    count: int = 3

    def normalized_count(self) -> int:
        return max(1, min(5, int(self.count or 3)))

    def to_source_brief(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TopicIdeaDTO:
    id: str
    title: str
    genre: str
    world_preset: str
    length_tier: str
    logline: str
    premise: str
    protagonist_hook: str
    core_conflict: str
    opening_hook: str
    selling_points: List[str]
    long_term_potential: str
    risk_notes: List[str]
    market_tags: List[str]
    score: int
    status: str
    adopted_novel_id: Optional[str]
    source_brief: Dict[str, Any]
    created_at: str
    updated_at: str

    @classmethod
    def from_domain(cls, idea: TopicIdea) -> "TopicIdeaDTO":
        return cls(**asdict(idea))
```

- [ ] **Step 5: Run the entity tests**

Run:

```bash
pytest tests/unit/domain/topic/test_topic_idea.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add domain/topic application/topic tests/unit/domain/topic/test_topic_idea.py
git commit -m "feat: add topic idea domain model"
```

Only stage the files listed above.

### Task 2: SQLite Schema And Repository

**Files:**
- Modify: `infrastructure/persistence/database/schema.sql`
- Create: `infrastructure/persistence/database/sqlite_topic_idea_repository.py`
- Test: `tests/unit/infrastructure/database/test_sqlite_topic_idea_repository.py`

- [ ] **Step 1: Write failing repository tests**

Create `tests/unit/infrastructure/database/test_sqlite_topic_idea_repository.py`:

```python
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_topic_idea_repository import (
    SqliteTopicIdeaRepository,
)
from domain.topic.entities import TopicIdea, TopicIdeaStatus


def test_repository_saves_lists_and_filters_status(tmp_path):
    db = DatabaseConnection(str(tmp_path / "topics.db"))
    repo = SqliteTopicIdeaRepository(db)
    idea = TopicIdea(
        id="topic-1",
        title="青铜旧神",
        genre="玄幻升级",
        world_preset="修仙风",
        length_tier="standard",
        logline="少年读懂神像裂纹。",
        premise="少年发现宗门祖师是旧神伪装。",
        selling_points=["升级爽", "宗门悬疑"],
        risk_notes=["旧神设定容易空泛"],
        market_tags=["玄幻", "克系"],
        score=87,
        source_brief={"keywords": ["旧神"]},
    )

    saved = repo.save(idea)
    loaded = repo.get_by_id(saved.id)
    drafts = repo.list(status=TopicIdeaStatus.DRAFT)

    assert loaded is not None
    assert loaded.title == "青铜旧神"
    assert loaded.selling_points == ["升级爽", "宗门悬疑"]
    assert loaded.source_brief == {"keywords": ["旧神"]}
    assert [i.id for i in drafts] == ["topic-1"]


def test_repository_updates_status_and_adopted_novel_id(tmp_path):
    db = DatabaseConnection(str(tmp_path / "topics.db"))
    repo = SqliteTopicIdeaRepository(db)
    repo.save(TopicIdea(id="topic-2", title="霓虹斩妖人"))

    updated = repo.update_status(
        "topic-2",
        TopicIdeaStatus.ADOPTED,
        adopted_novel_id="novel-2",
    )

    assert updated.status == TopicIdeaStatus.ADOPTED
    assert updated.adopted_novel_id == "novel-2"
    assert repo.get_by_id("topic-2").adopted_novel_id == "novel-2"
```

- [ ] **Step 2: Run repository tests to verify they fail**

Run:

```bash
pytest tests/unit/infrastructure/database/test_sqlite_topic_idea_repository.py -q
```

Expected: FAIL during import with `ModuleNotFoundError` for `sqlite_topic_idea_repository`.

- [ ] **Step 3: Add schema table and indexes**

Append near the `novels` table section in `infrastructure/persistence/database/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS topic_ideas (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    genre TEXT DEFAULT '',
    world_preset TEXT DEFAULT '',
    length_tier TEXT DEFAULT 'standard',
    logline TEXT DEFAULT '',
    premise TEXT DEFAULT '',
    protagonist_hook TEXT DEFAULT '',
    core_conflict TEXT DEFAULT '',
    opening_hook TEXT DEFAULT '',
    selling_points_json TEXT DEFAULT '[]',
    long_term_potential TEXT DEFAULT '',
    risk_notes_json TEXT DEFAULT '[]',
    market_tags_json TEXT DEFAULT '[]',
    score INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'adopted', 'archived')),
    adopted_novel_id TEXT,
    source_brief_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (adopted_novel_id) REFERENCES novels(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_topic_ideas_status ON topic_ideas(status);
CREATE INDEX IF NOT EXISTS idx_topic_ideas_created_at ON topic_ideas(created_at);
```

- [ ] **Step 4: Implement repository**

Create `infrastructure/persistence/database/sqlite_topic_idea_repository.py`:

```python
"""SQLite repository for topic ideas."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from domain.topic.entities import TopicIdea, TopicIdeaStatus
from infrastructure.persistence.database.connection import DatabaseConnection


def _json_dump(value: Any, fallback: Any) -> str:
    try:
        return json.dumps(value if value is not None else fallback, ensure_ascii=False)
    except TypeError:
        return json.dumps(fallback, ensure_ascii=False)


def _json_load(text: str, fallback: Any) -> Any:
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


class SqliteTopicIdeaRepository:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    def save(self, idea: TopicIdea) -> TopicIdea:
        now = self._now()
        created_at = idea.created_at or now
        updated_at = now
        conn = self.db.get_connection()
        conn.execute(
            """
            INSERT INTO topic_ideas (
                id, title, genre, world_preset, length_tier, logline, premise,
                protagonist_hook, core_conflict, opening_hook,
                selling_points_json, long_term_potential, risk_notes_json,
                market_tags_json, score, status, adopted_novel_id,
                source_brief_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                genre = excluded.genre,
                world_preset = excluded.world_preset,
                length_tier = excluded.length_tier,
                logline = excluded.logline,
                premise = excluded.premise,
                protagonist_hook = excluded.protagonist_hook,
                core_conflict = excluded.core_conflict,
                opening_hook = excluded.opening_hook,
                selling_points_json = excluded.selling_points_json,
                long_term_potential = excluded.long_term_potential,
                risk_notes_json = excluded.risk_notes_json,
                market_tags_json = excluded.market_tags_json,
                score = excluded.score,
                status = excluded.status,
                adopted_novel_id = excluded.adopted_novel_id,
                source_brief_json = excluded.source_brief_json,
                updated_at = excluded.updated_at
            """,
            (
                idea.id,
                idea.title,
                idea.genre,
                idea.world_preset,
                idea.length_tier,
                idea.logline,
                idea.premise,
                idea.protagonist_hook,
                idea.core_conflict,
                idea.opening_hook,
                _json_dump(idea.selling_points, []),
                idea.long_term_potential,
                _json_dump(idea.risk_notes, []),
                _json_dump(idea.market_tags, []),
                idea.score,
                idea.status,
                idea.adopted_novel_id,
                _json_dump(idea.source_brief, {}),
                created_at,
                updated_at,
            ),
        )
        conn.commit()
        return self.get_by_id(idea.id) or idea

    def get_by_id(self, topic_id: str) -> Optional[TopicIdea]:
        row = self.db.fetch_one("SELECT * FROM topic_ideas WHERE id = ?", (topic_id,))
        return self._row_to_idea(row) if row else None

    def list(self, status: Optional[str] = None) -> List[TopicIdea]:
        normalized = TopicIdeaStatus.normalize(status) if status else None
        if normalized:
            rows = self.db.fetch_all(
                "SELECT * FROM topic_ideas WHERE status = ? ORDER BY created_at DESC",
                (normalized,),
            )
        else:
            rows = self.db.fetch_all(
                "SELECT * FROM topic_ideas ORDER BY created_at DESC",
                (),
            )
        return [self._row_to_idea(r) for r in rows]

    def update_status(
        self,
        topic_id: str,
        status: str,
        adopted_novel_id: Optional[str] = None,
    ) -> TopicIdea:
        normalized = TopicIdeaStatus.normalize(status)
        now = self._now()
        conn = self.db.get_connection()
        conn.execute(
            """
            UPDATE topic_ideas
            SET status = ?, adopted_novel_id = COALESCE(?, adopted_novel_id), updated_at = ?
            WHERE id = ?
            """,
            (normalized, adopted_novel_id, now, topic_id),
        )
        conn.commit()
        idea = self.get_by_id(topic_id)
        if idea is None:
            raise ValueError(f"Topic idea not found: {topic_id}")
        return idea

    def _row_to_idea(self, row: Dict[str, Any]) -> TopicIdea:
        return TopicIdea(
            id=row["id"],
            title=row["title"],
            genre=row.get("genre", ""),
            world_preset=row.get("world_preset", ""),
            length_tier=row.get("length_tier", "standard"),
            logline=row.get("logline", ""),
            premise=row.get("premise", ""),
            protagonist_hook=row.get("protagonist_hook", ""),
            core_conflict=row.get("core_conflict", ""),
            opening_hook=row.get("opening_hook", ""),
            selling_points=_json_load(row.get("selling_points_json", ""), []),
            long_term_potential=row.get("long_term_potential", ""),
            risk_notes=_json_load(row.get("risk_notes_json", ""), []),
            market_tags=_json_load(row.get("market_tags_json", ""), []),
            score=row.get("score", 0),
            status=row.get("status", TopicIdeaStatus.DRAFT),
            adopted_novel_id=row.get("adopted_novel_id"),
            source_brief=_json_load(row.get("source_brief_json", ""), {}),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )
```

- [ ] **Step 5: Run repository tests**

Run:

```bash
pytest tests/unit/infrastructure/database/test_sqlite_topic_idea_repository.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add infrastructure/persistence/database/schema.sql infrastructure/persistence/database/sqlite_topic_idea_repository.py tests/unit/infrastructure/database/test_sqlite_topic_idea_repository.py
git commit -m "feat: persist topic ideas"
```

Only stage the files listed above.

### Task 3: Application Service

**Files:**
- Create: `application/topic/services/__init__.py`
- Create: `application/topic/services/topic_idea_service.py`
- Test: `tests/unit/application/services/test_topic_idea_service.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/unit/application/services/test_topic_idea_service.py`:

```python
import json
from unittest.mock import Mock

import pytest

from application.core.dtos.novel_dto import NovelDTO
from application.topic.dtos import TopicGenerateRequestDTO
from application.topic.services.topic_idea_service import TopicIdeaService
from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage
from domain.topic.entities import TopicIdea, TopicIdeaStatus


class MemoryTopicRepo:
    def __init__(self):
        self.items = {}

    def save(self, idea):
        self.items[idea.id] = idea
        return idea

    def get_by_id(self, topic_id):
        return self.items.get(topic_id)

    def list(self, status=None):
        ideas = list(self.items.values())
        if status:
            ideas = [i for i in ideas if i.status == status]
        return ideas

    def update_status(self, topic_id, status, adopted_novel_id=None):
        idea = self.items[topic_id]
        idea.status = status
        if adopted_novel_id:
            idea.adopted_novel_id = adopted_novel_id
        self.items[topic_id] = idea
        return idea


class FakeLLM:
    def __init__(self, content):
        self.content = content

    async def generate(self, prompt, config):
        return GenerationResult(
            self.content,
            TokenUsage(input_tokens=1, output_tokens=1),
        )


@pytest.mark.asyncio
async def test_generate_saves_model_topic_ideas():
    payload = {
        "topic_ideas": [
            {
                "title": "青铜旧神",
                "genre": "玄幻升级",
                "world_preset": "修仙风",
                "length_tier": "standard",
                "logline": "少年读懂神像裂纹。",
                "premise": "少年发现宗门祖师是旧神伪装。",
                "protagonist_hook": "不能修炼，但能读懂裂纹。",
                "core_conflict": "少年 vs 旧神宗门",
                "opening_hook": "祖师像夜里流血。",
                "selling_points": ["升级爽"],
                "long_term_potential": "旧神体系逐卷展开。",
                "risk_notes": ["设定别空泛"],
                "market_tags": ["玄幻"],
                "score": 88,
            }
        ]
    }
    repo = MemoryTopicRepo()
    service = TopicIdeaService(repo, FakeLLM(json.dumps(payload, ensure_ascii=False)), Mock())

    result = await service.generate(
        TopicGenerateRequestDTO(genre="玄幻升级", world_preset="修仙风", count=1)
    )

    assert len(result) == 1
    assert result[0].title == "青铜旧神"
    assert len(repo.items) == 1


@pytest.mark.asyncio
async def test_generate_uses_fallback_when_model_json_is_invalid():
    repo = MemoryTopicRepo()
    service = TopicIdeaService(repo, FakeLLM("not json"), Mock())

    result = await service.generate(TopicGenerateRequestDTO(genre="都市爽文", count=3))

    assert len(result) == 3
    assert all(item.title for item in result)
    assert len(repo.items) == 3


def test_adopt_is_idempotent_when_topic_already_adopted():
    repo = MemoryTopicRepo()
    repo.save(
        TopicIdea(
            id="topic-1",
            title="青铜旧神",
            premise="少年发现宗门祖师是旧神伪装。",
            status=TopicIdeaStatus.ADOPTED,
            adopted_novel_id="novel-existing",
        )
    )
    novel_service = Mock()
    novel_service.get_novel.return_value = NovelDTO(
        id="novel-existing",
        title="青铜旧神",
        author="作者",
        target_chapters=400,
        stage="planning",
        premise="",
        chapters=[],
        total_word_count=0,
    )
    service = TopicIdeaService(repo, None, novel_service)

    result = service.adopt("topic-1")

    assert result.id == "novel-existing"
    novel_service.create_novel.assert_not_called()


def test_adopt_creates_novel_and_marks_topic_adopted():
    repo = MemoryTopicRepo()
    repo.save(
        TopicIdea(
            id="topic-2",
            title="霓虹斩妖人",
            genre="科幻赛博",
            world_preset="赛博朋克风",
            length_tier="short",
            premise="义体医生卷入巨企养妖阴谋。",
        )
    )
    novel_service = Mock()
    novel_service.create_novel.return_value = NovelDTO(
        id="novel-topic-2",
        title="霓虹斩妖人",
        author="作者",
        target_chapters=150,
        stage="planning",
        premise="义体医生卷入巨企养妖阴谋。",
        chapters=[],
        total_word_count=0,
    )
    service = TopicIdeaService(repo, None, novel_service)

    result = service.adopt("topic-2")

    assert result.id == "novel-topic-2"
    assert repo.get_by_id("topic-2").status == TopicIdeaStatus.ADOPTED
    assert repo.get_by_id("topic-2").adopted_novel_id == "novel-topic-2"
```

- [ ] **Step 2: Run service tests to verify they fail**

Run:

```bash
pytest tests/unit/application/services/test_topic_idea_service.py -q
```

Expected: FAIL during import with `ModuleNotFoundError` for `application.topic.services.topic_idea_service`.

- [ ] **Step 3: Implement application service**

Create `application/topic/services/__init__.py`:

```python
"""Topic idea application services."""
```

Create `application/topic/services/topic_idea_service.py`:

```python
"""Topic idea incubation service."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from application.ai.knowledge_llm_contract import parse_json_from_response
from application.core.dtos.novel_dto import NovelDTO
from application.core.services.novel_service import NovelService
from application.topic.dtos import TopicGenerateRequestDTO, TopicIdeaDTO
from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt
from domain.topic.entities import TopicIdea, TopicIdeaStatus
from domain.topic.repositories import TopicIdeaRepository

logger = logging.getLogger(__name__)


class TopicIdeaService:
    def __init__(
        self,
        repository: TopicIdeaRepository,
        llm_service: Optional[LLMService],
        novel_service: NovelService,
    ):
        self.repository = repository
        self.llm_service = llm_service
        self.novel_service = novel_service

    async def generate(self, request: TopicGenerateRequestDTO) -> List[TopicIdeaDTO]:
        raw_items = await self._generate_raw_items(request)
        ideas = self._normalize_items(raw_items, request)
        saved = [self.repository.save(idea) for idea in ideas]
        return [TopicIdeaDTO.from_domain(i) for i in saved]

    def list(self, status: Optional[str] = None) -> List[TopicIdeaDTO]:
        normalized = TopicIdeaStatus.normalize(status) if status else None
        return [TopicIdeaDTO.from_domain(i) for i in self.repository.list(normalized)]

    def get(self, topic_id: str) -> TopicIdeaDTO:
        idea = self.repository.get_by_id(topic_id)
        if idea is None:
            raise ValueError(f"Topic idea not found: {topic_id}")
        return TopicIdeaDTO.from_domain(idea)

    def update_status(self, topic_id: str, status: str) -> TopicIdeaDTO:
        updated = self.repository.update_status(topic_id, TopicIdeaStatus.normalize(status))
        return TopicIdeaDTO.from_domain(updated)

    def adopt(self, topic_id: str) -> NovelDTO:
        idea = self.repository.get_by_id(topic_id)
        if idea is None:
            raise ValueError(f"Topic idea not found: {topic_id}")
        if idea.status == TopicIdeaStatus.ADOPTED and idea.adopted_novel_id:
            existing = self.novel_service.get_novel(idea.adopted_novel_id)
            if existing is not None:
                return existing

        novel_id = f"novel-{uuid.uuid4().hex[:12]}"
        novel = self.novel_service.create_novel(
            novel_id=novel_id,
            title=idea.title or idea.logline[:20] or "未命名选题",
            author="作者",
            target_chapters=0,
            premise=idea.premise or idea.logline,
            genre=idea.genre,
            world_preset=idea.world_preset,
            length_tier=idea.length_tier,
        )
        self.repository.update_status(topic_id, TopicIdeaStatus.ADOPTED, novel.id)
        return novel

    async def _generate_raw_items(self, request: TopicGenerateRequestDTO) -> List[Dict[str, Any]]:
        if self.llm_service is None:
            return self._fallback_items(request)
        prompt = self._build_prompt(request)
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=4096, temperature=0.88),
            )
            data = parse_json_from_response(result.content)
            items = data.get("topic_ideas", [])
            if isinstance(items, list) and items:
                return [i for i in items if isinstance(i, dict)]
        except Exception as e:
            logger.warning("topic idea generation failed, using fallback: %s", e)
        return self._fallback_items(request)

    def _normalize_items(
        self,
        items: List[Dict[str, Any]],
        request: TopicGenerateRequestDTO,
    ) -> List[TopicIdea]:
        out: List[TopicIdea] = []
        for item in items[: request.normalized_count()]:
            title = str(item.get("title") or "").strip()
            logline = str(item.get("logline") or "").strip()
            premise = str(item.get("premise") or "").strip()
            if not title and not logline:
                continue
            out.append(
                TopicIdea(
                    id=f"topic-{uuid.uuid4().hex[:12]}",
                    title=title or logline[:20],
                    genre=item.get("genre") or request.genre,
                    world_preset=item.get("world_preset") or request.world_preset,
                    length_tier=item.get("length_tier") or request.length_tier,
                    logline=logline,
                    premise=premise or logline,
                    protagonist_hook=item.get("protagonist_hook", ""),
                    core_conflict=item.get("core_conflict", ""),
                    opening_hook=item.get("opening_hook", ""),
                    selling_points=item.get("selling_points", []),
                    long_term_potential=item.get("long_term_potential", ""),
                    risk_notes=item.get("risk_notes", []),
                    market_tags=item.get("market_tags", []),
                    score=item.get("score", 0),
                    source_brief=request.to_source_brief(),
                )
            )
        if len(out) < request.normalized_count():
            needed = request.normalized_count() - len(out)
            out.extend(self._normalize_items(self._fallback_items(request)[:needed], request))
        return out[: request.normalized_count()]

    def _build_prompt(self, request: TopicGenerateRequestDTO) -> Prompt:
        system = """你是华语网络小说商业立项编辑。你要帮助作者在正式开书前生成可比较的选题方案。
必须输出合法 JSON，不要解释，不要 Markdown。每个选题都要具体、可开篇、可长线连载。"""
        user = f"""请基于以下输入生成 {request.normalized_count()} 个选题候选：
{json.dumps(request.to_source_brief(), ensure_ascii=False, indent=2)}

输出格式：
{{
  "topic_ideas": [
    {{
      "title": "书名候选",
      "genre": "赛道",
      "world_preset": "世界观基调",
      "length_tier": "short|standard|epic",
      "logline": "一句话卖点",
      "premise": "300-800字，可直接用于建档",
      "protagonist_hook": "主角钩子",
      "core_conflict": "核心冲突",
      "opening_hook": "开篇事件",
      "selling_points": ["商业看点"],
      "long_term_potential": "长线升级空间",
      "risk_notes": ["风险提示"],
      "market_tags": ["市场标签"],
      "score": 85
    }}
  ]
}}"""
        return Prompt(system=system, user=user)

    def _fallback_items(self, request: TopicGenerateRequestDTO) -> List[Dict[str, Any]]:
        genre = request.genre or "长篇小说"
        world = request.world_preset or "自定义世界观"
        return [
            {
                "title": "裂隙中的第一盏灯",
                "genre": genre,
                "world_preset": world,
                "length_tier": request.length_tier,
                "logline": "被边缘化的主角在一次失败任务中发现世界规则的裂缝。",
                "premise": "主角原本只是体系边缘的小人物，却在一次看似普通的失败任务里，发现权力核心一直隐瞒的规则漏洞。为了活下去，也为了夺回被剥夺的选择权，主角开始利用这道裂缝反向成长，逐步把个人求生推进成对旧秩序的挑战。",
                "protagonist_hook": "资源匮乏，但能看见别人忽略的规则漏洞。",
                "core_conflict": "底层求生者 vs 维持黑箱秩序的既得利益者。",
                "opening_hook": "一次失败任务带回的不是奖励，而是追杀名单。",
                "selling_points": ["底层逆袭", "规则破解", "强钩子开篇"],
                "long_term_potential": "从小范围求生扩展到组织、城市、世界规则的层层揭露。",
                "risk_notes": ["规则漏洞需要尽早具象化，避免空泛"],
                "market_tags": [genre, "逆袭", "悬念"],
                "score": 78,
            },
            {
                "title": "旧账簿上的新名字",
                "genre": genre,
                "world_preset": world,
                "length_tier": request.length_tier,
                "logline": "主角发现自己的名字出现在一份早已封存的死亡名单上。",
                "premise": "主角偶然得到一份旧账簿，里面记录着一批本该已经死亡的人，而自己的名字赫然在列。随着调查深入，主角发现这不是身份错误，而是一场跨越多年、仍在运转的筛选机制。为了确认自己为何被选中，主角必须主动踏进名单背后的权力网络。",
                "protagonist_hook": "身份被系统性抹除，却保留着唯一能反查真相的记忆细节。",
                "core_conflict": "追索真相的主角 vs 依靠名单维持秩序的隐秘组织。",
                "opening_hook": "主角参加葬礼，却在死者遗物里看见自己的死亡编号。",
                "selling_points": ["身份谜团", "阴谋推进", "强反转"],
                "long_term_potential": "名单机制可以逐卷揭露，每一卷打开一层更大的筛选逻辑。",
                "risk_notes": ["悬疑线索要及时兑现，避免只堆谜面"],
                "market_tags": [genre, "阴谋", "身份反转"],
                "score": 82,
            },
            {
                "title": "异常者的低语",
                "genre": genre,
                "world_preset": world,
                "length_tier": request.length_tier,
                "logline": "主角觉醒的能力不是变强，而是听见规则本身在撒谎。",
                "premise": "主角在濒死后获得一种无法被现有体系解释的异常感知：他能听见规则、契约、仪式或数据背后的低语。起初这只帮助他避开死亡，随后却让他意识到整个世界都建立在一套被篡改的解释之上。当各方势力开始争夺或清除他，主角必须决定是隐藏异常，还是利用异常改写规则。",
                "protagonist_hook": "不是战力最强，而是唯一能识破规则谎言的人。",
                "core_conflict": "异常认知者 vs 害怕规则被揭穿的旧体系。",
                "opening_hook": "所有人都说仪式成功，只有主角听见规则说了一句：假的。",
                "selling_points": ["异类觉醒", "规则反转", "世界观悬念"],
                "long_term_potential": "异常能力可逐步升级为解释、篡改、重写规则。",
                "risk_notes": ["能力边界必须清晰，否则容易失控"],
                "market_tags": [genre, "异常", "规则流"],
                "score": 80,
            },
        ]
```

- [ ] **Step 4: Run service tests**

Run:

```bash
pytest tests/unit/application/services/test_topic_idea_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add application/topic tests/unit/application/services/test_topic_idea_service.py
git commit -m "feat: add topic idea service"
```

Only stage the files listed above.

### Task 4: FastAPI Routes And Dependency Wiring

**Files:**
- Modify: `interfaces/api/dependencies.py`
- Create: `interfaces/api/v1/topic/__init__.py`
- Create: `interfaces/api/v1/topic/topic_ideas.py`
- Modify: `interfaces/main.py`
- Test: `tests/unit/interfaces/api/test_topic_ideas.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/unit/interfaces/api/test_topic_ideas.py`:

```python
from fastapi.testclient import TestClient

from application.core.dtos.novel_dto import NovelDTO
from application.topic.dtos import TopicIdeaDTO
from domain.topic.entities import TopicIdea
from interfaces.api.v1.topic.topic_ideas import get_topic_idea_service, router
from fastapi import FastAPI


class FakeTopicService:
    def __init__(self):
        self.idea = TopicIdeaDTO.from_domain(
            TopicIdea(
                id="topic-1",
                title="青铜旧神",
                genre="玄幻升级",
                world_preset="修仙风",
                length_tier="standard",
                logline="少年读懂神像裂纹。",
                premise="少年发现宗门祖师是旧神伪装。",
            )
        )

    async def generate(self, request):
        return [self.idea]

    def list(self, status=None):
        return [self.idea]

    def get(self, topic_id):
        return self.idea

    def update_status(self, topic_id, status):
        self.idea.status = status
        return self.idea

    def adopt(self, topic_id):
        return NovelDTO(
            id="novel-1",
            title="青铜旧神",
            author="作者",
            target_chapters=400,
            stage="planning",
            premise="少年发现宗门祖师是旧神伪装。",
            chapters=[],
            total_word_count=0,
        )


def make_client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_topic_idea_service] = lambda: FakeTopicService()
    return TestClient(app)


def test_generate_topics_endpoint():
    client = make_client()
    res = client.post("/api/v1/topics/generate", json={"genre": "玄幻升级", "count": 1})

    assert res.status_code == 200
    assert res.json()[0]["id"] == "topic-1"


def test_archive_topic_endpoint():
    client = make_client()
    res = client.patch("/api/v1/topics/topic-1", json={"status": "archived"})

    assert res.status_code == 200
    assert res.json()["status"] == "archived"


def test_adopt_topic_endpoint():
    client = make_client()
    res = client.post("/api/v1/topics/topic-1/adopt")

    assert res.status_code == 200
    assert res.json()["id"] == "novel-1"
```

- [ ] **Step 2: Run API tests to verify they fail**

Run:

```bash
pytest tests/unit/interfaces/api/test_topic_ideas.py -q
```

Expected: FAIL during import with `ModuleNotFoundError` for `interfaces.api.v1.topic`.

- [ ] **Step 3: Add dependency providers**

Modify `interfaces/api/dependencies.py` by adding imports where local imports are preferred and functions near other service getters:

```python
def get_topic_idea_repository():
    from infrastructure.persistence.database.sqlite_topic_idea_repository import (
        SqliteTopicIdeaRepository,
    )

    return SqliteTopicIdeaRepository(get_database())


def get_topic_idea_service():
    from application.topic.services.topic_idea_service import TopicIdeaService

    return TopicIdeaService(
        repository=get_topic_idea_repository(),
        llm_service=get_llm_service(),
        novel_service=get_novel_service(),
    )
```

- [ ] **Step 4: Implement topic router**

Create `interfaces/api/v1/topic/__init__.py`:

```python
"""Topic idea API package."""
```

Create `interfaces/api/v1/topic/topic_ideas.py`:

```python
"""Topic idea incubation API."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from application.core.dtos.novel_dto import NovelDTO
from application.topic.dtos import TopicGenerateRequestDTO, TopicIdeaDTO
from interfaces.api.dependencies import get_topic_idea_service

router = APIRouter(prefix="/topics", tags=["topics"])


class TopicGenerateRequest(BaseModel):
    genre: str = ""
    world_preset: str = ""
    keywords: List[str] = Field(default_factory=list)
    desired_selling_points: List[str] = Field(default_factory=list)
    avoid_patterns: List[str] = Field(default_factory=list)
    length_tier: str = "standard"
    count: int = Field(3, ge=1, le=5)

    def to_dto(self) -> TopicGenerateRequestDTO:
        return TopicGenerateRequestDTO(
            genre=self.genre,
            world_preset=self.world_preset,
            keywords=self.keywords,
            desired_selling_points=self.desired_selling_points,
            avoid_patterns=self.avoid_patterns,
            length_tier=self.length_tier,
            count=self.count,
        )


class TopicUpdateRequest(BaseModel):
    status: str


@router.post("/generate", response_model=List[TopicIdeaDTO])
async def generate_topic_ideas(
    request: TopicGenerateRequest,
    service=Depends(get_topic_idea_service),
):
    return await service.generate(request.to_dto())


@router.get("/", response_model=List[TopicIdeaDTO])
def list_topic_ideas(
    status: Optional[str] = Query(None),
    service=Depends(get_topic_idea_service),
):
    return service.list(status=status)


@router.get("/{topic_id}", response_model=TopicIdeaDTO)
def get_topic_idea(topic_id: str, service=Depends(get_topic_idea_service)):
    try:
        return service.get(topic_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{topic_id}", response_model=TopicIdeaDTO)
def update_topic_idea(
    topic_id: str,
    request: TopicUpdateRequest,
    service=Depends(get_topic_idea_service),
):
    try:
        return service.update_status(topic_id, request.status)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{topic_id}/adopt", response_model=NovelDTO)
def adopt_topic_idea(topic_id: str, service=Depends(get_topic_idea_service)):
    try:
        return service.adopt(topic_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

- [ ] **Step 5: Register router in main app**

Modify `interfaces/main.py` imports near existing API v1 imports:

```python
from interfaces.api.v1.topic import topic_ideas
```

Add router registration near the workbench or core module routes:

```python
app.include_router(topic_ideas.router, prefix="/api/v1")
```

- [ ] **Step 6: Run API tests and compile relevant Python files**

Run:

```bash
pytest tests/unit/interfaces/api/test_topic_ideas.py -q
python3 -m compileall -q domain/topic application/topic infrastructure/persistence/database/sqlite_topic_idea_repository.py interfaces/api/v1/topic interfaces/main.py interfaces/api/dependencies.py
```

Expected: pytest PASS and compileall exits with code 0.

- [ ] **Step 7: Commit Task 4**

```bash
git add interfaces/api/dependencies.py interfaces/api/v1/topic interfaces/main.py tests/unit/interfaces/api/test_topic_ideas.py
git commit -m "feat: expose topic idea API"
```

Only stage the files listed above.

### Task 5: Frontend API And Topic Panel

**Files:**
- Create: `frontend/src/api/topic.ts`
- Create: `frontend/src/components/topic/TopicIdeaPanel.vue`
- Modify: `frontend/src/views/Home.vue`

- [ ] **Step 1: Add typed topic API client**

Create `frontend/src/api/topic.ts`:

```ts
import { apiClient } from './config'
import type { NovelDTO } from './novel'

export interface TopicIdea {
  id: string
  title: string
  genre: string
  world_preset: string
  length_tier: string
  logline: string
  premise: string
  protagonist_hook: string
  core_conflict: string
  opening_hook: string
  selling_points: string[]
  long_term_potential: string
  risk_notes: string[]
  market_tags: string[]
  score: number
  status: 'draft' | 'adopted' | 'archived'
  adopted_novel_id?: string | null
  source_brief: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface TopicGeneratePayload {
  genre?: string
  world_preset?: string
  keywords?: string[]
  desired_selling_points?: string[]
  avoid_patterns?: string[]
  length_tier?: 'short' | 'standard' | 'epic'
  count?: number
}

export const topicApi = {
  generate: (data: TopicGeneratePayload) =>
    apiClient.post<TopicIdea[]>('/topics/generate', data, { timeout: 300000 }) as Promise<TopicIdea[]>,
  list: (status?: TopicIdea['status']) =>
    apiClient.get<TopicIdea[]>('/topics', { params: status ? { status } : undefined }) as Promise<TopicIdea[]>,
  updateStatus: (topicId: string, status: TopicIdea['status']) =>
    apiClient.patch<TopicIdea>(`/topics/${topicId}`, { status }) as Promise<TopicIdea>,
  adopt: (topicId: string) =>
    apiClient.post<NovelDTO>(`/topics/${topicId}/adopt`) as Promise<NovelDTO>,
}
```

- [ ] **Step 2: Create topic panel component**

Create `frontend/src/components/topic/TopicIdeaPanel.vue` with this component structure:

```vue
<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="选题立项池"
    :style="{ width: '94vw', maxWidth: '1120px', height: '82vh' }"
    :bordered="true"
    :segmented="{ content: true }"
  >
    <div class="topic-panel">
      <section class="topic-form">
        <n-form label-placement="top">
          <n-grid :cols="2" :x-gap="12" :y-gap="8" responsive="screen">
            <n-gi>
              <n-form-item label="赛道 / 类型">
                <n-select v-model:value="form.genre" :options="genreOptions" placeholder="选择赛道" />
              </n-form-item>
            </n-gi>
            <n-gi>
              <n-form-item label="世界观基调">
                <n-select v-model:value="form.world_preset" :options="worldPresetOptions" placeholder="选择基调" />
              </n-form-item>
            </n-gi>
          </n-grid>
          <n-form-item label="关键词">
            <n-dynamic-tags v-model:value="form.keywords" />
          </n-form-item>
          <n-form-item label="目标爽点">
            <n-dynamic-tags v-model:value="form.desired_selling_points" />
          </n-form-item>
          <n-form-item label="避雷套路">
            <n-dynamic-tags v-model:value="form.avoid_patterns" />
          </n-form-item>
          <n-form-item label="目标篇幅">
            <n-radio-group v-model:value="form.length_tier">
              <n-space>
                <n-radio value="short">短篇</n-radio>
                <n-radio value="standard">标准</n-radio>
                <n-radio value="epic">史诗</n-radio>
              </n-space>
            </n-radio-group>
          </n-form-item>
          <n-space justify="end">
            <n-button secondary @click="loadTopics">刷新</n-button>
            <n-button type="primary" :loading="generating" @click="handleGenerate">生成选题</n-button>
          </n-space>
        </n-form>
      </section>

      <section class="topic-list">
        <n-tabs v-model:value="activeStatus" type="segment" @update:value="loadTopics">
          <n-tab-pane name="draft" tab="草稿" />
          <n-tab-pane name="archived" tab="归档" />
          <n-tab-pane name="adopted" tab="已采用" />
        </n-tabs>
        <n-spin :show="loading">
          <n-empty v-if="topics.length === 0" description="暂无选题" />
          <div v-else class="topic-cards">
            <n-card v-for="idea in topics" :key="idea.id" size="small" class="topic-card">
              <template #header>
                <div class="topic-card-header">
                  <span>{{ idea.title }}</span>
                  <n-tag size="small" type="info">{{ idea.score }} 分</n-tag>
                </div>
              </template>
              <n-space vertical :size="8">
                <div class="topic-meta">
                  <n-tag size="small">{{ idea.genre || '未分类' }}</n-tag>
                  <n-tag size="small">{{ idea.world_preset || '未设定' }}</n-tag>
                  <n-tag size="small">{{ lengthLabel(idea.length_tier) }}</n-tag>
                </div>
                <p class="topic-logline">{{ idea.logline }}</p>
                <div v-if="idea.core_conflict" class="topic-line"><strong>冲突：</strong>{{ idea.core_conflict }}</div>
                <div v-if="idea.protagonist_hook" class="topic-line"><strong>主角：</strong>{{ idea.protagonist_hook }}</div>
                <div v-if="idea.opening_hook" class="topic-line"><strong>开篇：</strong>{{ idea.opening_hook }}</div>
                <div v-if="idea.selling_points.length" class="tag-row">
                  <n-tag v-for="point in idea.selling_points" :key="point" size="small" type="success">{{ point }}</n-tag>
                </div>
                <div v-if="idea.risk_notes.length" class="risk-list">
                  <div v-for="risk in idea.risk_notes" :key="risk">风险：{{ risk }}</div>
                </div>
                <n-space justify="end">
                  <n-button v-if="idea.status === 'draft'" size="small" secondary @click="setStatus(idea, 'archived')">归档</n-button>
                  <n-button v-if="idea.status === 'archived'" size="small" secondary @click="setStatus(idea, 'draft')">恢复</n-button>
                  <n-button
                    v-if="idea.status !== 'adopted'"
                    size="small"
                    type="primary"
                    :loading="adoptingId === idea.id"
                    @click="adoptTopic(idea)"
                  >
                    采用为新书
                  </n-button>
                </n-space>
              </n-space>
            </n-card>
          </div>
        </n-spin>
      </section>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { topicApi, type TopicIdea } from '@/api/topic'
import type { NovelDTO } from '@/api/novel'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'adopted', novel: NovelDTO): void
}>()

const message = useMessage()
const visible = computed({
  get: () => props.show,
  set: (value: boolean) => emit('update:show', value),
})

const form = reactive({
  genre: '',
  world_preset: '',
  keywords: [] as string[],
  desired_selling_points: [] as string[],
  avoid_patterns: [] as string[],
  length_tier: 'standard' as 'short' | 'standard' | 'epic',
})

const activeStatus = ref<TopicIdea['status']>('draft')
const topics = ref<TopicIdea[]>([])
const loading = ref(false)
const generating = ref(false)
const adoptingId = ref<string | null>(null)

const genreOptions = [
  { label: '玄幻升级', value: '玄幻升级' },
  { label: '都市爽文', value: '都市爽文' },
  { label: '仙侠修真', value: '仙侠修真' },
  { label: '科幻赛博', value: '科幻赛博' },
  { label: '悬疑推理', value: '悬疑推理' },
  { label: '历史架空', value: '历史架空' },
  { label: '游戏异界', value: '游戏异界' },
  { label: '言情甜宠', value: '言情甜宠' },
]

const worldPresetOptions = [
  { label: '修仙风', value: '修仙风' },
  { label: '赛博朋克风', value: '赛博朋克风' },
  { label: '悬疑风', value: '悬疑风' },
  { label: '高武江湖', value: '高武江湖' },
  { label: '末日废土', value: '末日废土' },
  { label: '西幻史诗', value: '西幻史诗' },
  { label: '现代都市', value: '现代都市' },
  { label: '克系诡异', value: '克系诡异' },
]

function lengthLabel(value: string) {
  if (value === 'short') return '短篇'
  if (value === 'epic') return '史诗'
  return '标准'
}

async function loadTopics() {
  loading.value = true
  try {
    topics.value = await topicApi.list(activeStatus.value)
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '选题加载失败')
  } finally {
    loading.value = false
  }
}

async function handleGenerate() {
  generating.value = true
  try {
    topics.value = await topicApi.generate({ ...form, count: 3 })
    activeStatus.value = 'draft'
    message.success('选题已生成')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '选题生成失败')
  } finally {
    generating.value = false
  }
}

async function setStatus(idea: TopicIdea, status: TopicIdea['status']) {
  try {
    await topicApi.updateStatus(idea.id, status)
    topics.value = topics.value.filter((item) => item.id !== idea.id)
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '状态更新失败')
  }
}

async function adoptTopic(idea: TopicIdea) {
  adoptingId.value = idea.id
  try {
    const novel = await topicApi.adopt(idea.id)
    message.success('已采用为新书')
    emit('adopted', novel)
    visible.value = false
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '采用失败')
  } finally {
    adoptingId.value = null
  }
}

watch(
  () => props.show,
  (open) => {
    if (open) void loadTopics()
  },
)
</script>

<style scoped>
.topic-panel {
  display: grid;
  grid-template-columns: minmax(280px, 360px) 1fr;
  gap: 18px;
  height: calc(82vh - 92px);
  min-height: 0;
}
.topic-form,
.topic-list {
  min-height: 0;
  overflow: auto;
}
.topic-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  padding-top: 12px;
}
.topic-card {
  border-radius: 8px;
}
.topic-card-header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}
.topic-meta,
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.topic-logline,
.topic-line,
.risk-list {
  margin: 0;
  color: var(--app-text-secondary);
  font-size: 13px;
  line-height: 1.55;
}
.risk-list {
  color: #a16207;
}
@media (max-width: 860px) {
  .topic-panel {
    grid-template-columns: 1fr;
    height: auto;
    max-height: calc(82vh - 92px);
  }
}
</style>
```

- [ ] **Step 3: Integrate panel into Home**

Modify `frontend/src/views/Home.vue`:

Add import:

```ts
import TopicIdeaPanel from '@/components/topic/TopicIdeaPanel.vue'
```

Add state near modal state:

```ts
const showTopicPanel = ref(false)
```

Add button in the create-card action area before the primary create button:

```vue
<n-button size="large" secondary round @click="showTopicPanel = true">
  选题立项池
</n-button>
```

Add modal near existing `NovelSetupGuide`:

```vue
<TopicIdeaPanel
  v-model:show="showTopicPanel"
  @adopted="handleTopicAdopted"
/>
```

Add handler in script:

```ts
const handleTopicAdopted = (novel: NovelDTO) => {
  setupWizard.value = {
    novelId: novel.id,
    targetChapters: novel.target_chapters,
  }
  fetchBooks()
}
```

- [ ] **Step 4: Run frontend checks**

Run:

```bash
cd frontend && npm run build
```

Expected: `npm run build` exits with code 0. The build script runs `vue-tsc -b` before `vite build`, so this covers TypeScript and production bundling.

- [ ] **Step 5: Commit Task 5**

```bash
git add frontend/src/api/topic.ts frontend/src/components/topic/TopicIdeaPanel.vue frontend/src/views/Home.vue
git commit -m "feat: add topic idea panel"
```

Only stage the files listed above.

### Task 6: End-To-End Verification And Memory Update

**Files:**
- Modify: `agent_memory/progress.md`
- Optional inspect only: `agent_memory/bugs.md`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest tests/unit/domain/topic/test_topic_idea.py tests/unit/infrastructure/database/test_sqlite_topic_idea_repository.py tests/unit/application/services/test_topic_idea_service.py tests/unit/interfaces/api/test_topic_ideas.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 2: Run compile check**

Run:

```bash
python3 -m compileall -q domain/topic application/topic infrastructure/persistence/database/sqlite_topic_idea_repository.py interfaces/api/v1/topic interfaces/main.py interfaces/api/dependencies.py
```

Expected: command exits with code 0.

- [ ] **Step 3: Run frontend build verification**

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript check and production bundling PASS.

- [ ] **Step 4: Start local backend and frontend for manual smoke check**

Run backend:

```bash
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005
```

Run frontend in a second terminal:

```bash
cd frontend && npm run dev
```

Open `http://localhost:3000`, click「选题立项池」, generate with fallback or configured LLM, archive one item, restore it from archived tab, adopt one topic, and confirm the existing new-book setup wizard opens.

- [ ] **Step 5: Update project progress memory**

Modify `agent_memory/progress.md` so the current status includes:

```markdown
## 已完成

- 已实现选题立项池一期：生成、保存、归档、恢复、采用为新书。
- 已接入首页弹窗与现有新书设置向导。

## 验证状态

- topic 后端单元测试通过。
- Python compileall 通过。
- 前端 build 通过（包含 vue-tsc 类型检查）。

## 下一步

- 选题二期可做「单条深化」：扩写完整立项案与前三章钩子。
```

- [ ] **Step 6: Commit verification memory update**

```bash
git add agent_memory/progress.md
git commit -m "docs: update topic idea progress"
```

Only stage `agent_memory/progress.md`.

## Self-Review

- Spec coverage: Task 1-2 cover independent topic data model and SQLite persistence; Task 3 covers LLM generation, fallback, list/status/adopt behavior; Task 4 covers API; Task 5 covers frontend entry and adopt-to-wizard bridge; Task 6 covers verification and memory update.
- Scope check: This plan implements only first-phase lightweight incubation. Deepening, evaluation, and comparison endpoints remain out of scope and are not exposed as inert UI buttons.
- Type consistency: Backend uses `TopicIdea`, `TopicIdeaDTO`, `TopicGenerateRequestDTO`, `TopicIdeaStatus`, and frontend mirrors response fields from `TopicIdeaDTO`.
- Existing dirty worktree caution: each commit step stages only listed files, so unrelated pre-existing changes stay untouched.
