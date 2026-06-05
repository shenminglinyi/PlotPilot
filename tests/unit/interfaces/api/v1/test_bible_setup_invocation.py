from types import SimpleNamespace

import pytest

from interfaces.api.v1.world import bible


class _FakeGateway:
    def __init__(self, **_kwargs):
        pass

    async def invoke(self, _request):
        return SimpleNamespace(
            session=SimpleNamespace(
                id="session-1",
                operation="bible.setup.worldbuilding",
                node_key="bible.setup.worldbuilding",
                policy=SimpleNamespace(value="full_interactive"),
                status=SimpleNamespace(value="awaiting_user"),
                context={"novel_id": "novel-1", "stage": "worldbuilding"},
                metadata={"source": "novel_setup_guide"},
                attempts=[],
                prompt_snapshot=None,
                variable_plan=None,
            ),
            attempt=None,
            decision=None,
            commit=None,
        )


def _fake_stage_definition():
    return SimpleNamespace(
        operation="bible.setup.worldbuilding",
        node_key="bible.setup.worldbuilding",
        contract_ensurer=lambda _db: None,
        context_provider=lambda **_kwargs: {"premise": "test premise"},
    )


@pytest.mark.asyncio
async def test_create_bible_setup_invocation_returns_session_payload(monkeypatch):
    fake_routes = SimpleNamespace(
        _repositories=lambda: {
            "spec": SimpleNamespace(get=lambda *_args, **_kwargs: None),
            "variable_hub": SimpleNamespace(get_output_bindings=lambda *_args, **_kwargs: []),
        },
        _save_invocation_result=lambda *_args, **_kwargs: None,
        _attempt_payload=lambda attempt: attempt,
        _decision_payload=lambda decision: decision,
        _commit_payload=lambda commit: commit,
        _next_action=lambda _status: "approval_required",
        _session_payload=lambda repos, session: {"id": session.id, "output_bindings": []},
    )

    monkeypatch.setattr(
        bible,
        "register_bible_setup_continuations",
        lambda: None,
    )
    monkeypatch.setattr(
        bible,
        "get_onboarding_stage_definition",
        lambda _stage: _fake_stage_definition(),
    )
    monkeypatch.setattr(bible, "_backfill_bible_setup_variable_hub", lambda **_kwargs: None)
    monkeypatch.setattr(bible, "AIInvocationGateway", _FakeGateway)

    import sys

    monkeypatch.setitem(
        sys.modules,
        "interfaces.api.v1.engine.ai_invocation_routes",
        fake_routes,
    )

    payload = await bible._create_bible_setup_invocation(
        novel_id="novel-1",
        stage="worldbuilding",
        novel=SimpleNamespace(title="Test Novel"),
        bible_generator=SimpleNamespace(llm_service=object()),
    )

    assert payload["session"] == {"id": "session-1", "output_bindings": []}
    assert payload["next_action"] == "approval_required"
