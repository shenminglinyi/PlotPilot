from pathlib import Path

import application.blueprint.services.setup_plot_outline_invocation as setup_plot_outline_invocation
from application.blueprint.services.setup_plot_outline_invocation import (
    SETUP_PLOT_OUTLINE_NODE,
    SETUP_PLOT_OUTLINE_OPERATION,
)
from application.onboarding.setup_stage_definitions import (
    find_onboarding_stage_definition,
    get_onboarding_stage_definition,
    get_onboarding_stage_registry,
)

_PLOT_OUTLINE_PACKAGE_DIR = (
    Path(__file__).resolve().parents[4]
    / "infrastructure"
    / "ai"
    / "prompt_packages"
    / "nodes"
    / "planning-plot-outline"
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


def test_plot_outline_input_contract_uses_variable_center_keys():
    definition = get_onboarding_stage_definition("plot_outline")
    bindings = {binding.alias: binding for binding in definition.input_contract()}

    assert "context_blob" not in bindings
    assert "worldbuilding_full" not in bindings
    assert "plot.main_options" not in bindings
    assert bindings["novel.premise"].variable_key == "novel.premise"
    assert "characters.protagonist" not in bindings
    assert "worldbuilding.style" not in bindings
    assert bindings["characters.list"].variable_key == "characters.list"
    assert bindings["locations.list"].variable_key == "locations.list"


def test_plot_outline_input_contract_normalizes_structured_variable_access(monkeypatch):
    monkeypatch.setattr(
        setup_plot_outline_invocation,
        "_declared_variable_keys",
        lambda node_key: {"novel.premise", "characters.list[0]", "worldbuilding.content.core_rules"},
    )

    bindings = {binding.alias: binding for binding in setup_plot_outline_invocation.setup_plot_outline_input_bindings()}

    assert "characters.list[0]" not in bindings
    assert "worldbuilding.content.core_rules" not in bindings
    assert bindings["characters.list"].variable_key == "characters.list"
    assert bindings["worldbuilding.content"].variable_key == "worldbuilding.content"


def test_plot_outline_prompt_package_keeps_source_settings_as_priority():
    system = (_PLOT_OUTLINE_PACKAGE_DIR / "system.md").read_text(encoding="utf-8")
    user = (_PLOT_OUTLINE_PACKAGE_DIR / "user.md").read_text(encoding="utf-8")
    combined = f"{system}\n{user}"

    assert "characters.protagonist" not in combined
    assert "characters.list[0]" not in combined
    assert "【人物设定（首位为主角）】" in user
    assert "金手指初次启用" not in combined
    assert "主角实力蜕变" not in combined
    assert "巅峰决战" not in combined
    assert "只有原设明确存在时" in combined
    assert "现实校园、都市、职场" in combined


def test_onboarding_output_contracts_use_novel_scope_and_expected_stage():
    plot_outline_definition = get_onboarding_stage_definition("plot_outline")

    plot_outline_outputs = {binding.variable_key: binding for binding in plot_outline_definition.output_contract()}

    assert plot_outline_outputs["plot.outline"].scope == "novel"
    assert plot_outline_outputs["plot.main_story_overview"].scope == "novel"
    assert plot_outline_outputs["plot.stage_plan"].stage == "planning"
