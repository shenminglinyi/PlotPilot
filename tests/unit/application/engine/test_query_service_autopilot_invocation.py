from application.engine.services.query_service import QueryService
from application.engine.services.shared_state_repository import NovelState, SharedStateRepository


def test_query_service_status_dict_exposes_active_invocation_flag():
    repo = SharedStateRepository(shared_dict={})
    repo.set_novel_state(
        "novel-1",
        NovelState(
            novel_id="novel-1",
            title="Demo",
            autopilot_status="running",
            current_stage="writing",
            current_act=None,
            current_chapter_in_act=None,
            current_beat_index=0,
            current_auto_chapters=0,
            target_chapters=10,
            target_words_per_chapter=2500,
            consecutive_error_count=0,
            last_chapter_tension=0,
            auto_approve_mode=False,
            needs_review=False,
            active_invocation_session_id="session-1",
            active_invocation_operation="autopilot.prose.from_script",
            active_invocation_node_key="autopilot-stream-beat",
            active_invocation_status="generating",
            active_invocation_policy="AUTOPILOT_PAUSE",
            has_active_invocation=True,
            requires_ai_review=False,
            autopilot_pause_reason="",
        ),
    )

    status = QueryService(repo).get_novel_status_dict("novel-1")

    assert status is not None
    assert status["active_invocation_session_id"] == "session-1"
    assert status["has_active_invocation"] is True
    assert status["active_invocation_status"] == "generating"


def test_query_service_keeps_completed_invocation_session_without_active_flag():
    repo = SharedStateRepository(shared_dict={})
    repo.set_novel_state(
        "novel-1",
        NovelState(
            novel_id="novel-1",
            title="Demo",
            autopilot_status="running",
            current_stage="writing",
            current_act=None,
            current_chapter_in_act=None,
            current_beat_index=0,
            current_auto_chapters=0,
            target_chapters=10,
            target_words_per_chapter=2500,
            consecutive_error_count=0,
            last_chapter_tension=0,
            auto_approve_mode=True,
            needs_review=False,
            active_invocation_session_id="session-1",
            active_invocation_operation="autopilot.prose.from_script",
            active_invocation_node_key="autopilot-stream-beat",
            active_invocation_status="completed",
            active_invocation_policy="DIRECT",
            has_active_invocation=False,
            requires_ai_review=False,
            autopilot_pause_reason="",
        ),
    )

    status = QueryService(repo).get_novel_status_dict("novel-1")

    assert status is not None
    assert status["active_invocation_session_id"] == "session-1"
    assert status["has_active_invocation"] is False
    assert status["requires_ai_review"] is False
