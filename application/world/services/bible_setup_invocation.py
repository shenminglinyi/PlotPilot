"""Bible onboarding AI Invocation contracts."""
from __future__ import annotations

from typing import Any, Mapping

from application.ai_invocation.dtos import InvocationPolicy, InvocationSpec, VariableBinding
from application.ai_invocation.prompt_assembler import CPMSPromptAssembler
from application.ai_invocation.prompt_runtime import runtime_prompt_value_names_for_spec
from application.ai_invocation.prompt_variables import (
    infer_variable_scope,
    infer_variable_stage,
    normalize_declared_variable_keys,
    prompt_declared_variable_keys,
)
from application.ai_invocation.spec_service import InMemoryInvocationSpecRepository, InvocationSpecService
from application.ai_invocation.variable_hub import InMemoryVariableHubRepository, VariableResolver
from application.world.services.bible_setup_output_bindings import ensure_bible_setup_output_bindings
from infrastructure.ai.prompt_keys import BIBLE_CHARACTERS, BIBLE_LOCATIONS, BIBLE_WORLDBUILDING
from infrastructure.ai.prompt_registry import get_prompt_registry

BIBLE_SETUP_WORLD_NODE = BIBLE_WORLDBUILDING
BIBLE_SETUP_CHARACTERS_NODE = BIBLE_CHARACTERS
BIBLE_SETUP_LOCATIONS_NODE = BIBLE_LOCATIONS

_BINDING_SET_BY_NODE = {
    BIBLE_SETUP_WORLD_NODE: f"{BIBLE_SETUP_WORLD_NODE}:input:v1",
    BIBLE_SETUP_CHARACTERS_NODE: f"{BIBLE_SETUP_CHARACTERS_NODE}:input:v1",
    BIBLE_SETUP_LOCATIONS_NODE: f"{BIBLE_SETUP_LOCATIONS_NODE}:input:v1",
}

_DISPLAY_NAMES = {
    "novel.title": "书名",
    "novel.premise": "故事创意",
    "novel.genre_major": "类型大类",
    "novel.genre_theme": "类型主题",
    "novel.genre_label": "类型标签",
    "novel.world_preset": "世界基调",
    "novel.story_structure": "剧情结构",
    "novel.pacing_control": "节奏把控",
    "novel.writing_style": "写作风格",
    "novel.special_requirements": "特殊要求",
    "novel.target_chapters": "目标章节数",
    "novel.target_words_per_chapter": "每章目标字数",
    "worldbuilding.style": "文风公约",
    "worldbuilding.content": "世界观",
    "characters.list": "角色列表",
    "characters.protagonist": "主角",
    "locations.list": "地点列表",
}

_VALUE_TYPES = {
    "worldbuilding.content": "object",
    "characters.list": "list",
    "characters.protagonist": "object",
    "locations.list": "list",
}

_OPTIONAL_KEYS_BY_NODE = {
    BIBLE_SETUP_WORLD_NODE: {
        "novel.genre_major",
        "novel.genre_theme",
        "novel.genre_label",
        "novel.world_preset",
        "novel.story_structure",
        "novel.pacing_control",
        "novel.writing_style",
        "novel.special_requirements",
        "novel.target_words_per_chapter",
    },
    BIBLE_SETUP_CHARACTERS_NODE: {
        "novel.genre_major",
        "novel.genre_theme",
        "novel.genre_label",
        "novel.world_preset",
        "novel.story_structure",
        "novel.pacing_control",
        "novel.writing_style",
        "novel.special_requirements",
        "novel.target_words_per_chapter",
        "characters.list",
    },
    BIBLE_SETUP_LOCATIONS_NODE: {
        "novel.genre_major",
        "novel.genre_theme",
        "novel.genre_label",
        "novel.world_preset",
        "novel.story_structure",
        "novel.pacing_control",
        "novel.writing_style",
        "novel.special_requirements",
        "novel.target_words_per_chapter",
    },
}

_FALLBACK_KEYS_BY_NODE = {
    BIBLE_SETUP_WORLD_NODE: {
        "novel.title",
        "novel.premise",
        "novel.genre_major",
        "novel.genre_theme",
        "novel.genre_label",
        "novel.world_preset",
        "novel.story_structure",
        "novel.pacing_control",
        "novel.writing_style",
        "novel.special_requirements",
        "novel.target_chapters",
        "novel.target_words_per_chapter",
    },
    BIBLE_SETUP_CHARACTERS_NODE: {
        "novel.title",
        "novel.premise",
        "novel.genre_major",
        "novel.genre_theme",
        "novel.genre_label",
        "novel.world_preset",
        "novel.story_structure",
        "novel.pacing_control",
        "novel.writing_style",
        "novel.special_requirements",
        "novel.target_chapters",
        "novel.target_words_per_chapter",
        "worldbuilding.style",
        "worldbuilding.content",
        "characters.list",
    },
    BIBLE_SETUP_LOCATIONS_NODE: {
        "novel.title",
        "novel.premise",
        "novel.genre_major",
        "novel.genre_theme",
        "novel.genre_label",
        "novel.world_preset",
        "novel.story_structure",
        "novel.pacing_control",
        "novel.writing_style",
        "novel.special_requirements",
        "novel.target_chapters",
        "novel.target_words_per_chapter",
        "worldbuilding.content",
        "characters.list",
    },
}

_REQUEST_ALIAS_TO_VARIABLE_KEY = {
    "novel_title": "novel.title",
    "title": "novel.title",
    "premise": "novel.premise",
    "genre_major": "novel.genre_major",
    "genre_theme": "novel.genre_theme",
    "genre_label": "novel.genre_label",
    "world_preset": "novel.world_preset",
    "special_requirements": "novel.special_requirements",
    "target_chapters": "novel.target_chapters",
    "target_words_per_chapter": "novel.target_words_per_chapter",
}

def _ensure_node_synced(node_key: str) -> None:
    try:
        from infrastructure.ai.prompt_package_sync import force_sync_builtin_prompt_node
        from infrastructure.persistence.database.connection import get_database

        force_sync_builtin_prompt_node(
            get_database(),
            node_key=node_key,
            change_summary="变量中心最终重构同步",
        )
    except Exception:
        pass


def _active_version_id(node_key: str) -> str:
    _ensure_node_synced(node_key)
    node = get_prompt_registry().get_node(node_key)
    if node is None:
        raise RuntimeError(f"CPMS 节点未发布: {node_key}")
    node_version_id = str(getattr(node, "active_version_id", None) or "")
    if not node_version_id:
        raise RuntimeError(f"CPMS 节点缺少 active version: {node_key}")
    return node_version_id


def _declared_variable_keys(node_key: str) -> set[str]:
    _ensure_node_synced(node_key)
    node = get_prompt_registry().get_node(node_key)
    if node is None:
        raise RuntimeError(f"CPMS 节点未发布: {node_key}")
    return prompt_declared_variable_keys(
        node.get_active_system(),
        node.get_active_user_template(),
    )


def _default_for(variable_key: str) -> Any:
    value_type = _VALUE_TYPES.get(variable_key, "string")
    if value_type == "list":
        return []
    if value_type == "object":
        return {}
    return ""


def bible_setup_input_bindings(node_key: str) -> list[VariableBinding]:
    optional_keys = _OPTIONAL_KEYS_BY_NODE.get(node_key, set())
    runtime_template_keys = runtime_prompt_value_names_for_spec(
        InvocationSpec(operation=f"bible.setup.{node_key.removeprefix('bible-')}", node_key=node_key)
    )
    known_variable_keys = set(_DISPLAY_NAMES) | set(_VALUE_TYPES) | optional_keys
    declared_keys = normalize_declared_variable_keys(
        _declared_variable_keys(node_key),
        known_variable_keys,
    )
    declared_keys.update(_FALLBACK_KEYS_BY_NODE.get(node_key, set()))
    declared_keys = {
        _REQUEST_ALIAS_TO_VARIABLE_KEY.get(variable_key, variable_key)
        for variable_key in declared_keys
        if variable_key not in runtime_template_keys
    }
    return [
        VariableBinding(
            alias=variable_key,
            variable_key=variable_key,
            required=variable_key not in optional_keys,
            default=_default_for(variable_key) if variable_key in optional_keys else None,
            source="cpms_template",
            value_type=_VALUE_TYPES.get(variable_key, "string"),
            scope=infer_variable_scope(variable_key),
            stage=infer_variable_stage(variable_key),
            display_name=_DISPLAY_NAMES.get(variable_key, variable_key),
        )
        for variable_key in sorted(declared_keys)
    ]


def bible_setup_world_spec() -> InvocationSpec:
    return InvocationSpec(
        operation="bible.setup.worldbuilding",
        node_key=BIBLE_SETUP_WORLD_NODE,
        prompt_node_version_id=_active_version_id(BIBLE_WORLDBUILDING),
        asset_link_set_id="",
        input_binding_set_id=f"{BIBLE_SETUP_WORLD_NODE}:input:v1",
        output_binding_set_id=f"{BIBLE_SETUP_WORLD_NODE}:output:v1",
        default_policy=InvocationPolicy.FULL_INTERACTIVE,
        risk_level="low",
        supports_stream=True,
        continuation_handler_key="bible_worldbuilding",
        metadata={
            "source": "novel_setup_guide",
            "bible_prompt_key": BIBLE_WORLDBUILDING,
            "required_outputs": ["style", "worldbuilding"],
        },
    )


def bible_setup_characters_spec() -> InvocationSpec:
    return InvocationSpec(
        operation="bible.setup.characters",
        node_key=BIBLE_SETUP_CHARACTERS_NODE,
        prompt_node_version_id=_active_version_id(BIBLE_CHARACTERS),
        asset_link_set_id="",
        input_binding_set_id=f"{BIBLE_SETUP_CHARACTERS_NODE}:input:v1",
        output_binding_set_id=f"{BIBLE_SETUP_CHARACTERS_NODE}:output:v1",
        default_policy=InvocationPolicy.FULL_INTERACTIVE,
        risk_level="low",
        supports_stream=True,
        continuation_handler_key="bible_characters",
        metadata={
            "source": "novel_setup_guide",
            "bible_prompt_key": BIBLE_CHARACTERS,
            "required_outputs": ["characters"],
        },
    )


def bible_setup_locations_spec() -> InvocationSpec:
    return InvocationSpec(
        operation="bible.setup.locations",
        node_key=BIBLE_SETUP_LOCATIONS_NODE,
        prompt_node_version_id=_active_version_id(BIBLE_LOCATIONS),
        asset_link_set_id="",
        input_binding_set_id=f"{BIBLE_SETUP_LOCATIONS_NODE}:input:v1",
        output_binding_set_id=f"{BIBLE_SETUP_LOCATIONS_NODE}:output:v1",
        default_policy=InvocationPolicy.FULL_INTERACTIVE,
        risk_level="low",
        supports_stream=True,
        continuation_handler_key="bible_locations",
        metadata={
            "source": "novel_setup_guide",
            "bible_prompt_key": BIBLE_LOCATIONS,
            "required_outputs": ["locations"],
        },
    )


def ensure_bible_setup_specs(service: InvocationSpecService) -> None:
    repo = getattr(service, "_repository", None)
    if repo is None or not hasattr(repo, "add"):
        return
    for spec in (bible_setup_world_spec(), bible_setup_characters_spec(), bible_setup_locations_spec()):
        repo.add(spec)


def build_bible_setup_spec_service() -> InvocationSpecService:
    return InvocationSpecService(
        InMemoryInvocationSpecRepository(
            [bible_setup_world_spec(), bible_setup_characters_spec(), bible_setup_locations_spec()]
        )
    )


def build_bible_setup_variable_resolver() -> VariableResolver:
    repo = InMemoryVariableHubRepository()
    for node_key, binding_set_id in _BINDING_SET_BY_NODE.items():
        repo.set_bindings(binding_set_id, node_key, bible_setup_input_bindings(node_key))
    ensure_bible_setup_output_bindings(repo)
    return VariableResolver(repo)


def ensure_bible_setup_contract(db, *, operation: str, node_key: str) -> InvocationSpec:
    from infrastructure.ai.prompt_manager import get_prompt_manager
    from infrastructure.ai.prompt_package_sync import force_sync_builtin_prompt_node
    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )
    from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue

    get_prompt_manager().ensure_seeded()
    force_sync_builtin_prompt_node(
        db,
        node_key=node_key,
        change_summary="变量中心最终重构同步",
    )
    spec_factory_by_operation = {
        "bible.setup.worldbuilding": bible_setup_world_spec,
        "bible.setup.characters": bible_setup_characters_spec,
        "bible.setup.locations": bible_setup_locations_spec,
    }
    factory = spec_factory_by_operation.get(operation)
    if factory is None:
        raise ValueError(f"unsupported bible setup operation: {operation}")
    spec = factory()
    if spec.node_key != node_key:
        raise ValueError(f"unsupported bible setup node: operation={operation}, node_key={node_key}")

    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(
            spec.input_binding_set_id,
            spec.node_key,
            bible_setup_input_bindings(spec.node_key),
            direction="input",
        )
        ensure_bible_setup_output_bindings(variable_repo, spec.node_key)
        SqliteInvocationSpecRepository(db).upsert(
            spec,
            spec_id=f"spec:{spec.node_key}:v1",
            spec_version=1,
            status="published",
        )
    return spec


class BibleSetupPromptAssembler(CPMSPromptAssembler):
    """Bible setup prompts are compiled directly from the published CPMS node."""


def build_bible_setup_variables(
    *,
    stage: str,
    novel: Any,
    bible_service: Any,
    worldbuilding_service: Any,
) -> Mapping[str, Any]:
    # Onboarding prompt facts come from Variable Hub only. The legacy context
    # provider is kept as an empty adapter so stage definitions remain stable.
    return {}
