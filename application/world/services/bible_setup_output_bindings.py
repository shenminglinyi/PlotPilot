"""Output bindings for setup-guide Bible AI Invocation nodes."""
from __future__ import annotations

from typing import Any

from application.ai_invocation.dtos import VariableBinding
from infrastructure.ai.prompt_keys import BIBLE_CHARACTERS, BIBLE_LOCATIONS, BIBLE_WORLDBUILDING

BIBLE_SETUP_WORLD_NODE = BIBLE_WORLDBUILDING
BIBLE_SETUP_CHARACTERS_NODE = BIBLE_CHARACTERS
BIBLE_SETUP_LOCATIONS_NODE = BIBLE_LOCATIONS

OUTPUT_BINDING_SET_BY_NODE = {
    BIBLE_SETUP_WORLD_NODE: f"{BIBLE_SETUP_WORLD_NODE}:output:v1",
    BIBLE_SETUP_CHARACTERS_NODE: f"{BIBLE_SETUP_CHARACTERS_NODE}:output:v1",
    BIBLE_SETUP_LOCATIONS_NODE: f"{BIBLE_SETUP_LOCATIONS_NODE}:output:v1",
}


def bible_setup_output_bindings(node_key: str) -> list[VariableBinding]:
    if node_key == BIBLE_SETUP_WORLD_NODE:
        return [
            VariableBinding(
                alias="style",
                variable_key="novel.style.guide",
                value_type="string",
                display_name="文风公约",
                scope="global",
                stage="setup",
            ),
            VariableBinding(
                alias="worldbuilding",
                variable_key="novel.worldbuilding",
                value_type="object",
                display_name="世界观",
                scope="global",
                stage="worldbuilding",
            ),
            VariableBinding(
                alias="core_rules",
                variable_key="novel.worldbuilding.core_rules",
                value_type="object",
                display_name="核心法则",
                scope="global",
                stage="worldbuilding",
            ),
            VariableBinding(
                alias="geography",
                variable_key="novel.worldbuilding.geography",
                value_type="object",
                display_name="地理生态",
                scope="global",
                stage="worldbuilding",
            ),
            VariableBinding(
                alias="society",
                variable_key="novel.worldbuilding.society",
                value_type="object",
                display_name="社会结构",
                scope="global",
                stage="worldbuilding",
            ),
            VariableBinding(
                alias="culture",
                variable_key="novel.worldbuilding.culture",
                value_type="object",
                display_name="历史文化",
                scope="global",
                stage="worldbuilding",
            ),
            VariableBinding(
                alias="daily_life",
                variable_key="novel.worldbuilding.daily_life",
                value_type="object",
                display_name="沉浸感细节",
                scope="global",
                stage="worldbuilding",
            ),
        ]
    if node_key == BIBLE_SETUP_CHARACTERS_NODE:
        return [
            VariableBinding(
                alias="characters",
                variable_key="novel.characters.list",
                value_type="list",
                display_name="角色列表",
                scope="global",
                stage="characters",
            ),
            VariableBinding(
                alias="protagonist",
                variable_key="novel.characters.protagonist",
                value_type="object",
                display_name="主角",
                scope="global",
                stage="characters",
            ),
        ]
    if node_key == BIBLE_SETUP_LOCATIONS_NODE:
        return [
            VariableBinding(
                alias="locations",
                variable_key="novel.locations.list",
                value_type="list",
                display_name="地点列表",
                scope="global",
                stage="locations",
            ),
        ]
    return []


def ensure_bible_setup_output_bindings(repo: Any, node_key: str | None = None) -> None:
    if repo is None or not hasattr(repo, "set_bindings"):
        return
    node_keys = [node_key] if node_key else list(OUTPUT_BINDING_SET_BY_NODE)
    for key in node_keys:
        binding_set_id = OUTPUT_BINDING_SET_BY_NODE.get(str(key))
        bindings = bible_setup_output_bindings(str(key))
        if binding_set_id and bindings:
            repo.set_bindings(binding_set_id, str(key), bindings, direction="output")
