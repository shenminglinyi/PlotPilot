"""CoC 线索账本服务测试。"""

import pytest

from application.analyst.services.coc_clue_service import CocClueService
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_coc_clue_repository import (
    SqliteCocClueRepository,
)


def _create_service(tmp_path):
    db = DatabaseConnection(str(tmp_path / "coc-clue.db"))
    db.execute(
        "INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
        ("novel-1", "测试小说", "novel-1"),
    )
    db.commit()
    return CocClueService(SqliteCocClueRepository(db))


def test_absolute_lock_blocks_key_text_and_reveal_chapter_changes(tmp_path):
    service = _create_service(tmp_path)
    saved = service.upsert_item(
        novel_id="novel-1",
        clue_key="bloody_ticket",
        clue_text="染血票据来自北站。",
        visibility="reader_known",
        reveal_chapter=2,
        confidence=0.88,
        lock_level="absolute",
        status="active",
    )

    with pytest.raises(ValueError, match="absolute lock"):
        service.upsert_item(
            novel_id="novel-1",
            entry_id=saved["id"],
            clue_key="bloody_ticket",
            clue_text="染血票据来自南站。",
            visibility="reader_known",
            reveal_chapter=2,
            confidence=0.88,
            lock_level="absolute",
            status="active",
        )


def test_create_event_by_clue_key_auto_creates_draft_item(tmp_path):
    service = _create_service(tmp_path)

    event = service.create_event(
        novel_id="novel-1",
        clue_key="old_well_map",
        chapter_number=3,
        event_type="mention",
        evidence="第3章首次提到井底地图。",
    )
    assert event["clue_key"] == "old_well_map"
    assert event["chapter_number"] == 3

    overview = service.get_overview("novel-1")
    created = [item for item in overview["items"] if item["clue_key"] == "old_well_map"]
    assert len(created) == 1
    assert created[0]["lock_level"] == "soft"
    assert "draft" in created[0]["notes"]
    assert "cognition_layers" in overview


def test_cognition_layers_split_by_visibility(tmp_path):
    service = _create_service(tmp_path)
    service.upsert_item(
        novel_id="novel-1",
        clue_key="ticket_stub",
        clue_text="车票缺了一角。",
        visibility="reader_known",
        known_by="林岚",
        confidence=0.6,
    )
    service.upsert_item(
        novel_id="novel-1",
        clue_key="archive_code",
        clue_text="档案室门禁码 11473。",
        visibility="protagonist_known",
        known_by="林岚",
        confidence=0.9,
    )
    service.upsert_item(
        novel_id="novel-1",
        clue_key="sponsor_name",
        clue_text="背后资助者姓裴。",
        visibility="author_only",
        known_by="",
        confidence=0.8,
    )

    layers = service.get_cognition_layers("novel-1")
    assert any("ticket_stub" in line for line in layers["reader_known"])
    assert any("archive_code" in line for line in layers["character_known"])
    assert any("sponsor_name" in line for line in layers["author_truth"])
