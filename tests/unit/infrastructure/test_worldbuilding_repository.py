from domain.worldbuilding.worldbuilding import Worldbuilding
from infrastructure.persistence.database.connection import get_database
from infrastructure.persistence.database.worldbuilding_repository import WorldbuildingRepository


def test_worldbuilding_repository_persists_v2_dimensions(tmp_path):
    db_path = str(tmp_path / "world.db")
    repo = WorldbuildingRepository(db_path)
    db = get_database(db_path)
    db.execute(
        "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
        ("novel-1", "测试", "novel-1", 10),
    )
    db.commit()
    wb = Worldbuilding(
        id="wb-1",
        novel_id="novel-1",
        schema_version=2,
        dimensions={
            "core_rules": {
                "power_system": "同步率体系",
                "cost_and_limitation": "神经损耗",
            },
            "daily_life": {
                "language_slang": "掉帧等于掉命",
            },
        },
    )

    repo.save(wb)
    loaded = repo.get_by_novel_id("novel-1")

    assert loaded is not None
    assert loaded.schema_version == 2
    assert loaded.core_rules["power_system"] == "同步率体系"
    assert loaded.core_rules["cost_and_limitation"] == "神经损耗"
    assert loaded.daily_life["language_slang"] == "掉帧等于掉命"
