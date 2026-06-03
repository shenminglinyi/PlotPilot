from types import SimpleNamespace

from application.world.services.bible_setup_invocation import (
    BIBLE_SETUP_CHARACTERS_NODE,
    BIBLE_SETUP_LOCATIONS_NODE,
    BIBLE_SETUP_WORLD_NODE,
    BibleSetupPromptAssembler,
    bible_setup_input_bindings,
    build_bible_setup_variable_resolver,
    build_bible_setup_variables,
    bible_setup_world_spec,
)
from application.world.services import bible_setup_invocation as setup_invocation


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


def test_bible_setup_variable_resolver_treats_genre_profile_blocks_as_optional_derived_context():
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

    assert plan.ok
    assert "genre_opening_profile" not in plan.required_missing
    assert "genre_reader_contract" not in plan.required_missing
    assert "genre_rhythm_constraints" not in plan.required_missing
    assert plan.aliases["genre_opening_profile"] == {}
    assert plan.aliases["genre_reader_contract"] == {}
    assert plan.aliases["genre_rhythm_constraints"] == {}


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


def test_bible_setup_character_prompt_inputs_are_not_variable_hub_facts():
    bindings = {binding.alias: binding for binding in bible_setup_input_bindings(BIBLE_SETUP_CHARACTERS_NODE)}

    for alias in (
        "premise",
        "novel_title",
        "genre_label",
        "world_preset",
        "target_chapters",
        "core_rules",
        "geography",
        "society",
        "culture",
        "daily_life",
        "style_guide",
        "existing_characters",
    ):
        assert bindings[alias].source == "prompt_input"


def test_bible_setup_character_variables_include_setup_context_without_variable_hub():
    novel = SimpleNamespace(
        id="novel-1",
        title="新书",
        premise="主角在现代城市获得异常能力后反击现实困境",
        target_chapters=100,
        target_words_per_chapter=2500,
        locked_genre="都市 / 都市异能",
        locked_world_preset="现代都市异能",
    )
    bible_service = SimpleNamespace(get_bible_by_novel=lambda _novel_id: None)
    worldbuilding_service = SimpleNamespace(
        get_worldbuilding=lambda _novel_id: {
            "core_rules": {"power_system": "异常能力受城市债务系统约束"},
            "geography": {"terrain": "现代都市"},
        }
    )

    variables = build_bible_setup_variables(
        stage="characters",
        novel=novel,
        bible_service=bible_service,
        worldbuilding_service=worldbuilding_service,
    )

    assert variables["premise"] == "主角在现代城市获得异常能力后反击现实困境"
    assert variables["novel_title"] == "新书"
    assert variables["genre_label"] == "都市 / 都市异能"
    assert variables["world_preset"] == "现代都市异能"
    assert variables["genre_reader_contract"]["reader_promise"]
    assert "异常能力" in variables["core_rules"]


def test_bible_setup_location_prompt_inputs_include_setup_context():
    bindings = {binding.alias: binding for binding in bible_setup_input_bindings(BIBLE_SETUP_LOCATIONS_NODE)}

    for alias in (
        "premise",
        "novel_title",
        "genre_label",
        "world_preset",
        "target_chapters",
        "core_rules",
        "characters",
        "protagonist",
        "character_context",
    ):
        assert bindings[alias].source == "prompt_input"


def test_bible_setup_location_variables_include_character_outputs_from_variable_hub(monkeypatch):
    novel = SimpleNamespace(
        id="novel-1",
        title="新书",
        premise="主角在现代城市获得异常能力后反击现实困境",
        target_chapters=100,
        target_words_per_chapter=2500,
        locked_genre="都市 / 都市异能",
        locked_world_preset="现代都市异能",
    )
    bible = SimpleNamespace(
        characters=[
            SimpleNamespace(name="旧角色", role="盟友", description="业务表角色", relationships=[]),
        ],
        locations=[],
        style_notes=[],
    )
    bible_service = SimpleNamespace(get_bible_by_novel=lambda _novel_id: bible)
    worldbuilding_service = SimpleNamespace(get_worldbuilding=lambda _novel_id: {})

    def fake_variable_hub_value(_novel_id, variable_key):
        if variable_key == "novel.characters.list":
            return [{"name": "变量角色", "role": "主角", "description": "上一阶段采纳角色"}]
        if variable_key == "novel.characters.protagonist":
            return {"name": "变量角色", "role": "主角"}
        return None

    monkeypatch.setattr(setup_invocation, "_variable_hub_value", fake_variable_hub_value)

    variables = build_bible_setup_variables(
        stage="locations",
        novel=novel,
        bible_service=bible_service,
        worldbuilding_service=worldbuilding_service,
    )

    assert variables["characters"][0]["name"] == "变量角色"
    assert variables["protagonist"]["name"] == "变量角色"
    assert "变量角色" in variables["character_context"]
    assert "上一阶段采纳角色" in variables["character_context"]


def test_bible_setup_prompt_assembler_prepends_setup_context_for_old_seeded_prompts():
    user = BibleSetupPromptAssembler._ensure_setup_context_block(
        "【核心法则】\n法则正文",
        {
            "premise": "主角在现代城市获得异常能力后反击现实困境",
            "novel_title": "新书",
            "genre_label": "都市 / 都市异能",
            "world_preset": "现代都市异能",
            "target_chapters": 100,
            "genre_reader_contract": {"reader_promise": "升级破局"},
        },
    )

    assert user.startswith("【故事创意】")
    assert "主角在现代城市获得异常能力" in user
    assert "都市 / 都市异能" in user
    assert "升级破局" in user
