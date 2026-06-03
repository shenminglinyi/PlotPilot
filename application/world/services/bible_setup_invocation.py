"""Bible onboarding AI Invocation contracts.

This module is the setup guide's bridge into AI Invocation. It owns the
operation/node contract and derived variables, while the gateway still owns the
common invocation state machine.
"""
from __future__ import annotations

from typing import Any, Mapping

from domain.ai.value_objects.prompt import Prompt

from application.ai_invocation.dtos import (
    InvocationPolicy,
    InvocationSpec,
    PromptSnapshot,
    VariableBinding,
    prompt_hash,
    stable_hash,
)
from application.ai_invocation.prompt_assembler import CPMSPromptAssembler
from application.ai_invocation.spec_service import InMemoryInvocationSpecRepository, InvocationSpecService
from application.ai_invocation.variable_hub import InMemoryVariableHubRepository, VariableResolver
from application.core.v1_length_tiers import strip_generated_premise_prefixes
from application.core.taxonomy.opening_profiles import resolve_opening_profile
from application.world.services.bible_service import BibleService
from application.world.services.worldbuilding_service import WorldbuildingService
from application.world.services.narrative_contract_loader import load_merged_worldbuilding_slices
from application.world.services.narrative_contract_text import format_worldbuilding_slices_for_prompt
from application.world.worldbuilding_schema import build_fields_desc_for_prompt
from application.world.worldbuilding_merge import WORLD_BUILDING_DIMENSION_KEYS
from infrastructure.ai.prompt_keys import (
    BIBLE_CHARACTERS,
    BIBLE_LOCATIONS,
    BIBLE_WORLDBUILDING,
)
from infrastructure.ai.prompt_registry import get_prompt_registry
from application.world.services.bible_setup_output_bindings import ensure_bible_setup_output_bindings

BIBLE_SETUP_WORLD_NODE = BIBLE_WORLDBUILDING
BIBLE_SETUP_CHARACTERS_NODE = BIBLE_CHARACTERS
BIBLE_SETUP_LOCATIONS_NODE = BIBLE_LOCATIONS
NOVEL_SETUP_VARIABLE_BINDINGS = (
    VariableBinding(
        alias="novel_title",
        variable_key="novel.setup.title",
        required=False,
        default="",
        display_name="名称",
        value_type="string",
        scope="global",
        stage="setup",
    ),
    VariableBinding(
        alias="premise",
        variable_key="novel.setup.premise",
        required=True,
        display_name="设定",
        value_type="string",
        scope="global",
        stage="setup",
    ),
    VariableBinding(
        alias="genre_major",
        variable_key="novel.setup.genre_major",
        required=False,
        default="",
        display_name="大类",
        value_type="string",
        scope="global",
        stage="setup",
    ),
    VariableBinding(
        alias="genre_theme",
        variable_key="novel.setup.genre_theme",
        required=False,
        default="",
        display_name="主题",
        value_type="string",
        scope="global",
        stage="setup",
    ),
    VariableBinding(
        alias="genre_label",
        variable_key="novel.setup.genre_label",
        required=False,
        default="",
        display_name="类型",
        value_type="string",
        scope="global",
        stage="setup",
    ),
    VariableBinding(
        alias="world_preset",
        variable_key="novel.setup.world_preset",
        required=False,
        default="",
        display_name="基调",
        value_type="string",
        scope="global",
        stage="setup",
    ),
    VariableBinding(
        alias="target_chapters",
        variable_key="novel.setup.target_chapters",
        required=True,
        default="100",
        display_name="章节数量",
        value_type="integer",
        scope="global",
        stage="setup",
    ),
    VariableBinding(
        alias="target_words_per_chapter",
        variable_key="novel.setup.target_words_per_chapter",
        required=False,
        default="",
        display_name="每章字数",
        value_type="integer",
        scope="global",
        stage="setup",
    ),
    VariableBinding(
        alias="genre_opening_profile",
        required=True,
        source="derived_config",
        display_name="类型开篇画像",
        value_type="object",
        scope="global",
        stage="planning",
    ),
    VariableBinding(
        alias="genre_reader_contract",
        required=True,
        source="derived_config",
        display_name="读者留存契约",
        value_type="object",
        scope="global",
        stage="planning",
    ),
    VariableBinding(
        alias="genre_rhythm_constraints",
        required=True,
        source="derived_config",
        display_name="类型节奏约束",
        value_type="object",
        scope="global",
        stage="planning",
    ),
)
_BINDING_SET_BY_NODE = {
    BIBLE_SETUP_WORLD_NODE: f"{BIBLE_SETUP_WORLD_NODE}:input:v1",
    BIBLE_SETUP_CHARACTERS_NODE: f"{BIBLE_SETUP_CHARACTERS_NODE}:input:v1",
    BIBLE_SETUP_LOCATIONS_NODE: f"{BIBLE_SETUP_LOCATIONS_NODE}:input:v1",
}


def _bible_setup_base_input_bindings() -> list[VariableBinding]:
    runtime_derived_aliases = {
        "genre_opening_profile",
        "genre_reader_contract",
        "genre_rhythm_constraints",
    }
    bindings: list[VariableBinding] = []
    for binding in NOVEL_SETUP_VARIABLE_BINDINGS:
        if binding.alias in runtime_derived_aliases:
            bindings.append(
                VariableBinding(
                    alias=binding.alias,
                    variable_key="",
                    required=binding.required,
                    default=binding.default,
                    source="derived_config",
                    enabled=binding.enabled,
                    value_type=binding.value_type,
                    scope=binding.scope,
                    stage=binding.stage,
                    display_name=binding.display_name,
                )
            )
        else:
            bindings.append(binding)
    return bindings


def _worldbuilding_input_bindings() -> list[VariableBinding]:
    return [
        VariableBinding(
            alias="core_rules",
            variable_key="novel.worldbuilding.core_rules.text",
            required=False,
            default="",
            display_name="核心法则",
            value_type="string",
            scope="global",
            stage="worldbuilding",
        ),
        VariableBinding(
            alias="geography",
            variable_key="novel.worldbuilding.geography.text",
            required=False,
            default="",
            display_name="地理生态",
            value_type="string",
            scope="global",
            stage="worldbuilding",
        ),
        VariableBinding(
            alias="society",
            variable_key="novel.worldbuilding.society.text",
            required=False,
            default="",
            display_name="社会结构",
            value_type="string",
            scope="global",
            stage="worldbuilding",
        ),
        VariableBinding(
            alias="culture",
            variable_key="novel.worldbuilding.culture.text",
            required=False,
            default="",
            display_name="历史文化",
            value_type="string",
            scope="global",
            stage="worldbuilding",
        ),
        VariableBinding(
            alias="daily_life",
            variable_key="novel.worldbuilding.daily_life.text",
            required=False,
            default="",
            display_name="沉浸感细节",
            value_type="string",
            scope="global",
            stage="worldbuilding",
        ),
    ]


def bible_setup_input_bindings(node_key: str) -> list[VariableBinding]:
    if node_key == BIBLE_SETUP_WORLD_NODE:
        return [
            *_bible_setup_base_input_bindings(),
            VariableBinding(
                alias="fields_desc",
                variable_key="",
                required=True,
                default=build_fields_desc_for_prompt(),
                source="runtime_only",
                display_name="世界观字段模板",
                value_type="string",
                scope="global",
                stage="worldbuilding",
            ),
        ]
    if node_key == BIBLE_SETUP_CHARACTERS_NODE:
        return [
            *_worldbuilding_input_bindings(),
            VariableBinding(
                alias="style_guide",
                variable_key="novel.style.guide",
                required=False,
                default="",
                display_name="文风公约",
                value_type="string",
                scope="global",
                stage="setup",
            ),
            VariableBinding(
                alias="existing_characters",
                variable_key="novel.characters.list.text",
                required=False,
                default="",
                display_name="已有角色",
                value_type="string",
                scope="global",
                stage="characters",
            ),
            VariableBinding(
                alias="surname_seed",
                variable_key="novel.characters.surname_seed",
                required=False,
                default="",
                display_name="姓氏种子",
                value_type="string",
                scope="global",
                stage="characters",
            ),
        ]
    if node_key == BIBLE_SETUP_LOCATIONS_NODE:
        return [
            *_worldbuilding_input_bindings(),
            VariableBinding(
                alias="existing_locations",
                variable_key="novel.locations.list.text",
                required=False,
                default="",
                display_name="已有地点",
                value_type="string",
                scope="global",
                stage="locations",
            ),
            VariableBinding(
                alias="character_context",
                variable_key="novel.characters.context.text",
                required=False,
                default="",
                display_name="角色上下文",
                value_type="string",
                scope="global",
                stage="characters",
            ),
        ]
    return []


def _split_genre_label(genre_label: str) -> tuple[str, str]:
    parts = [part.strip() for part in str(genre_label or "").split("/") if part.strip()]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " / ".join(parts[1:])


def _build_worldbuilding_prompt_fields(
    *,
    bible: Any = None,
    worldbuilding: Any = None,
) -> dict[str, str]:
    """统一生成 5 维世界观字段，避免再派生 worldbuilding_full。"""
    if isinstance(worldbuilding, Mapping):
        slices = {dim: dict((worldbuilding or {}).get(dim) or {}) for dim in WORLD_BUILDING_DIMENSION_KEYS}
    else:
        slices = load_merged_worldbuilding_slices(bible=bible, worldbuilding=worldbuilding)
    fields: dict[str, str] = {}
    for dim_key in WORLD_BUILDING_DIMENSION_KEYS:
        fields[dim_key] = format_worldbuilding_slices_for_prompt(
            {dim_key: slices.get(dim_key) or {}}
        )
    return fields


def _worldbuilding_dimension_prompt_fields(fields: Mapping[str, str]) -> dict[str, str]:
    return {
        key: str(fields.get(key) or "")
        for key in WORLD_BUILDING_DIMENSION_KEYS
    }


def _active_version_id(node_key: str) -> str:
    node = get_prompt_registry().get_node(node_key)
    return str(getattr(node, "active_version_id", None) or "")


def bible_setup_world_spec() -> InvocationSpec:
    return InvocationSpec(
        operation="bible.setup.worldbuilding",
        node_key=BIBLE_SETUP_WORLD_NODE,
        prompt_node_version_id=_active_version_id(BIBLE_WORLDBUILDING),
        asset_link_set_id="",
        input_binding_set_id=f"{BIBLE_SETUP_WORLD_NODE}:input:v1",
        output_binding_set_id=f"{BIBLE_SETUP_WORLD_NODE}:output:v1",
        default_policy=InvocationPolicy.FULL_INTERACTIVE,
        risk_level="low",
        supports_stream=True,
        continuation_handler_key="bible_worldbuilding",
        metadata={
            "source": "novel_setup_guide",
            "bible_prompt_key": BIBLE_WORLDBUILDING,
            "required_outputs": ["style", "worldbuilding"],
            "output_contract_notes": [
                "输出必须是 JSON 对象，字段名和契约路径完全一致",
                "style 必须是顶层字段；不要写进 worldbuilding 内部",
                "新增字段需要先扩展输出契约，不能只在提示词里口头约定",
            ],
        },
    )


def bible_setup_characters_spec() -> InvocationSpec:
    return InvocationSpec(
        operation="bible.setup.characters",
        node_key=BIBLE_SETUP_CHARACTERS_NODE,
        prompt_node_version_id=_active_version_id(BIBLE_CHARACTERS),
        asset_link_set_id="",
        input_binding_set_id=f"{BIBLE_SETUP_CHARACTERS_NODE}:input:v1",
        output_binding_set_id=f"{BIBLE_SETUP_CHARACTERS_NODE}:output:v1",
        default_policy=InvocationPolicy.FULL_INTERACTIVE,
        risk_level="low",
        supports_stream=True,
        continuation_handler_key="bible_characters",
        metadata={
            "source": "novel_setup_guide",
            "bible_prompt_key": BIBLE_CHARACTERS,
            "required_outputs": ["characters"],
        },
    )


def bible_setup_locations_spec() -> InvocationSpec:
    return InvocationSpec(
        operation="bible.setup.locations",
        node_key=BIBLE_SETUP_LOCATIONS_NODE,
        prompt_node_version_id=_active_version_id(BIBLE_LOCATIONS),
        asset_link_set_id="",
        input_binding_set_id=f"{BIBLE_SETUP_LOCATIONS_NODE}:input:v1",
        output_binding_set_id=f"{BIBLE_SETUP_LOCATIONS_NODE}:output:v1",
        default_policy=InvocationPolicy.FULL_INTERACTIVE,
        risk_level="low",
        supports_stream=True,
        continuation_handler_key="bible_locations",
        metadata={
            "source": "novel_setup_guide",
            "bible_prompt_key": BIBLE_LOCATIONS,
            "required_outputs": ["locations"],
        },
    )


def ensure_bible_setup_specs(service: InvocationSpecService) -> None:
    repo = getattr(service, "_repository", None)
    if repo is None or not hasattr(repo, "add"):
        return
    for spec in (bible_setup_world_spec(), bible_setup_characters_spec(), bible_setup_locations_spec()):
        repo.add(spec)


def build_bible_setup_spec_service() -> InvocationSpecService:
    return InvocationSpecService(
        InMemoryInvocationSpecRepository(
            [bible_setup_world_spec(), bible_setup_characters_spec(), bible_setup_locations_spec()]
        )
    )


def build_bible_setup_variable_resolver() -> VariableResolver:
    repo = InMemoryVariableHubRepository()
    repo.set_bindings(
        _BINDING_SET_BY_NODE[BIBLE_SETUP_WORLD_NODE],
        BIBLE_SETUP_WORLD_NODE,
        bible_setup_input_bindings(BIBLE_SETUP_WORLD_NODE),
    )
    repo.set_bindings(
        _BINDING_SET_BY_NODE[BIBLE_SETUP_CHARACTERS_NODE],
        BIBLE_SETUP_CHARACTERS_NODE,
        bible_setup_input_bindings(BIBLE_SETUP_CHARACTERS_NODE),
    )
    repo.set_bindings(
        _BINDING_SET_BY_NODE[BIBLE_SETUP_LOCATIONS_NODE],
        BIBLE_SETUP_LOCATIONS_NODE,
        bible_setup_input_bindings(BIBLE_SETUP_LOCATIONS_NODE),
    )
    ensure_bible_setup_output_bindings(repo)
    return VariableResolver(repo)


def ensure_bible_setup_contract(db, *, operation: str, node_key: str) -> InvocationSpec:
    from infrastructure.ai.prompt_manager import get_prompt_manager
    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )
    from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue

    get_prompt_manager().ensure_seeded()
    spec_factory_by_operation = {
        "bible.setup.worldbuilding": bible_setup_world_spec,
        "bible.setup.characters": bible_setup_characters_spec,
        "bible.setup.locations": bible_setup_locations_spec,
    }
    factory = spec_factory_by_operation.get(operation)
    if factory is None:
        raise ValueError(f"unsupported bible setup operation: {operation}")
    spec = factory()
    if spec.node_key != node_key:
        raise ValueError(f"unsupported bible setup node: operation={operation}, node_key={node_key}")

    with sqlite_writes_bypass_queue():
        variable_repo = SqliteVariableHubRepository(db)
        variable_repo.set_bindings(spec.input_binding_set_id, spec.node_key, bible_setup_input_bindings(spec.node_key), direction="input")
        ensure_bible_setup_output_bindings(variable_repo, spec.node_key)
        SqliteInvocationSpecRepository(db).upsert(
            spec,
            spec_id=f"spec:{spec.node_key}:v1",
            spec_version=1,
            status="published",
        )
    return spec


class BibleSetupPromptAssembler(CPMSPromptAssembler):
    """Compile setup-guide virtual nodes from published Bible CPMS nodes."""

    def compile(self, *, spec: InvocationSpec, variable_plan):  # type: ignore[override]
        prompt_key = str(spec.metadata.get("bible_prompt_key") or spec.node_key)
        registry = get_prompt_registry()
        node = registry.get_node(prompt_key)
        if node is None:
            return super().compile(spec=spec, variable_plan=variable_plan)

        aliases = dict(variable_plan.aliases)
        rendered = registry.render(prompt_key, aliases)
        system = rendered.system if rendered else node.get_active_system()
        user = rendered.user if rendered else node.get_active_user_template()

        if spec.node_key == BIBLE_SETUP_WORLD_NODE:
            style_contract = (
                "同时生成文风公约，并把文风写入顶层字段 `style`。最终必须输出一个 JSON 对象，"
                "包含 `style` 和 `worldbuilding` 两个顶层字段。"
            )
            user = f"{user}\n\n{style_contract}\n\n输出格式：\n{{\n  \"style\": \"文风公约文本\",\n  \"worldbuilding\": {{ ... }}\n}}"
        prompt = Prompt(system=system or "", user=user or "")
        template_hash = stable_hash(
            {"system_template": node.get_active_system(), "user_template": node.get_active_user_template()}
        )
        node_version_id = str(getattr(node, "active_version_id", None) or prompt_key)
        composition_hash = stable_hash(
            {
                "node_key": spec.node_key,
                "node_version_id": node_version_id,
                "input_binding_set_id": spec.input_binding_set_id,
                "output_binding_set_id": spec.output_binding_set_id,
                "source_node_key": prompt_key,
            }
        )
        diagnostics = list(variable_plan.diagnostics)
        if rendered and getattr(rendered, "warnings", None):
            diagnostics.extend(str(item) for item in rendered.warnings)
        if variable_plan.required_missing:
            diagnostics.append("存在未解析的必填变量")
        return PromptSnapshot(
            prompt=prompt,
            node_key=spec.node_key,
            node_version_id=node_version_id,
            asset_link_set_id=spec.asset_link_set_id,
            input_binding_set_id=spec.input_binding_set_id,
            output_binding_set_id=spec.output_binding_set_id,
            variable_snapshot_hash=variable_plan.snapshot_hash,
            template_hash=template_hash,
            composition_hash=composition_hash,
            rendered_prompt_hash=prompt_hash(prompt),
            missing_variables=tuple(getattr(rendered, "missing_variables", []) or ()) if rendered else (),
            diagnostics=tuple(diagnostics),
            asset_version_ids=(node_version_id,),
            template_prompt=Prompt(
                system=node.get_active_system() or "",
                user=node.get_active_user_template() or "",
            ),
        )


def build_bible_setup_variables(
    *,
    stage: str,
    novel: Any,
    bible_service: BibleService,
    worldbuilding_service: WorldbuildingService | None,
) -> Mapping[str, Any]:
    novel_title = str(getattr(novel, "title", "") or "").strip()
    premise = strip_generated_premise_prefixes(
        getattr(novel, "premise", "") or getattr(novel, "title", "") or ""
    )
    target_chapters = int(getattr(novel, "target_chapters", 100) or 100)
    target_words_per_chapter = int(getattr(novel, "target_words_per_chapter", 0) or 0)
    genre_label = str(getattr(novel, "locked_genre", "") or "").strip()
    world_preset = str(getattr(novel, "locked_world_preset", "") or "").strip()
    if not genre_label or not world_preset:
        from application.core.premise_genre_world import parse_genre_world_from_premise

        parsed_genre, parsed_world = parse_genre_world_from_premise(premise)
        genre_label = genre_label or parsed_genre
        world_preset = world_preset or parsed_world
    genre_major, genre_theme = _split_genre_label(genre_label)
    genre_profile = resolve_opening_profile(genre_label, strict=True).as_variables()
    if stage == "worldbuilding":
        return {
            "premise": premise,
            "target_chapters": target_chapters,
            "target_words_per_chapter": target_words_per_chapter,
            "fields_desc": build_fields_desc_for_prompt(),
            "novel_title": novel_title,
            "genre_major": genre_major,
            "genre_theme": genre_theme,
            "genre_label": genre_label,
            "world_preset": world_preset,
            **genre_profile,
        }

    bible = bible_service.get_bible_by_novel(getattr(novel, "id", ""))
    wb = worldbuilding_service.get_worldbuilding(getattr(novel, "id", "")) if worldbuilding_service else None
    from application.world.services.narrative_contract_loader import load_merged_worldbuilding_slices
    from application.world.services.narrative_contract_text import format_worldbuilding_slices_for_prompt
    from application.world.services.character_naming import build_character_surname_seed

    style_guide = ""
    existing_characters = ""
    existing_locations = ""
    character_context = ""
    if bible:
        style_guide = "\n".join(
            str(note.content or "").strip()
            for note in bible.style_notes or []
            if str(note.content or "").strip()
        )
        existing_characters = "\n".join(
            f"- {c.name}: {c.description}"
            for c in bible.characters or []
        )
        existing_locations = "\n".join(
            f"- {loc.name}: {loc.description}"
            for loc in bible.locations or []
        )
        character_context = existing_characters
    worldbuilding_fields = _build_worldbuilding_prompt_fields(bible=bible, worldbuilding=wb)

    if stage == "characters":
        seed = build_character_surname_seed(
            8,
            rng_seed=f"{premise}|{target_chapters}|{worldbuilding_fields.get('core_rules', '')}",
        )
        return {
            **_worldbuilding_dimension_prompt_fields(worldbuilding_fields),
            **genre_profile,
            "style_guide": style_guide,
            "existing_characters": existing_characters,
            "surname_seed": seed.to_prompt_block(),
        }
    if stage == "locations":
        return {
            **_worldbuilding_dimension_prompt_fields(worldbuilding_fields),
            **genre_profile,
            "existing_locations": existing_locations,
            "character_context": character_context,
        }
    raise ValueError(f"unsupported bible setup stage: {stage}")
