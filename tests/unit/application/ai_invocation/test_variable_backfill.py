from types import SimpleNamespace

from application.ai_invocation.variable_backfill import VariableHubBackfillService
from application.ai_invocation.variable_hub import InMemoryVariableHubRepository, VariableWrite
from domain.novel.value_objects.novel_id import NovelId


class _NovelRepo:
    def __init__(self, novels):
        self._novels = novels

    def list_all(self):
        return list(self._novels)

    def get_by_id(self, novel_id):
        for item in self._novels:
            if item.novel_id == novel_id:
                return item
        return None


class _BibleRepo:
    def __init__(self, bible):
        self._bible = bible

    def get_by_novel_id(self, novel_id):
        return self._bible if novel_id == NovelId("novel-1") else None


class _WorldbuildingRepo:
    def __init__(self, wb):
        self._wb = wb

    def get_by_novel_id(self, novel_id):
        return self._wb if novel_id == "novel-1" else None


def test_variable_hub_backfill_writes_missing_historical_facts():
    repo = InMemoryVariableHubRepository()
    novel = SimpleNamespace(
        novel_id=NovelId("novel-1"),
        title="旧书",
        premise="旧设定",
        target_chapters=80,
        target_words_per_chapter=3000,
        locked_genre="都市 / 都市异能",
    )
    bible = SimpleNamespace(
        characters=[
            SimpleNamespace(
                character_id=SimpleNamespace(value="char-1"),
                name="阿澄",
                description="主角",
                relationships=[],
            )
        ],
        locations=[
            SimpleNamespace(id="loc-1", name="天枢城", description="主城", location_type="城市", parent_id=None)
        ],
        style_notes=[SimpleNamespace(category="文风公约", content="克制冷峻")],
        world_settings=[],
    )
    wb = SimpleNamespace(
        normalized_dimensions=lambda: {
            "core_rules": {"power_system": "体系A"},
            "geography": {"terrain": "地形A"},
            "society": {},
            "culture": {},
            "daily_life": {},
        }
    )

    result = VariableHubBackfillService(
        variable_hub_repository=repo,
        novel_repository=_NovelRepo([novel]),
        bible_repository=_BibleRepo(bible),
        worldbuilding_repository=_WorldbuildingRepo(wb),
    ).backfill_all()

    assert result.values_written >= 8
    assert repo.get_value("novel.setup.title", "novel_id:novel-1").value == "旧书"
    assert repo.get_value("novel.characters.protagonist", "novel_id:novel-1").value["name"] == "阿澄"
    assert repo.get_value("novel.locations.list", "novel_id:novel-1").value[0]["name"] == "天枢城"
    assert repo.get_value("novel.worldbuilding.core_rules", "novel_id:novel-1").value["power_system"] == "体系A"
    assert repo.get_value("novel.genre.opening_profile", "novel_id:novel-1").value["genre_major"] == "都市"


def test_variable_hub_backfill_does_not_overwrite_existing_values():
    repo = InMemoryVariableHubRepository()
    repo.set_value(
        VariableWrite(
            key="novel.setup.title",
            value="新标题",
            context_key="novel_id:novel-1",
            source_node_key="accepted-session",
        )
    )
    novel = SimpleNamespace(
        novel_id=NovelId("novel-1"),
        title="旧标题",
        premise="旧设定",
        target_chapters=80,
        target_words_per_chapter=3000,
    )

    result = VariableHubBackfillService(
        variable_hub_repository=repo,
        novel_repository=_NovelRepo([novel]),
    ).backfill_novel("novel-1")

    assert result.skipped_existing == 1
    assert repo.get_value("novel.setup.title", "novel_id:novel-1").value == "新标题"
