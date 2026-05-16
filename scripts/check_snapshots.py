"""检查快照数据"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.persistence.database.connection import get_database

db = get_database()

# 1. 查看所有快照
rows = db.fetch_all("SELECT id, novel_id, trigger_type, name, description, chapter_pointers, created_at FROM novel_snapshots ORDER BY created_at")
print(f"=== 快照总数: {len(rows)} ===")
for r in rows:
    print(dict(r))

# 2. 查看小说列表
novels = db.fetch_all("SELECT id, title, autopilot_status, current_stage, current_auto_chapters, current_act, current_chapter_in_act, current_beat_index FROM novels ORDER BY updated_at DESC")
print(f"\n=== 小说总数: {len(novels)} ===")
for n in novels:
    print(dict(n))

# 3. 查看章节列表（只看当前小说的）
for n in novels:
    nid = n['id']
    chapters = db.fetch_all(
        "SELECT number, status, word_count, tension_score FROM chapters WHERE novel_id = ? ORDER BY number",
        (nid,)
    )
    if chapters:
        print(f"\n=== 小说 {nid} 章节 ===")
        for c in chapters:
            print(dict(c))

# 4. 检查故事线
for n in novels:
    nid = n['id']
    try:
        storylines = db.fetch_all(
            "SELECT id, novel_id, storyline_type, name, status, estimated_chapter_start, estimated_chapter_end FROM storylines WHERE novel_id = ?",
            (nid,)
        )
        if storylines:
            print(f"\n=== 小说 {nid} 故事线 ===")
            for s in storylines:
                print(dict(s))
    except Exception as e:
        print(f"故事线查询失败: {e}")

db.close()
