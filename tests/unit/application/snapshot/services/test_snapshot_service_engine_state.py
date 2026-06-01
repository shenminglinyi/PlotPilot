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


def test_create_snapshot_persists_structured_bible_state(temp_db):
    """快照应保存真实 Bible 结构化状态，而不是固定存在性占位。"""
    import json

    novel_id = "test-novel"
    temp_db.execute("INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
                    (novel_id, "测试小说", "test-novel"))
    temp_db.execute("""
        CREATE TABLE IF NOT EXISTS bibles (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL UNIQUE,
            schema_version INTEGER NOT NULL DEFAULT 1,
            extensions TEXT NOT NULL DEFAULT '{}',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    temp_db.execute("""
        CREATE TABLE IF NOT EXISTS unified_characters (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            public_profile TEXT NOT NULL DEFAULT '',
            hidden_profile TEXT NOT NULL DEFAULT '',
            reveal_chapter INTEGER,
            role TEXT NOT NULL DEFAULT '',
            verbal_tic TEXT NOT NULL DEFAULT '',
            idle_behavior TEXT NOT NULL DEFAULT '',
            voice_style TEXT NOT NULL DEFAULT '',
            sentence_pattern TEXT NOT NULL DEFAULT '',
            speech_tempo TEXT NOT NULL DEFAULT '',
            core_belief TEXT NOT NULL DEFAULT '',
            moral_taboos_json TEXT NOT NULL DEFAULT '[]',
            active_wounds_json TEXT NOT NULL DEFAULT '[]',
            mental_state TEXT NOT NULL DEFAULT 'NORMAL',
            mental_state_reason TEXT NOT NULL DEFAULT '',
            current_state_summary TEXT NOT NULL DEFAULT '',
            last_updated_chapter INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        )
    """)
    temp_db.execute("""
        CREATE TABLE IF NOT EXISTS bible_world_settings (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            setting_type TEXT NOT NULL DEFAULT 'other',
            updated_at TEXT
        )
    """)
    temp_db.execute("""
        CREATE TABLE IF NOT EXISTS bible_locations (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            location_type TEXT NOT NULL DEFAULT 'other',
            parent_id TEXT,
            updated_at TEXT
        )
    """)
    temp_db.execute("""
        CREATE TABLE IF NOT EXISTS bible_timeline_notes (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            event TEXT NOT NULL DEFAULT '',
            time_point TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        )
    """)
    temp_db.execute("""
        CREATE TABLE IF NOT EXISTS bible_style_notes (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            updated_at TEXT
        )
    """)
    temp_db.execute(
        "INSERT INTO bibles (id, novel_id, schema_version, extensions, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("bible-1", novel_id, 2, '{"mode":"test"}', "2026-06-01T00:00:00", "2026-06-01T01:00:00"),
    )
    temp_db.execute(
        """
        INSERT INTO unified_characters (
            id, novel_id, name, description, public_profile, hidden_profile,
            reveal_chapter, role, verbal_tic, idle_behavior, voice_style,
            sentence_pattern, speech_tempo, core_belief, moral_taboos_json,
            active_wounds_json, mental_state, mental_state_reason,
            current_state_summary, last_updated_chapter, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "char-1", novel_id, "林舟", "角色描述", "公开信息", "隐藏信息",
            3, "主角", "且慢", "捻袖口", "冷静", "短句", "偏慢",
            "守信", '["背叛"]', '[{"name":"旧伤"}]', "紧张", "被追问",
            "刚完成交易", 5, "2026-06-01T01:00:00",
        ),
    )
    temp_db.execute(
        "INSERT INTO bible_world_settings (id, novel_id, name, description, setting_type, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("world-1", novel_id, "能力规则", "能力需要代价", "rule", "2026-06-01T01:00:00"),
    )
    temp_db.execute(
        "INSERT INTO bible_locations (id, novel_id, name, description, location_type, parent_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("loc-1", novel_id, "旧仓库", "城郊仓库", "site", None, "2026-06-01T01:00:00"),
    )
    temp_db.execute(
        "INSERT INTO bible_timeline_notes (id, novel_id, event, time_point, description, sort_order, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("time-1", novel_id, "第一次交易", "第一章", "双方试探", 1, "2026-06-01T01:00:00"),
    )
    temp_db.execute(
        "INSERT INTO bible_style_notes (id, novel_id, category, content, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("style-1", novel_id, "叙述", "短句推进", "2026-06-01T01:00:00"),
    )
    temp_db.commit()

    chapter_repo = SqliteChapterRepository(temp_db)
    service = SnapshotService(temp_db, chapter_repo)

    snapshot_id = service.create_snapshot(
        novel_id=novel_id,
        trigger_type="MANUAL",
        name="带 Bible 的快照",
    )

    row = temp_db.fetch_one("SELECT bible_state FROM novel_snapshots WHERE id = ?", (snapshot_id,))
    bible_state = json.loads(row["bible_state"])

    assert bible_state["exists"] is True
    assert bible_state["bible_id"] == "bible-1"
    assert bible_state["schema_version"] == 2
    assert bible_state["summary"] == {
        "characters": 1,
        "world_settings": 1,
        "locations": 1,
        "timeline_notes": 1,
        "style_notes": 1,
    }
    assert bible_state["characters"][0]["name"] == "林舟"
    assert bible_state["characters"][0]["verbal_tic"] == "且慢"
    assert bible_state["world_settings"][0]["name"] == "能力规则"
    assert "chapter_content" not in json.dumps(bible_state, ensure_ascii=False)


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


def test_delete_snapshot_reparents_children_without_deleting_chapters(temp_db):
    """删除中间快照时，子快照重挂到上级快照，章节表不受影响。"""
    novel_id = "test-novel"
    temp_db.execute(
        "INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
        (novel_id, "测试小说", "test-novel"),
    )
    temp_db.execute(
        "INSERT INTO chapters (id, novel_id, number, title, status, word_count) VALUES (?, ?, ?, ?, ?, ?)",
        ("chapter-1", novel_id, 1, "第一章", "completed", 1200),
    )
    temp_db.commit()

    chapter_repo = SqliteChapterRepository(temp_db)
    service = SnapshotService(temp_db, chapter_repo)

    root_id = "snapshot-root"
    middle_id = "snapshot-middle"
    child_id = "snapshot-child"
    for snapshot_id, parent_id, name in (
        (root_id, None, "根快照"),
        (middle_id, root_id, "中间快照"),
        (child_id, middle_id, "子快照"),
    ):
        temp_db.execute(
            """
            INSERT INTO novel_snapshots (
                id, novel_id, parent_snapshot_id, branch_name, trigger_type,
                name, description, chapter_pointers, bible_state, foreshadow_state,
                story_state, character_masks, emotion_ledger, active_foreshadows,
                outline, recent_chapters_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                novel_id,
                parent_id,
                "main",
                "MANUAL",
                name,
                None,
                '["chapter-1"]',
                "{}",
                "{}",
                "{}",
                "{}",
                "{}",
                "[]",
                "",
                "",
                "2026-06-01T00:00:00",
            ),
        )
    temp_db.commit()

    assert service.delete_snapshot(middle_id, novel_id=novel_id) is True
    assert service.get_snapshot(middle_id) is None

    child = service.get_snapshot(child_id)
    assert child is not None
    assert child["parent_snapshot_id"] == root_id

    chapter = temp_db.fetch_one("SELECT id FROM chapters WHERE id = ?", ("chapter-1",))
    assert chapter == {"id": "chapter-1"}


def test_delete_snapshot_rejects_cross_novel_delete(temp_db):
    """删除接口传入作品 ID 时，拒绝跨作品误删。"""
    temp_db.execute(
        "INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
        ("novel-a", "甲作品", "novel-a"),
    )
    temp_db.execute(
        "INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
        ("novel-b", "乙作品", "novel-b"),
    )
    temp_db.commit()

    chapter_repo = SqliteChapterRepository(temp_db)
    service = SnapshotService(temp_db, chapter_repo)
    snapshot_id = service.create_snapshot(
        novel_id="novel-a",
        trigger_type="MANUAL",
        name="甲作品快照",
    )

    with pytest.raises(ValueError, match="快照不属于该作品"):
        service.delete_snapshot(snapshot_id, novel_id="novel-b")

    assert service.get_snapshot(snapshot_id) is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
