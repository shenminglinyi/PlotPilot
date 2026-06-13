from pathlib import Path

from application.ai_invocation.variable_hub import VariableWrite
from application.ai_invocation.prompt_assembler import CPMSPromptAssembler
from application.world.services.bible_setup_invocation import (
    BIBLE_SETUP_CHARACTERS_NODE,
    BIBLE_SETUP_LOCATIONS_NODE,
    BIBLE_SETUP_WORLD_NODE,
    bible_setup_characters_spec,
    bible_setup_input_bindings,
    bible_setup_locations_spec,
    bible_setup_world_spec,
    build_bible_setup_variable_resolver,
    build_bible_setup_variables,
)
from application.world.services.bible_setup_output_bindings import bible_setup_output_bindings


_BIBLE_LOCATIONS_PACKAGE_DIR = (
    Path(__file__).resolve().parents[4]
    / "infrastructure"
    / "ai"
    / "prompt_packages"
    / "nodes"
    / "bible-locations"
)


def test_bible_setup_variables_no_longer_builds_runtime_prompt_context():
    assert build_bible_setup_variables(
        stage="worldbuilding",
        novel=None,
        bible_service=None,
        worldbuilding_service=None,
    ) == {}


def test_bible_setup_worldbuilding_inputs_use_variable_center_keys():
    bindings = {binding.alias: binding for binding in bible_setup_input_bindings(BIBLE_SETUP_WORLD_NODE)}

    assert bindings["novel.premise"].variable_key == "novel.premise"
    assert bindings["novel.title"].variable_key == "novel.title"
    assert "fields_desc" not in bindings
    assert "genre_opening_profile" not in bindings
    assert "worldbuilding_full" not in bindings


def test_bible_setup_character_inputs_keep_existing_characters_optional():
    bindings = {binding.alias: binding for binding in bible_setup_input_bindings(BIBLE_SETUP_CHARACTERS_NODE)}

    assert bindings["characters.list"].variable_key == "characters.list"
    assert bindings["characters.list"].required is False
    assert bindings["characters.list"].default == []
    assert bindings["worldbuilding.content"].required is True
    assert bindings["worldbuilding.style"].required is True


def test_bible_setup_location_inputs_do_not_include_existing_locations():
    bindings = {binding.alias: binding for binding in bible_setup_input_bindings(BIBLE_SETUP_LOCATIONS_NODE)}

    assert "locations.list" not in bindings
    assert "characters.protagonist" not in bindings
    assert bindings["characters.list"].required is True


def test_bible_setup_output_bindings_use_novel_scope_and_domain_stages():
    world_bindings = {binding.variable_key: binding for binding in bible_setup_output_bindings(BIBLE_SETUP_WORLD_NODE)}
    character_bindings = {binding.variable_key: binding for binding in bible_setup_output_bindings(BIBLE_SETUP_CHARACTERS_NODE)}
    location_bindings = {binding.variable_key: binding for binding in bible_setup_output_bindings(BIBLE_SETUP_LOCATIONS_NODE)}

    assert world_bindings["worldbuilding.style"].scope == "novel"
    assert world_bindings["worldbuilding.style"].stage == "setup"
    assert world_bindings["worldbuilding.content"].scope == "novel"
    assert world_bindings["worldbuilding.content"].stage == "worldbuilding"
    assert character_bindings["characters.list"].scope == "novel"
    assert character_bindings["characters.list"].stage == "characters"
    assert character_bindings["characters.protagonist"].scope == "novel"
    assert location_bindings["locations.list"].scope == "novel"
    assert location_bindings["locations.list"].stage == "locations"


def test_bible_setup_world_resolver_reads_from_variable_hub():
    resolver = build_bible_setup_variable_resolver()
    repo = resolver._repository
    repo.set_value(VariableWrite(key="novel.title", value="新书", context_key="novel_id:novel-1"))
    repo.set_value(VariableWrite(key="novel.premise", value="都市异能主角反击困境", context_key="novel_id:novel-1"))
    repo.set_value(VariableWrite(key="novel.target_chapters", value=100, context_key="novel_id:novel-1"))
    repo.set_value(VariableWrite(key="novel.target_words_per_chapter", value=2500, context_key="novel_id:novel-1"))

    plan = resolver.resolve(
        spec=bible_setup_world_spec(),
        explicit_variables={},
        context={"novel_id": "novel-1"},
    )

    assert plan.ok
    assert plan.aliases["novel.title"] == "新书"
    assert plan.aliases["novel.premise"] == "都市异能主角反击困境"
    assert plan.aliases["novel.target_chapters"] == 100
    assert plan.aliases["novel.target_words_per_chapter"] == 2500


def test_bible_setup_character_resolver_allows_missing_optional_existing_characters():
    resolver = build_bible_setup_variable_resolver()
    repo = resolver._repository
    context_key = "novel_id:novel-1"
    repo.set_value(VariableWrite(key="novel.title", value="新书", context_key=context_key))
    repo.set_value(VariableWrite(key="novel.premise", value="现代都市异常能力", context_key=context_key))
    repo.set_value(VariableWrite(key="novel.target_chapters", value=100, context_key=context_key))
    repo.set_value(VariableWrite(key="novel.target_words_per_chapter", value=2500, context_key=context_key))
    repo.set_value(VariableWrite(key="worldbuilding.style", value="冷峻克制", context_key=context_key))
    repo.set_value(
        VariableWrite(
            key="worldbuilding.content",
            value={"core_rules": {"power_system": "债务异能体系"}},
            context_key=context_key,
        )
    )

    plan = resolver.resolve(
        spec=bible_setup_characters_spec(),
        explicit_variables={},
        context={"novel_id": "novel-1"},
    )

    assert plan.ok
    assert plan.aliases["characters.list"] == []
    assert "characters.list" not in plan.required_missing


def test_bible_setup_character_prompt_renders_author_premise():
    resolver = build_bible_setup_variable_resolver()
    repo = resolver._repository
    context_key = "novel_id:novel-1"
    premise = "大三那年的春天，苏念唯一的亲人奶奶走了。沈屿在春末最后一场雨之前出现。"
    repo.set_value(VariableWrite(key="novel.title", value="新书", context_key=context_key))
    repo.set_value(VariableWrite(key="novel.premise", value=premise, context_key=context_key))
    repo.set_value(VariableWrite(key="novel.target_chapters", value=100, context_key=context_key))
    repo.set_value(VariableWrite(key="novel.target_words_per_chapter", value=2500, context_key=context_key))
    repo.set_value(VariableWrite(key="worldbuilding.style", value="细腻写实", context_key=context_key))
    repo.set_value(
        VariableWrite(
            key="worldbuilding.content",
            value={"society": {"class_system": "校园和都市职场并行"}},
            context_key=context_key,
        )
    )

    spec = bible_setup_characters_spec()
    plan = resolver.resolve(
        spec=spec,
        explicit_variables={},
        context={"novel_id": "novel-1"},
    )

    prompt = CPMSPromptAssembler().compile(spec=spec, variable_plan=plan).prompt

    assert plan.ok
    assert "故事创意/原始设定" in prompt.user
    assert "苏念唯一的亲人奶奶走了" in prompt.user
    assert "沈屿在春末最后一场雨之前出现" in prompt.user


def test_bible_setup_location_resolver_reads_character_list_from_variable_hub():
    resolver = build_bible_setup_variable_resolver()
    repo = resolver._repository
    context_key = "novel_id:novel-1"
    repo.set_value(VariableWrite(key="novel.title", value="新书", context_key=context_key))
    repo.set_value(VariableWrite(key="novel.premise", value="现代都市异常能力", context_key=context_key))
    repo.set_value(VariableWrite(key="novel.target_chapters", value=100, context_key=context_key))
    repo.set_value(VariableWrite(key="novel.target_words_per_chapter", value=2500, context_key=context_key))
    repo.set_value(VariableWrite(key="worldbuilding.content", value={"core_rules": {"law": "债务法则"}}, context_key=context_key))
    repo.set_value(VariableWrite(key="characters.list", value=[{"name": "变量角色"}], context_key=context_key))

    plan = resolver.resolve(
        spec=bible_setup_locations_spec(),
        explicit_variables={},
        context={"novel_id": "novel-1"},
    )

    assert plan.ok
    assert plan.aliases["characters.list"][0]["name"] == "变量角色"
    assert "characters.protagonist" not in plan.aliases


def test_bible_setup_location_prompt_keeps_author_premise_as_hard_constraint():
    resolver = build_bible_setup_variable_resolver()
    repo = resolver._repository
    context_key = "novel_id:novel-1"
    premise = "大三那年的春天，苏念唯一的亲人奶奶走了。沈屿在图书馆门口递来一杯热可可。"
    repo.set_value(VariableWrite(key="novel.title", value="新书", context_key=context_key))
    repo.set_value(VariableWrite(key="novel.premise", value=premise, context_key=context_key))
    repo.set_value(VariableWrite(key="novel.genre_major", value="玄幻", context_key=context_key))
    repo.set_value(VariableWrite(key="novel.genre_theme", value="东方玄幻", context_key=context_key))
    repo.set_value(VariableWrite(key="novel.genre_label", value="玄幻 / 东方玄幻", context_key=context_key))
    repo.set_value(VariableWrite(key="novel.target_chapters", value=100, context_key=context_key))
    repo.set_value(VariableWrite(key="novel.target_words_per_chapter", value=2500, context_key=context_key))
    repo.set_value(
        VariableWrite(
            key="worldbuilding.content",
            value={"core_rules": {"power_system": "灵根修炼"}},
            context_key=context_key,
        )
    )
    repo.set_value(
        VariableWrite(
            key="characters.list",
            value=[{"name": "苏念", "description": "大三学生"}, {"name": "沈屿", "description": "本校研究生"}],
            context_key=context_key,
        )
    )

    spec = bible_setup_locations_spec()
    plan = resolver.resolve(
        spec=spec,
        explicit_variables={},
        context={"novel_id": "novel-1"},
    )
    class _PackageLocationsNode:
        active_version_id = spec.prompt_node_version_id

        def get_active_system(self):
            return (_BIBLE_LOCATIONS_PACKAGE_DIR / "system.md").read_text(encoding="utf-8")

        def get_active_user_template(self):
            return (_BIBLE_LOCATIONS_PACKAGE_DIR / "user.md").read_text(encoding="utf-8")

    class _PackageRegistry:
        def get_node(self, _node_key, use_cache=True):
            return _PackageLocationsNode()

    prompt = CPMSPromptAssembler(registry=_PackageRegistry()).compile(
        spec=spec,
        variable_plan=plan,
    ).prompt

    assert plan.ok
    assert "故事创意/原始设定" in prompt.user
    assert "苏念唯一的亲人奶奶走了" in prompt.user
    assert "沈屿在图书馆门口递来一杯热可可" in prompt.user
    assert "【人物设定（首位为主角）】" in prompt.user
    assert "【主角】" not in prompt.user
    assert "现实校园、都市、职场等原始场域不得被改写为宗门、秘境" in prompt.user
    assert "苏念" in prompt.user
    assert "沈屿" in prompt.user
