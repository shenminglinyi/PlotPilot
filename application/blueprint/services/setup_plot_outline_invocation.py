"""AI Invocation contract for the setup-guide plot outline stage."""
from __future__ import annotations

import json
from typing import Any, Mapping

from application.ai_invocation.dtos import InvocationPolicy, InvocationSpec, VariableBinding
from application.ai_invocation.prompt_variables import (
    infer_variable_scope,
    infer_variable_stage,
    normalize_declared_variable_keys,
    prompt_declared_variable_keys,
)
from application.blueprint.services.setup_plot_outline_continuation import register_setup_plot_outline_continuation
from infrastructure.ai.prompt_keys import PLANNING_PLOT_OUTLINE
from infrastructure.ai.prompt_registry import get_prompt_registry
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue

SETUP_PLOT_OUTLINE_STAGE = "plot_outline"
SETUP_PLOT_OUTLINE_OPERATION = "setup.plot_outline"
SETUP_PLOT_OUTLINE_NODE = PLANNING_PLOT_OUTLINE


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

def setup_plot_outline_input_bindings() -> list[VariableBinding]:
    display_names = {
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
        "characters.protagonist": "主角",
        "characters.list": "角色列表",
        "locations.list": "地点列表",
        "worldbuilding.style": "文风公约",
        "worldbuilding.content": "世界观",
    }
    value_types = {
        "characters.protagonist": "object",
        "characters.list": "list",
        "locations.list": "list",
        "worldbuilding.content": "object",
    }
    optional_keys = {
        "novel.genre_major",
        "novel.genre_theme",
        "novel.genre_label",
        "novel.world_preset",
        "novel.story_structure",
        "novel.pacing_control",
        "novel.writing_style",
        "novel.special_requirements",
        "novel.target_words_per_chapter",
    }
    known_variable_keys = set(display_names) | set(value_types) | optional_keys
    declared_keys = normalize_declared_variable_keys(
        _declared_variable_keys(SETUP_PLOT_OUTLINE_NODE),
        known_variable_keys,
    )
    return [
        VariableBinding(
            alias=variable_key,
            variable_key=variable_key,
            required=variable_key not in optional_keys,
            default=(
                [] if value_types.get(variable_key) == "list"
                else {} if value_types.get(variable_key) == "object"
                else ""
            ) if variable_key in optional_keys else None,
            source="cpms_template",
            value_type=value_types.get(variable_key, "string"),
            scope=infer_variable_scope(variable_key),
            stage=infer_variable_stage(variable_key),
            display_name=display_names.get(variable_key, variable_key),
        )
        for variable_key in sorted(declared_keys)
    ]


def setup_plot_outline_output_bindings() -> list[VariableBinding]:
    return [
        VariableBinding(
            alias="plot_outline",
            variable_key="plot.outline",
            source_path="plot_outline",
            value_type="object",
            preview_source="continuation",
            display_name="剧情总纲",
            scope="novel",
            stage="planning",
            required=True,
        ),
        VariableBinding(
            alias="main_story_overview",
            variable_key="plot.main_story_overview",
            source_path="plot_outline.main_story_overview",
            value_type="string",
            preview_source="continuation",
            display_name="故事主线概述",
            scope="novel",
            stage="planning",
            required=False,
        ),
        VariableBinding(
            alias="stage_plan",
            variable_key="plot.stage_plan",
            source_path="plot_outline.stage_plan",
            value_type="list",
            preview_source="continuation",
            display_name="阶段规划",
            scope="novel",
            stage="planning",
            required=True,
        ),
        VariableBinding(
            alias="expected_ending",
            variable_key="plot.expected_ending",
            source_path="plot_outline.expected_ending",
            value_type="string",
            preview_source="continuation",
            display_name="预期结局",
            scope="novel",
            stage="planning",
            required=False,
        ),
        VariableBinding(
            alias="core_conflict",
            variable_key="plot.core_conflict",
            source_path="plot_outline.core_conflict",
            value_type="string",
            preview_source="continuation",
            display_name="核心冲突",
            scope="novel",
            stage="planning",
            required=False,
        ),
    ]


def setup_plot_outline_spec() -> InvocationSpec:
    return InvocationSpec(
        operation=SETUP_PLOT_OUTLINE_OPERATION,
        node_key=SETUP_PLOT_OUTLINE_NODE,
        prompt_node_version_id=_active_version_id(SETUP_PLOT_OUTLINE_NODE),
        input_binding_set_id=f"{SETUP_PLOT_OUTLINE_NODE}:input:v1",
        output_binding_set_id=f"{SETUP_PLOT_OUTLINE_NODE}:output:v1",
        default_policy=InvocationPolicy.FULL_INTERACTIVE,
        risk_level="low",
        supports_stream=True,
        continuation_handler_key="setup_plot_outline",
        metadata={
            "source": "novel_setup_guide",
            "cpms_node_key": SETUP_PLOT_OUTLINE_NODE,
            "required_outputs": ["plot_outline"],
            "output_contract_notes": [
                "输出必须是 JSON 对象，可由业务 continuation 归一化为 plot_outline",
                "业务 continuation 只消费结构化剧情总纲，不接收自由文本 context_blob",
            ],
        },
    )


def ensure_setup_plot_outline_contract(db) -> InvocationSpec:
    from infrastructure.ai.prompt_manager import get_prompt_manager
    from infrastructure.ai.prompt_package_sync import force_sync_builtin_prompt_node
    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    get_prompt_manager().ensure_seeded()
    force_sync_builtin_prompt_node(
        db,
        node_key=SETUP_PLOT_OUTLINE_NODE,
        change_summary="变量中心最终重构同步",
    )
    spec = setup_plot_outline_spec()
    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        existing_output_bindings = variable_repo.get_output_bindings(
            spec.output_binding_set_id,
            spec.node_key,
        )
        variable_repo.set_bindings(
            spec.input_binding_set_id,
            spec.node_key,
            setup_plot_outline_input_bindings(),
            direction="input",
        )
        variable_repo.set_bindings(
            spec.output_binding_set_id,
            spec.node_key,
            existing_output_bindings or setup_plot_outline_output_bindings(),
            direction="output",
        )
        SqliteInvocationSpecRepository(db).upsert(
            spec,
            spec_id=f"spec:{spec.node_key}:v1",
            spec_version=1,
            status="published",
        )
        register_setup_plot_outline_continuation()
    return spec


def build_setup_plot_outline_invocation_variables(ctx: Mapping[str, Any]) -> dict[str, Any]:
    return {}


def plot_outline_context_provider(*, setup_service: Any, novel_id: str) -> Mapping[str, Any]:
    return build_setup_plot_outline_invocation_variables(setup_service.build_context(novel_id))


def plot_outline_ui_events() -> Mapping[str, Any]:
    return {
        "sse_phase": {"type": "phase", "phase": "plot_outline", "message": "正在生成剧情总纲"},
        "review_event": "approval_required",
        "done_event": "done",
    }


def debug_contract_summary() -> str:
    return json.dumps(
        {
            "stage": SETUP_PLOT_OUTLINE_STAGE,
            "operation": SETUP_PLOT_OUTLINE_OPERATION,
            "node_key": SETUP_PLOT_OUTLINE_NODE,
            "input_aliases": [binding.alias for binding in setup_plot_outline_input_bindings()],
            "output_aliases": [binding.alias for binding in setup_plot_outline_output_bindings()],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
