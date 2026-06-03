"""Application-level AI invocation contract registry."""
from __future__ import annotations

import json
from typing import Any, Mapping

from application.ai_invocation.dtos import InvocationPolicy, InvocationSpec, VariableBinding
from infrastructure.ai.prompt_keys import CHAPTER_GENERATION_MAIN
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue


class InvocationContractRegistry:
    """Ensure published invocation specs live outside interface routes."""

    def __init__(self, db=None):
        if db is None:
            from infrastructure.persistence.database.connection import get_database

            db = get_database()
        self._db = db

    def ensure_published(self, operation: str, node_key: str) -> InvocationSpec:
        if operation == "autopilot.outline.partition":
            from application.ai_invocation.contracts.autopilot_planning import (
                ensure_autopilot_outline_partition_contract,
            )

            ensure_autopilot_outline_partition_contract(self._db)
        elif operation == "autopilot.macro.plan" and node_key == "planning-quick-macro":
            from application.ai_invocation.contracts.autopilot_planning import (
                ensure_autopilot_macro_plan_contract,
            )

            ensure_autopilot_macro_plan_contract(self._db)
        elif operation == "autopilot.act.plan" and node_key == "planning-act":
            from application.ai_invocation.contracts.autopilot_planning import (
                ensure_autopilot_act_plan_contract,
            )

            ensure_autopilot_act_plan_contract(self._db)
        elif operation == "autopilot.prose.from_script" and node_key == "autopilot-stream-beat":
            from application.ai_invocation.contracts.autopilot_writing import ensure_autopilot_stream_beat_contract

            ensure_autopilot_stream_beat_contract(self._db)
        elif operation == "autopilot.chapter.audit":
            from application.ai_invocation.contracts.autopilot_writing import ensure_autopilot_audit_contract

            ensure_autopilot_audit_contract(self._db)
        elif operation == "autopilot.chapter.aftermath":
            from application.ai_invocation.contracts.autopilot_writing import ensure_autopilot_aftermath_contract

            ensure_autopilot_aftermath_contract(self._db)
        elif operation == "autopilot.voice.rewrite" and node_key == "voice-rewrite":
            from application.ai_invocation.contracts.autopilot_helpers import ensure_autopilot_voice_rewrite_contract

            ensure_autopilot_voice_rewrite_contract(self._db)
        elif operation == "autopilot.bridge.extract" and node_key == "chapter-bridge-extract":
            from application.ai_invocation.contracts.autopilot_helpers import ensure_autopilot_bridge_extract_contract

            ensure_autopilot_bridge_extract_contract(self._db)
        elif operation == "autopilot.bridge.check" and node_key == "chapter-bridge-check":
            from application.ai_invocation.contracts.autopilot_helpers import ensure_autopilot_bridge_check_contract

            ensure_autopilot_bridge_check_contract(self._db)
        elif operation == "autopilot.bridge.fix" and node_key == "chapter-bridge-fix":
            from application.ai_invocation.contracts.autopilot_helpers import ensure_autopilot_bridge_fix_contract

            ensure_autopilot_bridge_fix_contract(self._db)
        elif operation == "autopilot.tension.score" and node_key == "tension-scoring":
            from application.ai_invocation.contracts.autopilot_helpers import ensure_autopilot_tension_score_contract

            ensure_autopilot_tension_score_contract(self._db)
        elif operation == "autopilot.beat.bridge" and node_key == "beat-cot-bridge":
            from application.ai_invocation.contracts.autopilot_helpers import ensure_autopilot_beat_bridge_contract

            ensure_autopilot_beat_bridge_contract(self._db)
        elif operation == "autopilot.chapter.narrative_sync" and node_key == "chapter-narrative-sync":
            from application.ai_invocation.contracts.autopilot_helpers import ensure_autopilot_narrative_sync_contract

            ensure_autopilot_narrative_sync_contract(self._db)
        elif operation == "chapter.generate" and node_key == CHAPTER_GENERATION_MAIN:
            self._ensure_chapter_generation_contract()
        elif operation == "chapter.generate.prose" and node_key == "chapter-prose-generation":
            from application.ai_invocation.contracts.chapter_prose_generation import (
                ensure_chapter_prose_generation_contract,
            )

            ensure_chapter_prose_generation_contract(self._db)
        else:
            raise ValueError(f"Unsupported invocation contract: operation={operation}, node_key={node_key}")

        from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteInvocationSpecRepository

        spec = SqliteInvocationSpecRepository(self._db).get(operation, node_key)
        if spec is None:
            raise RuntimeError(f"InvocationSpec publish failed: operation={operation}, node_key={node_key}")
        return spec

    def _ensure_chapter_generation_contract(self) -> None:
        from infrastructure.ai.prompt_registry import get_prompt_registry
        from infrastructure.ai.prompt_template_engine import get_template_engine
        from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
            SqliteInvocationSpecRepository,
            SqliteVariableHubRepository,
        )

        registry = get_prompt_registry()
        node = registry.get_node(CHAPTER_GENERATION_MAIN)
        if node is None:
            raise RuntimeError(f"CPMS 节点未发布: {CHAPTER_GENERATION_MAIN}")
        node_version_id = getattr(node, "active_version_id", None) or ""
        if not node_version_id:
            raise RuntimeError(f"CPMS 节点缺少 active version: {CHAPTER_GENERATION_MAIN}")

        engine = get_template_engine()
        aliases = sorted(
            engine.extract_variables(node.get_active_system())
            | engine.extract_variables(node.get_active_user_template())
        )
        binding_set_id = f"{CHAPTER_GENERATION_MAIN}:input:v1"
        required_aliases = {"outline", "context", "genre_profile_block"}
        chapter_global_bindings = self._chapter_global_bindings()
        input_bindings: list[VariableBinding] = []
        for alias in sorted(set(aliases) | set(chapter_global_bindings)):
            meta = chapter_global_bindings.get(alias, {})
            input_bindings.append(
                VariableBinding(
                    alias=alias,
                    variable_key=str(meta.get("variable_key") or ""),
                    required=alias in required_aliases or bool(meta.get("required")),
                    default=None if alias in required_aliases or bool(meta.get("required")) else "",
                    source="novel_genre_profile" if meta else "cpms_template",
                    value_type=str(meta.get("value_type") or "string"),
                    scope=str(meta.get("scope") or "chapter"),
                    stage=str(meta.get("stage") or "writing"),
                    display_name=str(meta.get("display_name") or alias),
                )
            )

        with sqlite_writes_bypass_queue():
            variable_repo = SqliteVariableHubRepository(self._db)
            variable_repo.set_bindings(binding_set_id, CHAPTER_GENERATION_MAIN, input_bindings, direction="input")
            SqliteInvocationSpecRepository(self._db).upsert(
                InvocationSpec(
                    operation="chapter.generate",
                    node_key=CHAPTER_GENERATION_MAIN,
                    prompt_node_version_id=node_version_id,
                    input_binding_set_id=binding_set_id,
                    default_policy=InvocationPolicy.FULL_INTERACTIVE,
                    risk_level="medium",
                    supports_stream=False,
                    continuation_handler_key="manual_chapter_generation_stream",
                    metadata={
                        "source": "manual_chapter_generation",
                        "cpms_node_key": CHAPTER_GENERATION_MAIN,
                    },
                ),
                spec_id=f"spec:{CHAPTER_GENERATION_MAIN}:v1",
                spec_version=1,
                status="published",
            )

    @staticmethod
    def _chapter_global_bindings() -> Mapping[str, Mapping[str, Any]]:
        return {
            "genre_profile_block": {
                "variable_key": "novel.genre.profile_block",
                "display_name": "类型画像提示块",
                "value_type": "string",
                "scope": "global",
                "stage": "writing",
                "required": True,
            },
            "genre_opening_profile": {
                "variable_key": "novel.genre.opening_profile",
                "display_name": "类型开篇画像",
                "value_type": "object",
                "scope": "global",
                "stage": "planning",
                "required": True,
            },
            "genre_reader_contract": {
                "variable_key": "novel.genre.reader_contract",
                "display_name": "读者留存契约",
                "value_type": "object",
                "scope": "global",
                "stage": "planning",
                "required": True,
            },
            "genre_rhythm_constraints": {
                "variable_key": "novel.genre.rhythm_constraints",
                "display_name": "类型节奏约束",
                "value_type": "object",
                "scope": "global",
                "stage": "planning",
                "required": True,
            },
        }


def ensure_invocation_contract(operation: str, node_key: str, db=None) -> InvocationSpec:
    return InvocationContractRegistry(db).ensure_published(operation, node_key)
