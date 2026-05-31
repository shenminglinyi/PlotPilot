"""Continuation handlers for accepted AI Invocation outputs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from application.ai_invocation.dtos import AdoptionDecision, InvocationSession


@dataclass(frozen=True)
class ContinuationContext:
    session: InvocationSession
    decision: AdoptionDecision


ContinuationHandler = Callable[[ContinuationContext], Mapping[str, Any]]


class ContinuationRegistry:
    """Small registry that keeps business continuation logic out of routes."""

    def __init__(self):
        self._handlers: dict[str, ContinuationHandler] = {}

    def register(self, key: str, handler: ContinuationHandler) -> None:
        if not key:
            raise ValueError("continuation handler key is required")
        self._handlers[key] = handler

    def execute(self, context: ContinuationContext) -> dict[str, Any]:
        key = context.session.continuation.handler_key if context.session.continuation else ""
        if not key:
            return {}
        handler = self._handlers.get(key)
        if handler is None:
            raise KeyError(f"continuation handler not registered: {key}")
        return dict(handler(context) or {})


_registry = ContinuationRegistry()


def register_continuation_handler(key: str, handler: ContinuationHandler) -> None:
    _registry.register(key, handler)


def execute_continuation(context: ContinuationContext) -> dict[str, Any]:
    return _registry.execute(context)
