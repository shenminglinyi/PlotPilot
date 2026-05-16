"""完整数据诊断 v4 - 安全查询"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.persistence.database.connection import get_database

db = get_database()

novel_id = 'novel-1778502724263'

# 1. 小说关键状态
novel = db.fetch_one("SELECT id, title, autopilot_status, current_stage, current_auto_chapters, current_act, current_chapter_in_act, current_beat_index, target_chapters, target_words_per_chapter, consecutive_error_count, last_chapter_tension, last_audit_chapter_number, beats_completed, updated_at FROM novels WHERE id = ?", (novel_id,))
if novel:
    print("=== 小说状态 ===")
    for k, v in dict(novel).items():
        print(f"  {k}: {v}")

# 2. 快照
snapshots = db.fetch_all("SELECT id, trigger_type, name, description, chapter_pointers, created_at FROM novel_snapshots WHERE novel_id = ? ORDER BY created_at", (novel_id,))
print(f"\n=== 快照: {len(snapshots)} ===")
for s in snapshots:
    print(f"  [{s['trigger_type']}] {s['name']} - {s['description']} @ {s['created_at']}")
    print(f"    章节指针: {s['chapter_pointers']}")

# 3. 章节进度
chapters = db.fetch_all(
    "SELECT number, status, word_count, tension_score FROM chapters WHERE novel_id = ? ORDER BY number",
    (novel_id,)
)
print(f"\n=== 章节进度 ===")
completed_count = 0
for c in chapters:
    status_icon = "✅" if c['status'] == 'completed' else "⬜"
    if c['status'] == 'completed':
        completed_count += 1
    print(f"  {status_icon} 第{c['number']}章: {c['status']} {c['word_count']}字 张力={c['tension_score']}")
print(f"  完成: {completed_count}/{len(chapters)}")

# 4. 故事线
storylines = db.fetch_all(
    "SELECT storyline_type, name, status, estimated_chapter_start, estimated_chapter_end FROM storylines WHERE novel_id = ?",
    (novel_id,)
)
print(f"\n=== 故事线: {len(storylines)} 条 ===")
for s in storylines:
    print(f"  [{s['storyline_type']}] {s['name']} ({s['status']}) 章节{s['estimated_chapter_start']}-{s['estimated_chapter_end']}")

# 5. 伏笔
try:
    foreshadow = db.fetch_one(
        "SELECT payload FROM novel_foreshadow_registry WHERE novel_id = ?",
        (novel_id,)
    )
    if foreshadow:
        data = json.loads(foreshadow['payload'])
        entries = data.get('subtext_entries', [])
        print(f"\n=== 伏笔: {len(entries)} 条 ===")
        for f in entries[:10]:
            print(f"  [{f.get('status','?')}] {f.get('description', f.get('hint',''))[:80]}")
except Exception as e:
    print(f"\n=== 伏笔查询失败: {e} ===")

# 6. Bible 角色表结构
try:
    cols = db.fetch_all("PRAGMA table_info(bible_characters)")
    col_names = [c['name'] for c in cols]
    print(f"\n=== bible_characters 列: {col_names} ===")
    chars = db.fetch_all("SELECT * FROM bible_characters WHERE novel_id = ? LIMIT 10", (novel_id,))
    for c in chars:
        d = dict(c)
        print(f"  {d.get('name','?')} - {d}")
except Exception as e:
    print(f"  查询失败: {e}")

# 7. 故事节点表结构
try:
    cols = db.fetch_all("PRAGMA table_info(story_nodes)")
    col_names = [c['name'] for c in cols]
    print(f"\n=== story_nodes 列: {col_names} ===")
    nodes = db.fetch_all("SELECT * FROM story_nodes WHERE novel_id = ? ORDER BY chapter_number LIMIT 10", (novel_id,))
    print(f"  节点数(前10): {len(nodes)}")
    for n in nodes[:5]:
        d = dict(n)
        ch = d.get('chapter_number', '?')
        nt = d.get('node_type', '?')
        title = d.get('title', d.get('name', '?'))
        print(f"  ch={ch} type={nt} title={title}")
except Exception as e:
    print(f"  查询失败: {e}")

# 8. 编年史
try:
    cols = db.fetch_all("PRAGMA table_info(chronicles)")
    col_names = [c['name'] for c in cols]
    print(f"\n=== chronicles 列: {col_names} ===")
    chronicles = db.fetch_all("SELECT * FROM chronicles WHERE novel_id = ? ORDER BY chapter_number LIMIT 10", (novel_id,))
    if chronicles:
        for c in chronicles:
            d = dict(c)
            print(f"  ch={d.get('chapter_number')} {str(d.get('event_summary', d.get('timeline_note','')))[:80]}")
except Exception as e:
    print(f"  编年史查询失败: {e}")

# 9. 章节内容预览
for ch_num in [1, 2]:
    ch = db.fetch_one("SELECT content FROM chapters WHERE novel_id = ? AND number = ?", (novel_id, ch_num))
    if ch:
        content = ch['content'] or ''
        print(f"\n=== 第{ch_num}章内容预览 ({len(content)}字) ===")
        print(content[:200])

db.close()
