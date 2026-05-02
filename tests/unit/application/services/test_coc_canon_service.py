"""CoC 正典注册表服务测试。"""

import pytest

from application.analyst.services.coc_canon_service import CocCanonService
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_coc_canon_repository import (
    SqliteCocCanonRepository,
)


def _create_service(tmp_path):
    db = DatabaseConnection(str(tmp_path / "coc-canon.db"))
    db.execute(
        "INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
        ("novel-1", "测试小说", "novel-1"),
    )
    db.commit()
    return CocCanonService(SqliteCocCanonRepository(db))


def test_absolute_lock_blocks_core_field_changes(tmp_path):
    service = _create_service(tmp_path)
    service.upsert_entry(
        novel_id="novel-1",
        canon_type="character",
        title="林晚",
        public_facts="林晚是法医。",
        hidden_truth="她是卧底。",
        lock_level="absolute",
        mutable_notes="可更新备注",
        status="active",
    )

    with pytest.raises(ValueError, match="absolute lock"):
        service.upsert_entry(
            novel_id="novel-1",
            canon_type="character",
            title="林晚",
            public_facts="林晚是刑警。",
            hidden_truth="她是卧底。",
            lock_level="absolute",
            mutable_notes="备注",
            status="active",
        )


def test_absolute_lock_allows_mutable_notes_update(tmp_path):
    service = _create_service(tmp_path)
    service.upsert_entry(
        novel_id="novel-1",
        canon_type="organization",
        title="镜湖会",
        public_facts="地下情报组织。",
        hidden_truth="受王室资助。",
        lock_level="absolute",
        mutable_notes="初始备注",
        status="active",
    )

    updated = service.upsert_entry(
        novel_id="novel-1",
        canon_type="organization",
        title="镜湖会",
        public_facts="地下情报组织。",
        hidden_truth="受王室资助。",
        lock_level="absolute",
        mutable_notes="已补充线人名单来源。",
        status="active",
    )
    assert updated["mutable_notes"] == "已补充线人名单来源。"


def test_create_event_by_title_auto_creates_draft_entry(tmp_path):
    service = _create_service(tmp_path)
    event = service.create_event(
        novel_id="novel-1",
        title="黄铜钥匙",
        chapter_number=2,
        event_type="mention",
        evidence="第2章出现黄铜钥匙。",
    )
    assert event["title"] == "黄铜钥匙"

    overview = service.get_overview("novel-1")
    assert any(item["title"] == "黄铜钥匙" and item["status"] == "draft" for item in overview["entries"])
    assert "cognition_layers" in overview


def test_cognition_layers_include_author_truth_and_reader_known(tmp_path):
    service = _create_service(tmp_path)
    service.upsert_entry(
        novel_id="novel-1",
        canon_type="world_rule",
        title="灯塔信号",
        public_facts="午夜会闪三次绿灯。",
        hidden_truth="信号其实是旧教团的召集暗号。",
        lock_level="strict",
        mutable_notes="",
        status="active",
    )

    layers = service.get_cognition_layers("novel-1")
    assert any("灯塔信号" in line for line in layers["reader_known"])
    assert any("召集暗号" in line for line in layers["author_truth"])
    assert any("召集暗号" in text for text in layers["author_truth_snippets"])
