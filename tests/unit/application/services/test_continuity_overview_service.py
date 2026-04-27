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
        CREATE TABLE story_nodes (
            id TEXT PRIMARY KEY,
            novel_id TEXT,
            node_type TEXT,
            number INTEGER
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
        "INSERT INTO story_nodes (id, novel_id, node_type, number) VALUES (?, ?, ?, ?)",
        ("sn-4", "novel-1", "chapter", 4),
    )
    db.execute(
        "INSERT INTO chapter_elements (id, chapter_id, element_type, element_id, relation_type) VALUES (?, ?, ?, ?, ?)",
        ("elem-1", "sn-4", "character", "char-lin", "appears"),
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
    assert overview["character_dropouts"][0]["character_name"] == "林羽"
    assert overview["character_dropouts"][0]["chapters_absent"] == 8
    assert overview["relationship_spotlights"][0]["relation"] == "盟友"
