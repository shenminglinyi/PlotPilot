from pathlib import Path

from application.analyst.services.power_system_service import PowerSystemService
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_power_system_repository import (
    SqlitePowerSystemRepository,
)
from interfaces.api.v1.analyst.power_system import (
    CreatePowerEventRequest,
    UpsertPowerProfileRequest,
    UpsertPowerRulesRequest,
    create_power_event,
    get_power_system_overview,
    upsert_power_profile,
    upsert_power_rules,
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


def test_power_system_route_functions_round_trip():
    db = DatabaseConnection(":memory:")
    db.get_connection().executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.get_connection().commit()
    db.execute(
        "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
        ("novel-power-api", "战力接口测试", "novel-power-api", 20),
    )
    db.commit()
    service = PowerSystemService(SqlitePowerSystemRepository(db))
    novel_service = _FakeNovelService()

    rules = upsert_power_rules(
        UpsertPowerRulesRequest(
            tier_schema="黑铁 < 青铜 < 白银 < 黄金",
            core_rules="升级必须有经验、任务或代价。",
            taboo_rules="禁止无代价越级。",
            escalation_rules="每次升阶都需要验证战。",
        ),
        novel_id="novel-power-api",
        novel_service=novel_service,
        service=service,
    )
    assert "黑铁" in rules.tier_schema

    profile = upsert_power_profile(
        UpsertPowerProfileRequest(
            character_name="林夜",
            tier="黄金",
            rank_score=82,
            abilities="影刃",
            limitations="三章只能使用一次底牌。",
            last_verified_chapter=8,
        ),
        novel_id="novel-power-api",
        novel_service=novel_service,
        service=service,
    )
    assert profile.character_name == "林夜"

    event = create_power_event(
        CreatePowerEventRequest(
            chapter_number=9,
            character_name="林夜",
            opponent="白银 Boss",
            outcome="获胜但受伤",
            power_delta=1,
            evidence="消耗底牌并受伤。",
        ),
        novel_id="novel-power-api",
        novel_service=novel_service,
        service=service,
    )
    assert event.chapter_number == 9

    overview = get_power_system_overview(
        novel_id="novel-power-api",
        novel_service=novel_service,
        service=service,
    )
    assert overview.profiles[0].character_name == "林夜"
    assert overview.recent_events[0].chapter_number == 9
