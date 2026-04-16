from infrastructure.persistence.mappers.foreshadowing_mapper import ForeshadowingMapper


def test_from_dict_coerces_string_chapter_fields():
    data = {
        "id": "fr-1",
        "novel_id": "novel-1",
        "foreshadowings": [
            {
                "id": "f-1",
                "planted_in_chapter": "3",
                "description": "衣物被更换",
                "importance": 2,
                "status": "planted",
                "suggested_resolve_chapter": "8",
                "resolved_in_chapter": None,
            }
        ],
        "subtext_entries": [
            {
                "id": "s-1",
                "chapter": "4",
                "character_id": "char-1",
                "hidden_clue": "鞋底有泥",
                "sensory_anchors": {"visual": "泥点"},
                "status": "pending",
                "consumed_at_chapter": None,
                "suggested_resolve_chapter": "9",
                "resolve_chapter_window": "2",
                "importance": "high",
                "created_at": "2026-04-16T12:00:00",
            }
        ],
    }

    registry = ForeshadowingMapper.from_dict(data)

    foreshadowing = registry.get_by_id("f-1")
    assert foreshadowing is not None
    assert foreshadowing.planted_in_chapter == 3
    assert foreshadowing.suggested_resolve_chapter == 8

    subtext = registry.subtext_entries[0]
    assert subtext.chapter == 4
    assert subtext.suggested_resolve_chapter == 9
    assert subtext.resolve_chapter_window == 2
