from pathlib import Path

import pytest

from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_chapter_candidate_draft_repository import (
    SqliteChapterCandidateDraftRepository,
)


SCHEMA_PATH = (
    Path(__file__).resolve().parents[5]
    / "infrastructure"
    / "persistence"
    / "database"
    / "schema.sql"
)


@pytest.fixture
def repository():
    db = DatabaseConnection(":memory:")
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    db.get_connection().executescript(schema_sql)
    db.get_connection().commit()
    db.execute(
        "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
        ("novel-candidate-1", "候选稿测试小说", "novel-candidate-1", 10),
    )
    db.get_connection().commit()
    return SqliteChapterCandidateDraftRepository(db)


def test_create_and_list_candidate_drafts(repository):
    repository.create(
        novel_id="novel-candidate-1",
        chapter_number=3,
        source="kimi",
        title="第3章候选稿",
        content="这是 Kimi 生成的候选正文。",
        rationale="更偏冷感表达",
        metadata={"temperature": 0.7},
    )

    drafts = repository.list_by_chapter("novel-candidate-1", 3)

    assert len(drafts) == 1
    assert drafts[0]["source"] == "kimi"
    assert drafts[0]["status"] == "draft"
    assert drafts[0]["content"] == "这是 Kimi 生成的候选正文。"


def test_list_candidate_drafts_can_filter_by_branch_name(repository):
    repository.create(
        novel_id="novel-candidate-1",
        chapter_number=3,
        source="kimi",
        title="主线稿",
        content="主线候选正文。",
        branch_name="main",
    )
    repository.create(
        novel_id="novel-candidate-1",
        chapter_number=3,
        source="kimi",
        title="分支稿",
        content="分支候选正文。",
        branch_name="branch-alt",
    )

    drafts = repository.list_by_chapter(
        "novel-candidate-1",
        3,
        branch_name="branch-alt",
    )

    assert len(drafts) == 1
    assert drafts[0]["branch_name"] == "branch-alt"
    assert drafts[0]["title"] == "分支稿"
