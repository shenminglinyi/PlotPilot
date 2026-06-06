"""Autopilot continuation handlers."""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from application.ai_invocation.continuation import ContinuationContext, register_continuation_handler
from application.ai_invocation.dtos import InvocationPolicy
from application.ai_invocation.autopilot.shared_state import write_autopilot_shared_state

logger = logging.getLogger(__name__)


def _publish_shared_state(novel_id: str, **fields: Any) -> None:
    if not write_autopilot_shared_state(novel_id, **fields):
        logger.debug("autopilot continuation shared state publish skipped: novel=%s", novel_id)


def _clear_invocation_state(novel_id: str, **extra: Any) -> None:
    _publish_shared_state(
        novel_id,
        active_invocation_session_id="",
        active_invocation_operation="",
        active_invocation_node_key="",
        active_invocation_status="completed",
        active_invocation_policy="",
        has_active_invocation=False,
        requires_ai_review=False,
        autopilot_pause_reason="",
        **extra,
    )


def _resume_autopilot_stage(novel_id: str, stage: str, **fields: Any) -> None:
    try:
        from application.paths import get_db_path
        from infrastructure.persistence.database.connection import get_database
        from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue

        db = get_database(get_db_path())
        set_parts = [
            "autopilot_status = 'running'",
            "current_stage = ?",
            "updated_at = CURRENT_TIMESTAMP",
        ]
        params: list[Any] = [stage]
        for key, value in fields.items():
            set_parts.append(f"{key} = ?")
            params.append(value)
        params.append(novel_id)
        with sqlite_writes_bypass_queue():
            db.execute(
                f"UPDATE novels SET {', '.join(set_parts)} WHERE id = ?",
                tuple(params),
            )
            db.commit()
    except Exception as exc:
        logger.warning(
            "autopilot continuation failed to resume stage in DB: novel=%s stage=%s error=%s",
            novel_id,
            stage,
            exc,
        )
    try:
        from application.engine.services.novel_stop_signal import publish_start_signal

        publish_start_signal(novel_id)
    except Exception as exc:
        logger.debug("autopilot continuation start signal skipped: %s", exc)


def _append_chapter_draft(novel_id: str, chapter_number: int, content: str) -> int:
    try:
        from application.paths import get_db_path
        from infrastructure.persistence.database.connection import get_database
        from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue

        db = get_database(get_db_path())
        with sqlite_writes_bypass_queue():
            row = db.fetch_one(
                "SELECT id, title, outline, content FROM chapters WHERE novel_id = ? AND number = ?",
                (novel_id, chapter_number),
            )
            prior = str((row or {}).get("content") or "").strip()
            addition = str(content or "").strip()
            merged = prior
            if addition:
                merged = f"{prior}\n\n{addition}".strip() if prior else addition
            word_count = len(merged)
            if row is None:
                db.execute(
                    """
                    INSERT INTO chapters (
                        id, novel_id, number, title, content, outline, status, word_count,
                        tension_score, plot_tension, emotional_tension, pacing_tension,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, 0, 0, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        f"autopilot:{novel_id}:{chapter_number}",
                        novel_id,
                        chapter_number,
                        f"第{chapter_number}章",
                        merged,
                        "",
                        word_count,
                    ),
                )
            else:
                db.execute(
                    """
                    UPDATE chapters
                    SET content = ?, status = 'draft', word_count = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE novel_id = ? AND number = ?
                    """,
                    (merged, word_count, novel_id, chapter_number),
                )
            db.commit()
            return word_count
    except Exception as exc:
        logger.warning(
            "autopilot continuation failed to append chapter draft: novel=%s chapter=%s error=%s",
            novel_id,
            chapter_number,
            exc,
        )
        return 0


def register_autopilot_continuations() -> None:
    def _outline_partition(ctx: ContinuationContext) -> Mapping[str, Any]:
        content = ctx.decision.accepted_content or ""
        try:
            payload = json.loads(content) if content.strip() else {}
        except Exception as exc:
            raise ValueError("autopilot_outline_partition_requires_json_object") from exc

        if not isinstance(payload, dict):
            raise ValueError("autopilot_outline_partition_requires_json_object")

        novel_id = str(ctx.session.context.get("novel_id") or "")
        chapter_number = ctx.session.context.get("chapter_number")
        micro_beats = payload.get("atoms") or payload.get("micro_beats") or []
        if not isinstance(micro_beats, list) or not micro_beats:
            raise ValueError("autopilot_outline_partition_requires_non_empty_atoms")
        if ctx.session.policy == InvocationPolicy.DIRECT:
            return {
                "atoms": micro_beats,
                "chapter_plan": payload,
                "chapter_number": chapter_number,
                "planned_micro_beats": micro_beats,
                "outline_plan_mode": payload.get("mode") or "autopilot_outline_partition",
            }
        if novel_id:
            _clear_invocation_state(
                novel_id,
                autopilot_status="running",
                current_stage="writing",
                autopilot_pending_chapter_number=chapter_number,
                autopilot_pending_chapter_plan=payload,
                planned_micro_beats=micro_beats,
                outline_plan_mode=payload.get("mode") or "autopilot_outline_partition",
            )
            _resume_autopilot_stage(novel_id, "writing")
        return {
            "atoms": micro_beats,
            "chapter_plan": payload,
            "chapter_number": chapter_number,
            "planned_micro_beats": micro_beats,
            "outline_plan_mode": payload.get("mode") or "autopilot_outline_partition",
        }

    register_continuation_handler("autopilot_outline_partition", _outline_partition)

    def _macro_plan(ctx: ContinuationContext) -> Mapping[str, Any]:
        content = ctx.decision.accepted_content or ""
        try:
            payload = json.loads(content) if content.strip() else {}
        except Exception as exc:
            raise ValueError("autopilot_macro_plan_requires_json_object") from exc
        if isinstance(payload, list):
            payload = {"parts": payload}
        if not isinstance(payload, dict):
            raise ValueError("autopilot_macro_plan_requires_json_object")
        parts = payload.get("parts") or payload.get("structure") or []
        if not isinstance(parts, list) or not parts:
            raise ValueError("autopilot_macro_plan_requires_non_empty_parts")

        novel_id = str(ctx.session.context.get("novel_id") or "")
        target_chapters = int(ctx.session.context.get("target_chapters") or 0)
        result = {
            "success": True,
            "structure": parts,
            "quality_metrics": {},
            "generation_time": 0,
        }
        if novel_id and ctx.session.policy != InvocationPolicy.DIRECT:
            _clear_invocation_state(
                novel_id,
                autopilot_status="running",
                current_stage="macro_planning",
                autopilot_pending_macro_plan=result,
                autopilot_pending_macro_target_chapters=target_chapters,
                macro_structure_ready=False,
                writing_substep="macro_planning",
                writing_substep_label="宏观规划 · 等待结构落库",
            )
            _resume_autopilot_stage(novel_id, "macro_planning")
        return {
            "parts": parts,
            "macro_plan": result,
            "target_chapters": target_chapters,
        }

    def _act_plan(ctx: ContinuationContext) -> Mapping[str, Any]:
        content = ctx.decision.accepted_content or ""
        try:
            payload = json.loads(content) if content.strip() else {}
        except Exception as exc:
            raise ValueError("autopilot_act_plan_requires_json_object") from exc
        if not isinstance(payload, dict):
            raise ValueError("autopilot_act_plan_requires_json_object")
        chapters = payload.get("chapters") or []
        if not isinstance(chapters, list) or not chapters:
            raise ValueError("autopilot_act_plan_requires_non_empty_chapters")

        novel_id = str(ctx.session.context.get("novel_id") or "")
        act_id = str(ctx.session.context.get("act_id") or "")
        if novel_id and act_id and ctx.session.policy != InvocationPolicy.DIRECT:
            _clear_invocation_state(
                novel_id,
                autopilot_status="running",
                current_stage="act_planning",
                autopilot_pending_act_plan_id=act_id,
                autopilot_pending_act_chapters=chapters,
            )
            _resume_autopilot_stage(novel_id, "act_planning")
        return {
            "chapters": chapters,
            "act_id": act_id,
            "act_plan": {
                "success": True,
                "act_id": act_id,
                "chapters": chapters,
            },
        }

    def _prose_generation(ctx: ContinuationContext) -> Mapping[str, Any]:
        content = ctx.decision.accepted_content or ""
        novel_id = str(ctx.session.context.get("novel_id") or "")
        chapter_number = int(ctx.session.context.get("chapter_number") or 0)
        beat_index = int(ctx.session.context.get("beat_index") or 0)
        if novel_id and ctx.session.policy != InvocationPolicy.DIRECT and chapter_number > 0:
            total_words = _append_chapter_draft(novel_id, chapter_number, content)
            next_beat_index = beat_index + 1
            _clear_invocation_state(
                novel_id,
                autopilot_status="running",
                current_stage="writing",
                current_beat_index=next_beat_index,
                current_chapter_number=chapter_number,
                accumulated_words=total_words,
            )
            _resume_autopilot_stage(
                novel_id,
                "writing",
                current_beat_index=next_beat_index,
            )
        return {
            "content": content,
            "beat_content": content,
            "chapter_number": chapter_number,
            "beat_index": beat_index,
        }

    def _audit(ctx: ContinuationContext) -> Mapping[str, Any]:
        content = ctx.decision.accepted_content or ""
        try:
            payload = json.loads(content) if content.strip() else {}
        except Exception as exc:
            raise ValueError("autopilot_audit_requires_json_object") from exc
        if not isinstance(payload, dict):
            raise ValueError("autopilot_audit_requires_json_object")
        novel_id = str(ctx.session.context.get("novel_id") or "")
        chapter_number = int(ctx.session.context.get("chapter_number") or 0)
        if novel_id and ctx.session.policy != InvocationPolicy.DIRECT and chapter_number > 0:
            _clear_invocation_state(
                novel_id,
                autopilot_status="running",
                current_stage="auditing",
                autopilot_pending_audit_chapter_number=chapter_number,
                autopilot_pending_audit_report=payload,
            )
            _resume_autopilot_stage(novel_id, "auditing")
        return {
            "chapter_audit_report": payload,
            "chapter.audit.report": payload,
            "chapter.audit.risk_flags": payload.get("risk_flags", []) if isinstance(payload, dict) else [],
        }

    def _aftermath(ctx: ContinuationContext) -> Mapping[str, Any]:
        content = ctx.decision.accepted_content or ""
        try:
            payload = json.loads(content) if content.strip() else {}
        except Exception as exc:
            raise ValueError("autopilot_aftermath_requires_json_object") from exc
        if not isinstance(payload, dict):
            raise ValueError("autopilot_aftermath_requires_json_object")
        novel_id = str(ctx.session.context.get("novel_id") or "")
        chapter_number = int(ctx.session.context.get("chapter_number") or 0)
        if novel_id and ctx.session.policy != InvocationPolicy.DIRECT and chapter_number > 0:
            _clear_invocation_state(
                novel_id,
                autopilot_status="running",
                current_stage="auditing",
                autopilot_pending_aftermath_chapter_number=chapter_number,
                autopilot_pending_aftermath_payload=payload,
            )
            _resume_autopilot_stage(novel_id, "auditing")
        return {
            "chapter_aftermath": payload,
            "chapter.summary": payload.get("summary", "") if isinstance(payload, dict) else "",
            "chapter.state_delta": payload.get("state_delta", {}) if isinstance(payload, dict) else {},
            "chapter.foreshadow_updates": payload.get("foreshadow_updates", []) if isinstance(payload, dict) else [],
        }

    register_continuation_handler("autopilot_prose_generation", _prose_generation)
    register_continuation_handler("autopilot_macro_plan", _macro_plan)
    register_continuation_handler("autopilot_act_plan", _act_plan)
    register_continuation_handler("autopilot_audit", _audit)
    register_continuation_handler("autopilot_after_chapter_extract", _aftermath)
