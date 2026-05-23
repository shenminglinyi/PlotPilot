from __future__ import annotations

from typing import Iterable, List, Tuple

from domain.evolution.contracts import ActionType, CharacterStatus
from domain.evolution.models import CHARACTER_STATUSES, EvolutionAction, EvolutionState, ReducerError


class EvolutionReducer:
    """Pure reducer for schema-first narrative state.

    Invalid actions produce errors and leave state untouched for that action.
    Applied action ids make replay idempotent.
    """

    def reduce(
        self,
        opening_state: EvolutionState,
        actions: Iterable[EvolutionAction],
    ) -> Tuple[EvolutionState, List[ReducerError]]:
        state = opening_state.clone()
        errors: List[ReducerError] = []
        seen = set(state.applied_action_ids)

        for action in actions:
            if not action.action_id:
                errors.append(ReducerError("", action.type, "action_id is required"))
                continue
            if action.action_id in seen:
                continue
            before = state.clone()
            try:
                self._apply(state, action)
            except ValueError as exc:
                state = before
                errors.append(ReducerError(action.action_id, action.type, str(exc)))
                continue
            seen.add(action.action_id)
            state.applied_action_ids.append(action.action_id)

        return state, errors

    def _apply(self, state: EvolutionState, action: EvolutionAction) -> None:
        typ = action.type
        payload = action.payload or {}

        if typ == ActionType.MOVE_CHARACTER.value:
            char_id = self._require(payload, "character_id")
            to_location = self._require(payload, "to_location")
            char = state.characters.setdefault(char_id, self._default_character())
            if char.get("status") == CharacterStatus.DEAD.value:
                raise ValueError(f"cannot move dead character {char_id}")
            char["location"] = to_location
            return

        if typ == ActionType.SET_CHARACTER_STATUS.value:
            char_id = self._require(payload, "character_id")
            status = self._require(payload, "status")
            if status not in CHARACTER_STATUSES:
                raise ValueError(f"unknown character status: {status}")
            char = state.characters.setdefault(char_id, self._default_character())
            char["status"] = status
            return

        if typ == ActionType.TRANSFER_ITEM.value:
            item_id = self._require(payload, "item_id")
            to_id = payload.get("to_id")
            item = state.items.setdefault(item_id, self._default_item())
            item["owner_id"] = to_id
            if to_id:
                char = state.characters.setdefault(str(to_id), self._default_character())
                inv = char.setdefault("inventory", [])
                if item_id not in inv:
                    inv.append(item_id)
            from_id = payload.get("from_id")
            if from_id and str(from_id) in state.characters:
                inv = state.characters[str(from_id)].setdefault("inventory", [])
                state.characters[str(from_id)]["inventory"] = [x for x in inv if x != item_id]
            return

        if typ == ActionType.REVEAL_FACT.value:
            fact_id = self._require(payload, "fact_id")
            target = payload.get("target", "reader")
            if target == "reader":
                self._append_unique(state.facts.setdefault("reader_known", []), fact_id)
            elif target == "character":
                for char_id in payload.get("character_ids") or []:
                    known = state.facts.setdefault("character_known", {}).setdefault(str(char_id), [])
                    self._append_unique(known, fact_id)
            else:
                raise ValueError(f"unknown fact reveal target: {target}")
            return

        if typ == ActionType.UPDATE_DEBT_PROGRESS.value:
            debt_id = self._require(payload, "debt_id")
            debt = state.debts.setdefault(debt_id, {"progress": [], "status": "open"})
            if payload.get("status") in {"resolved", "abandoned"}:
                raise ValueError("LLM cannot directly close narrative debts")
            delta = payload.get("progress_delta")
            if delta:
                debt.setdefault("progress", []).append(str(delta))
            return

        if typ == ActionType.UPDATE_STORYLINE_PROGRESS.value:
            storyline_id = self._require(payload, "storyline_id")
            story = state.storylines.setdefault(storyline_id, {"progress": [], "status": "active"})
            if payload.get("status") in {"completed", "abandoned"}:
                raise ValueError("LLM cannot directly close storylines")
            delta = payload.get("progress_delta") or payload.get("milestone")
            if delta:
                story.setdefault("progress", []).append(str(delta))
            return

        if typ == ActionType.SET_SCENE_STATE.value:
            for key in ["time_anchor", "location"]:
                if key in payload and payload[key] is not None:
                    state.scene[key] = str(payload[key])
            if "unresolved_actions" in payload:
                state.scene["unresolved_actions"] = list(payload.get("unresolved_actions") or [])
            if "narrative_modifiers" in payload:
                state.scene["narrative_modifiers"] = list(payload.get("narrative_modifiers") or [])
            if "emotional_residue" in payload:
                state.scene["emotional_residue"] = str(payload.get("emotional_residue") or "")
            return

        if typ == ActionType.SET_EMOTIONAL_RESIDUE.value:
            state.scene["emotional_residue"] = str(payload.get("description") or "")
            return

        if typ == ActionType.COMPLETE_EVENT.value:
            event_id = self._require(payload, "event_id")
            self._append_unique(state.completed_events, event_id)
            return

        raise ValueError(f"unknown action type: {typ}")

    @staticmethod
    def _default_character() -> dict:
        return {"location": "", "status": "alive", "inventory": [], "known_facts": []}

    @staticmethod
    def _default_item() -> dict:
        return {"owner_id": None, "location": "", "status": "unknown"}

    @staticmethod
    def _require(payload: dict, key: str) -> str:
        value = payload.get(key)
        if value is None or str(value).strip() == "":
            raise ValueError(f"{key} is required")
        return str(value)

    @staticmethod
    def _append_unique(values: list, value: str) -> None:
        if value not in values:
            values.append(value)
