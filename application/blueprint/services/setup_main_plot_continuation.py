"""Continuation handler for setup.main_plot_options."""
from __future__ import annotations

import json
from typing import Any, Mapping

from application.ai_invocation.continuation import ContinuationContext, register_continuation_handler
from application.blueprint.services.setup_main_plot_suggestion_service import normalize_main_plot_options


def _context_from_session(context: ContinuationContext) -> dict[str, Any]:
    raw = context.session.context.get("setup_context")
    setup_context = dict(raw) if isinstance(raw, Mapping) else {}
    aliases = context.session.variable_plan.aliases if context.session.variable_plan is not None else {}
    if not isinstance(aliases, Mapping):
        aliases = {}

    theme_metadata = setup_context.get("theme_metadata") if isinstance(setup_context.get("theme_metadata"), Mapping) else {}
    merged = {
        **setup_context,
        "novel_title": aliases.get("novel_title", setup_context.get("novel_title", "")),
        "premise": aliases.get("premise", setup_context.get("premise", "")),
        "target_chapters": aliases.get("target_chapters", setup_context.get("target_chapters", 100)),
        "target_words_per_chapter": aliases.get(
            "target_words_per_chapter",
            setup_context.get("target_words_per_chapter", 0),
        ),
        "fusion_axis": aliases.get("fusion_axis", setup_context.get("fusion_axis", {})),
        "fusion_contract": aliases.get("fusion_contract", setup_context.get("fusion_contract", "")),
        "protagonist": aliases.get("protagonist", setup_context.get("protagonist", {})),
        "other_characters": aliases.get("other_characters", setup_context.get("other_characters", [])),
        "locations": aliases.get("locations", setup_context.get("locations", [])),
        "worldview_summary": aliases.get("worldview_summary", setup_context.get("worldview_summary", [])),
        "style_hint": aliases.get("style_hint", setup_context.get("style_hint", "")),
        "worldbuilding_full": aliases.get("worldbuilding_full", setup_context.get("worldbuilding_full", "")),
        "core_rules": aliases.get("core_rules", setup_context.get("core_rules", {})),
        "geography": aliases.get("geography", setup_context.get("geography", {})),
        "society": aliases.get("society", setup_context.get("society", {})),
        "culture": aliases.get("culture", setup_context.get("culture", {})),
        "daily_life": aliases.get("daily_life", setup_context.get("daily_life", {})),
        "context_blob": aliases.get("context_blob", setup_context.get("context_blob", "")),
    }
    merged["theme_metadata"] = {
        **dict(theme_metadata),
        "genre_label": aliases.get("genre_label", theme_metadata.get("genre_label", "")),
        "world_preset": aliases.get("world_preset", theme_metadata.get("world_preset", "")),
    }
    return merged


def setup_main_plot_options_handler(context: ContinuationContext) -> Mapping[str, Any]:
    ctx = _context_from_session(context)
    if not ctx:
        return {}
    options = normalize_main_plot_options(context.decision.accepted_content or "", ctx)
    return {
        "novel_id": str(context.session.context.get("novel_id") or ""),
        "plot_options": options,
        "plot_options_json": json.dumps(options, ensure_ascii=False),
        "session_id": context.session.id,
        "context_blob": ctx.get("context_blob") or "",
        "worldbuilding_full": ctx.get("worldbuilding_full") or "",
        "protagonist": ctx.get("protagonist") or {},
        "locations": ctx.get("locations") or [],
        "fusion_contract": ctx.get("fusion_contract") or "",
    }


def register_setup_main_plot_continuation() -> None:
    register_continuation_handler("setup_main_plot_options", setup_main_plot_options_handler)
