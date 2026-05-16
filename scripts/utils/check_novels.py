"""查询数据库中的小说"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.persistence.database.connection import DatabaseConnection

db = DatabaseConnection("data/plotpilot.db")
conn = db.get_connection()
cursor = conn.cursor()

print("数据库中的小说：")
cursor.execute("SELECT id, title, slug FROM novels")
novels = cursor.fetchall()

if novels:
    for novel in novels:
        print(f"  ID: {novel[0]}")
        print(f"  标题: {novel[1]}")
        print(f"  Slug: {novel[2]}")
        print()
else:
    print("  (无数据)")
