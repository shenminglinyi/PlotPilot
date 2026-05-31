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
from application.world.services.bible_service import BibleService
from application.world.services.worldbuilding_service import WorldbuildingService
from application.world.worldbuilding_schema import build_fields_desc_for_prompt
from infrastructure.ai.prompt_keys import (
    BIBLE_CHARACTERS,
    BIBLE_LOCATIONS,
    BIBLE_WORLDBUILDING,
)
from infrastructure.ai.prompt_registry import get_prompt_registry

BIBLE_SETUP_WORLD_NODE = BIBLE_WORLDBUILDING
BIBLE_SETUP_CHARACTERS_NODE = BIBLE_CHARACTERS
BIBLE_SETUP_LOCATIONS_NODE = BIBLE_LOCATIONS
_BINDING_SET_BY_NODE = {
    BIBLE_SETUP_WORLD_NODE: f"{BIBLE_SETUP_WORLD_NODE}:input:v1",
    BIBLE_SETUP_CHARACTERS_NODE: f"{BIBLE_SETUP_CHARACTERS_NODE}:input:v1",
    BIBLE_SETUP_LOCATIONS_NODE: f"{BIBLE_SETUP_LOCATIONS_NODE}:input:v1",
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
        [
            VariableBinding(alias="premise", required=True),
            VariableBinding(alias="target_chapters", required=True, default="100"),
            VariableBinding(alias="fields_desc", required=True),
            VariableBinding(alias="existing_settings", required=False, default=""),
        ],
    )
    repo.set_bindings(
        _BINDING_SET_BY_NODE[BIBLE_SETUP_CHARACTERS_NODE],
        BIBLE_SETUP_CHARACTERS_NODE,
        [
            VariableBinding(alias="worldbuilding", required=True),
            VariableBinding(alias="style_guide", required=False, default=""),
            VariableBinding(alias="existing_characters", required=False, default=""),
            VariableBinding(alias="surname_seed", required=False, default=""),
        ],
    )
    repo.set_bindings(
        _BINDING_SET_BY_NODE[BIBLE_SETUP_LOCATIONS_NODE],
        BIBLE_SETUP_LOCATIONS_NODE,
        [
            VariableBinding(alias="worldbuilding", required=True),
            VariableBinding(alias="existing_locations", required=False, default=""),
            VariableBinding(alias="character_context", required=False, default=""),
        ],
    )
    return VariableResolver(repo)


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
        )


def build_bible_setup_variables(
    *,
    stage: str,
    novel: Any,
    bible_service: BibleService,
    worldbuilding_service: WorldbuildingService | None,
) -> Mapping[str, Any]:
    premise = (getattr(novel, "premise", "") or getattr(novel, "title", "") or "").strip()
    target_chapters = str(int(getattr(novel, "target_chapters", 100) or 100))
    if stage == "worldbuilding":
        return {
            "premise": premise,
            "target_chapters": target_chapters,
            "fields_desc": build_fields_desc_for_prompt(),
            "existing_settings": "",
        }

    bible = bible_service.get_bible_by_novel(getattr(novel, "id", ""))
    wb = worldbuilding_service.get_worldbuilding(getattr(novel, "id", "")) if worldbuilding_service else None
    from application.world.services.narrative_contract_loader import load_merged_worldbuilding_slices
    from application.world.services.narrative_contract_text import format_worldbuilding_slices_for_prompt
    from application.world.services.character_naming import build_character_surname_seed

    slices = load_merged_worldbuilding_slices(bible=bible, worldbuilding=wb)
    worldbuilding = format_worldbuilding_slices_for_prompt(slices)
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

    if stage == "characters":
        seed = build_character_surname_seed(
            8,
            rng_seed=f"{premise}|{target_chapters}|{worldbuilding}",
        )
        return {
            "worldbuilding": worldbuilding,
            "style_guide": style_guide,
            "existing_characters": existing_characters,
            "surname_seed": seed.to_prompt_block(),
        }
    if stage == "locations":
        return {
            "worldbuilding": worldbuilding,
            "existing_locations": existing_locations,
            "character_context": character_context,
        }
    raise ValueError(f"unsupported bible setup stage: {stage}")
