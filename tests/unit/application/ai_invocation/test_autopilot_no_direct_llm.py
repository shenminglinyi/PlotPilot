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


def test_autopilot_panel_respects_ai_invocation_debug_flag():
    text = Path("frontend/src/components/autopilot/AutopilotPanel.vue").read_text(encoding="utf-8")

    assert "function statusHasActiveInvocation" in text
    assert 'v-if="reviewGateNeedsAIPanel && featureFlags.aiInvocationDebug"' in text
    assert "void openActiveInvocation(sessionId, { showPanel: featureFlags.aiInvocationDebug })" in text
    assert "if (!sessionId) return" in text
    assert "if (!statusHasActiveInvocation(s) || !sessionId) return" not in text
    assert "if (!s?.requires_ai_review || !sessionId) return" not in text


def test_ai_invocation_review_panel_is_debug_only():
    app_text = Path("frontend/src/App.vue").read_text(encoding="utf-8")
    store_text = Path("frontend/src/stores/aiInvocationStore.ts").read_text(encoding="utf-8-sig")

    assert '<AIInvocationReviewPanel v-if="featureFlags.aiInvocationDebug" />' in app_text
    assert "<AIInvocationReviewPanel />" not in app_text
    assert "function showDebugPanel()" in store_text
    assert "if (debugPanelEnabled.value) {" in store_text
    assert "visible.value = true" in store_text
    assert "if (debugPanelEnabled.value) return" in store_text


def test_daemon_shared_state_fallback_uses_runtime_state_after_daemon_guard():
    text = Path("engine/runtime/daemon_host.py").read_text(encoding="utf-8")

    heartbeat_guard = "if multiprocessing.current_process().daemon:"
    fallback_import = "from interfaces.runtime_state import update_shared_novel_state"

    assert heartbeat_guard in text
    assert fallback_import in text
    assert text.index(heartbeat_guard) < text.index(fallback_import)
