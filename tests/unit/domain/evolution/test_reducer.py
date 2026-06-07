from domain.evolution.models import EvolutionAction, EvolutionState
from domain.evolution.reducer import EvolutionReducer


def test_reducer_is_idempotent_for_action_id():
    reducer = EvolutionReducer()
    opening = EvolutionState.empty()
    action = EvolutionAction(
        action_id="a1",
        type="MOVE_CHARACTER",
        payload={"character_id": "顾言之", "to_location": "皇城东门"},
    )

    state, errors = reducer.reduce(opening, [action, action])

    assert errors == []
    assert state.characters["顾言之"]["location"] == "皇城东门"
    assert state.applied_action_ids == ["a1"]


def test_dead_character_cannot_move_and_state_is_not_polluted():
    reducer = EvolutionReducer()
    opening = EvolutionState.empty()
    opening.characters["顾言之"] = {"status": "dead", "location": "悬崖底", "inventory": []}

    state, errors = reducer.reduce(
        opening,
        [
            EvolutionAction(
                action_id="a2",
                type="MOVE_CHARACTER",
                payload={"character_id": "顾言之", "to_location": "地牢"},
            )
        ],
    )

    assert len(errors) == 1
    assert state.characters["顾言之"]["location"] == "悬崖底"
    assert state.applied_action_ids == []


def test_ambiguous_status_is_supported():
    state, errors = EvolutionReducer().reduce(
        EvolutionState.empty(),
        [
            EvolutionAction(
                action_id="a3",
                type="SET_CHARACTER_STATUS",
                payload={"character_id": "乔知诺", "status": "ambiguous"},
            )
        ],
    )

    assert errors == []
    assert state.characters["乔知诺"]["status"] == "ambiguous"


def test_llm_cannot_resolve_debt_directly():
    state, errors = EvolutionReducer().reduce(
        EvolutionState.empty(),
        [
            EvolutionAction(
                action_id="a4",
                type="UPDATE_DEBT_PROGRESS",
                payload={"debt_id": "debt_key", "status": "resolved"},
            )
        ],
    )

    assert len(errors) == 1
    assert "debt_key" not in state.debts
