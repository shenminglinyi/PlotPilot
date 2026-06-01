from types import SimpleNamespace

from application.audit.services.chapter_review_service import ChapterReviewService


def test_extract_characters_from_content_uses_cast_names_and_aliases():
    service = ChapterReviewService(
        chapter_repo=None,
        cast_repo=None,
        timeline_repo=None,
        storyline_repo=None,
        foreshadowing_repo=None,
        vector_store=None,
        llm_service=None,
    )
    characters = [
        SimpleNamespace(name="沈岚", aliases=["老沈"]),
        SimpleNamespace(name="顾明", aliases=[]),
    ]

    found = service._extract_characters_from_content(
        "老沈把证据递给顾明，顾明没有立刻接。",
        characters,
    )

    assert found == ["沈岚", "顾明"]
