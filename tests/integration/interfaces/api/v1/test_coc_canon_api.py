from pathlib import Path

import pytest
from fastapi import HTTPException

from application.analyst.services.coc_canon_service import CocCanonService
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_coc_canon_repository import (
    SqliteCocCanonRepository,
)
from interfaces.api.v1.analyst.coc_canon import (
    ApplyCocPresetRequest,
    apply_coc_preset,
    list_coc_preset_templates,
    CreateCocCanonEventRequest,
    UpsertCocCanonEntryRequest,
    create_coc_canon_event,
    get_coc_canon_overview,
    upsert_coc_canon_entry,
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


def test_coc_canon_route_functions_round_trip():
    db = DatabaseConnection(":memory:")
    db.get_connection().executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.get_connection().commit()
    db.execute(
        "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
        ("novel-coc-api", "正典接口测试", "novel-coc-api", 12),
    )
    db.commit()

    service = CocCanonService(SqliteCocCanonRepository(db))
    novel_service = _FakeNovelService()

    entry = upsert_coc_canon_entry(
        UpsertCocCanonEntryRequest(
            canon_type="character",
            title="林晚",
            public_facts="法医，左手旧伤。",
            hidden_truth="真实身份是卧底。",
            lock_level="absolute",
            mutable_notes="只允许补充线索来源。",
            status="active",
        ),
        novel_id="novel-coc-api",
        novel_service=novel_service,
        service=service,
    )
    assert entry.title == "林晚"

    event = create_coc_canon_event(
        CreateCocCanonEventRequest(
            entry_id=entry.id,
            chapter_number=3,
            event_type="confirm",
            evidence="第3章明确写到左手旧伤复发。",
        ),
        novel_id="novel-coc-api",
        novel_service=novel_service,
        service=service,
    )
    assert event.chapter_number == 3
    assert event.title == "林晚"

    overview = get_coc_canon_overview(
        novel_id="novel-coc-api",
        novel_service=novel_service,
        service=service,
    )
    assert overview.entries[0].lock_level == "absolute"
    assert overview.recent_events[0].event_type == "confirm"


def test_coc_canon_route_rejects_absolute_core_patch():
    db = DatabaseConnection(":memory:")
    db.get_connection().executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.get_connection().commit()
    db.execute(
        "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
        ("novel-coc-api-2", "正典接口测试2", "novel-coc-api-2", 12),
    )
    db.commit()

    service = CocCanonService(SqliteCocCanonRepository(db))
    novel_service = _FakeNovelService()
    entry = upsert_coc_canon_entry(
        UpsertCocCanonEntryRequest(
            canon_type="character",
            title="周砚",
            public_facts="刑警。",
            hidden_truth="卧底。",
            lock_level="absolute",
        ),
        novel_id="novel-coc-api-2",
        novel_service=novel_service,
        service=service,
    )

    with pytest.raises(HTTPException) as exc_info:
        upsert_coc_canon_entry(
            UpsertCocCanonEntryRequest(
                entry_id=entry.id,
                canon_type="character",
                title="周砚",
                public_facts="法医。",
                hidden_truth="卧底。",
                lock_level="absolute",
            ),
            novel_id="novel-coc-api-2",
            novel_service=novel_service,
            service=service,
        )

    assert exc_info.value.status_code == 400
    assert "absolute lock" in str(exc_info.value.detail)


def test_coc_preset_apply_and_list():
    db = DatabaseConnection(":memory:")
    db.get_connection().executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.get_connection().commit()
    db.execute(
        "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
        ("novel-coc-preset", "预设测试", "novel-coc-preset", 20),
    )
    db.commit()

    canon_service = CocCanonService(SqliteCocCanonRepository(db))
    from application.analyst.services.coc_clue_service import CocClueService
    from application.analyst.services.coc_preset_service import CocPresetService
    from application.analyst.services.prop_ledger_service import PropLedgerService
    from infrastructure.persistence.database.sqlite_coc_clue_repository import SqliteCocClueRepository
    from infrastructure.persistence.database.sqlite_prop_ledger_repository import SqlitePropLedgerRepository

    clue_service = CocClueService(SqliteCocClueRepository(db))
    prop_service = PropLedgerService(SqlitePropLedgerRepository(db))
    preset_service = CocPresetService(canon_service, clue_service, prop_service)
    novel_service = _FakeNovelService()

    templates = list_coc_preset_templates(
        novel_id="novel-coc-preset",
        novel_service=novel_service,
        preset_service=preset_service,
    )
    template_keys = {item.key for item in templates}
    assert "analysis-loop-721" in template_keys
    assert "fog-harbor-gray-card" in template_keys
    fog_template = next(item for item in templates if item.key == "fog-harbor-gray-card")
    assert fog_template.canon_count >= 10
    assert fog_template.clue_count >= 12
    assert fog_template.prop_count >= 6

    result = apply_coc_preset(
        ApplyCocPresetRequest(preset_key="fog-harbor-gray-card", overwrite_existing=False),
        novel_id="novel-coc-preset",
        novel_service=novel_service,
        preset_service=preset_service,
    )
    assert result.created_canon >= 10
    assert result.created_clues >= 12
    assert result.created_props >= 6
    assert canon_service.repository.get_entry_by_key(
        "novel-coc-preset",
        "character_truth",
        "主角：白雨翔",
    )
    assert clue_service.repository.get_item_by_key("novel-coc-preset", "witness-ritual-mainline")
    assert prop_service.repository.get_item_by_name("novel-coc-preset", "灰卡")
