"""写作手法知识库风格档案服务测试。"""

from application.style_bible.dtos import (
    StyleProfileGenerateRequestDTO,
    StyleSampleImportRequestDTO,
)
from application.style_bible.services.style_profile_service import StyleProfileService
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_style_bible_repository import (
    SqliteStyleBibleRepository,
)


def _service(tmp_path) -> StyleProfileService:
    db = DatabaseConnection(str(tmp_path / "style-profile.db"))
    return StyleProfileService(SqliteStyleBibleRepository(db))


def test_style_profile_service_imports_sample_and_creates_profile(tmp_path):
    service = _service(tmp_path)
    result = service.import_sample(
        StyleSampleImportRequestDTO(
            title="雨夜样本",
            content="第1章 雨夜\n\n雨落在窗上。\n\n“你来了？”他低声问。\n\n她心里一紧。",
            novel_id="novel-1",
            scene_type="悬疑",
            allowed_for_generation=True,
            create_profile=True,
            profile_name="克制悬疑",
        )
    )

    assert result.sample.title == "雨夜样本"
    assert result.sample.allowed_for_generation is True
    assert len(result.chunks) >= 3
    assert result.chunks[0].metrics["avg_sentence_length"] > 0
    assert result.profile is not None
    assert result.profile.name == "克制悬疑"
    assert {card.category for card in result.cards}.issuperset({"pacing", "dialogue"})


def test_style_profile_service_generates_fallback_cards_without_llm(tmp_path):
    service = _service(tmp_path)
    imported = service.import_sample(
        StyleSampleImportRequestDTO(
            title="反AI样本",
            content="林晚推开门。空气仿佛凝固，他眼中闪过一丝复杂。",
            novel_id="novel-1",
            allowed_for_generation=True,
        )
    )

    result = service.generate_profile_from_samples(
        StyleProfileGenerateRequestDTO(
            novel_id="novel-1",
            name="去AI味短句",
            sample_ids=[imported.sample.id],
            use_llm=True,
        )
    )

    assert result.profile.name == "去AI味短句"
    assert result.profile.metrics["sample_count"] == 1
    assert {card.category for card in result.cards}.issuperset({"pacing", "anti_ai", "hook"})
    assert any("不要" in card.prompt_instruction for card in result.cards)


def test_style_profile_service_normalizes_llm_payload_shapes(tmp_path):
    service = _service(tmp_path)
    payload = service.normalize_llm_profile_payload(
        {
            "profile_summary": ["短句", "悬疑"],
            "rhythm_rules": {"a": "每段有推进"},
            "forbidden_patterns": "五味杂陈",
            "technique_cards": [
                {
                    "title": ["对白试探"],
                    "category": ["dialogue"],
                    "scene_type": {"name": "悬疑"},
                    "rule_text": ["对白必须互相试探"],
                    "example_summary": {"summary": "用问句推进"},
                    "prompt_instruction": ["每两轮对白释放一个新信息"],
                }
            ],
        }
    )

    assert payload["profile_summary"] == "短句；悬疑"
    assert payload["rhythm_rules"] == ["每段有推进"]
    assert payload["forbidden_patterns"] == ["五味杂陈"]
    assert payload["technique_cards"][0]["title"] == "对白试探"
    assert payload["technique_cards"][0]["scene_type"] == "悬疑"


def test_style_profile_service_analyzes_samples_not_allowed_for_generation(tmp_path):
    service = _service(tmp_path)
    imported = service.import_sample(
        StyleSampleImportRequestDTO(
            title="只分析样本",
            content="风从窗外吹进来。\n\n她意识到门外有人。",
            novel_id="novel-1",
            allowed_for_generation=False,
        )
    )

    result = service.generate_profile_from_samples(
        StyleProfileGenerateRequestDTO(
            novel_id="novel-1",
            name="只学习手法",
            sample_ids=[imported.sample.id],
        )
    )

    assert imported.sample.allowed_for_generation is False
    assert imported.chunks[0].metrics["environment_ratio"] > 0
    assert result.profile.id
    assert result.cards
