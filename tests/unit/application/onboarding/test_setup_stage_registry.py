from application.blueprint.services.setup_plot_outline_invocation import (
    SETUP_PLOT_OUTLINE_NODE,
    SETUP_PLOT_OUTLINE_OPERATION,
)
from application.onboarding.setup_stage_definitions import (
    find_onboarding_stage_definition,
    get_onboarding_stage_definition,
    get_onboarding_stage_registry,
)


def test_setup_guide_registers_all_onboarding_stages():
    registry = get_onboarding_stage_registry()

    assert set(registry.stages()) >= {"worldbuilding", "characters", "locations", "plot_outline"}
    assert get_onboarding_stage_definition("worldbuilding").operation == "bible.setup.worldbuilding"
    assert get_onboarding_stage_definition("characters").continuation_handler == "bible_characters"
    assert get_onboarding_stage_definition("locations").continuation_handler == "bible_locations"


def test_plot_outline_stage_is_resolved_by_operation_and_node():
    definition = find_onboarding_stage_definition(
        operation=SETUP_PLOT_OUTLINE_OPERATION,
        node_key=SETUP_PLOT_OUTLINE_NODE,
    )

    assert definition is not None
    assert definition.stage == "plot_outline"
    assert definition.continuation_handler == "setup_plot_outline"


def test_plot_outline_input_contract_uses_structured_variables():
    definition = get_onboarding_stage_definition("plot_outline")
    bindings = {binding.alias: binding for binding in definition.input_contract()}

    assert "context_blob" not in bindings
    assert "worldbuilding_full" not in bindings
    assert bindings["core_rules"].variable_key == "novel.worldbuilding.core_rules"
    assert bindings["characters_brief"].variable_key == "novel.characters.list"
    assert bindings["plot_outline_phase_schema"].source == "derived_config"
    assert bindings["plot_outline_phase_schema"].value_type == "list"
