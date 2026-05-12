"""一次性迁移：旧表 → unified_characters / unified_props

运行: python scripts/migrate_to_unified.py
"""
from __future__ import annotations
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.persistence.database.connection import get_database


def _now():
    return datetime.utcnow().isoformat()


def migrate_characters(db):
    conn = db.get_connection()
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bible_characters' LIMIT 1"
    ).fetchone()
    if not exists:
        print("[migrate] bible_characters 表不存在，跳过角色迁移")
        return
    rows = conn.execute("SELECT * FROM bible_characters").fetchall()
    migrated = 0
    for r in rows:
        d = dict(r)
        eng = conn.execute(
            "SELECT base_layer FROM characters WHERE name = ?", (d["name"],)
        ).fetchone()
        base_layer = {}
        if eng:
            try:
                base_layer = json.loads(eng["base_layer"] or "{}")
            except Exception:
                pass
        cs_row = conn.execute(
            "SELECT * FROM character_states WHERE character_id = ?", (d["id"],)
        ).fetchone()
        cs = dict(cs_row) if cs_row else {}
        try:
            conn.execute("""
                INSERT OR IGNORE INTO unified_characters (
                    id, novel_id, name, description, public_profile, hidden_profile,
                    reveal_chapter, role, verbal_tic, idle_behavior,
                    voice_style, sentence_pattern, speech_tempo,
                    core_belief, moral_taboos_json, active_wounds_json,
                    mental_state, mental_state_reason,
                    emotional_arc_json, current_state_summary, last_updated_chapter,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                d["id"], d["novel_id"], d["name"],
                d.get("description", ""),
                d.get("public_profile", ""),
                d.get("hidden_profile", ""),
                d.get("reveal_chapter"),
                base_layer.get("role", ""),
                d.get("verbal_tic", ""),
                d.get("idle_behavior", ""),
                base_layer.get("voice_style", ""),
                base_layer.get("sentence_pattern", ""),
                base_layer.get("speech_tempo", ""),
                d.get("core_belief", ""),
                d.get("moral_taboos_json", "[]"),
                d.get("active_wounds_json", "[]"),
                cs.get("mental_state", "NORMAL") if cs else "NORMAL",
                "",
                cs.get("emotional_arc", "[]") if cs else "[]",
                cs.get("current_state_summary", "") if cs else "",
                cs.get("last_updated_chapter", 0) if cs else 0,
                d.get("created_at", _now()),
                _now(),
            ))
            migrated += 1
        except Exception as e:
            print(f"[migrate] 角色迁移失败 {d.get('name')}: {e}")
    conn.commit()
    print(f"[migrate] 角色迁移: {migrated} 条")


def migrate_props(db):
    conn = db.get_connection()
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bible_props' LIMIT 1"
    ).fetchone()
    if not exists:
        print("[migrate] bible_props 表不存在，跳过道具迁移")
        return
    rows = conn.execute("SELECT * FROM bible_props").fetchall()
    migrated = 0
    for r in rows:
        d = dict(r)
        try:
            conn.execute("""
                INSERT OR IGNORE INTO unified_props (
                    id, novel_id, name, description, aliases_json, prop_category,
                    lifecycle_state, introduced_chapter, holder_character_id,
                    attributes_json, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                d["id"], d["novel_id"], d["name"],
                d.get("description", ""),
                d.get("aliases_json", "[]"),
                "OTHER",
                "DORMANT",
                d.get("first_chapter"),
                d.get("holder_character_id"),
                "{}",
                d.get("created_at", _now()),
                _now(),
            ))
            migrated += 1
        except Exception as e:
            print(f"[migrate] 道具迁移失败 {d.get('name')}: {e}")
    conn.commit()
    print(f"[migrate] 道具迁移: {migrated} 条")


if __name__ == "__main__":
    db = get_database()
    migrate_characters(db)
    migrate_props(db)
    print("[migrate] 完成")
