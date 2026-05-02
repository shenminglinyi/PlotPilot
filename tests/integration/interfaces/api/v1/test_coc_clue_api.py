from pathlib import Path

from application.analyst.services.coc_clue_service import CocClueService
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_coc_clue_repository import (
    SqliteCocClueRepository,
)
from interfaces.api.v1.analyst.coc_clue import (
    CreateCocClueEventRequest,
    UpsertCocClueItemRequest,
    create_coc_clue_event,
    get_coc_clue_overview,
    upsert_coc_clue_item,
)


SCHEMA_PATH = (
    Path(__file__).resolve().parents[5]
    / "infrastructure"
    / "persistence"
    / "database"
    / "schema.sql"
)


class _FakeNovelService:
    def get_novel(self, novel_id: str):
        return {"id": novel_id}


def test_coc_clue_route_functions_round_trip():
    db = DatabaseConnection(":memory:")
    db.get_connection().executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.get_connection().commit()
    db.execute(
        "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
        ("novel-coc-clue-api", "线索接口测试", "novel-coc-clue-api", 15),
    )
    db.commit()

    service = CocClueService(SqliteCocClueRepository(db))
    novel_service = _FakeNovelService()

    item = upsert_coc_clue_item(
        UpsertCocClueItemRequest(
            clue_key="raincoat_fiber",
            clue_text="雨衣纤维与案发现场匹配。",
            visibility="reader_known",
            reveal_chapter=4,
            known_by="林晚",
            confidence=0.81,
            lock_level="strict",
            status="active",
            notes="等待实验室复检。",
        ),
        novel_id="novel-coc-clue-api",
        novel_service=novel_service,
        service=service,
    )
    assert item.clue_key == "raincoat_fiber"

    event = create_coc_clue_event(
        CreateCocClueEventRequest(
            entry_id=item.id,
            chapter_number=5,
            event_type="confirm",
            evidence="第5章法医复检确认纤维来源。",
        ),
        novel_id="novel-coc-clue-api",
        novel_service=novel_service,
        service=service,
    )
    assert event.clue_key == "raincoat_fiber"
    assert event.chapter_number == 5

    overview = get_coc_clue_overview(
        novel_id="novel-coc-clue-api",
        novel_service=novel_service,
        service=service,
    )
    assert overview.items[0].visibility == "reader_known"
    assert overview.recent_events[0].event_type == "confirm"
