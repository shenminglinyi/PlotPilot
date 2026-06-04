"""Autopilot helper invocation contracts."""
from __future__ import annotations

from collections.abc import Iterable

from application.ai_invocation.dtos import InvocationPolicy, InvocationSpec, VariableBinding
from infrastructure.ai.prompt_keys import (
    BEAT_COT_BRIDGE,
    CHAPTER_BRIDGE_CHECK,
    CHAPTER_BRIDGE_EXTRACT,
    CHAPTER_BRIDGE_FIX,
    CHAPTER_NARRATIVE_SYNC,
    TENSION_SCORING,
    VOICE_REWRITE,
)
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


def _extract_aliases(node_key: str) -> list[str]:
    from infrastructure.ai.prompt_registry import get_prompt_registry
    from infrastructure.ai.prompt_template_engine import get_template_engine

    node = get_prompt_registry().get_node(node_key)
    if node is None:
        raise RuntimeError(f"CPMS 节点未发布: {node_key}")
    engine = get_template_engine()
    aliases = engine.extract_variables(node.get_active_system()) | engine.extract_variables(node.get_active_user_template())
    return sorted(aliases)


def _bindings_for_aliases(
    aliases: Iterable[str],
    *,
    optional_aliases: Iterable[str] = (),
) -> list[VariableBinding]:
    optional = set(optional_aliases)
    bindings: list[VariableBinding] = []
    for alias in aliases:
        bindings.append(
            VariableBinding(
                alias=alias,
                required=alias not in optional,
                default="" if alias in optional else None,
                source="autopilot_helper",
                scope="runtime",
                stage="runtime",
                display_name=alias,
            )
        )
    return bindings


def _ensure_helper_contract(
    *,
    db,
    operation: str,
    node_key: str,
    optional_aliases: Iterable[str] = (),
    risk_level: str = "low",
) -> None:
    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    input_binding_set_id = f"{node_key}:input:autopilot-helper:v1"
    input_bindings = _bindings_for_aliases(_extract_aliases(node_key), optional_aliases=optional_aliases)

    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(input_binding_set_id, node_key, input_bindings, direction="input")
        SqliteInvocationSpecRepository(db).upsert(
            InvocationSpec(
                operation=operation,
                node_key=node_key,
                prompt_node_version_id=_active_node_version(node_key),
                input_binding_set_id=input_binding_set_id,
                default_policy=InvocationPolicy.DIRECT,
                risk_level=risk_level,
                supports_stream=False,
                metadata={"source": "autopilot_helper", "cpms_node_key": node_key},
            ),
            spec_id=f"spec:{node_key}:autopilot-helper:v1",
            spec_version=1,
            status="published",
        )


def ensure_autopilot_voice_rewrite_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()
    _ensure_helper_contract(
        db=db,
        operation="autopilot.voice.rewrite",
        node_key=VOICE_REWRITE,
        risk_level="medium",
    )


def ensure_autopilot_bridge_extract_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()
    _ensure_helper_contract(
        db=db,
        operation="autopilot.bridge.extract",
        node_key=CHAPTER_BRIDGE_EXTRACT,
        risk_level="low",
    )


def ensure_autopilot_bridge_check_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()
    _ensure_helper_contract(
        db=db,
        operation="autopilot.bridge.check",
        node_key=CHAPTER_BRIDGE_CHECK,
        risk_level="low",
    )


def ensure_autopilot_bridge_fix_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()
    _ensure_helper_contract(
        db=db,
        operation="autopilot.bridge.fix",
        node_key=CHAPTER_BRIDGE_FIX,
        risk_level="medium",
    )


def ensure_autopilot_tension_score_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()
    _ensure_helper_contract(
        db=db,
        operation="autopilot.tension.score",
        node_key=TENSION_SCORING,
        risk_level="low",
    )


def ensure_autopilot_beat_bridge_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()
    _ensure_helper_contract(
        db=db,
        operation="autopilot.beat.bridge",
        node_key=BEAT_COT_BRIDGE,
        optional_aliases={"chapter_outline"},
        risk_level="low",
    )


def ensure_autopilot_narrative_sync_contract(db=None) -> None:
    if db is None:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()
    _ensure_helper_contract(
        db=db,
        operation="autopilot.chapter.narrative_sync",
        node_key=CHAPTER_NARRATIVE_SYNC,
        optional_aliases={"foreshadow_context"},
        risk_level="medium",
    )
