"""Published setup-guide onboarding stage definitions."""
from __future__ import annotations

from typing import Any, Mapping

from application.onboarding.stage_registry import OnboardingStageDefinition, OnboardingStageRegistry


def _bible_context_provider(*, stage: str, novel: Any, bible_generator: Any) -> Mapping[str, Any]:
    from application.world.services.bible_setup_invocation import build_bible_setup_variables

    return build_bible_setup_variables(
        stage=stage,
        novel=novel,
        bible_service=bible_generator.bible_service,
        worldbuilding_service=bible_generator.worldbuilding_service,
    )


def _ensure_bible_stage_contract(stage: str):
    def _ensure(db) -> Any:
        from application.world.services.bible_setup_invocation import ensure_bible_setup_contract

        definition = get_onboarding_stage_definition(stage)
        return ensure_bible_setup_contract(db, operation=definition.operation, node_key=definition.node_key)

    return _ensure


def _definitions() -> list[OnboardingStageDefinition]:
    from application.blueprint.services.setup_main_plot_invocation import (
        SETUP_MAIN_PLOT_NODE,
        SETUP_MAIN_PLOT_OPERATION,
        SETUP_MAIN_PLOT_STAGE,
        build_setup_main_plot_invocation_variables,
        ensure_setup_main_plot_contract,
        main_plot_ui_events,
        setup_main_plot_input_bindings,
        setup_main_plot_output_bindings,
        setup_main_plot_spec,
    )
    from application.world.services.bible_setup_invocation import (
        BIBLE_SETUP_CHARACTERS_NODE,
        BIBLE_SETUP_LOCATIONS_NODE,
        BIBLE_SETUP_WORLD_NODE,
        bible_setup_characters_spec,
        bible_setup_input_bindings,
        bible_setup_locations_spec,
        bible_setup_world_spec,
    )
    from application.world.services.bible_setup_output_bindings import bible_setup_output_bindings

    return [
        OnboardingStageDefinition(
            stage="worldbuilding",
            operation="bible.setup.worldbuilding",
            node_key=BIBLE_SETUP_WORLD_NODE,
            input_contract=lambda: bible_setup_input_bindings(BIBLE_SETUP_WORLD_NODE),
            output_contract=lambda: bible_setup_output_bindings(BIBLE_SETUP_WORLD_NODE),
            context_provider=_bible_context_provider,
            continuation_handler="bible_worldbuilding",
            spec_provider=bible_setup_world_spec,
            contract_ensurer=_ensure_bible_stage_contract("worldbuilding"),
            ui_events={
                "sse_phase": "worldbuilding",
                "review_event": "approval_required",
                "done_event": "worldbuilding_done",
            },
        ),
        OnboardingStageDefinition(
            stage="characters",
            operation="bible.setup.characters",
            node_key=BIBLE_SETUP_CHARACTERS_NODE,
            input_contract=lambda: bible_setup_input_bindings(BIBLE_SETUP_CHARACTERS_NODE),
            output_contract=lambda: bible_setup_output_bindings(BIBLE_SETUP_CHARACTERS_NODE),
            context_provider=_bible_context_provider,
            continuation_handler="bible_characters",
            spec_provider=bible_setup_characters_spec,
            contract_ensurer=_ensure_bible_stage_contract("characters"),
            ui_events={
                "sse_phase": "characters",
                "review_event": "approval_required",
                "done_event": "characters_done",
            },
        ),
        OnboardingStageDefinition(
            stage="locations",
            operation="bible.setup.locations",
            node_key=BIBLE_SETUP_LOCATIONS_NODE,
            input_contract=lambda: bible_setup_input_bindings(BIBLE_SETUP_LOCATIONS_NODE),
            output_contract=lambda: bible_setup_output_bindings(BIBLE_SETUP_LOCATIONS_NODE),
            context_provider=_bible_context_provider,
            continuation_handler="bible_locations",
            spec_provider=bible_setup_locations_spec,
            contract_ensurer=_ensure_bible_stage_contract("locations"),
            ui_events={
                "sse_phase": "locations",
                "review_event": "approval_required",
                "done_event": "locations_done",
            },
        ),
        OnboardingStageDefinition(
            stage=SETUP_MAIN_PLOT_STAGE,
            operation=SETUP_MAIN_PLOT_OPERATION,
            node_key=SETUP_MAIN_PLOT_NODE,
            input_contract=setup_main_plot_input_bindings,
            output_contract=setup_main_plot_output_bindings,
            context_provider=lambda *, setup_context: build_setup_main_plot_invocation_variables(setup_context),
            continuation_handler="setup_main_plot_options",
            spec_provider=setup_main_plot_spec,
            contract_ensurer=ensure_setup_main_plot_contract,
            ui_events=main_plot_ui_events(),
        ),
    ]


_REGISTRY: OnboardingStageRegistry | None = None


def get_onboarding_stage_registry() -> OnboardingStageRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = OnboardingStageRegistry(_definitions())
    return _REGISTRY


def get_onboarding_stage_definition(stage: str) -> OnboardingStageDefinition:
    return get_onboarding_stage_registry().get(stage)


def find_onboarding_stage_definition(*, operation: str, node_key: str) -> OnboardingStageDefinition | None:
    return get_onboarding_stage_registry().find(operation=operation, node_key=node_key)


def ensure_onboarding_stage_contract(*, operation: str, node_key: str, db: Any):
    return get_onboarding_stage_registry().ensure_contract(operation=operation, node_key=node_key, db=db)

