from application.blueprint.services.setup_main_plot_invocation import (
    SETUP_MAIN_PLOT_NODE,
    SETUP_MAIN_PLOT_OPERATION,
)
from application.onboarding.setup_stage_definitions import (
    find_onboarding_stage_definition,
    get_onboarding_stage_definition,
    get_onboarding_stage_registry,
)


def test_setup_guide_registers_all_onboarding_stages():
    registry = get_onboarding_stage_registry()

    assert set(registry.stages()) >= {"worldbuilding", "characters", "locations", "main_plot"}
    assert get_onboarding_stage_definition("worldbuilding").operation == "bible.setup.worldbuilding"
    assert get_onboarding_stage_definition("characters").continuation_handler == "bible_characters"
    assert get_onboarding_stage_definition("locations").continuation_handler == "bible_locations"


def test_main_plot_stage_is_resolved_by_operation_and_node():
    definition = find_onboarding_stage_definition(
        operation=SETUP_MAIN_PLOT_OPERATION,
        node_key=SETUP_MAIN_PLOT_NODE,
    )

    assert definition is not None
    assert definition.stage == "main_plot"
    assert definition.continuation_handler == "setup_main_plot_options"


def test_main_plot_input_contract_uses_structured_variables():
    definition = get_onboarding_stage_definition("main_plot")
    bindings = {binding.alias: binding for binding in definition.input_contract()}

    assert "context_blob" not in bindings
    assert "worldbuilding_full" not in bindings
    assert bindings["core_rules"].variable_key == "novel.worldbuilding.core_rules"
    assert bindings["characters"].variable_key == "novel.characters.list"
    assert bindings["fusion_axis"].source == "derived_config"
    assert bindings["worldview_summary"].value_type == "list"

