"""SQLite StyleBibleRepository 测试。"""

from domain.style_bible.entities import (
    StyleProfile,
    StyleSample,
    StyleSampleChunk,
    StyleTechniqueCard,
)
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_style_bible_repository import (
    SqliteStyleBibleRepository,
)


def test_sqlite_style_bible_repository_saves_sample_with_chunks(tmp_path):
    db = DatabaseConnection(str(tmp_path / "style-bible.db"))
    repo = SqliteStyleBibleRepository(db)
    sample = StyleSample(
        title="第一章参考",
        content="林晚推开门。\n\n“你来了？”",
        novel_id="novel-1",
        profile_id="profile-1",
        allowed_for_generation=True,
    )
    chunks = [
        StyleSampleChunk(
            sample_id=sample.id,
            chunk_type="chapter",
            sequence=1,
            chapter_number=1,
            title="第一章",
            content=sample.content,
            metrics={"avg_sentence_length": 6.5},
        ),
        StyleSampleChunk(
            sample_id=sample.id,
            chunk_type="paragraph",
            sequence=2,
            chapter_number=1,
            content="林晚推开门。",
        ),
    ]

    saved = repo.save_sample(sample, chunks)

    assert saved.id == sample.id
    loaded = repo.get_sample(sample.id)
    assert loaded is not None
    assert loaded.title == "第一章参考"
    assert loaded.allowed_for_generation is True
    assert loaded.char_count == sample.char_count
    assert repo.list_samples(novel_id="novel-1")[0].id == sample.id

    rows = db.fetch_all(
        "SELECT * FROM style_sample_chunks WHERE sample_id = ? ORDER BY sequence",
        (sample.id,),
    )
    assert [row["chunk_type"] for row in rows] == ["chapter", "paragraph"]
    assert rows[0]["metrics_json"] == '{"avg_sentence_length": 6.5}'


def test_sqlite_style_bible_repository_deduplicates_sample_by_hash_and_novel(tmp_path):
    db = DatabaseConnection(str(tmp_path / "style-bible-dedup.db"))
    repo = SqliteStyleBibleRepository(db)
    first = StyleSample(title="样本一", content="同一段文本", novel_id="novel-1")
    duplicate = StyleSample(title="样本二", content="同一段文本", novel_id="novel-1")
    other_novel = StyleSample(title="样本三", content="同一段文本", novel_id="novel-2")

    repo.save_sample(first, [])
    repo.save_sample(duplicate, [])
    repo.save_sample(other_novel, [])

    assert [sample.title for sample in repo.list_samples(novel_id="novel-1")] == ["样本一"]
    assert [sample.title for sample in repo.list_samples(novel_id="novel-2")] == ["样本三"]


def test_sqlite_style_bible_repository_saves_profiles_and_cards(tmp_path):
    db = DatabaseConnection(str(tmp_path / "style-bible-profile.db"))
    repo = SqliteStyleBibleRepository(db)
    profile = StyleProfile(
        name="克制悬疑",
        novel_id="novel-1",
        profile={"summary": "短句推进"},
        metrics={"dialogue_ratio": 0.31},
        rules=["每 800 字一次信息变化"],
        forbidden_patterns=["五味杂陈"],
    )

    saved = repo.save_profile(profile)

    assert saved.id == profile.id
    loaded = repo.get_profile(profile.id)
    assert loaded is not None
    assert loaded.profile == {"summary": "短句推进"}
    assert loaded.metrics == {"dialogue_ratio": 0.31}
    assert loaded.rules == ["每 800 字一次信息变化"]
    assert loaded.forbidden_patterns == ["五味杂陈"]
    assert [item.id for item in repo.list_profiles(novel_id="novel-1")] == [profile.id]

    cards = repo.save_technique_cards(
        profile.id,
        [
            StyleTechniqueCard(
                profile_id=profile.id,
                title="对白试探",
                category="dialogue",
                scene_type="悬疑",
                rule_text="对白必须有试探。",
                prompt_instruction="每两轮对白释放一个新信息。",
            ),
            StyleTechniqueCard(
                profile_id=profile.id,
                title="禁用总结",
                category="anti_ai",
                rule_text="不要总结式抒情。",
                prompt_instruction="用动作和选择表现情绪，不写总结。",
                enabled=False,
            ),
        ],
    )

    enabled_cards = repo.list_technique_cards(profile.id, enabled=True)
    assert [card.title for card in enabled_cards] == ["对白试探"]

    cards[0].disable()
    repo.update_technique_card(cards[0])

    assert repo.list_technique_cards(profile.id, enabled=True) == []
    assert [card.enabled for card in repo.list_technique_cards(profile.id)] == [False, False]


def test_database_connection_creates_style_bible_tables_for_empty_database(tmp_path):
    db = DatabaseConnection(str(tmp_path / "empty-style-bible.db"))

    table_names = {
        row["name"]
        for row in db.fetch_all(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name LIKE 'style_%'
            """
        )
    }

    assert {
        "style_samples",
        "style_sample_chunks",
        "style_profiles",
        "style_technique_cards",
    }.issubset(table_names)
