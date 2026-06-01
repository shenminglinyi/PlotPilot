"""Autopilot runtime materializers."""
from __future__ import annotations

from typing import Any, Mapping

from application.ai_invocation.variable_hub import VariableWrite, VariableHubRepository


class ChapterContextMaterializer:
    """Materialize chapter runtime context into variable-hub friendly payloads."""

    def materialize(
        self,
        *,
        bundle: Mapping[str, Any],
        outline: str,
        target_chapter_words: int,
        repository: VariableHubRepository | None = None,
        context_key: str = "global",
        source_node_key: str = "autopilot_outline_partition",
    ) -> dict[str, Any]:
        materialized = {
            "materialized.chapter.generation_context": {
                "bundle": dict(bundle or {}),
                "outline": outline,
                "target_chapter_words": int(target_chapter_words or 0),
            },
            "chapter.outline": outline,
            "chapter.target_words": int(target_chapter_words or 0),
            "runtime.continuity_hint": str(bundle.get("continuity_hint") or bundle.get("voice_anchors") or ""),
        }
        if repository is not None:
            for key, value in materialized.items():
                repository.set_value(
                    VariableWrite(
                        key=key,
                        value=value,
                        context_key=context_key,
                        source_node_key=source_node_key,
                        source_trace_id=source_node_key,
                        scope="chapter",
                        stage="planning",
                        display_name=key,
                    )
                )
        return materialized


class ChapterOutlineMaterializer:
    """Materialize chapter outline level signals."""

    def materialize(self, *, chapter_plan: Mapping[str, Any]) -> dict[str, Any]:
        atoms = chapter_plan.get("atoms") or chapter_plan.get("micro_beats") or []
        return {
            "chapter.micro_beats": atoms,
            "chapter.execution_plan": dict(chapter_plan or {}),
        }
