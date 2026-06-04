"""AI Invocation contract for the setup-guide plot outline stage."""
from __future__ import annotations

import json
from typing import Any, Mapping

from application.ai_invocation.dtos import InvocationPolicy, InvocationSpec, VariableBinding
from application.ai_invocation.variable_projection import render_variable_value
from application.blueprint.services.setup_plot_outline_continuation import register_setup_plot_outline_continuation
from application.core.taxonomy.opening_profiles import resolve_opening_profile
from infrastructure.ai.prompt_keys import PLANNING_PLOT_OUTLINE
from infrastructure.ai.prompt_registry import get_prompt_registry
from infrastructure.ai.prompt_template_engine import get_template_engine
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue

SETUP_PLOT_OUTLINE_STAGE = "plot_outline"
SETUP_PLOT_OUTLINE_OPERATION = "setup.plot_outline"
SETUP_PLOT_OUTLINE_NODE = PLANNING_PLOT_OUTLINE
SETUP_PLOT_OUTLINE_PHASE_SCHEMA = [
    {"phase": "opening", "label": "开篇阶段", "range_percent": "1-15%"},
    {"phase": "development", "label": "发展阶段", "range_percent": "15-40%"},
    {"phase": "deepening", "label": "深化阶段", "range_percent": "40-70%"},
    {"phase": "climax", "label": "高潮阶段", "range_percent": "70-90%"},
    {"phase": "ending", "label": "收尾阶段", "range_percent": "90-100%"},
]


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


def _split_genre_label(genre_label: str) -> tuple[str, str]:
    parts = [part.strip() for part in str(genre_label or "").split("/") if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], ""
    return "", ""


def setup_plot_outline_input_bindings() -> list[VariableBinding]:
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
        "characters_brief": VariableBinding(
            alias="characters_brief",
            variable_key="novel.characters.list",
            display_name="角色摘要",
            value_type="string",
            scope="global",
            stage="characters",
            source="prompt_input",
            default="",
            projection_key="characters.brief",
            render_mode="projection",
        ),
        "locations_brief": VariableBinding(
            alias="locations_brief",
            variable_key="novel.locations.list",
            display_name="地点摘要",
            value_type="string",
            scope="global",
            stage="locations",
            source="prompt_input",
            default="",
            projection_key="locations.brief",
            render_mode="projection",
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
        "plot_outline_phase_schema": VariableBinding(
            alias="plot_outline_phase_schema",
            display_name="剧情阶段结构",
            value_type="list",
            scope="global",
            stage="planning",
            source="derived_config",
            default=SETUP_PLOT_OUTLINE_PHASE_SCHEMA,
        ),
        "core_rules": VariableBinding(
            alias="core_rules",
            variable_key="novel.worldbuilding.core_rules",
            display_name="核心法则",
            value_type="object",
            scope="global",
            stage="worldbuilding",
            source="prompt_input",
            default={},
        ),
        "geography": VariableBinding(
            alias="geography",
            variable_key="novel.worldbuilding.geography",
            display_name="地理生态",
            value_type="object",
            scope="global",
            stage="worldbuilding",
            source="prompt_input",
            default={},
        ),
        "society": VariableBinding(
            alias="society",
            variable_key="novel.worldbuilding.society",
            display_name="社会结构",
            value_type="object",
            scope="global",
            stage="worldbuilding",
            source="prompt_input",
            default={},
        ),
        "culture": VariableBinding(
            alias="culture",
            variable_key="novel.worldbuilding.culture",
            display_name="历史文化",
            value_type="object",
            scope="global",
            stage="worldbuilding",
            source="prompt_input",
            default={},
        ),
        "daily_life": VariableBinding(
            alias="daily_life",
            variable_key="novel.worldbuilding.daily_life",
            display_name="沉浸感细节",
            value_type="object",
            scope="global",
            stage="worldbuilding",
            source="prompt_input",
            default={},
        ),
    }

    for alias in _declared_aliases(SETUP_PLOT_OUTLINE_NODE):
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


def setup_plot_outline_output_bindings() -> list[VariableBinding]:
    return [
        VariableBinding(
            alias="plot_outline",
            variable_key="novel.plot.outline",
            source_path="plot_outline",
            value_type="object",
            display_name="剧情总纲",
            scope="global",
            stage="planning",
            required=True,
        ),
        VariableBinding(
            alias="main_story_overview",
            variable_key="novel.plot.main_story_overview",
            source_path="plot_outline.main_story_overview",
            value_type="string",
            display_name="故事主线概述",
            scope="global",
            stage="planning",
            required=True,
        ),
        VariableBinding(
            alias="stage_plan",
            variable_key="novel.plot.stage_plan",
            source_path="plot_outline.stage_plan",
            value_type="list",
            display_name="阶段规划",
            scope="global",
            stage="planning",
            required=True,
        ),
        VariableBinding(
            alias="expected_ending",
            variable_key="novel.plot.expected_ending",
            source_path="plot_outline.expected_ending",
            value_type="string",
            display_name="预期结局",
            scope="global",
            stage="planning",
            required=True,
        ),
        VariableBinding(
            alias="core_conflict",
            variable_key="novel.plot.core_conflict",
            source_path="plot_outline.core_conflict",
            value_type="string",
            display_name="核心冲突",
            scope="global",
            stage="planning",
            required=True,
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
                "输出必须是 JSON 对象，顶层字段为 plot_outline",
                "业务 continuation 只消费结构化剧情总纲，不接收自由文本 context_blob",
            ],
        },
    )


def ensure_setup_plot_outline_contract(db) -> InvocationSpec:
    from infrastructure.ai.prompt_manager import get_prompt_manager
    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    get_prompt_manager().ensure_seeded()
    spec = setup_plot_outline_spec()
    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(
            spec.input_binding_set_id,
            spec.node_key,
            setup_plot_outline_input_bindings(),
            direction="input",
        )
        variable_repo.set_bindings(
            spec.output_binding_set_id,
            spec.node_key,
            setup_plot_outline_output_bindings(),
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
    theme_metadata = ctx.get("theme_metadata") if isinstance(ctx.get("theme_metadata"), Mapping) else {}
    genre_label = str(theme_metadata.get("genre_label") or "").strip()
    genre_major, genre_theme = _split_genre_label(genre_label)
    resolved_profile = resolve_opening_profile(genre_label, strict=False)
    genre_profile = resolved_profile.as_variables() if resolved_profile is not None else {
        "genre_opening_profile": {},
        "genre_reader_contract": {},
        "genre_rhythm_constraints": {},
    }
    return {
        "novel_title": str(ctx.get("novel_title") or "").strip(),
        "premise": str(ctx.get("premise") or "").strip(),
        "genre_major": genre_major,
        "genre_theme": genre_theme,
        "genre_label": genre_label,
        "world_preset": str(theme_metadata.get("world_preset") or "").strip(),
        "target_chapters": int(ctx.get("target_chapters") or 0),
        "target_words_per_chapter": int(ctx.get("target_words_per_chapter") or 0),
        "protagonist_card": render_variable_value(
            ctx.get("protagonist") or {},
            projection_key="character.card",
            render_mode="projection",
        ),
        "characters_brief": render_variable_value(
            ctx.get("characters") or ctx.get("other_characters") or [],
            projection_key="characters.brief",
            render_mode="projection",
        ),
        "locations_brief": render_variable_value(
            ctx.get("locations") or [],
            projection_key="locations.brief",
            render_mode="projection",
        ),
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
        "plot_outline_phase_schema": SETUP_PLOT_OUTLINE_PHASE_SCHEMA,
        "core_rules": ctx.get("core_rules") or {},
        "geography": ctx.get("geography") or {},
        "society": ctx.get("society") or {},
        "culture": ctx.get("culture") or {},
        "daily_life": ctx.get("daily_life") or {},
        **genre_profile,
    }


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
