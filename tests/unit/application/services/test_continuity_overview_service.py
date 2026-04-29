import sqlite3
from types import SimpleNamespace

from application.analyst.services.continuity_overview_service import ContinuityOverviewService
from domain.novel.entities.timeline_registry import TimelineRegistry
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.timeline_event import TimelineEvent


class _FakeDb:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql: str, params=()):
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        return cursor


class _FakeBibleService:
    def get_bible_by_novel(self, novel_id: str):
        return SimpleNamespace(
            characters=[
                SimpleNamespace(
                    id="char-lin",
                    name="林羽",
                    relationships=[
                        {"target": "苏晴", "relation": "盟友", "description": "目前仍互相信任"}
                    ],
                ),
                SimpleNamespace(
                    id="char-su",
                    name="苏晴",
                    relationships=[],
                ),
                SimpleNamespace(
                    id="char-yan",
                    name="严舟",
                    relationships=[
                        {"target": "苏晴", "relation": "旧友", "description": "多年未再合作"}
                    ],
                ),
            ]
        )


class _FakeChapterService:
    def list_chapters_by_novel(self, novel_id: str):
        return [SimpleNamespace(number=5), SimpleNamespace(number=12)]


class _FakeVoiceDriftService:
    def get_drift_report(self, novel_id: str):
        return {
            "scores": [
                {"chapter_number": 11, "similarity_score": 0.82},
                {"chapter_number": 12, "similarity_score": 0.63},
            ],
            "drift_alert": True,
            "alert_threshold": 0.75,
            "alert_consecutive": 5,
        }


class _FakeTimelineRepository:
    def get_by_novel_id(self, novel_id: NovelId):
        return TimelineRegistry(
            id="tl-1",
            novel_id=novel_id,
            events=[
                TimelineEvent(
                    id="evt-11",
                    chapter_number=11,
                    event="深夜潜入",
                    timestamp="当夜",
                    timestamp_type="relative",
                )
            ],
        )


def test_get_overview_collects_dropouts_and_existing_signals():
    db = _FakeDb()
    db.execute(
        """
        CREATE TABLE chapters (
            id TEXT PRIMARY KEY,
            novel_id TEXT,
            number INTEGER,
            title TEXT,
            content TEXT,
            outline TEXT,
            status TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE story_nodes (
            id TEXT PRIMARY KEY,
            novel_id TEXT,
            node_type TEXT,
            number INTEGER,
            outline TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE chapter_elements (
            id TEXT PRIMARY KEY,
            chapter_id TEXT,
            element_type TEXT,
            element_id TEXT,
            relation_type TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE knowledge (
            id TEXT PRIMARY KEY,
            novel_id TEXT UNIQUE
        )
        """
    )
    db.execute(
        """
        CREATE TABLE chapter_summaries (
            id TEXT PRIMARY KEY,
            knowledge_id TEXT NOT NULL,
            chapter_number INTEGER NOT NULL,
            summary TEXT,
            key_events TEXT,
            open_threads TEXT,
            consistency_note TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE chapter_reviews (
            novel_id TEXT NOT NULL,
            chapter_number INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            memo TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        "INSERT INTO knowledge (id, novel_id) VALUES (?, ?)",
        ("novel-1-knowledge", "novel-1"),
    )
    db.execute(
        "INSERT INTO story_nodes (id, novel_id, node_type, number) VALUES (?, ?, ?, ?)",
        ("sn-4", "novel-1", "chapter", 4),
    )
    db.execute(
        "INSERT INTO story_nodes (id, novel_id, node_type, number, outline) VALUES (?, ?, ?, ?, ?)",
        (
            "sn-12",
            "novel-1",
            "chapter",
            12,
            "林羽与苏晴在码头对峙，关系出现裂痕，并决定当夜潜入仓库。",
        ),
    )
    db.execute(
        """
        INSERT INTO chapters (id, novel_id, number, title, content, outline, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ch-12",
            "novel-1",
            12,
            "第12章",
            "林羽在码头和苏晴爆发争执，两人的信任开始松动。深夜里，他决定独自潜入仓库。",
            "林羽与苏晴在码头对峙，关系出现裂痕，并决定当夜潜入仓库。",
            "draft",
        ),
    )
    db.execute(
        "INSERT INTO chapter_elements (id, chapter_id, element_type, element_id, relation_type) VALUES (?, ?, ?, ?, ?)",
        ("elem-1", "sn-4", "character", "char-yan", "appears"),
    )
    db.execute(
        "INSERT INTO chapter_elements (id, chapter_id, element_type, element_id, relation_type) VALUES (?, ?, ?, ?, ?)",
        ("elem-1b", "sn-4", "character", "char-su", "appears"),
    )
    db.execute(
        "INSERT INTO chapter_elements (id, chapter_id, element_type, element_id, relation_type) VALUES (?, ?, ?, ?, ?)",
        ("elem-2", "sn-12", "character", "char-lin", "appears"),
    )
    db.execute(
        "INSERT INTO chapter_elements (id, chapter_id, element_type, element_id, relation_type) VALUES (?, ?, ?, ?, ?)",
        ("elem-3", "sn-12", "character", "char-su", "appears"),
    )
    db.execute(
        """
        INSERT INTO chapter_summaries (
            id, knowledge_id, chapter_number, summary, key_events, open_threads, consistency_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "sum-12",
            "novel-1-knowledge",
            12,
            "林羽与苏晴在码头对峙后关系趋紧，林羽决定独自潜入仓库。",
            "码头对峙；潜入仓库",
            "苏晴是否还会相信林羽",
            "本章强化了两人的信任裂痕。",
        ),
    )
    db.execute(
        """
        INSERT INTO chapter_reviews (novel_id, chapter_number, status, memo)
        VALUES (?, ?, ?, ?)
        """,
        (
            "novel-1",
            12,
            "draft",
            "新增了赵四的临时线索，和原大纲不完全一致，建议检查是否偏离。",
        ),
    )

    service = ContinuityOverviewService(
        bible_service=_FakeBibleService(),
        chapter_service=_FakeChapterService(),
        voice_drift_service=_FakeVoiceDriftService(),
        timeline_repository=_FakeTimelineRepository(),
        db_connection=db,
    )

    overview = service.get_overview("novel-1", 12, dropout_gap=5)

    assert overview["chapter_number"] == 12
    assert overview["latest_chapter_number"] == 12
    assert overview["voice_drift"]["drift_alert"] is True
    assert overview["voice_drift"]["latest_similarity_score"] == 0.63
    assert overview["timeline"]["current_chapter_has_event"] is False
    assert overview["timeline"]["total_events"] == 1
    assert overview["character_dropouts"][0]["character_name"] == "严舟"
    assert overview["character_dropouts"][0]["chapters_absent"] == 8
    assert overview["character_dropouts"][0]["tracked_relationship_count"] == 1
    assert overview["character_dropouts"][0]["stale_relationship_count"] == 1
    assert overview["character_dropouts"][0]["stale_relationship_targets"] == ["苏晴"]
    assert overview["character_dropouts"][0]["dropout_scope"] == "linked"
    assert overview["relationship_spotlights"][0]["relation"] == "盟友"
    assert overview["relationship_tracking"]["active_signals"][0]["source_character"] == "林羽"
    assert overview["relationship_tracking"]["active_signals"][0]["target_character"] == "苏晴"
    assert overview["relationship_tracking"]["active_signals"][0]["change_signal"] == "关系趋紧"
    assert overview["relationship_tracking"]["stale_pairs"][0]["source_character"] == "严舟"
    assert overview["relationship_tracking"]["stale_pairs"][0]["target_character"] == "苏晴"
    assert overview["outline_deviation"]["status"] == "warning"
    assert "审阅备注提示可能偏离大纲" in overview["outline_deviation"]["warning_reasons"]


def test_get_overview_prefers_structured_relationship_events_and_outline_statuses():
    db = _FakeDb()
    db.execute(
        """
        CREATE TABLE chapters (
            id TEXT PRIMARY KEY,
            novel_id TEXT,
            number INTEGER,
            title TEXT,
            content TEXT,
            outline TEXT,
            status TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE story_nodes (
            id TEXT PRIMARY KEY,
            novel_id TEXT,
            node_type TEXT,
            number INTEGER,
            outline TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE chapter_elements (
            id TEXT PRIMARY KEY,
            chapter_id TEXT,
            element_type TEXT,
            element_id TEXT,
            relation_type TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE continuity_relationship_events (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            chapter_number INTEGER NOT NULL,
            source_character TEXT NOT NULL,
            target_character TEXT NOT NULL DEFAULT '',
            relation TEXT NOT NULL DEFAULT '关系',
            event_type TEXT NOT NULL DEFAULT 'update',
            description TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT 'info',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE outline_node_statuses (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            chapter_number INTEGER NOT NULL,
            node_key TEXT NOT NULL,
            outline_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            note TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        INSERT INTO story_nodes (id, novel_id, node_type, number, outline)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "sn-12",
            "novel-1",
            "chapter",
            12,
            "林羽与苏晴在码头确认合作；两人发现仓库暗门；严舟留下误导线索。",
        ),
    )
    db.execute(
        """
        INSERT INTO chapters (id, novel_id, number, title, content, outline, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ch-12",
            "novel-1",
            12,
            "第12章",
            "林羽独自行动。",
            "林羽与苏晴在码头确认合作；两人发现仓库暗门；严舟留下误导线索。",
            "draft",
        ),
    )
    db.execute(
        """
        INSERT INTO chapter_elements (id, chapter_id, element_type, element_id, relation_type)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("elem-lin", "sn-12", "character", "char-lin", "appears"),
    )
    db.execute(
        """
        INSERT INTO continuity_relationship_events (
            id, novel_id, chapter_number, source_character, target_character,
            relation, event_type, description, evidence, severity
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "rel-event-1",
            "novel-1",
            12,
            "林羽",
            "苏晴",
            "盟友",
            "trust_break",
            "林羽隐瞒暗门线索，苏晴开始怀疑他。",
            "苏晴收起地图，没有再回应林羽。",
            "warning",
        ),
    )
    db.execute(
        """
        INSERT INTO outline_node_statuses (
            id, novel_id, chapter_number, node_key, outline_text, status, note, evidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "outline-1",
            "novel-1",
            12,
            "node-1",
            "林羽与苏晴在码头确认合作",
            "changed",
            "合作被改成隐瞒，关系方向发生变化。",
            "林羽独自行动。",
        ),
    )
    db.execute(
        """
        INSERT INTO outline_node_statuses (
            id, novel_id, chapter_number, node_key, outline_text, status, note, evidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "outline-2",
            "novel-1",
            12,
            "node-2",
            "两人发现仓库暗门",
            "missing",
            "暗门节点未落地。",
            "",
        ),
    )

    service = ContinuityOverviewService(
        bible_service=_FakeBibleService(),
        chapter_service=_FakeChapterService(),
        voice_drift_service=_FakeVoiceDriftService(),
        timeline_repository=_FakeTimelineRepository(),
        db_connection=db,
    )

    overview = service.get_overview("novel-1", 12, dropout_gap=5)

    assert overview["relationship_tracking"]["source"] == "structured"
    assert overview["relationship_tracking"]["active_signals"][0]["change_signal"] == "trust_break"
    assert overview["relationship_tracking"]["active_signals"][0]["signal_excerpt"] == "苏晴收起地图，没有再回应林羽。"
    assert overview["outline_deviation"]["source"] == "structured"
    assert overview["outline_deviation"]["status"] == "warning"
    assert overview["outline_deviation"]["overlap_score"] == 0
    assert overview["outline_deviation"]["outline_nodes"][0]["status"] == "changed"
    assert "结构化大纲节点存在变更或缺失" in overview["outline_deviation"]["warning_reasons"]
