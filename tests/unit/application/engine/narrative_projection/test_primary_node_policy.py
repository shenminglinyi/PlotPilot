"""primary_node_policy — 声明式主节点解析"""
from __future__ import annotations

import pytest

from application.engine.narrative_projection.primary_node_policy import (
    clear_policy_hooks_for_tests,
    register_policy_hook,
    resolve_primary_node_type,
)
from application.engine.narrative_projection.runtime_snapshot import NarrativeRuntimeSnapshot


@pytest.fixture(autouse=True)
def _clear_hooks_after_each() -> None:
    yield
    clear_policy_hooks_for_tests()


def test_resolve_llm_calling():
    s = NarrativeRuntimeSnapshot("n1", "running", "writing", "llm_calling", None)
    assert resolve_primary_node_type(s) == ("exec_writer", "running")


def test_hook_overrides():
    def force_ctx(_s: NarrativeRuntimeSnapshot, _sem):
        return ("ctx_memory", "running")

    register_policy_hook(force_ctx)
    s = NarrativeRuntimeSnapshot("n1", "running", "writing", "llm_calling", None)
    assert resolve_primary_node_type(s) == ("ctx_memory", "running")
