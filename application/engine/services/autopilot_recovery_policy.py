"""Autopilot recovery decision service.

The API expresses intent to run/stop. This service decides the stable runtime
entry point from persisted domain state.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from domain.novel.entities.novel import NovelStage

logger = logging.getLogger(__name__)


RETRYABLE_STAGES = {
    NovelStage.MACRO_PLANNING.value,
    NovelStage.ACT_PLANNING.value,
    NovelStage.WRITING.value,
    NovelStage.AUDITING.value,
}


@dataclass(frozen=True)
class AutopilotRecoveryDecision:
    novel_id: str
    next_stage: str
    chapter_number: Optional[int] = None
    discard_transient_generation: bool = False
    clear_stop_signal: bool = True
    clear_pending_invocation: bool = False
    preserve_review_gate: bool = False
    story_pipeline_mode: bool = True
    reason: str = ""


class AutopilotRecoveryPolicy:
    def __init__(
        self,
        db: Any = None,
        *,
        workspace: Any = None,
        story_pipeline_writing_enabled: Optional[bool] = None,
    ) -> None:
        self._database = db
        self._workspace = workspace
        self._story_pipeline_writing_enabled = story_pipeline_writing_enabled

    def decide_on_start(self, novel_id: str) -> AutopilotRecoveryDecision:
        row = self._fetch_novel(str(novel_id))
        if row is None:
            raise ValueError("novel_not_found")
        return self._decide_from_row(row, for_start=True)

    def decide_on_daemon_tick(self, novel: Any) -> AutopilotRecoveryDecision:
        novel_id = novel.novel_id.value if hasattr(getattr(novel, "novel_id", None), "value") else str(getattr(novel, "novel_id", ""))
        row = self._fetch_novel(novel_id)
        if row is None:
            current_stage = getattr(novel, "current_stage", NovelStage.MACRO_PLANNING)
            current_stage = current_stage.value if hasattr(current_stage, "value") else str(current_stage)
            return AutopilotRecoveryDecision(
                novel_id=novel_id,
                next_stage=current_stage or NovelStage.MACRO_PLANNING.value,
                clear_stop_signal=False,
                reason="novel_state_unavailable",
            )
        return self._decide_from_row(row, for_start=False)

    def apply_transient_cleanup(self, decision: AutopilotRecoveryDecision) -> None:
        if decision.discard_transient_generation and decision.chapter_number and self._workspace is not None:
            self._workspace.discard(decision.novel_id, decision.chapter_number)
            self._archive_legacy_draft(decision.novel_id, decision.chapter_number)
        if decision.clear_pending_invocation:
            self._cancel_retryable_pending_invocations(decision.novel_id)

    def _decide_from_row(self, row: dict[str, Any], *, for_start: bool) -> AutopilotRecoveryDecision:
        novel_id = str(row["id"])
        stage = str(row.get("current_stage") or NovelStage.MACRO_PLANNING.value)
        if stage == NovelStage.PLANNING.value:
            stage = NovelStage.MACRO_PLANNING.value

        pending = self._find_pending_invocation(novel_id)
        if stage == NovelStage.PAUSED_FOR_REVIEW.value:
            return AutopilotRecoveryDecision(
                novel_id=novel_id,
                next_stage=stage,
                chapter_number=self._current_chapter_number(novel_id),
                clear_stop_signal=True,
                clear_pending_invocation=False,
                preserve_review_gate=True,
                story_pipeline_mode=self._is_story_pipeline_writing_enabled(),
                reason="paused_for_review_preserved",
            )

        if stage == NovelStage.COMPLETED.value:
            return AutopilotRecoveryDecision(
                novel_id=novel_id,
                next_stage=stage,
                clear_stop_signal=False,
                story_pipeline_mode=self._is_story_pipeline_writing_enabled(),
                reason="completed",
            )

        if stage == NovelStage.AUDITING.value:
            chapter_number = self._latest_completed_chapter_number(novel_id)
            if chapter_number is not None:
                return AutopilotRecoveryDecision(
                    novel_id=novel_id,
                    next_stage=NovelStage.AUDITING.value,
                    chapter_number=chapter_number,
                    clear_stop_signal=True,
                    clear_pending_invocation=self._is_retryable_pending(pending),
                    story_pipeline_mode=self._is_story_pipeline_writing_enabled(),
                    reason="completed_chapter_reaudit",
                )
            stage = NovelStage.WRITING.value

        if stage == NovelStage.WRITING.value:
            chapter_number = self._current_uncompleted_chapter_number(novel_id)
            story_pipeline = self._is_story_pipeline_writing_enabled()
            return AutopilotRecoveryDecision(
                novel_id=novel_id,
                next_stage=NovelStage.WRITING.value,
                chapter_number=chapter_number,
                discard_transient_generation=story_pipeline and chapter_number is not None,
                clear_stop_signal=True,
                clear_pending_invocation=self._is_retryable_pending(pending),
                story_pipeline_mode=story_pipeline,
                reason="retry_writing_step" if story_pipeline else "resume_legacy_writing",
            )

        if stage == NovelStage.ACT_PLANNING.value:
            return AutopilotRecoveryDecision(
                novel_id=novel_id,
                next_stage=NovelStage.ACT_PLANNING.value,
                chapter_number=self._current_chapter_number(novel_id),
                clear_stop_signal=True,
                clear_pending_invocation=self._is_retryable_pending(pending),
                story_pipeline_mode=self._is_story_pipeline_writing_enabled(),
                reason="retry_act_planning",
            )

        return AutopilotRecoveryDecision(
            novel_id=novel_id,
            next_stage=NovelStage.MACRO_PLANNING.value,
            chapter_number=self._current_chapter_number(novel_id),
            clear_stop_signal=True,
            clear_pending_invocation=self._is_retryable_pending(pending),
            story_pipeline_mode=self._is_story_pipeline_writing_enabled(),
            reason="retry_macro_planning",
        )

    def _is_story_pipeline_writing_enabled(self) -> bool:
        if self._story_pipeline_writing_enabled is not None:
            return bool(self._story_pipeline_writing_enabled)
        try:
            from infrastructure.engine.story_pipeline_environment import StoryPipelineEnvironmentSettings

            return StoryPipelineEnvironmentSettings.from_env().mode in {"writing", "full"}
        except Exception:
            return True

    def _get_db(self) -> Any:
        if self._database is None:
            from application.paths import get_db_path
            from infrastructure.persistence.database.connection import get_database

            self._database = get_database(get_db_path())
        return self._database

    def _fetch_novel(self, novel_id: str) -> Optional[dict[str, Any]]:
        row = self._get_db().fetch_one("SELECT * FROM novels WHERE id = ?", (novel_id,))
        return dict(row) if row else None

    def _latest_completed_chapter_number(self, novel_id: str) -> Optional[int]:
        row = self._get_db().fetch_one(
            "SELECT MAX(number) AS n FROM chapters WHERE novel_id = ? AND status = 'completed'",
            (novel_id,),
        )
        return int(row["n"]) if row and row.get("n") is not None else None

    def _current_uncompleted_chapter_number(self, novel_id: str) -> Optional[int]:
        row = self._get_db().fetch_one(
            """
            SELECT number FROM chapters
            WHERE novel_id = ? AND status != 'completed'
            ORDER BY number ASC LIMIT 1
            """,
            (novel_id,),
        )
        if row and row.get("number") is not None:
            return int(row["number"])
        row = self._get_db().fetch_one(
            """
            SELECT sn.number
            FROM story_nodes sn
            LEFT JOIN chapters c ON c.novel_id = sn.novel_id AND c.number = sn.number
            WHERE sn.novel_id = ? AND sn.node_type = 'chapter'
              AND COALESCE(c.status, 'draft') != 'completed'
            ORDER BY sn.number ASC LIMIT 1
            """,
            (novel_id,),
        )
        if row and row.get("number") is not None:
            return int(row["number"])
        completed = self._latest_completed_chapter_number(novel_id)
        return (completed + 1) if completed is not None else None

    def _current_chapter_number(self, novel_id: str) -> Optional[int]:
        return self._current_uncompleted_chapter_number(novel_id) or self._latest_completed_chapter_number(novel_id)

    def _find_pending_invocation(self, novel_id: str) -> Optional[dict[str, Any]]:
        try:
            row = self._get_db().fetch_one(
                """
                SELECT id, operation, status, context_json, metadata_json
                FROM ai_invocation_sessions
                WHERE json_extract(context_json, '$.novel_id') = ?
                  AND status IN (
                    'requested', 'spec_resolved', 'context_resolved', 'variables_resolved',
                    'prompt_compiled', 'awaiting_pre_call_review', 'generating',
                    'awaiting_acceptance', 'awaiting_commit', 'blocked',
                    'failed', 'cancelled'
                  )
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (novel_id,),
            )
            return dict(row) if row else None
        except Exception:
            return None

    def _fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        db = self._get_db()
        try:
            rows = db.fetch_all(sql, params)
        except AttributeError:
            rows = db.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def _commit(self) -> None:
        db = self._get_db()
        try:
            db.commit()
        except AttributeError:
            try:
                db.conn.commit()
            except AttributeError:
                pass

    def _is_retryable_pending(self, pending: Optional[dict[str, Any]]) -> bool:
        if not pending:
            return False
        try:
            ctx = json.loads(pending.get("context_json") or "{}")
            meta = json.loads(pending.get("metadata_json") or "{}")
        except Exception:
            ctx, meta = {}, {}
        stage = str(meta.get("stage") or ctx.get("stage") or "").strip()
        if stage == NovelStage.PAUSED_FOR_REVIEW.value:
            return False
        if self._session_has_human_decision(str(pending.get("id") or "")):
            return False
        status = str(pending.get("status") or "")
        operation = str(pending.get("operation") or "")
        retryable_operation = operation.startswith("autopilot.") or operation.startswith("pipeline.")
        return stage in RETRYABLE_STAGES or (retryable_operation and status in {"failed", "cancelled", "blocked"})

    def _session_has_human_decision(self, session_id: str) -> bool:
        if not session_id:
            return False
        try:
            row = self._get_db().fetch_one(
                """
                SELECT 1 AS present
                FROM ai_adoption_decisions
                WHERE session_id = ?
                  AND COALESCE(accepted_by, '') NOT IN ('', 'system', 'autopilot')
                LIMIT 1
                """,
                (session_id,),
            )
            return bool(row)
        except Exception:
            return False

    def _cancel_retryable_pending_invocations(self, novel_id: str) -> int:
        try:
            rows = self._fetch_all(
                """
                SELECT id, operation, status, context_json, metadata_json
                FROM ai_invocation_sessions
                WHERE json_extract(context_json, '$.novel_id') = ?
                  AND status IN (
                    'requested', 'spec_resolved', 'context_resolved', 'variables_resolved',
                    'prompt_compiled', 'awaiting_pre_call_review', 'generating',
                    'awaiting_acceptance', 'awaiting_commit', 'blocked',
                    'failed'
                  )
                """,
                (novel_id,),
            )
        except Exception:
            return 0

        cancelled = 0
        for row in rows:
            if not self._is_retryable_pending(row):
                continue
            metadata = {}
            try:
                metadata = json.loads(row.get("metadata_json") or "{}")
            except Exception:
                metadata = {}
            metadata.update(
                {
                    "recovery_cancelled": True,
                    "recovery_reason": "retryable_step_restarted",
                }
            )
            try:
                self._get_db().execute(
                    """
                    UPDATE ai_invocation_sessions
                    SET status = 'cancelled',
                        metadata_json = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (json.dumps(metadata, ensure_ascii=False, sort_keys=True), row["id"]),
                )
                cancelled += 1
            except Exception as exc:
                logger.debug("pending invocation cleanup skipped session=%s: %s", row.get("id"), exc)
        if cancelled:
            self._commit()
            logger.info("清理可重试 pending invocation novel=%s count=%d", novel_id, cancelled)
        return cancelled

    def _archive_legacy_draft(self, novel_id: str, chapter_number: int) -> None:
        try:
            row = self._get_db().fetch_one(
                """
                SELECT id, content, outline, status
                FROM chapters
                WHERE novel_id = ? AND number = ? AND status != 'completed'
                """,
                (novel_id, int(chapter_number)),
            )
            if not row or not str(row.get("content") or "").strip():
                return
            from infrastructure.persistence.database.chapter_draft_repository import ChapterDraftRepository

            repo = ChapterDraftRepository(self._get_db())
            content = str(row.get("content") or "")
            for existing in repo.list_drafts(novel_id, int(chapter_number), limit=10):
                if existing.source == "pre_regen" and existing.content == content:
                    return
            repo.save_draft(
                novel_id=novel_id,
                chapter_id=str(row.get("id") or f"chapter-{novel_id}-{chapter_number}"),
                chapter_number=int(chapter_number),
                content=content,
                outline=str(row.get("outline") or ""),
                source="pre_regen",
            )
            self._commit()
        except Exception as exc:
            logger.debug("旧 draft 归档跳过 novel=%s ch=%s: %s", novel_id, chapter_number, exc)
