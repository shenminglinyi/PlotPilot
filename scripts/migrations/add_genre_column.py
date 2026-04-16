"""迁移脚本：为 novels 表添加 genre 列

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

    # 检查 genre 列是否已存在
    cursor.execute("PRAGMA table_info(novels)")
    columns = [row[1] for row in cursor.fetchall()]

    if "genre" not in columns:
        print("Adding 'genre' column to novels table...")
        cursor.execute("ALTER TABLE novels ADD COLUMN genre TEXT DEFAULT ''")
        conn.commit()
        print("Done: genre column added successfully.")
    else:
        print("Column 'genre' already exists, skipping migration.")

    conn.close()


if __name__ == "__main__":
    migrate()
