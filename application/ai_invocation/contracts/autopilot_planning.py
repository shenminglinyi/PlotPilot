"""Autopilot planning invocation contracts."""
from __future__ import annotations

from application.ai_invocation.dtos import InvocationPolicy, InvocationSpec, VariableBinding
from infrastructure.ai.prompt_keys import OUTLINE_BEAT_PARTITION
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue


def ensure_autopilot_outline_partition_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()

    from infrastructure.ai.prompt_manager import get_prompt_manager
    from infrastructure.ai.prompt_registry import get_prompt_registry
    from infrastructure.ai.prompt_template_engine import get_template_engine
    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    try:
        get_prompt_manager().ensure_seeded()
    except Exception:
        pass

    node = get_prompt_registry().get_node(OUTLINE_BEAT_PARTITION)
    if node is None:
        raise RuntimeError(f"CPMS 节点未发布: {OUTLINE_BEAT_PARTITION}")
    node_version_id = getattr(node, "active_version_id", None) or ""
    if not node_version_id:
        raise RuntimeError(f"CPMS 节点缺少 active version: {OUTLINE_BEAT_PARTITION}")

    engine = get_template_engine()
    aliases = sorted(
        engine.extract_variables(node.get_active_system())
        | engine.extract_variables(node.get_active_user_template())
        | {"outline", "target_chapter_words"}
    )
    binding_set_id = f"{OUTLINE_BEAT_PARTITION}:input:v1"
    output_binding_set_id = f"{OUTLINE_BEAT_PARTITION}:output:v1"
    input_bindings: list[VariableBinding] = []
    for alias in aliases:
        input_bindings.append(
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
        )
    output_bindings = [
        VariableBinding(
            alias="atoms",
            variable_key="chapter.micro_beats",
            required=False,
            source="autopilot_outline_partition",
            value_type="list",
            scope="chapter",
            stage="planning",
            display_name="章前微观节拍",
        ),
        VariableBinding(
            alias="chapter_plan",
            variable_key="chapter.execution_plan",
            required=False,
            source="autopilot_outline_partition",
            value_type="object",
            scope="chapter",
            stage="planning",
            display_name="章节执行计划",
        ),
    ]

    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(binding_set_id, OUTLINE_BEAT_PARTITION, input_bindings, direction="input")
        variable_repo.set_bindings(output_binding_set_id, OUTLINE_BEAT_PARTITION, output_bindings, direction="output")
        SqliteInvocationSpecRepository(db).upsert(
            InvocationSpec(
                operation="autopilot.outline.partition",
                node_key=OUTLINE_BEAT_PARTITION,
                prompt_node_version_id=node_version_id,
                input_binding_set_id=binding_set_id,
                output_binding_set_id=output_binding_set_id,
                default_policy=InvocationPolicy.AUTOPILOT_PAUSE,
                risk_level="medium",
                supports_stream=False,
                continuation_handler_key="autopilot_outline_partition",
                metadata={
                    "source": "autopilot",
                    "cpms_node_key": OUTLINE_BEAT_PARTITION,
                },
            ),
            spec_id=f"spec:{OUTLINE_BEAT_PARTITION}:autopilot:v1",
            spec_version=1,
            status="published",
        )
