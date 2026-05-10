"""测试 novel_snapshots 表的引擎状态字段扩展。"""
import sqlite3
from pathlib import Path

import pytest

SCHEMA_PATH = (
    Path(__file__).resolve().parents[5] / "infrastructure" / "persistence" / "database" / "schema.sql"
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[5]
    / "infrastructure"
    / "persistence"
    / "database"
    / "migrations"
    / "add_engine_state_to_snapshots.sql"
)


@pytest.fixture
def db_conn(tmp_path):
    """创建临时数据库并应用 schema。"""
    db_path = tmp_path / "test_snapshots.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    yield conn
    conn.close()


def test_novel_snapshots_engine_state_columns_after_migration(db_conn):
    """验证迁移后 novel_snapshots 表包含引擎状态字段。"""
    # 应用迁移（如果列已存在，会报错，这是预期的）
    if MIGRATION_PATH.exists():
        migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")
        try:
            db_conn.executescript(migration_sql)
        except sqlite3.OperationalError as e:
            # 如果是 "duplicate column" 错误，说明列已存在，这是正常的
            if "duplicate column" not in str(e):
                raise

    cursor = db_conn.execute("PRAGMA table_info(novel_snapshots)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    # 验证新增的引擎状态字段
    required_columns = [
        ("story_state", "TEXT"),
        ("character_masks", "TEXT"),
        ("emotion_ledger", "TEXT"),
        ("active_foreshadows", "TEXT"),
        ("outline", "TEXT"),
        ("recent_chapters_summary", "TEXT"),
    ]

    for col_name, col_type in required_columns:
        assert col_name in columns, f"{col_name} 列不存在"
        assert columns[col_name] == col_type, f"{col_name} 列类型应为 {col_type}"


def test_novel_snapshots_engine_state_columns_have_defaults_after_migration(db_conn):
    """验证迁移后引擎状态字段有默认值。"""
    # 应用迁移（如果列已存在，会报错，这是预期的）
    if MIGRATION_PATH.exists():
        migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")
        try:
            db_conn.executescript(migration_sql)
        except sqlite3.OperationalError as e:
            # 如果是 "duplicate column" 错误，说明列已存在，这是正常的
            if "duplicate column" not in str(e):
                raise

    # 创建测试小说
    db_conn.execute("INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)", ("test-novel", "测试小说", "test-novel"))

    # 插入快照（不提供引擎状态字段的值）
    db_conn.execute(
        """
        INSERT INTO novel_snapshots (id, novel_id, trigger_type, name, chapter_pointers)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("snapshot-1", "test-novel", "MANUAL", "测试快照", "[]"),
    )

    # 查询并验证默认值
    cursor = db_conn.execute(
        """
        SELECT story_state, character_masks, emotion_ledger,
               active_foreshadows, outline, recent_chapters_summary
        FROM novel_snapshots WHERE id = ?
        """,
        ("snapshot-1",),
    )

    row = cursor.fetchone()
    assert row is not None, "快照记录未找到"

    story_state, character_masks, emotion_ledger, active_foreshadows, outline, recent_chapters_summary = row

    # 验证默认值
    assert story_state == "{}", f"story_state 默认值应为 '{{}}', 实际为: {story_state}"
    assert character_masks == "{}", f"character_masks 默认值应为 '{{}}', 实际为: {character_masks}"
    assert emotion_ledger == "{}", f"emotion_ledger 默认值应为 '{{}}', 实际为: {emotion_ledger}"
    assert active_foreshadows == "[]", f"active_foreshadows 默认值应为 '[]', 实际为: {active_foreshadows}"
    assert outline == "", f"outline 默认值应为空字符串, 实际为: {outline}"
    assert recent_chapters_summary == "", f"recent_chapters_summary 默认值应为空字符串, 实际为: {recent_chapters_summary}"


def test_migration_file_exists():
    """验证迁移文件存在。"""
    assert MIGRATION_PATH.exists(), f"迁移文件不存在: {MIGRATION_PATH}"


def test_migration_applies_successfully(db_conn):
    """验证迁移可以成功应用。"""
    # 读取迁移 SQL
    if not MIGRATION_PATH.exists():
        pytest.skip("迁移文件尚未创建")

    migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")

    # 应用迁移（如果列已存在，会报错，这是预期的）
    try:
        db_conn.executescript(migration_sql)
    except sqlite3.OperationalError as e:
        # 如果是 "duplicate column" 错误，说明列已存在，这是正常的
        if "duplicate column" not in str(e):
            pytest.fail(f"迁移执行失败: {e}")

    # 验证字段已添加
    cursor = db_conn.execute("PRAGMA table_info(novel_snapshots)")
    columns = {row[1] for row in cursor.fetchall()}

    expected_columns = [
        "story_state",
        "character_masks",
        "emotion_ledger",
        "active_foreshadows",
        "outline",
        "recent_chapters_summary",
    ]

    for col in expected_columns:
        assert col in columns, f"迁移后 {col} 列仍不存在"
