"""Autopilot continuation handlers."""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from application.ai_invocation.continuation import ContinuationContext, register_continuation_handler

logger = logging.getLogger(__name__)


def _publish_shared_state(novel_id: str, **fields: Any) -> None:
    try:
        from interfaces.main import update_shared_novel_state

        update_shared_novel_state(novel_id, **fields)
    except Exception as exc:
        logger.debug("autopilot continuation shared state publish skipped: %s", exc)


def _resume_autopilot_writing(novel_id: str) -> None:
    try:
        from application.paths import get_db_path
        from infrastructure.persistence.database.connection import get_database
        from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue

        db = get_database(get_db_path())
        with sqlite_writes_bypass_queue():
            db.execute(
                """
                UPDATE novels
                SET autopilot_status = 'running',
                    current_stage = 'writing',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (novel_id,),
            )
            db.commit()
    except Exception as exc:
        logger.warning("autopilot continuation failed to resume writing in DB: novel=%s error=%s", novel_id, exc)
    try:
        from application.engine.services.novel_stop_signal import publish_start_signal

        publish_start_signal(novel_id)
    except Exception as exc:
        logger.debug("autopilot continuation start signal skipped: %s", exc)


def register_autopilot_continuations() -> None:
    def _outline_partition(ctx: ContinuationContext) -> Mapping[str, Any]:
        content = ctx.decision.accepted_content or ""
        try:
            payload = json.loads(content) if content.strip() else {}
        except Exception:
            payload = {}

        if not isinstance(payload, dict):
            payload = {}

        novel_id = str(ctx.session.context.get("novel_id") or "")
        chapter_number = ctx.session.context.get("chapter_number")
        if novel_id:
            micro_beats = payload.get("atoms") or payload.get("micro_beats") or []
            _publish_shared_state(
                novel_id,
                autopilot_status="running",
                current_stage="writing",
                active_invocation_session_id="",
                active_invocation_operation="",
                active_invocation_node_key="",
                active_invocation_status="completed",
                active_invocation_policy="",
                requires_ai_review=False,
                autopilot_pause_reason="",
                autopilot_pending_chapter_number=chapter_number,
                autopilot_pending_chapter_plan=payload,
                planned_micro_beats=micro_beats,
                outline_plan_mode=payload.get("mode") or "autopilot_outline_partition",
            )
            _resume_autopilot_writing(novel_id)
        return {
            "atoms": micro_beats,
            "chapter_plan": payload,
            "chapter_number": chapter_number,
            "planned_micro_beats": micro_beats,
            "outline_plan_mode": payload.get("mode") or "autopilot_outline_partition",
        }

    register_continuation_handler("autopilot_outline_partition", _outline_partition)

    def _prose_generation(ctx: ContinuationContext) -> Mapping[str, Any]:
        content = ctx.decision.accepted_content or ""
        novel_id = str(ctx.session.context.get("novel_id") or "")
        if novel_id:
            _publish_shared_state(
                novel_id,
                active_invocation_session_id="",
                active_invocation_operation="",
                active_invocation_node_key="",
                active_invocation_status="completed",
                active_invocation_policy="",
                requires_ai_review=False,
                autopilot_pause_reason="",
            )
        return {
            "content": content,
            "beat_content": content,
            "chapter_number": ctx.session.context.get("chapter_number"),
            "beat_index": ctx.session.context.get("beat_index"),
        }

    def _audit(ctx: ContinuationContext) -> Mapping[str, Any]:
        content = ctx.decision.accepted_content or ""
        try:
            payload = json.loads(content) if content.strip() else {}
        except Exception:
            payload = {"raw_report": content}
        return {
            "chapter_audit_report": payload,
            "chapter.audit.report": payload,
            "chapter.audit.risk_flags": payload.get("risk_flags", []) if isinstance(payload, dict) else [],
        }

    def _aftermath(ctx: ContinuationContext) -> Mapping[str, Any]:
        content = ctx.decision.accepted_content or ""
        try:
            payload = json.loads(content) if content.strip() else {}
        except Exception:
            payload = {"raw": content}
        return {
            "chapter_aftermath": payload,
            "chapter.summary": payload.get("summary", "") if isinstance(payload, dict) else "",
            "chapter.state_delta": payload.get("state_delta", {}) if isinstance(payload, dict) else {},
            "chapter.foreshadow_updates": payload.get("foreshadow_updates", []) if isinstance(payload, dict) else [],
        }

    register_continuation_handler("autopilot_prose_generation", _prose_generation)
    register_continuation_handler("autopilot_audit", _audit)
    register_continuation_handler("autopilot_after_chapter_extract", _aftermath)
