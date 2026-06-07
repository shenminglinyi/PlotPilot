"""FastAPI route registration for PlotPilot."""
from __future__ import annotations

from fastapi import FastAPI

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

    app.include_router(novels.router, prefix=API_V1_PREFIX)
    app.include_router(taxonomy_routes.router, prefix=API_V1_PREFIX)
    app.include_router(chapters.router, prefix=NOVELS_API_PREFIX)
    app.include_router(manuscript_entity_routes.router, prefix=NOVELS_API_PREFIX)
    app.include_router(export.router, prefix=API_V1_PREFIX)
    app.include_router(llm_settings.router, prefix=API_V1_PREFIX)
    app.include_router(llm_settings.embedding_router, prefix=API_V1_PREFIX)
    app.include_router(scene_generation_routes.router, prefix=API_V1_PREFIX)

    app.include_router(bible.router, prefix=API_V1_PREFIX)
    app.include_router(cast.router, prefix=API_V1_PREFIX)
    app.include_router(knowledge.router, prefix=API_V1_PREFIX)
    app.include_router(knowledge_graph_routes.router, prefix=API_V1_PREFIX)
    app.include_router(worldbuilding_routes.router, prefix=API_V1_PREFIX)

    app.include_router(continuous_planning_routes.router, prefix=API_V1_PREFIX)
    app.include_router(beat_sheet_routes.router, prefix=API_V1_PREFIX)
    app.include_router(story_structure.router, prefix=API_V1_PREFIX)
    app.include_router(confluence_router, prefix=API_V1_PREFIX)

    app.include_router(generation.router, prefix=API_V1_PREFIX)
    app.include_router(context_intelligence.router, prefix=API_V1_PREFIX)
    app.include_router(chronicles.router, prefix=API_V1_PREFIX)
    app.include_router(snapshot_routes.router, prefix=API_V1_PREFIX)
    app.include_router(autopilot_routes.router, prefix=API_V1_PREFIX)
    app.include_router(workbench_context_routes.router, prefix=API_V1_PREFIX)
    app.include_router(character_scheduler_routes.router, prefix=API_V1_PREFIX)
    app.include_router(checkpoint_routes.router, prefix=API_V1_PREFIX)
    app.include_router(narrative_engine_routes.router, prefix=API_V1_PREFIX)
    app.include_router(narrative_engine_routes.surface_router, prefix=API_V1_PREFIX)
    app.include_router(governance_routes.router, prefix=API_V1_PREFIX)
    app.include_router(worldline_routes.router, prefix=API_V1_PREFIX)
    app.include_router(evolution_routes.router, prefix=API_V1_PREFIX)
    app.include_router(ai_invocation_routes.router, prefix=API_V1_PREFIX)
    app.include_router(prop_routes.router, prefix=API_V1_PREFIX)
    app.include_router(trace_router, prefix=API_V1_PREFIX)
    app.include_router(dag_router, prefix=API_V1_PREFIX)

    app.include_router(chapter_review_routes.router, prefix=API_V1_PREFIX)
    app.include_router(macro_refactor.router, prefix=API_V1_PREFIX)
    app.include_router(chapter_element_routes.router, prefix=API_V1_PREFIX)

    app.include_router(voice.router, prefix=API_V1_PREFIX)
    app.include_router(narrative_state.router, prefix=API_V1_PREFIX)
    app.include_router(foreshadow_ledger.router, prefix=API_V1_PREFIX)
    app.include_router(system_routes.router, prefix=API_V1_PREFIX)
    app.include_router(reader_module.router, prefix=API_V1_PREFIX)

    app.include_router(writer_block.router, prefix=API_V1_PREFIX)
    app.include_router(sandbox.router, prefix=API_V1_PREFIX)
    app.include_router(monitor.router, prefix=API_V1_PREFIX)
    app.include_router(llm_control.router, prefix=API_V1_PREFIX)
    app.include_router(anti_ai_routes.router, prefix=API_V1_PREFIX)

    stats_repository = SqliteStatsRepositoryAdapter(get_database())
    stats_service = StatsService(stats_repository)
    stats_router = create_stats_router(stats_service)
    app.include_router(stats_router, prefix=STATS_API_PREFIX, tags=["statistics"])
