from domain.novel.services.narrative_state_replay import replay_entity_state


def test_replay_add_and_remove():
    base = {"魔法": "水系"}
    events = [
        {"mutations": [{"attribute": "魔法", "action": "add", "value": "火系"}]},
        {
            "mutations": [
                {"attribute": "临时", "action": "add", "value": "x"},
                {"attribute": "临时", "action": "remove", "value": ""},
            ]
        },
    ]

    state = replay_entity_state(base, events)

    assert state["魔法"] == "火系"
    assert "临时" not in state


def test_replay_empty_events_returns_copy():
    base = {"魔法": "水系", "等级": "5"}

    state = replay_entity_state(base, [])

    assert state == base
    assert state is not base


def test_replay_unknown_action_is_ignored():
    base = {"魔法": "水系"}
    events = [
        {"mutations": [{"attribute": "魔法", "action": "unknown", "value": "火系"}]},
        {"mutations": [{"attribute": "等级", "action": "add", "value": "10"}]},
    ]

    state = replay_entity_state(base, events)

    assert state["魔法"] == "水系"
    assert state["等级"] == "10"


def test_replay_multiple_mutations_in_single_event():
    base = {"a": "1"}
    events = [
        {
            "mutations": [
                {"attribute": "b", "action": "add", "value": "2"},
                {"attribute": "c", "action": "add", "value": "3"},
                {"attribute": "a", "action": "remove", "value": ""},
            ]
        }
    ]

    state = replay_entity_state(base, events)

    assert "a" not in state
    assert state["b"] == "2"
    assert state["c"] == "3"


def test_replay_remove_nonexistent_attribute():
    base = {"魔法": "水系"}
    events = [
        {"mutations": [{"attribute": "不存在", "action": "remove", "value": ""}]}
    ]

    state = replay_entity_state(base, events)

    assert state == base


def test_replay_preserves_base_immutability():
    base = {"魔法": "水系"}
    original_base = base.copy()
    events = [
        {"mutations": [{"attribute": "魔法", "action": "add", "value": "火系"}]}
    ]

    state = replay_entity_state(base, events)

    assert base == original_base
    assert state["魔法"] == "火系"


def test_replay_filters_entity_scoped_mutations():
    state = replay_entity_state(
        {"status": "old"},
        [
            {
                "mutations": [
                    {
                        "entity_id": "prop-1",
                        "attribute": "status",
                        "action": "add",
                        "value": "active",
                    },
                    {
                        "entity_id": "prop-2",
                        "attribute": "status",
                        "action": "add",
                        "value": "lost",
                    },
                ]
            }
        ],
        target_entity_id="prop-1",
    )

    assert state["status"] == "active"


def test_replay_appends_list_mutations():
    state = replay_entity_state(
        {"related_props": [{"prop_id": "old"}]},
        [
            {
                "mutations": [
                    {
                        "entity_id": "char-1",
                        "attribute": "related_props",
                        "action": "append",
                        "value": {"prop_id": "prop-1"},
                    }
                ]
            }
        ],
        target_entity_id="char-1",
    )

    assert state["related_props"] == [{"prop_id": "old"}, {"prop_id": "prop-1"}]


def test_replay_append_unique_is_idempotent():
    value = {"prop_id": "prop-1", "relation": "used"}
    state = replay_entity_state(
        {"related_props": [value]},
        [
            {
                "mutations": [
                    {
                        "entity_id": "char-1",
                        "attribute": "related_props",
                        "action": "append_unique",
                        "value": value,
                    }
                ]
            }
        ],
        target_entity_id="char-1",
    )

    assert state["related_props"] == [value]
