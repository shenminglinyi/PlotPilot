"""AI Invocation contract for the setup-guide main plot stage."""
from __future__ import annotations

import json
from typing import Any, Mapping

from application.ai_invocation.dtos import InvocationPolicy, InvocationSpec, VariableBinding
from application.ai_invocation.variable_projection import render_variable_value
from application.blueprint.services.setup_main_plot_continuation import register_setup_main_plot_continuation
from application.blueprint.services.setup_main_plot_suggestion_service import SETUP_TASK_MARKER
from application.core.taxonomy.opening_profiles import resolve_opening_profile
from infrastructure.ai.prompt_keys import PLANNING_MAIN_PLOT_OPTION
from infrastructure.ai.prompt_registry import get_prompt_registry
from infrastructure.ai.prompt_template_engine import get_template_engine
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue

SETUP_MAIN_PLOT_STAGE = "main_plot"
SETUP_MAIN_PLOT_OPERATION = "setup.main_plot_options"
SETUP_MAIN_PLOT_NODE = PLANNING_MAIN_PLOT_OPTION


def _active_version_id(node_key: str) -> str:
    node = get_prompt_registry().get_node(node_key)
    if node is None:
        raise RuntimeError(f"CPMS 节点未发布: {node_key}")
    node_version_id = str(getattr(node, "active_version_id", None) or "")
    if not node_version_id:
        raise RuntimeError(f"CPMS 节点缺少 active version: {node_key}")
    return node_version_id


def _declared_aliases(node_key: str) -> set[str]:
    node = get_prompt_registry().get_node(node_key)
    if node is None:
        raise RuntimeError(f"CPMS 节点未发布: {node_key}")
    engine = get_template_engine()
    return (
        engine.extract_variables(node.get_active_system())
        | engine.extract_variables(node.get_active_user_template())
    )


def setup_main_plot_input_bindings() -> list[VariableBinding]:
    bindings: dict[str, VariableBinding] = {
        "novel_title": VariableBinding(
            alias="novel_title",
            variable_key="novel.setup.title",
            display_name="名称",
            value_type="string",
            scope="global",
            stage="setup",
            source="prompt_input",
        ),
        "premise": VariableBinding(
            alias="premise",
            variable_key="novel.setup.premise",
            display_name="设定",
            value_type="string",
            scope="global",
            stage="setup",
            source="prompt_input",
        ),
        "genre_major": VariableBinding(
            alias="genre_major",
            display_name="大类",
            value_type="string",
            scope="global",
            stage="setup",
            source="derived_config",
            default="",
        ),
        "genre_theme": VariableBinding(
            alias="genre_theme",
            display_name="主题",
            value_type="string",
            scope="global",
            stage="setup",
            source="derived_config",
            default="",
        ),
        "genre_label": VariableBinding(
            alias="genre_label",
            variable_key="novel.setup.genre_label",
            display_name="类型",
            value_type="string",
            scope="global",
            stage="setup",
            source="prompt_input",
        ),
        "world_preset": VariableBinding(
            alias="world_preset",
            variable_key="novel.setup.world_preset",
            display_name="基调",
            value_type="string",
            scope="global",
            stage="setup",
            source="prompt_input",
        ),
        "target_chapters": VariableBinding(
            alias="target_chapters",
            variable_key="novel.setup.target_chapters",
            display_name="章节数量",
            value_type="integer",
            scope="global",
            stage="setup",
            source="prompt_input",
            default=100,
        ),
        "target_words_per_chapter": VariableBinding(
            alias="target_words_per_chapter",
            variable_key="novel.setup.target_words_per_chapter",
            display_name="每章字数",
            value_type="integer",
            scope="global",
            stage="setup",
            source="prompt_input",
            default=0,
        ),
        "fusion_contract": VariableBinding(
            alias="fusion_contract",
            variable_key="novel.plot.fusion_contract",
            display_name="融合故事合同",
            value_type="string",
            scope="global",
            stage="planning",
            source="prompt_input",
            default="",
        ),
        "fusion_axis": VariableBinding(
            alias="fusion_axis",
            display_name="融合轴约束",
            value_type="object",
            scope="global",
            stage="planning",
            source="derived_config",
            default={},
        ),
        "genre_opening_profile": VariableBinding(
            alias="genre_opening_profile",
            display_name="类型开篇画像",
            value_type="object",
            scope="global",
            stage="planning",
            source="derived_config",
            default={},
        ),
        "genre_reader_contract": VariableBinding(
            alias="genre_reader_contract",
            display_name="读者留存契约",
            value_type="object",
            scope="global",
            stage="planning",
            source="derived_config",
            default={},
        ),
        "genre_rhythm_constraints": VariableBinding(
            alias="genre_rhythm_constraints",
            display_name="类型节奏约束",
            value_type="object",
            scope="global",
            stage="planning",
            source="derived_config",
            default={},
        ),
        "protagonist": VariableBinding(
            alias="protagonist",
            variable_key="novel.characters.protagonist",
            display_name="主角",
            value_type="object",
            scope="global",
            stage="characters",
            source="prompt_input",
            default={},
        ),
        "protagonist_card": VariableBinding(
            alias="protagonist_card",
            variable_key="novel.characters.protagonist",
            display_name="主角卡",
            value_type="string",
            scope="global",
            stage="characters",
            source="prompt_input",
            default="",
            projection_key="character.card",
            render_mode="projection",
        ),
        "characters": VariableBinding(
            alias="characters",
            variable_key="novel.characters.list",
            display_name="角色列表",
            value_type="list",
            scope="global",
            stage="characters",
            source="prompt_input",
            default=[],
        ),
        "characters_brief": VariableBinding(
            alias="characters_brief",
            variable_key="novel.characters.list",
            display_name="角色列表摘要",
            value_type="string",
            scope="global",
            stage="characters",
            source="prompt_input",
            default="",
            projection_key="characters.brief",
            render_mode="projection",
        ),
        "other_characters": VariableBinding(
            alias="other_characters",
            variable_key="novel.characters.list",
            display_name="其他角色",
            value_type="list",
            scope="global",
            stage="characters",
            source="prompt_input",
            default=[],
        ),
        "locations": VariableBinding(
            alias="locations",
            variable_key="novel.locations.list",
            display_name="地点列表",
            value_type="list",
            scope="global",
            stage="locations",
            source="prompt_input",
            default=[],
        ),
        "locations_brief": VariableBinding(
            alias="locations_brief",
            variable_key="novel.locations.list",
            display_name="地点列表摘要",
            value_type="string",
            scope="global",
            stage="locations",
            source="prompt_input",
            default="",
            projection_key="locations.brief",
            render_mode="projection",
        ),
        "worldview_summary": VariableBinding(
            alias="worldview_summary",
            display_name="世界观摘要",
            value_type="list",
            scope="global",
            stage="worldbuilding",
            source="prompt_input",
            default=[],
        ),
        "worldbuilding_context": VariableBinding(
            alias="worldbuilding_context",
            variable_key="novel.worldbuilding",
            display_name="世界观上下文",
            value_type="string",
            scope="global",
            stage="worldbuilding",
            source="prompt_input",
            default="",
            projection_key="worldbuilding.context",
            render_mode="projection",
        ),
        "style_hint": VariableBinding(
            alias="style_hint",
            variable_key="novel.style.guide",
            display_name="文风公约",
            value_type="string",
            scope="global",
            stage="setup",
            source="prompt_input",
            default="",
        ),
    }
    for alias, display_name in (
        ("core_rules", "核心法则"),
        ("geography", "地理生态"),
        ("society", "社会结构"),
        ("culture", "历史文化"),
        ("daily_life", "沉浸感细节"),
    ):
        bindings[alias] = VariableBinding(
            alias=alias,
            variable_key=f"novel.worldbuilding.{alias}",
            display_name=display_name,
            value_type="object",
            scope="global",
            stage="worldbuilding",
            source="prompt_input",
            default={},
        )

    for alias in _declared_aliases(SETUP_MAIN_PLOT_NODE):
        bindings.setdefault(
            alias,
            VariableBinding(
                alias=alias,
                required=False,
                default="",
                source="cpms_template",
                value_type="string",
                scope="global",
                stage="planning",
                display_name=alias,
            ),
        )
    return [bindings[alias] for alias in sorted(bindings)]


def setup_main_plot_output_bindings() -> list[VariableBinding]:
    return [
        VariableBinding(
            alias="plot_options",
            variable_key="novel.plot.main_options",
            value_type="list",
            display_name="主线候选",
            scope="global",
            stage="planning",
        ),
        VariableBinding(
            alias="plot_options_json",
            variable_key="novel.plot.main_options_json",
            value_type="string",
            display_name="主线候选 JSON",
            scope="global",
            stage="planning",
        ),
    ]


def setup_main_plot_spec() -> InvocationSpec:
    return InvocationSpec(
        operation=SETUP_MAIN_PLOT_OPERATION,
        node_key=SETUP_MAIN_PLOT_NODE,
        prompt_node_version_id=_active_version_id(SETUP_MAIN_PLOT_NODE),
        input_binding_set_id=f"{SETUP_MAIN_PLOT_NODE}:input:v1",
        output_binding_set_id=f"{SETUP_MAIN_PLOT_NODE}:output:v1",
        default_policy=InvocationPolicy.FULL_INTERACTIVE,
        risk_level="low",
        supports_stream=True,
        continuation_handler_key="setup_main_plot_options",
        metadata={
            "source": "novel_setup_guide",
            "cpms_node_key": SETUP_MAIN_PLOT_NODE,
            "setup_task_marker": SETUP_TASK_MARKER,
            "required_outputs": ["plot_options"],
            "output_contract_notes": [
                "输出必须是 JSON 对象，顶层字段为 plot_options",
                "业务 continuation 只消费结构化 plot_options，不接收 context_blob",
            ],
        },
    )


def ensure_setup_main_plot_contract(db) -> InvocationSpec:
    from infrastructure.ai.prompt_manager import get_prompt_manager
    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    get_prompt_manager().ensure_seeded()
    spec = setup_main_plot_spec()
    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(
            spec.input_binding_set_id,
            spec.node_key,
            setup_main_plot_input_bindings(),
            direction="input",
        )
        variable_repo.set_bindings(
            spec.output_binding_set_id,
            spec.node_key,
            setup_main_plot_output_bindings(),
            direction="output",
        )
        SqliteInvocationSpecRepository(db).upsert(
            spec,
            spec_id=f"spec:{spec.node_key}:v1",
            spec_version=1,
            status="published",
        )
        register_setup_main_plot_continuation()
    return spec


def build_setup_main_plot_invocation_variables(ctx: Mapping[str, Any]) -> dict[str, Any]:
    theme_metadata = ctx.get("theme_metadata") if isinstance(ctx.get("theme_metadata"), Mapping) else {}
    genre_label = str(theme_metadata.get("genre_label") or "").strip()
    genre_major, genre_theme = _split_genre_label(genre_label)
    resolved_profile = resolve_opening_profile(genre_label, strict=False)
    genre_profile = resolved_profile.as_variables() if resolved_profile is not None else {
        "genre_opening_profile": {},
        "genre_reader_contract": {},
        "genre_rhythm_constraints": {},
    }
    aliases = {
        "novel_title": str(ctx.get("novel_title") or "").strip(),
        "premise": str(ctx.get("premise") or "").strip(),
        "genre_major": genre_major,
        "genre_theme": genre_theme,
        "genre_label": genre_label,
        "world_preset": str(theme_metadata.get("world_preset") or "").strip(),
        "target_chapters": int(ctx.get("target_chapters") or 0),
        "target_words_per_chapter": int(ctx.get("target_words_per_chapter") or 0),
        "fusion_axis": ctx.get("fusion_axis") or {},
        "fusion_contract": str(ctx.get("fusion_contract") or ""),
        **genre_profile,
        "protagonist": ctx.get("protagonist") or {},
        "protagonist_card": render_variable_value(ctx.get("protagonist") or {}, projection_key="character.card", render_mode="projection"),
        "characters": ctx.get("characters") or ctx.get("other_characters") or [],
        "characters_brief": render_variable_value(ctx.get("characters") or ctx.get("other_characters") or [], projection_key="characters.brief", render_mode="projection"),
        "other_characters": ctx.get("other_characters") or [],
        "locations": ctx.get("locations") or [],
        "locations_brief": render_variable_value(ctx.get("locations") or [], projection_key="locations.brief", render_mode="projection"),
        "worldview_summary": ctx.get("worldview_summary") or [],
        "worldbuilding_context": render_variable_value(
            {
                "core_rules": ctx.get("core_rules") or {},
                "geography": ctx.get("geography") or {},
                "society": ctx.get("society") or {},
                "culture": ctx.get("culture") or {},
                "daily_life": ctx.get("daily_life") or {},
            },
            projection_key="worldbuilding.context",
            render_mode="projection",
        ),
        "style_hint": str(ctx.get("style_hint") or ""),
        "core_rules": ctx.get("core_rules") or {},
        "geography": ctx.get("geography") or {},
        "society": ctx.get("society") or {},
        "culture": ctx.get("culture") or {},
        "daily_life": ctx.get("daily_life") or {},
    }
    return aliases


def _split_genre_label(genre_label: str) -> tuple[str, str]:
    parts = [part.strip() for part in str(genre_label or "").split("/") if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], ""
    return "", ""


def main_plot_context_provider(*, setup_service: Any, novel_id: str) -> Mapping[str, Any]:
    return build_setup_main_plot_invocation_variables(setup_service.build_context(novel_id))


def main_plot_ui_events() -> Mapping[str, Any]:
    return {
        "sse_phase": {"type": "phase", "phase": "plot_options", "message": "正在生成叙事结构"},
        "review_event": "approval_required",
        "done_event": "done",
    }


def debug_contract_summary() -> str:
    return json.dumps(
        {
            "stage": SETUP_MAIN_PLOT_STAGE,
            "operation": SETUP_MAIN_PLOT_OPERATION,
            "node_key": SETUP_MAIN_PLOT_NODE,
            "input_aliases": [binding.alias for binding in setup_main_plot_input_bindings()],
            "output_aliases": [binding.alias for binding in setup_main_plot_output_bindings()],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
