from pathlib import Path


def test_autopilot_modules_do_not_import_llm_service_directly():
    root = Path("application/ai_invocation/autopilot")
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "from domain.ai.services.llm_service import LLMService" in text:
            offenders.append(path.as_posix())
    assert offenders == []


def test_autopilot_runtime_no_longer_contains_direct_llm_fallback_copy():
    targets = [
        Path("engine/pipeline/base.py"),
        Path("engine/runtime/daemon_host.py"),
    ]
    forbidden_fragments = [
        "回退直连 LLM",
        "降级为直连流式 LLM",
    ]
    offenders = []
    for path in targets:
        text = path.read_text(encoding="utf-8")
        if any(fragment in text for fragment in forbidden_fragments):
            offenders.append(path.as_posix())
    assert offenders == []


def test_daemon_stream_watch_routes_novel_calls_to_invocation_before_provider_stream():
    text = Path("engine/runtime/daemon_host.py").read_text(encoding="utf-8")
    invocation_call = "return await self._stream_llm_via_autopilot_invocation("
    provider_stream = "async for chunk in self.llm_service.stream_generate(prompt, config):"
    direct_failure = "raise"

    assert invocation_call in text
    assert provider_stream in text
    assert text.index(invocation_call) < text.index(provider_stream)
    novel_branch_start = text.index("if novel is not None:")
    provider_stream_index = text.index(provider_stream)
    novel_branch = text[novel_branch_start:provider_stream_index]
    assert "AI Invocation 写作通道不可用，停止自动驾驶直连回退" in novel_branch
    assert direct_failure in novel_branch


def test_autopilot_panel_opens_ai_panel_for_any_active_invocation():
    text = Path("frontend/src/components/autopilot/AutopilotPanel.vue").read_text(encoding="utf-8")

    assert "function statusHasActiveInvocation" in text
    assert "if (!sessionId) return" in text
    assert "if (!statusHasActiveInvocation(s) || !sessionId) return" not in text
    assert "if (!s?.requires_ai_review || !sessionId) return" not in text


def test_daemon_shared_state_fallback_does_not_import_interfaces_main_when_daemon():
    text = Path("engine/runtime/daemon_host.py").read_text(encoding="utf-8")

    heartbeat_guard = "if multiprocessing.current_process().daemon:"
    fallback_import = "from interfaces.main import update_shared_novel_state"

    assert heartbeat_guard in text
    assert fallback_import in text
    assert text.index(heartbeat_guard) < text.index(fallback_import)
