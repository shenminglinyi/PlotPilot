"""测试 SnapshotService 的引擎状态支持"""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from application.snapshot.services.snapshot_service import SnapshotService
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        # 创建临时数据库文件
        conn = sqlite3.connect(str(db_path))

        # 创建必要的表
        conn.executescript("""
            CREATE TABLE novels (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                slug TEXT NOT NULL
            );

            CREATE TABLE chapters (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                number INTEGER NOT NULL,
                title TEXT,
                status TEXT DEFAULT 'draft',
                word_count INTEGER DEFAULT 0
            );

            CREATE TABLE novel_snapshots (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                parent_snapshot_id TEXT,
                branch_name TEXT DEFAULT 'main',
                trigger_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                chapter_pointers TEXT DEFAULT '[]',
                bible_state TEXT DEFAULT '{}',
                foreshadow_state TEXT DEFAULT '{}',
                story_state TEXT DEFAULT '{}',
                character_masks TEXT DEFAULT '{}',
                emotion_ledger TEXT DEFAULT '{}',
                active_foreshadows TEXT DEFAULT '[]',
                outline TEXT DEFAULT '',
                recent_chapters_summary TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
        """)
        conn.close()

        # 使用 DatabaseConnection 包装器
        db = DatabaseConnection(str(db_path))
        yield db
        db.close()


def test_create_snapshot_with_engine_state(temp_db):
    """测试创建快照时可以传入引擎状态参数"""
    # 准备
    novel_id = "test-novel"
    temp_db.execute("INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
                    (novel_id, "测试小说", "test-novel"))
    temp_db.commit()

    chapter_repo = SqliteChapterRepository(temp_db)
    service = SnapshotService(temp_db, chapter_repo)

    # 测试数据
    story_state = {"current_act": 1, "current_chapter": 5}
    character_masks = {"char1": {"name": "张三", "role": "主角"}}
    emotion_ledger = {"tension": 0.8, "emotion": "hope"}
    active_foreshadows = ["f1", "f2"]
    outline = "第一章：开端"
    recent_summary = "最近五章的摘要..."

    # 执行
    snapshot_id = service.create_snapshot(
        novel_id=novel_id,
        trigger_type="MANUAL",
        name="测试快照",
        story_state=story_state,
        character_masks=character_masks,
        emotion_ledger=emotion_ledger,
        active_foreshadows=active_foreshadows,
        outline=outline,
        recent_summary=recent_summary,
    )

    # 验证
    assert snapshot_id is not None

    # 查询数据库验证数据存储
    cursor = temp_db.execute(
        "SELECT story_state, character_masks, emotion_ledger, active_foreshadows, outline, recent_chapters_summary "
        "FROM novel_snapshots WHERE id = ?",
        (snapshot_id,)
    )
    row = cursor.fetchone()
    assert row is not None

    import json
    assert json.loads(row[0]) == story_state
    assert json.loads(row[1]) == character_masks
    assert json.loads(row[2]) == emotion_ledger
    assert json.loads(row[3]) == active_foreshadows
    assert row[4] == outline
    assert row[5] == recent_summary


def test_create_snapshot_without_engine_state(temp_db):
    """测试创建快照时不传引擎状态参数也能正常工作（向后兼容）"""
    # 准备
    novel_id = "test-novel"
    temp_db.execute("INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
                    (novel_id, "测试小说", "test-novel"))
    temp_db.commit()

    chapter_repo = SqliteChapterRepository(temp_db)
    service = SnapshotService(temp_db, chapter_repo)

    # 执行（不传引擎状态参数）
    snapshot_id = service.create_snapshot(
        novel_id=novel_id,
        trigger_type="MANUAL",
        name="测试快照",
    )

    # 验证
    assert snapshot_id is not None


def test_get_snapshot_parses_engine_state(temp_db):
    """测试 get_snapshot 方法正确解析引擎状态字段"""
    # 准备
    novel_id = "test-novel"
    temp_db.execute("INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
                    (novel_id, "测试小说", "test-novel"))
    temp_db.commit()

    chapter_repo = SqliteChapterRepository(temp_db)
    service = SnapshotService(temp_db, chapter_repo)

    story_state = {"act": 2}
    character_masks = {"char1": "active"}

    snapshot_id = service.create_snapshot(
        novel_id=novel_id,
        trigger_type="MANUAL",
        name="测试快照",
        story_state=story_state,
        character_masks=character_masks,
    )

    # 执行
    snapshot = service.get_snapshot(snapshot_id)

    # 验证
    assert snapshot is not None
    assert snapshot["story_state"] == story_state
    assert snapshot["character_masks"] == character_masks
    assert snapshot["emotion_ledger"] == {}
    assert snapshot["active_foreshadows"] == []
    assert snapshot["outline"] == ""
    assert snapshot["recent_chapters_summary"] == ""


def test_rollback_to_snapshot_includes_restored_flag(temp_db):
    """测试 rollback_to_snapshot 返回 has_engine_state 标志"""
    # 准备
    novel_id = "test-novel"
    temp_db.execute("INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
                    (novel_id, "测试小说", "test-novel"))
    temp_db.commit()

    chapter_repo = SqliteChapterRepository(temp_db)
    service = SnapshotService(temp_db, chapter_repo)

    # 创建带引擎状态的快照
    snapshot_id = service.create_snapshot(
        novel_id=novel_id,
        trigger_type="MANUAL",
        name="测试快照",
        story_state={"act": 1},
    )

    # 执行
    result = service.rollback_to_snapshot(novel_id, snapshot_id)

    # 验证
    assert "has_engine_state" in result
    assert result["has_engine_state"] is True


def test_rollback_without_engine_state_returns_false(temp_db):
    """测试回滚不包含引擎状态的快照时，has_engine_state 为 False"""
    # 准备
    novel_id = "test-novel"
    temp_db.execute("INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
                    (novel_id, "测试小说", "test-novel"))
    temp_db.commit()

    chapter_repo = SqliteChapterRepository(temp_db)
    service = SnapshotService(temp_db, chapter_repo)

    # 创建不带引擎状态的快照
    snapshot_id = service.create_snapshot(
        novel_id=novel_id,
        trigger_type="MANUAL",
        name="测试快照",
    )

    # 执行
    result = service.rollback_to_snapshot(novel_id, snapshot_id)

    # 验证
    assert "has_engine_state" in result
    assert result["has_engine_state"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
