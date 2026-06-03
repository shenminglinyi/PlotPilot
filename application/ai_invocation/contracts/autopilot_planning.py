"""Autopilot planning invocation contracts."""
from __future__ import annotations

from application.ai_invocation.dtos import InvocationPolicy, InvocationSpec, VariableBinding
from infrastructure.ai.prompt_keys import OUTLINE_BEAT_PARTITION, PLANNING_ACT, PLANNING_QUICK_MACRO
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue


def _active_node_version(node_key: str) -> str:
    from infrastructure.ai.prompt_manager import get_prompt_manager
    from infrastructure.ai.prompt_registry import get_prompt_registry

    try:
        get_prompt_manager().ensure_seeded()
    except Exception:
        pass
    node = get_prompt_registry().get_node(node_key)
    if node is None:
        raise RuntimeError(f"CPMS 节点未发布: {node_key}")
    node_version_id = getattr(node, "active_version_id", None) or ""
    if not node_version_id:
        raise RuntimeError(f"CPMS 节点缺少 active version: {node_key}")
    return node_version_id


def _template_aliases(node_key: str, required_aliases: set[str]) -> list[str]:
    from infrastructure.ai.prompt_registry import get_prompt_registry
    from infrastructure.ai.prompt_template_engine import get_template_engine

    node = get_prompt_registry().get_node(node_key)
    if node is None:
        raise RuntimeError(f"CPMS 节点未发布: {node_key}")
    engine = get_template_engine()
    return sorted(
        engine.extract_variables(node.get_active_system())
        | engine.extract_variables(node.get_active_user_template())
        | set(required_aliases)
    )


def ensure_autopilot_outline_partition_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()

    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    input_binding_set_id = f"{OUTLINE_BEAT_PARTITION}:input:v1"
    output_binding_set_id = f"{OUTLINE_BEAT_PARTITION}:output:v1"
    input_bindings = [
        VariableBinding(
            alias=alias,
            required=alias in {"outline", "target_chapter_words"},
            default=2500 if alias == "target_chapter_words" else None,
            source="autopilot_runtime" if alias in {"outline", "target_chapter_words"} else "cpms_template",
            value_type="integer" if alias == "target_chapter_words" else "string",
            scope="chapter",
            stage="planning",
            display_name={
                "outline": "章节大纲",
                "target_chapter_words": "章节目标字数",
            }.get(alias, alias),
        )
        for alias in _template_aliases(OUTLINE_BEAT_PARTITION, {"outline", "target_chapter_words"})
    ]
    output_bindings = [
        VariableBinding(
            alias="atoms",
            variable_key="chapter.micro_beats",
            required=True,
            source="autopilot_outline_partition",
            value_type="list",
            scope="chapter",
            stage="planning",
            display_name="章前微观节拍",
        ),
        VariableBinding(
            alias="chapter_plan",
            variable_key="chapter.execution_plan",
            required=True,
            source="autopilot_outline_partition",
            value_type="object",
            scope="chapter",
            stage="planning",
            display_name="章节执行计划",
        ),
    ]

    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(input_binding_set_id, OUTLINE_BEAT_PARTITION, input_bindings, direction="input")
        variable_repo.set_bindings(output_binding_set_id, OUTLINE_BEAT_PARTITION, output_bindings, direction="output")
        SqliteInvocationSpecRepository(db).upsert(
            InvocationSpec(
                operation="autopilot.outline.partition",
                node_key=OUTLINE_BEAT_PARTITION,
                prompt_node_version_id=_active_node_version(OUTLINE_BEAT_PARTITION),
                input_binding_set_id=input_binding_set_id,
                output_binding_set_id=output_binding_set_id,
                default_policy=InvocationPolicy.AUTOPILOT_PAUSE,
                risk_level="medium",
                supports_stream=False,
                continuation_handler_key="autopilot_outline_partition",
                metadata={"source": "autopilot", "cpms_node_key": OUTLINE_BEAT_PARTITION},
            ),
            spec_id=f"spec:{OUTLINE_BEAT_PARTITION}:autopilot:v1",
            spec_version=1,
            status="published",
        )


def ensure_autopilot_macro_plan_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()

    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    variable_keys = {
        "premise": "novel.setup.premise",
        "target_chapters": "novel.setup.target_chapters",
        "characters": "novel.characters.list",
        "planning_depth": "novel.planning.macro.depth",
        "rec_parts": "novel.planning.macro.rec_parts",
        "rec_volumes_per_part": "novel.planning.macro.rec_volumes_per_part",
        "rec_acts_per_volume": "novel.planning.macro.rec_acts_per_volume",
        "rec_chapters_per_act": "novel.planning.macro.rec_chapters_per_act",
        "total_recommended_acts": "novel.planning.macro.total_recommended_acts",
    }
    integer_aliases = {
        "target_chapters",
        "rec_parts",
        "rec_volumes_per_part",
        "rec_acts_per_volume",
        "rec_chapters_per_act",
        "total_recommended_acts",
    }
    object_aliases = {
        "genre_opening_profile",
        "genre_reader_contract",
        "genre_rhythm_constraints",
    }
    list_aliases = {"characters"}
    setup_aliases = {"premise", "target_chapters"}
    runtime_only_aliases = {"worldview"}
    derived_config_aliases = {
        "genre_opening_profile",
        "genre_reader_contract",
        "genre_rhythm_constraints",
    }
    input_binding_set_id = f"{PLANNING_QUICK_MACRO}:input:autopilot:v1"
    output_binding_set_id = f"{PLANNING_QUICK_MACRO}:output:autopilot:v1"
    input_bindings = [
        VariableBinding(
            alias=alias,
            variable_key=variable_keys.get(alias, ""),
            required=alias in variable_keys,
            default=None if alias in variable_keys else "",
            source=(
                "variable_hub" if alias in variable_keys else
                "runtime_only" if alias in runtime_only_aliases else
                "derived_config" if alias in derived_config_aliases else
                "cpms_template"
            ),
            value_type=(
                "integer" if alias in integer_aliases else
                "object" if alias in object_aliases else
                "list" if alias in list_aliases else
                "string"
            ),
            scope="global" if alias in setup_aliases or alias in object_aliases or alias in list_aliases else "novel",
            stage="setup" if alias in setup_aliases else "planning",
            display_name={
                "premise": "设定",
                "target_chapters": "章节数量",
                "worldview": "世界观运行时摘要",
                "characters": "角色列表",
                "genre_opening_profile": "类型开篇画像",
                "genre_reader_contract": "读者留存契约",
                "genre_rhythm_constraints": "类型节奏约束",
            }.get(alias, alias),
        )
        for alias in _template_aliases(PLANNING_QUICK_MACRO, set(variable_keys))
    ]
    output_bindings = [
        VariableBinding(
            alias="parts",
            variable_key="novel.planning.macro.parts",
            required=True,
            source="autopilot_macro_plan",
            value_type="list",
            scope="novel",
            stage="planning",
            display_name="宏观结构",
        ),
    ]

    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(input_binding_set_id, PLANNING_QUICK_MACRO, input_bindings, direction="input")
        variable_repo.set_bindings(output_binding_set_id, PLANNING_QUICK_MACRO, output_bindings, direction="output")
        SqliteInvocationSpecRepository(db).upsert(
            InvocationSpec(
                operation="autopilot.macro.plan",
                node_key=PLANNING_QUICK_MACRO,
                prompt_node_version_id=_active_node_version(PLANNING_QUICK_MACRO),
                input_binding_set_id=input_binding_set_id,
                output_binding_set_id=output_binding_set_id,
                default_policy=InvocationPolicy.AUTOPILOT_PAUSE,
                risk_level="medium",
                supports_stream=True,
                continuation_handler_key="autopilot_macro_plan",
                metadata={"source": "autopilot", "cpms_node_key": PLANNING_QUICK_MACRO},
            ),
            spec_id=f"spec:{PLANNING_QUICK_MACRO}:autopilot-macro:v1",
            spec_version=1,
            status="published",
        )


def ensure_autopilot_act_plan_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()

    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    variable_keys = {
        "context": "novel.planning.act.context",
        "chapter_count": "novel.planning.act.chapter_count",
    }
    input_binding_set_id = f"{PLANNING_ACT}:input:autopilot:v1"
    output_binding_set_id = f"{PLANNING_ACT}:output:autopilot:v1"
    input_bindings = [
        VariableBinding(
            alias=alias,
            variable_key=variable_keys.get(alias, ""),
            required=alias in variable_keys,
            default=None if alias in variable_keys else "",
            source="autopilot_runtime" if alias in variable_keys else "cpms_template",
            value_type="integer" if alias == "chapter_count" else "string",
            scope="novel",
            stage="planning",
            display_name=alias,
        )
        for alias in _template_aliases(PLANNING_ACT, set(variable_keys))
    ]
    output_bindings = [
        VariableBinding(
            alias="chapters",
            variable_key="novel.planning.act.chapters",
            required=True,
            source="autopilot_act_plan",
            value_type="list",
            scope="novel",
            stage="planning",
            display_name="幕级章节规划",
        ),
    ]

    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(input_binding_set_id, PLANNING_ACT, input_bindings, direction="input")
        variable_repo.set_bindings(output_binding_set_id, PLANNING_ACT, output_bindings, direction="output")
        SqliteInvocationSpecRepository(db).upsert(
            InvocationSpec(
                operation="autopilot.act.plan",
                node_key=PLANNING_ACT,
                prompt_node_version_id=_active_node_version(PLANNING_ACT),
                input_binding_set_id=input_binding_set_id,
                output_binding_set_id=output_binding_set_id,
                default_policy=InvocationPolicy.AUTOPILOT_PAUSE,
                risk_level="medium",
                supports_stream=True,
                continuation_handler_key="autopilot_act_plan",
                metadata={"source": "autopilot", "cpms_node_key": PLANNING_ACT},
            ),
            spec_id=f"spec:{PLANNING_ACT}:autopilot-act:v1",
            spec_version=1,
            status="published",
        )
