from pathlib import Path

import pytest

from application.analyst.services.power_system_service import PowerSystemService
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_power_system_repository import (
    SqlitePowerSystemRepository,
)


SCHEMA_PATH = (
    Path(__file__).resolve().parents[4]
    / "infrastructure"
    / "persistence"
    / "database"
    / "schema.sql"
)


@pytest.fixture
def service():
    db = DatabaseConnection(":memory:")
    db.get_connection().executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.get_connection().commit()
    db.execute(
        "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
        ("novel-power-1", "战力测试", "novel-power-1", 30),
    )
    db.commit()
    return PowerSystemService(SqlitePowerSystemRepository(db))


def test_power_overview_warns_for_missing_rules_and_unlimited_high_power(service):
    service.upsert_profile(
        novel_id="novel-power-1",
        character_name="林夜",
        tier="黄金",
        rank_score=85,
        abilities="影刃爆发",
        limitations="",
    )

    overview = service.get_overview("novel-power-1")

    titles = [item["title"] for item in overview["warnings"]]
    assert "尚未固化战力规则" in titles
    assert "林夜 缺少高战力限制" in titles


def test_power_overview_warns_for_unpaid_leapfrog_victory(service):
    service.upsert_rules(novel_id="novel-power-1")
    service.create_event(
        novel_id="novel-power-1",
        chapter_number=12,
        character_name="林夜",
        opponent="黄金 Boss",
        outcome="越级击败对手",
        power_delta=2,
        evidence="爆发新技能直接获胜",
    )

    overview = service.get_overview("novel-power-1")

    assert any("疑似无代价越级" in item["title"] for item in overview["warnings"])
