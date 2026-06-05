"""Continuation handler for setup.main_plot_options."""
from __future__ import annotations

import json
from typing import Any, Mapping

from application.ai_invocation.continuation import ContinuationContext, register_continuation_handler
from application.ai_invocation.output_binding_resolution import (
    extract_bound_output_values,
    load_session_output_bindings,
    parse_accepted_json,
)
from application.blueprint.services.setup_main_plot_suggestion_service import (
    normalize_main_plot_options,
    normalize_main_plot_options_data,
)


def _context_from_session(context: ContinuationContext) -> dict[str, Any]:
    raw = context.session.context.get("setup_context")
    setup_context = dict(raw) if isinstance(raw, Mapping) else {}
    aliases = context.session.variable_plan.aliases if context.session.variable_plan is not None else {}
    if not isinstance(aliases, Mapping):
        aliases = {}

    return {
        "target_chapters": aliases.get("novel.target_chapters", setup_context.get("target_chapters", 100)),
        "fusion_axis": setup_context.get("fusion_axis", {}),
        "fusion_contract": aliases.get("plot.fusion_contract", setup_context.get("fusion_contract", "")),
        "protagonist": aliases.get("characters.protagonist", {}),
        "characters": aliases.get("characters.list", setup_context.get("characters", setup_context.get("other_characters", []))),
        "locations": aliases.get("locations.list", setup_context.get("locations", [])),
    }


def setup_main_plot_options_handler(context: ContinuationContext) -> Mapping[str, Any]:
    ctx = _context_from_session(context)
    if not ctx:
        return {}
    parsed = parse_accepted_json(context.decision.accepted_content or "")
    options = None
    if parsed is not None:
        bindings = load_session_output_bindings(context.session)
        _, by_variable_key = extract_bound_output_values(parsed, bindings)
        raw_options = by_variable_key.get("plot.main_options")
        if raw_options is not None:
            options = normalize_main_plot_options_data(raw_options, ctx)
    if options is None:
        options = normalize_main_plot_options(context.decision.accepted_content or "", ctx)
    return {
        "novel_id": str(context.session.context.get("novel_id") or ""),
        "plot_options": options,
        "plot_options_json": json.dumps(options, ensure_ascii=False),
        "session_id": context.session.id,
        "protagonist": ctx.get("protagonist") or {},
        "characters": ctx.get("characters") or [],
        "locations": ctx.get("locations") or [],
        "fusion_contract": ctx.get("fusion_contract") or "",
    }


def register_setup_main_plot_continuation() -> None:
    register_continuation_handler("setup_main_plot_options", setup_main_plot_options_handler)
