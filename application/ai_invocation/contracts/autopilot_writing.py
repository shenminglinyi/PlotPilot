"""Autopilot writing invocation contracts."""
from __future__ import annotations

from application.ai_invocation.dtos import InvocationPolicy, InvocationSpec, VariableBinding
from infrastructure.ai.prompt_keys import (
    ANTI_AI_CHAPTER_AUDIT,
    AUTOPILOT_STREAM_BEAT,
    CHAPTER_AFTERMATH,
    CHAPTER_PROSE_GENERATION,
)
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue

AUTOPILOT_CHAPTER_PROSE_OPERATION = "autopilot.chapter.prose"
AUTOPILOT_STREAM_BEAT_OPERATION = "autopilot.prose.from_script"
AUTOPILOT_CHAPTER_PROSE_CONTINUATION = "autopilot_prose_generation"


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


def ensure_autopilot_stream_beat_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()

    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    input_binding_set_id = f"{AUTOPILOT_STREAM_BEAT}:input:v1"
    output_binding_set_id = f"{AUTOPILOT_STREAM_BEAT}:output:v1"
    input_bindings = [
        VariableBinding(alias="outline", variable_key="chapter.outline", required=True, source="autopilot_runtime", scope="chapter", stage="writing", display_name="章节执行剧本"),
        VariableBinding(alias="last_paragraph", variable_key="chapter.draft_so_far", required=False, default="", source="autopilot_runtime", scope="chapter", stage="writing", display_name="上一段结尾"),
        VariableBinding(alias="beat_goal", variable_key="beat.current", required=True, source="autopilot_runtime", scope="beat", stage="writing", display_name="当前节拍目标"),
        VariableBinding(alias="target_words", variable_key="beat.target_words", required=True, default=800, source="autopilot_runtime", value_type="integer", scope="beat", stage="writing", display_name="节拍目标字数"),
        VariableBinding(alias="context_block", variable_key="materialized.beat.prompt_context", required=False, default="", source="autopilot_runtime", scope="beat", stage="writing", display_name="节拍上下文"),
    ]
    output_bindings = [
        VariableBinding(alias="content", variable_key="chapter.prose.draft", required=True, source="autopilot_prose_generation", scope="chapter", stage="writing", display_name="章节正文草稿"),
        VariableBinding(alias="beat_content", variable_key="beat.prose.draft", required=True, source="autopilot_prose_generation", scope="beat", stage="writing", display_name="节拍正文"),
    ]

    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(input_binding_set_id, AUTOPILOT_STREAM_BEAT, input_bindings, direction="input")
        variable_repo.set_bindings(output_binding_set_id, AUTOPILOT_STREAM_BEAT, output_bindings, direction="output")
        SqliteInvocationSpecRepository(db).upsert(
            InvocationSpec(
                operation=AUTOPILOT_STREAM_BEAT_OPERATION,
                node_key=AUTOPILOT_STREAM_BEAT,
                prompt_node_version_id=_active_node_version(AUTOPILOT_STREAM_BEAT),
                input_binding_set_id=input_binding_set_id,
                output_binding_set_id=output_binding_set_id,
                default_policy=InvocationPolicy.DIRECT,
                risk_level="medium",
                supports_stream=True,
                continuation_handler_key=AUTOPILOT_CHAPTER_PROSE_CONTINUATION,
                metadata={"source": "autopilot", "cpms_node_key": AUTOPILOT_STREAM_BEAT},
            ),
            spec_id=f"spec:{AUTOPILOT_STREAM_BEAT}:autopilot:v1",
            spec_version=1,
            status="published",
        )


def ensure_autopilot_chapter_prose_contract(db=None) -> None:
    """Publish the full-chapter prose composer used by StoryPipeline.

    It deliberately reuses the workbench prose CPMS node but has its own
    autopilot operation and continuation. The manual operation still owns the
    chapters-table projection; StoryPipeline owns persistence through its normal
    save/validate/aftermath stages.
    """
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()

    from application.ai_invocation.contracts.chapter_prose_generation import chapter_prose_input_bindings
    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    input_binding_set_id = f"{CHAPTER_PROSE_GENERATION}:autopilot:input:v1"
    output_binding_set_id = f"{CHAPTER_PROSE_GENERATION}:autopilot:output:v1"
    output_bindings = [
        VariableBinding(
            alias="content",
            variable_key="chapter.prose.draft",
            required=True,
            source="autopilot_prose_generation",
            scope="chapter",
            stage="writing",
            display_name="章节正文草稿",
        ),
        VariableBinding(
            alias="beat_content",
            variable_key="beat.prose.draft",
            required=False,
            source="autopilot_prose_generation",
            scope="chapter",
            stage="writing",
            display_name="章节正文",
        ),
    ]

    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(
            input_binding_set_id,
            CHAPTER_PROSE_GENERATION,
            chapter_prose_input_bindings(),
            direction="input",
        )
        variable_repo.set_bindings(
            output_binding_set_id,
            CHAPTER_PROSE_GENERATION,
            output_bindings,
            direction="output",
        )
        SqliteInvocationSpecRepository(db).upsert(
            InvocationSpec(
                operation=AUTOPILOT_CHAPTER_PROSE_OPERATION,
                node_key=CHAPTER_PROSE_GENERATION,
                prompt_node_version_id=_active_node_version(CHAPTER_PROSE_GENERATION),
                input_binding_set_id=input_binding_set_id,
                output_binding_set_id=output_binding_set_id,
                default_policy=InvocationPolicy.DIRECT,
                risk_level="medium",
                supports_stream=True,
                continuation_handler_key=AUTOPILOT_CHAPTER_PROSE_CONTINUATION,
                metadata={"source": "story_pipeline", "cpms_node_key": CHAPTER_PROSE_GENERATION},
            ),
            spec_id=f"spec:{CHAPTER_PROSE_GENERATION}:autopilot:v1",
            spec_version=1,
            status="published",
        )


def ensure_autopilot_audit_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()

    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    input_binding_set_id = f"{ANTI_AI_CHAPTER_AUDIT}:input:v1"
    output_binding_set_id = f"{ANTI_AI_CHAPTER_AUDIT}:output:v1"
    input_bindings = [
        VariableBinding(
            alias="content",
            variable_key="chapter.prose.draft",
            required=True,
            source="autopilot_runtime",
            scope="chapter",
            stage="audit",
            display_name="章节正文",
        ),
    ]
    output_bindings = [
        VariableBinding(
            alias="chapter.audit.report",
            variable_key="chapter.audit.report",
            required=True,
            source="autopilot_audit",
            value_type="object",
            scope="chapter",
            stage="audit",
            display_name="章节审计报告",
        ),
        VariableBinding(
            alias="chapter.audit.risk_flags",
            variable_key="chapter.audit.risk_flags",
            source="autopilot_audit",
            value_type="list",
            scope="chapter",
            stage="audit",
            display_name="审计风险标记",
        ),
    ]

    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(input_binding_set_id, ANTI_AI_CHAPTER_AUDIT, input_bindings, direction="input")
        variable_repo.set_bindings(output_binding_set_id, ANTI_AI_CHAPTER_AUDIT, output_bindings, direction="output")
        SqliteInvocationSpecRepository(db).upsert(
            InvocationSpec(
                operation="autopilot.chapter.audit",
                node_key=ANTI_AI_CHAPTER_AUDIT,
                prompt_node_version_id=_active_node_version(ANTI_AI_CHAPTER_AUDIT),
                input_binding_set_id=input_binding_set_id,
                output_binding_set_id=output_binding_set_id,
                default_policy=InvocationPolicy.DIRECT,
                risk_level="medium",
                supports_stream=False,
                continuation_handler_key="autopilot_audit",
                metadata={"source": "autopilot", "cpms_node_key": ANTI_AI_CHAPTER_AUDIT},
            ),
            spec_id=f"spec:{ANTI_AI_CHAPTER_AUDIT}:autopilot:v1",
            spec_version=1,
            status="published",
        )


def ensure_autopilot_aftermath_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()

    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    input_binding_set_id = f"{CHAPTER_AFTERMATH}:input:v1"
    output_binding_set_id = f"{CHAPTER_AFTERMATH}:output:v1"
    input_bindings = [
        VariableBinding(
            alias="content",
            variable_key="chapter.prose.draft",
            required=True,
            source="autopilot_runtime",
            scope="chapter",
            stage="audit",
            display_name="章节正文",
        ),
    ]
    output_bindings = [
        VariableBinding(
            alias="chapter.summary",
            variable_key="chapter.summary",
            required=True,
            source="autopilot_after_chapter_extract",
            scope="chapter",
            stage="audit",
            display_name="章节摘要",
        ),
        VariableBinding(
            alias="chapter.state_delta",
            variable_key="chapter.state_delta",
            source="autopilot_after_chapter_extract",
            value_type="object",
            scope="chapter",
            stage="audit",
            display_name="章节状态变化",
        ),
        VariableBinding(
            alias="chapter.foreshadow_updates",
            variable_key="chapter.foreshadow_updates",
            source="autopilot_after_chapter_extract",
            value_type="list",
            scope="chapter",
            stage="audit",
            display_name="伏笔更新",
        ),
    ]

    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(input_binding_set_id, CHAPTER_AFTERMATH, input_bindings, direction="input")
        variable_repo.set_bindings(output_binding_set_id, CHAPTER_AFTERMATH, output_bindings, direction="output")
        SqliteInvocationSpecRepository(db).upsert(
            InvocationSpec(
                operation="autopilot.chapter.aftermath",
                node_key=CHAPTER_AFTERMATH,
                prompt_node_version_id=_active_node_version(CHAPTER_AFTERMATH),
                input_binding_set_id=input_binding_set_id,
                output_binding_set_id=output_binding_set_id,
                default_policy=InvocationPolicy.DIRECT,
                risk_level="low",
                supports_stream=False,
                continuation_handler_key="autopilot_after_chapter_extract",
                metadata={"source": "autopilot", "cpms_node_key": CHAPTER_AFTERMATH},
            ),
            spec_id=f"spec:{CHAPTER_AFTERMATH}:autopilot:v1",
            spec_version=1,
            status="published",
        )
