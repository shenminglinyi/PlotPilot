"""迁移脚本：为 novels 表添加 genre、theme_agent_enabled 和 enabled_theme_skills 列

适用于已有数据库的升级，新建数据库已在 schema.sql 中包含此列。
"""
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from application.paths import get_db_path


def migrate():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查列是否已存在
    cursor.execute("PRAGMA table_info(novels)")
    columns = [row[1] for row in cursor.fetchall()]

    if "genre" not in columns:
        print("Adding 'genre' column to novels table...")
        cursor.execute("ALTER TABLE novels ADD COLUMN genre TEXT DEFAULT ''")
        conn.commit()
        print("Done: genre column added successfully.")
    else:
        print("Column 'genre' already exists, skipping.")

    if "theme_agent_enabled" not in columns:
        print("Adding 'theme_agent_enabled' column to novels table...")
        cursor.execute("ALTER TABLE novels ADD COLUMN theme_agent_enabled INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        print("Done: theme_agent_enabled column added successfully.")
    else:
        print("Column 'theme_agent_enabled' already exists, skipping.")

    if "enabled_theme_skills" not in columns:
        print("Adding 'enabled_theme_skills' column to novels table...")
        cursor.execute("ALTER TABLE novels ADD COLUMN enabled_theme_skills TEXT DEFAULT '[]'")
        conn.commit()
        print("Done: enabled_theme_skills column added successfully.")
    else:
        print("Column 'enabled_theme_skills' already exists, skipping.")

    conn.close()


if __name__ == "__main__":
    migrate()
