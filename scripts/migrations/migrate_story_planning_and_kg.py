#!/usr/bin/env python3
"""
已废弃：请使用 `infrastructure/persistence/database/schema.sql` 作为唯一建表真源
（由 DatabaseConnection 在启动时 executescript）。

本脚本仅保留作历史参考；新建/清空库后勿再依赖此处对 triples 旧列的 ALTER。
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# 数据库路径
DB_PATH = Path(__file__).parent.parent / "data" / "plotpilot.db"

def check_column_exists(cursor, table: str, column: str) -> bool:
    """检查列是否存在"""
    cursor.execute(f"PRAGMA table_info({table})")
    columns = {col[1] for col in cursor.fetchall()}
    return column in columns

def check_table_exists(cursor, table: str) -> bool:
    """检查表是否存在"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    return cursor.fetchone() is not None

def migrate_story_nodes(cursor):
    """迁移 story_nodes 表"""
    print("\n=== 迁移 story_nodes 表 ===")

    fields = [
        ("planning_status", "TEXT DEFAULT 'draft'"),
        ("planning_source", "TEXT DEFAULT 'manual'"),
        ("outline", "TEXT"),
        ("suggested_chapter_count", "INTEGER"),
        ("themes", "TEXT"),
        ("key_events", "TEXT"),
        ("narrative_arc", "TEXT"),
        ("conflicts", "TEXT"),
        ("pov_character_id", "TEXT"),
        ("timeline_start", "TEXT"),
        ("timeline_end", "TEXT"),
    ]

    for field_name, field_type in fields:
        if not check_column_exists(cursor, "story_nodes", field_name):
            cursor.execute(f"ALTER TABLE story_nodes ADD COLUMN {field_name} {field_type}")
            print(f"✓ 添加字段: {field_name}")
        else:
            print(f"⊙ 字段已存在: {field_name}")

def create_chapter_elements(cursor):
    """创建 chapter_elements 表"""
    print("\n=== 创建 chapter_elements 表 ===")

    if check_table_exists(cursor, "chapter_elements"):
        print("⊙ 表已存在: chapter_elements")
        return

    cursor.execute("""
        CREATE TABLE chapter_elements (
            id TEXT PRIMARY KEY,
            chapter_id TEXT NOT NULL,
            element_type TEXT NOT NULL CHECK(element_type IN ('character', 'location', 'item', 'organization', 'event')),
            element_id TEXT NOT NULL,

            relation_type TEXT NOT NULL CHECK(relation_type IN (
                'appears',
                'mentioned',
                'scene',
                'uses',
                'involved',
                'occurs'
            )),

            importance TEXT DEFAULT 'normal' CHECK(importance IN ('major', 'normal', 'minor')),
            appearance_order INTEGER,
            notes TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (chapter_id) REFERENCES story_nodes(id) ON DELETE CASCADE,
            UNIQUE(chapter_id, element_type, element_id, relation_type)
        )
    """)
    print("✓ 创建表: chapter_elements")

    cursor.execute("CREATE INDEX idx_chapter_elements_chapter ON chapter_elements(chapter_id)")
    cursor.execute("CREATE INDEX idx_chapter_elements_element ON chapter_elements(element_type, element_id)")
    print("✓ 创建索引")

def create_chapter_scenes(cursor):
    """创建 chapter_scenes 表"""
    print("\n=== 创建 chapter_scenes 表 ===")

    if check_table_exists(cursor, "chapter_scenes"):
        print("⊙ 表已存在: chapter_scenes")
        return

    cursor.execute("""
        CREATE TABLE chapter_scenes (
            id TEXT PRIMARY KEY,
            chapter_id TEXT NOT NULL,
            scene_number INTEGER NOT NULL,

            location_id TEXT,
            timeline TEXT,

            summary TEXT,
            purpose TEXT,

            content TEXT,
            word_count INTEGER DEFAULT 0,

            characters TEXT,

            order_index INTEGER NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (chapter_id) REFERENCES story_nodes(id) ON DELETE CASCADE,
            FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL,
            UNIQUE(chapter_id, scene_number)
        )
    """)
    print("✓ 创建表: chapter_scenes")

    cursor.execute("CREATE INDEX idx_chapter_scenes_chapter ON chapter_scenes(chapter_id)")
    print("✓ 创建索引")

def migrate_triples(cursor):
    """迁移 triples 表"""
    print("\n=== 迁移 triples 表 ===")

    fields = [
        ("confidence", "REAL DEFAULT 1.0"),
        ("source_type", "TEXT DEFAULT 'manual'"),
        ("source_chapter_id", "TEXT"),
        ("first_appearance", "TEXT"),
        ("related_chapters", "TEXT"),
    ]

    for field_name, field_type in fields:
        if not check_column_exists(cursor, "triples", field_name):
            cursor.execute(f"ALTER TABLE triples ADD COLUMN {field_name} {field_type}")
            print(f"✓ 添加字段: {field_name}")
        else:
            print(f"⊙ 字段已存在: {field_name}")

    # 创建索引
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_triples_confidence ON triples(confidence)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_triples_source ON triples(source_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_triples_chapter ON triples(source_chapter_id)")
        print("✓ 创建索引")
    except Exception as e:
        print(f"⊙ 索引可能已存在: {e}")

def verify_migration(cursor):
    """验证迁移结果"""
    print("\n=== 验证迁移结果 ===")

    # 检查 story_nodes 字段
    cursor.execute("PRAGMA table_info(story_nodes)")
    story_nodes_columns = {col[1] for col in cursor.fetchall()}
    required_story_nodes = {
        "planning_status", "planning_source", "outline", "suggested_chapter_count",
        "themes", "key_events", "narrative_arc", "conflicts",
        "pov_character_id", "timeline_start", "timeline_end"
    }
    missing = required_story_nodes - story_nodes_columns
    if missing:
        print(f"✗ story_nodes 缺少字段: {missing}")
        return False
    print("✓ story_nodes 字段完整")

    # 检查 chapter_elements 表
    if not check_table_exists(cursor, "chapter_elements"):
        print("✗ chapter_elements 表不存在")
        return False
    print("✓ chapter_elements 表存在")

    # 检查 chapter_scenes 表
    if not check_table_exists(cursor, "chapter_scenes"):
        print("✗ chapter_scenes 表不存在")
        return False
    print("✓ chapter_scenes 表存在")

    # 检查 triples 字段
    cursor.execute("PRAGMA table_info(triples)")
    triples_columns = {col[1] for col in cursor.fetchall()}
    required_triples = {
        "confidence", "source_type", "source_chapter_id",
        "first_appearance", "related_chapters"
    }
    missing = required_triples - triples_columns
    if missing:
        print(f"✗ triples 缺少字段: {missing}")
        return False
    print("✓ triples 字段完整")

    return True

def main():
    """执行迁移"""
    print("=" * 60)
    print("数据库迁移：故事结构规划 + 知识图谱自动推断")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"数据库：{DB_PATH}")
    print("=" * 60)

    if not DB_PATH.exists():
        print(f"\n✗ 数据库文件不存在: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 执行迁移
        migrate_story_nodes(cursor)
        create_chapter_elements(cursor)
        create_chapter_scenes(cursor)
        migrate_triples(cursor)

        # 提交事务
        conn.commit()
        print("\n✓ 事务已提交")

        # 验证迁移
        if verify_migration(cursor):
            print("\n" + "=" * 60)
            print("✅ 迁移成功完成！")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("⚠️  迁移完成但验证失败，请检查")
            print("=" * 60)
            sys.exit(1)

    except Exception as e:
        conn.rollback()
        print(f"\n✗ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
