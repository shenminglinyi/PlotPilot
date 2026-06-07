"""FastAPI route registration for PlotPilot."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from fastapi import APIRouter, FastAPI

from infrastructure.persistence.database.connection import get_database
from interfaces.api.settings import (
    API_V1_PREFIX,
    NOVELS_API_PREFIX,
    STATS_API_PREFIX,
)
from interfaces.api.stats.repositories.sqlite_stats_repository_adapter import (
    SqliteStatsRepositoryAdapter,
)
from interfaces.api.stats.routers.stats import create_stats_router
from interfaces.api.stats.services.stats_service import StatsService


@dataclass(frozen=True)
class RouterRegistration:
    """Declarative API router registration metadata."""

    router: APIRouter
    prefix: str
    tags: tuple[str, ...] = ()


def _include_registered_routes(
    app: FastAPI,
    registrations: Sequence[RouterRegistration],
) -> None:
    for registration in registrations:
        kwargs = {}
        if registration.tags:
            kwargs["tags"] = list(registration.tags)
        app.include_router(
            registration.router,
            prefix=registration.prefix,
            **kwargs,
        )


def register_api_routes(app: FastAPI) -> None:
    """Register all backend routes without changing public prefixes."""
    from interfaces.api.v1 import anti_ai as anti_ai_routes
    from interfaces.api.v1 import reader as reader_module
    from interfaces.api.v1 import system as system_routes
    from interfaces.api.v1.analyst import foreshadow_ledger, narrative_state, voice
    from interfaces.api.v1.audit import (
        chapter_element_routes,
        chapter_review_routes,
        macro_refactor,
    )
    from interfaces.api.v1.blueprint import (
        beat_sheet_routes,
        continuous_planning_routes,
        story_structure,
    )
    from interfaces.api.v1.blueprint.confluence_routes import router as confluence_router
    from interfaces.api.v1.core import (
        chapters,
        export,
        manuscript_entity_routes,
        novels,
        scene_generation_routes,
        settings as llm_settings,
    )
    from interfaces.api.v1.engine import (
        ai_invocation_routes,
        autopilot_routes,
        character_scheduler_routes,
        checkpoint_routes,
        chronicles,
        context_intelligence,
        evolution_routes,
        generation,
        governance_routes,
        narrative_engine_routes,
        snapshot_routes,
        workbench_context_routes,
        worldline_routes,
    )
    from interfaces.api.v1.engine.dag.dag_routes import router as dag_router
    from interfaces.api.v1.engine.trace_routes import router as trace_router
    from interfaces.api.v1.meta import taxonomy_routes
    from interfaces.api.v1.prop import prop_routes
    from interfaces.api.v1.workbench import llm_control, monitor, sandbox, writer_block
    from interfaces.api.v1.world import (
        bible,
        cast,
        knowledge,
        knowledge_graph_routes,
        worldbuilding_routes,
    )

    _include_registered_routes(
        app,
        (
            RouterRegistration(novels.router, API_V1_PREFIX),
            RouterRegistration(taxonomy_routes.router, API_V1_PREFIX),
            RouterRegistration(chapters.router, NOVELS_API_PREFIX),
            RouterRegistration(manuscript_entity_routes.router, NOVELS_API_PREFIX),
            RouterRegistration(export.router, API_V1_PREFIX),
            RouterRegistration(llm_settings.router, API_V1_PREFIX),
            RouterRegistration(llm_settings.embedding_router, API_V1_PREFIX),
            RouterRegistration(scene_generation_routes.router, API_V1_PREFIX),
            RouterRegistration(bible.router, API_V1_PREFIX),
            RouterRegistration(cast.router, API_V1_PREFIX),
            RouterRegistration(knowledge.router, API_V1_PREFIX),
            RouterRegistration(knowledge_graph_routes.router, API_V1_PREFIX),
            RouterRegistration(worldbuilding_routes.router, API_V1_PREFIX),
            RouterRegistration(continuous_planning_routes.router, API_V1_PREFIX),
            RouterRegistration(beat_sheet_routes.router, API_V1_PREFIX),
            RouterRegistration(story_structure.router, API_V1_PREFIX),
            RouterRegistration(confluence_router, API_V1_PREFIX),
            RouterRegistration(generation.router, API_V1_PREFIX),
            RouterRegistration(context_intelligence.router, API_V1_PREFIX),
            RouterRegistration(chronicles.router, API_V1_PREFIX),
            RouterRegistration(snapshot_routes.router, API_V1_PREFIX),
            RouterRegistration(autopilot_routes.router, API_V1_PREFIX),
            RouterRegistration(workbench_context_routes.router, API_V1_PREFIX),
            RouterRegistration(character_scheduler_routes.router, API_V1_PREFIX),
            RouterRegistration(checkpoint_routes.router, API_V1_PREFIX),
            RouterRegistration(narrative_engine_routes.router, API_V1_PREFIX),
            RouterRegistration(narrative_engine_routes.surface_router, API_V1_PREFIX),
            RouterRegistration(governance_routes.router, API_V1_PREFIX),
            RouterRegistration(worldline_routes.router, API_V1_PREFIX),
            RouterRegistration(evolution_routes.router, API_V1_PREFIX),
            RouterRegistration(ai_invocation_routes.router, API_V1_PREFIX),
            RouterRegistration(prop_routes.router, API_V1_PREFIX),
            RouterRegistration(trace_router, API_V1_PREFIX),
            RouterRegistration(dag_router, API_V1_PREFIX),
            RouterRegistration(chapter_review_routes.router, API_V1_PREFIX),
            RouterRegistration(macro_refactor.router, API_V1_PREFIX),
            RouterRegistration(chapter_element_routes.router, API_V1_PREFIX),
            RouterRegistration(voice.router, API_V1_PREFIX),
            RouterRegistration(narrative_state.router, API_V1_PREFIX),
            RouterRegistration(foreshadow_ledger.router, API_V1_PREFIX),
            RouterRegistration(system_routes.router, API_V1_PREFIX),
            RouterRegistration(reader_module.router, API_V1_PREFIX),
            RouterRegistration(writer_block.router, API_V1_PREFIX),
            RouterRegistration(sandbox.router, API_V1_PREFIX),
            RouterRegistration(monitor.router, API_V1_PREFIX),
            RouterRegistration(llm_control.router, API_V1_PREFIX),
            RouterRegistration(anti_ai_routes.router, API_V1_PREFIX),
        ),
    )

    stats_repository = SqliteStatsRepositoryAdapter(get_database())
    stats_service = StatsService(stats_repository)
    stats_router = create_stats_router(stats_service)
    _include_registered_routes(
        app,
        (RouterRegistration(stats_router, STATS_API_PREFIX, ("statistics",)),),
    )
