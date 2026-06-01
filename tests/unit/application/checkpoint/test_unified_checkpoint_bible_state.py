"""统一 Checkpoint 的 Bible 状态采集测试。"""
import json
import sqlite3
import tempfile
from pathlib import Path

from application.checkpoint.services.unified_checkpoint_service import UnifiedCheckpointService
from infrastructure.persistence.database.connection import DatabaseConnection


class EmptyChapterRepository:
    def list_by_novel(self, novel_id):
        return []


def test_create_checkpoint_persists_structured_bible_state():
    """Checkpoint 应与 Snapshot 共用真实 Bible 状态，不再写固定占位。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "checkpoint.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE novels (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                slug TEXT NOT NULL
            );

            CREATE TABLE novel_checkpoints (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                parent_id TEXT,
                branch_name TEXT NOT NULL DEFAULT 'main',
                trigger_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                chapter_pointers TEXT NOT NULL DEFAULT '[]',
                bible_state TEXT NOT NULL DEFAULT '{}',
                foreshadow_state TEXT NOT NULL DEFAULT '{}',
                story_state TEXT NOT NULL DEFAULT '{}',
                character_masks TEXT NOT NULL DEFAULT '{}',
                emotion_ledger TEXT NOT NULL DEFAULT '{}',
                active_foreshadows TEXT NOT NULL DEFAULT '[]',
                outline TEXT NOT NULL DEFAULT '',
                recent_summary TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE novel_branches (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                name TEXT NOT NULL,
                head_id TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(novel_id, name)
            );

            CREATE TABLE bibles (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL UNIQUE,
                schema_version INTEGER NOT NULL DEFAULT 1,
                extensions TEXT NOT NULL DEFAULT '{}',
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE unified_characters (
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
            );

            CREATE TABLE bible_world_settings (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                setting_type TEXT NOT NULL DEFAULT 'other',
                updated_at TEXT
            );

            CREATE TABLE bible_locations (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                location_type TEXT NOT NULL DEFAULT 'other',
                parent_id TEXT,
                updated_at TEXT
            );

            CREATE TABLE bible_timeline_notes (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                event TEXT NOT NULL DEFAULT '',
                time_point TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT
            );

            CREATE TABLE bible_style_notes (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                updated_at TEXT
            );
        """)
        conn.close()

        db = DatabaseConnection(str(db_path))
        try:
            novel_id = "checkpoint-novel"
            db.execute(
                "INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
                (novel_id, "测试小说", "checkpoint-novel"),
            )
            db.execute(
                "INSERT INTO bibles (id, novel_id, schema_version, extensions, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("bible-1", novel_id, 1, "{}", "2026-06-01T00:00:00", "2026-06-01T01:00:00"),
            )
            db.execute(
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
                    "char-1", novel_id, "顾眠", "侦探", "公开", "",
                    None, "主角", "等一下", "转笔", "克制", "", "",
                    "求真", "[]", "[]", "警觉", "", "刚发现线索", 2,
                    "2026-06-01T01:00:00",
                ),
            )
            db.commit()

            service = UnifiedCheckpointService(db, EmptyChapterRepository())
            checkpoint_id = service.create_checkpoint(
                novel_id=novel_id,
                trigger_type="MANUAL",
                name="带 Bible 的 checkpoint",
            )

            row = db.fetch_one("SELECT bible_state FROM novel_checkpoints WHERE id = ?", (checkpoint_id,))
            bible_state = json.loads(row["bible_state"])

            assert bible_state["exists"] is True
            assert bible_state["summary"]["characters"] == 1
            assert bible_state["characters"][0]["name"] == "顾眠"
            assert bible_state["characters"][0]["idle_behavior"] == "转笔"
        finally:
            db.close()
