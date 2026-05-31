"""Continuation handler for setup.main_plot_options."""
from __future__ import annotations

import json
from typing import Any, Mapping

from application.ai_invocation.continuation import ContinuationContext, register_continuation_handler
from application.blueprint.services.setup_main_plot_suggestion_service import normalize_main_plot_options


def _context_from_session(context: Mapping[str, Any]) -> dict[str, Any]:
    raw = context.get("setup_context")
    return dict(raw) if isinstance(raw, Mapping) else {}


def setup_main_plot_options_handler(context: ContinuationContext) -> Mapping[str, Any]:
    ctx = _context_from_session(context.session.context)
    if not ctx:
        return {}
    options = normalize_main_plot_options(context.decision.accepted_content or "", ctx)
    return {
        "novel_id": str(context.session.context.get("novel_id") or ""),
        "plot_options": options,
        "plot_options_json": json.dumps(options, ensure_ascii=False),
        "session_id": context.session.id,
    }


def register_setup_main_plot_continuation() -> None:
    register_continuation_handler("setup_main_plot_options", setup_main_plot_options_handler)
