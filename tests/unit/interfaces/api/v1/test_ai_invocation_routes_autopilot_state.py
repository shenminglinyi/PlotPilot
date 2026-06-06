from application.ai_invocation.dtos import InvocationPolicy, InvocationSession, InvocationSessionStatus
from interfaces.api.v1.engine.ai_invocation_routes import _is_prompt_draft_editable, _publish_autopilot_session_state
from interfaces.api.v1.engine.autopilot_routes import (
    _build_status_pure_memory,
    _resume_block_reason_from_status,
)


def _session(status: InvocationSessionStatus) -> InvocationSession:
    return InvocationSession(
        id="session-1",
        operation="autopilot.chapter.audit",
        node_key="anti-ai-chapter-audit",
        policy=InvocationPolicy.REVIEW_AFTER_CALL,
        status=status,
        context={"novel_id": "novel-1", "chapter_number": 7},
        metadata={"novel_id": "novel-1"},
    )


def test_publish_autopilot_session_state_marks_review_required(monkeypatch):
    captured = {}

    def fake_publish(self, novel_id, payload):
        captured["novel_id"] = novel_id
        captured["payload"] = dict(payload)

    monkeypatch.setattr(
        "application.ai_invocation.autopilot.publisher.AutopilotSessionPublisher.publish",
        fake_publish,
    )

    _publish_autopilot_session_state(_session(InvocationSessionStatus.AWAITING_ACCEPTANCE))

    assert captured["novel_id"] == "novel-1"
    assert captured["payload"]["active_invocation_session_id"] == "session-1"
    assert captured["payload"]["has_active_invocation"] is True
    assert captured["payload"]["requires_ai_review"] is True
    assert captured["payload"]["autopilot_pause_reason"] == "awaiting_ai_review"


def test_publish_autopilot_session_state_clears_completed_session(monkeypatch):
    captured = {}

    def fake_publish(self, novel_id, payload):
        captured["novel_id"] = novel_id
        captured["payload"] = dict(payload)

    monkeypatch.setattr(
        "application.ai_invocation.autopilot.publisher.AutopilotSessionPublisher.publish",
        fake_publish,
    )

    _publish_autopilot_session_state(_session(InvocationSessionStatus.COMPLETED))

    assert captured["novel_id"] == "novel-1"
    assert captured["payload"]["active_invocation_session_id"] == "session-1"
    assert captured["payload"]["has_active_invocation"] is False
    assert captured["payload"]["requires_ai_review"] is False
    assert captured["payload"]["active_invocation_status"] == "completed"


def test_publish_autopilot_session_state_keeps_generating_session_active(monkeypatch):
    captured = {}

    def fake_publish(self, novel_id, payload):
        captured["novel_id"] = novel_id
        captured["payload"] = dict(payload)

    monkeypatch.setattr(
        "application.ai_invocation.autopilot.publisher.AutopilotSessionPublisher.publish",
        fake_publish,
    )

    _publish_autopilot_session_state(_session(InvocationSessionStatus.GENERATING))

    assert captured["novel_id"] == "novel-1"
    assert captured["payload"]["active_invocation_session_id"] == "session-1"
    assert captured["payload"]["has_active_invocation"] is True
    assert captured["payload"]["requires_ai_review"] is False
    assert captured["payload"]["autopilot_pause_reason"] == ""
    assert captured["payload"]["active_invocation_status"] == "generating"


def test_autopilot_status_pure_memory_exposes_active_invocation():
    status = _build_status_pure_memory(
        "novel-1",
        {
            "_updated_at": 1,
            "autopilot_status": "running",
            "current_stage": "writing",
            "target_chapters": 10,
            "active_invocation_session_id": "session-1",
            "active_invocation_operation": "autopilot.prose.from_script",
            "active_invocation_node_key": "autopilot-stream-beat",
            "active_invocation_status": "awaiting_pre_call_review",
            "active_invocation_policy": "AUTOPILOT_PAUSE",
            "has_active_invocation": True,
            "requires_ai_review": True,
            "autopilot_pause_reason": "awaiting_ai_review",
        },
    )

    assert status["active_invocation_session_id"] == "session-1"
    assert status["has_active_invocation"] is True
    assert status["requires_ai_review"] is True
    assert status["autopilot_pause_reason"] == "awaiting_ai_review"
    assert status["review_gate"]["status"] == "awaiting_ai_review"
    assert status["review_gate"]["can_resume"] is False


def test_autopilot_status_blocks_resume_when_macro_invocation_failed():
    status = _build_status_pure_memory(
        "novel-1",
        {
            "_updated_at": 1,
            "autopilot_status": "running",
            "current_stage": "paused_for_review",
            "target_chapters": 500,
            "active_invocation_session_id": "session-1",
            "active_invocation_operation": "autopilot.macro.plan",
            "active_invocation_node_key": "planning-quick-macro",
            "active_invocation_status": "blocked",
            "active_invocation_policy": "AUTOPILOT_PAUSE",
            "has_active_invocation": True,
            "requires_ai_review": True,
            "autopilot_pause_reason": "autopilot_macro_plan_requires_json_object",
        },
    )

    gate = status["review_gate"]
    assert gate["type"] == "macro_plan"
    assert gate["status"] == "failed"
    assert gate["artifact_status"] == "missing"
    assert gate["can_resume"] is False
    assert "尚无可确认" in gate["message"]
    assert _resume_block_reason_from_status(status) == gate["message"]


def test_autopilot_status_allows_ready_macro_review_gate():
    status = _build_status_pure_memory(
        "novel-1",
        {
            "_updated_at": 1,
            "autopilot_status": "running",
            "current_stage": "paused_for_review",
            "target_chapters": 120,
            "writing_substep": "macro_planning",
        },
    )

    gate = status["review_gate"]
    assert gate["type"] == "macro_plan"
    assert gate["status"] == "ready"
    assert gate["can_resume"] is True
    assert _resume_block_reason_from_status(status) is None


def test_autopilot_status_blocks_resume_while_macro_structure_is_not_ready():
    status = _build_status_pure_memory(
        "novel-1",
        {
            "_updated_at": 1,
            "autopilot_status": "running",
            "current_stage": "paused_for_review",
            "target_chapters": 500,
            "current_auto_chapters": 0,
            "macro_structure_ready": False,
        },
    )

    gate = status["review_gate"]
    assert gate["type"] == "macro_plan"
    assert gate["status"] == "persisting"
    assert gate["can_resume"] is False
    assert "没有可确认的大纲结构" in gate["message"]


def test_prompt_draft_is_editable_for_pre_call_blocked_session_only():
    blocked_before_attempt = _session(InvocationSessionStatus.BLOCKED)
    blocked_after_attempt = _session(InvocationSessionStatus.BLOCKED)
    blocked_after_attempt.attempts = ("attempt-1",)

    assert _is_prompt_draft_editable(_session(InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW)) is True
    assert _is_prompt_draft_editable(blocked_before_attempt) is True
    assert _is_prompt_draft_editable(blocked_after_attempt) is False
