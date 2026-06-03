from types import SimpleNamespace

from application.world.services.bible_setup_invocation import (
    BIBLE_SETUP_WORLD_NODE,
    bible_setup_input_bindings,
    build_bible_setup_variable_resolver,
    build_bible_setup_variables,
    bible_setup_world_spec,
)


def test_bible_setup_variables_include_configured_genre_profile():
    novel = SimpleNamespace(
        id="novel-1",
        title="新书",
        premise="主角在现代城市获得异常能力后反击现实困境",
        target_chapters=100,
        target_words_per_chapter=2500,
        locked_genre="都市 / 都市异能",
        locked_world_preset="现代都市异能",
    )

    variables = build_bible_setup_variables(
        stage="worldbuilding",
        novel=novel,
        bible_service=None,
        worldbuilding_service=None,
    )

    assert variables["genre_major"] == "都市"
    assert variables["genre_theme"] == "都市异能"
    assert variables["genre_opening_profile"]["genre_major"] == "都市"
    assert variables["genre_reader_contract"]["reader_promise"]
    assert variables["genre_rhythm_constraints"]["payoff_interval"]


def test_bible_setup_variable_resolver_requires_genre_profile_blocks():
    resolver = build_bible_setup_variable_resolver()
    plan = resolver.resolve(
        spec=bible_setup_world_spec(),
        explicit_variables={
            "premise": "只有设定，没有类型画像",
            "target_chapters": 100,
            "fields_desc": "字段说明",
        },
        context={"novel_id": "novel-1"},
    )

    assert not plan.ok
    assert "genre_opening_profile" in plan.required_missing
    assert "genre_reader_contract" in plan.required_missing
    assert "genre_rhythm_constraints" in plan.required_missing
    assert any("必填变量缺失" in item for item in plan.diagnostics)


def test_bible_setup_variable_resolver_accepts_profile_variables():
    novel = SimpleNamespace(
        id="novel-1",
        title="新书",
        premise="主角在现代城市获得异常能力后反击现实困境",
        target_chapters=100,
        target_words_per_chapter=2500,
        locked_genre="都市 / 都市异能",
        locked_world_preset="现代都市异能",
    )
    variables = build_bible_setup_variables(
        stage="worldbuilding",
        novel=novel,
        bible_service=None,
        worldbuilding_service=None,
    )

    plan = build_bible_setup_variable_resolver().resolve(
        spec=bible_setup_world_spec(),
        explicit_variables=variables,
        context={"novel_id": "novel-1"},
    )

    assert plan.ok
    assert plan.aliases["genre_opening_profile"]["source_level"] == "secondary"
    assert BIBLE_SETUP_WORLD_NODE in bible_setup_world_spec().input_binding_set_id


def test_bible_setup_worldbuilding_inputs_are_bound_to_variable_hub_keys():
    bindings = {binding.alias: binding for binding in bible_setup_input_bindings(BIBLE_SETUP_WORLD_NODE)}

    assert bindings["premise"].variable_key == "novel.setup.premise"
    assert "novel_setup" not in bindings
    assert "worldbuilding_full" not in bindings
    assert "core_rules" not in bindings
    assert bindings["fields_desc"].variable_key == ""
    assert bindings["fields_desc"].source == "runtime_only"
    assert bindings["genre_opening_profile"].variable_key == ""
    assert bindings["genre_opening_profile"].source == "derived_config"
