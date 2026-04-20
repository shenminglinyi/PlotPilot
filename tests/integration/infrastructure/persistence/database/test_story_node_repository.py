"""StoryNodeRepository integration tests."""

import asyncio
import sqlite3
from pathlib import Path

import pytest

from domain.structure.story_node import NodeType, StoryNode
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository

SCHEMA_PATH = (
    Path(__file__).resolve().parents[5]
    / "infrastructure"
    / "persistence"
    / "database"
    / "schema.sql"
)


@pytest.fixture
def repo_db(tmp_path):
    db_path = tmp_path / "story-node-repo.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return StoryNodeRepository(str(db_path)), db_path


def test_delete_cascades_to_descendant_story_nodes(repo_db):
    repo, db_path = repo_db
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
        ("novel-1", "Novel 1", "novel-1", 10),
    )
    conn.commit()
    conn.close()

    repo.save_sync(
        StoryNode(
            id="volume-1",
            novel_id="novel-1",
            node_type=NodeType.VOLUME,
            number=1,
            title="Volume 1",
            order_index=0,
        )
    )
    repo.save_sync(
        StoryNode(
            id="act-1",
            novel_id="novel-1",
            parent_id="volume-1",
            node_type=NodeType.ACT,
            number=1,
            title="Act 1",
            order_index=0,
        )
    )

    deleted = asyncio.run(repo.delete("volume-1"))

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, parent_id, node_type FROM story_nodes ORDER BY id"
    ).fetchall()
    conn.close()

    assert deleted is True
    assert rows == []
