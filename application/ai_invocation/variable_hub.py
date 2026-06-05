"""Variable Hub 最小解析底座。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from application.ai_invocation.dtos import InvocationSpec, VariableBinding, VariablePlan, stable_hash
from application.ai_invocation.variable_projection import render_variable_value
from application.core.v1_length_tiers import strip_v1_structure_black_box_hint

RUNTIME_ONLY_BINDING_SOURCES = frozenset(
    {"runtime_only", "derived_config", "system_template", "prompt_input"}
)
SNAPSHOT_EXCLUDED_BINDING_SOURCES = frozenset({"runtime_only", "derived_config", "system_template"})
WORLD_BUILDING_DIMENSION_KEYS = ("core_rules", "geography", "society", "culture", "daily_life")
VARIABLE_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "novel.title": ("novel.setup.title",),
    "novel.setup.title": ("novel.title",),
    "novel.premise": ("novel.setup.premise",),
    "novel.setup.premise": ("novel.premise",),
    "novel.target_chapters": ("novel.setup.target_chapters",),
    "novel.setup.target_chapters": ("novel.target_chapters",),
    "novel.target_words_per_chapter": ("novel.setup.target_words_per_chapter",),
    "novel.setup.target_words_per_chapter": ("novel.target_words_per_chapter",),
    "novel.genre_label": ("novel.setup.genre_label",),
    "novel.setup.genre_label": ("novel.genre_label",),
    "novel.genre_major": ("novel.setup.genre_major",),
    "novel.setup.genre_major": ("novel.genre_major",),
    "novel.genre_theme": ("novel.setup.genre_theme",),
    "novel.setup.genre_theme": ("novel.genre_theme",),
    "novel.world_preset": ("novel.setup.world_preset",),
    "novel.setup.world_preset": ("novel.world_preset",),
    "novel.story_structure": ("novel.setup.story_structure",),
    "novel.setup.story_structure": ("novel.story_structure",),
    "novel.pacing_control": ("novel.setup.pacing_control",),
    "novel.setup.pacing_control": ("novel.pacing_control",),
    "novel.writing_style": ("novel.setup.writing_style",),
    "novel.setup.writing_style": ("novel.writing_style",),
    "novel.special_requirements": ("novel.setup.special_requirements",),
    "novel.setup.special_requirements": ("novel.special_requirements",),
    "worldbuilding.style": ("novel.style.guide",),
    "novel.style.guide": ("worldbuilding.style",),
    "worldbuilding.content": ("novel.worldbuilding",),
    "novel.worldbuilding": ("worldbuilding.content",),
    "worldbuilding.core_rules": ("novel.worldbuilding.core_rules",),
    "novel.worldbuilding.core_rules": ("worldbuilding.core_rules",),
    "worldbuilding.geography": ("novel.worldbuilding.geography",),
    "novel.worldbuilding.geography": ("worldbuilding.geography",),
    "worldbuilding.society": ("novel.worldbuilding.society",),
    "novel.worldbuilding.society": ("worldbuilding.society",),
    "worldbuilding.culture": ("novel.worldbuilding.culture",),
    "novel.worldbuilding.culture": ("worldbuilding.culture",),
    "worldbuilding.daily_life": ("novel.worldbuilding.daily_life",),
    "novel.worldbuilding.daily_life": ("worldbuilding.daily_life",),
    "characters.list": ("novel.characters.list",),
    "novel.characters.list": ("characters.list",),
    "characters.protagonist": ("novel.characters.protagonist",),
    "novel.characters.protagonist": ("characters.protagonist",),
    "locations.list": ("novel.locations.list",),
    "novel.locations.list": ("locations.list",),
    "plot.fusion_contract": ("novel.plot.fusion_contract",),
    "novel.plot.fusion_contract": ("plot.fusion_contract",),
    "plot.main_options": ("novel.plot.main_options",),
    "novel.plot.main_options": ("plot.main_options",),
    "plot.main_options_json": ("novel.plot.main_options_json",),
    "novel.plot.main_options_json": ("plot.main_options_json",),
    "plot.outline": ("novel.plot.outline",),
    "novel.plot.outline": ("plot.outline",),
    "plot.main_story_overview": ("novel.plot.main_story_overview",),
    "novel.plot.main_story_overview": ("plot.main_story_overview",),
    "plot.stage_plan": ("novel.plot.stage_plan",),
    "novel.plot.stage_plan": ("plot.stage_plan",),
    "plot.expected_ending": ("novel.plot.expected_ending",),
    "novel.plot.expected_ending": ("plot.expected_ending",),
    "plot.core_conflict": ("novel.plot.core_conflict",),
    "novel.plot.core_conflict": ("plot.core_conflict",),
}


@dataclass(frozen=True)
class VariableDefinition:
    key: str
    display_name: str = ""
    value_type: str = "string"
    required: bool = False
    default: Any = None
    description: str = ""


@dataclass(frozen=True)
class VariableValue:
    key: str
    value: Any
    context_key: str = "global"
    source_ref: str = ""
    version_number: int = 1


@dataclass(frozen=True)
class VariableWrite:
    key: str
    value: Any
    context_key: str = "global"
    source_session_id: str = ""
    source_attempt_id: str = ""
    source_trace_id: str = ""
    source_node_key: str = ""
    source_commit_id: str = ""
    lineage: Mapping[str, Any] = field(default_factory=dict)
    value_type: str = "string"
    display_name: str = ""
    scope: str = "global"
    stage: str = "runtime"


def sanitize_variable_value(variable_key: str, value: Any) -> Any:
    """Remove server-generated internal text from user-facing Variable Hub values."""
    if variable_key in {"novel.setup.premise", "novel.premise"} and isinstance(value, str):
        return strip_v1_structure_black_box_hint(value)
    return value


def compose_worldbuilding_dimensions(source: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    composed: dict[str, Any] = {}
    for key in WORLD_BUILDING_DIMENSION_KEYS:
        value = source.get(key)
        if isinstance(value, Mapping):
            composed[key] = dict(value)
    return composed


def variable_key_candidates(variable_key: str) -> tuple[str, ...]:
    normalized = str(variable_key or "").strip()
    aliases = tuple(
        candidate
        for candidate in VARIABLE_KEY_ALIASES.get(normalized, ())
        if candidate and candidate != normalized
    )
    return (normalized, *aliases)


class VariableHubRepository(Protocol):
    def get_bindings(self, binding_set_id: str, node_key: str) -> list[VariableBinding]:
        """读取节点输入变量绑定。"""

    def get_output_bindings(self, binding_set_id: str, node_key: str) -> list[VariableBinding]:
        """读取节点输出变量绑定。"""

    def get_value(self, variable_key: str, context_key: str) -> VariableValue | None:
        """读取变量值。"""

    def get_definition(self, variable_key: str) -> VariableDefinition | None:
        """读取变量定义。"""

    def set_value(self, value: VariableValue | VariableWrite) -> VariableValue | None:
        """写入变量值。"""

    def list_current_values(self, context_key: str) -> list[Mapping[str, Any]]:
        """列出当前上下文可见的所有当前变量值。"""

    def set_bindings(
        self,
        binding_set_id: str,
        node_key: str,
        bindings: list[VariableBinding],
        *,
        direction: str = "input",
    ) -> None:
        """注册节点输入或输出变量绑定。"""


@dataclass
class InMemoryVariableHubRepository:
    """内存 Variable Hub 仓储。"""

    definitions: dict[str, VariableDefinition] = field(default_factory=dict)
    values: dict[tuple[str, str], VariableValue] = field(default_factory=dict)
    bindings: dict[tuple[str, str, str], list[VariableBinding]] = field(default_factory=dict)

    def add_definition(self, definition: VariableDefinition) -> None:
        self.definitions[definition.key] = definition

    def set_value(self, value: VariableValue) -> None:
        self.values[(value.key, value.context_key)] = value

    def write_value(self, write: VariableWrite) -> VariableValue:
        existing = self.values.get((write.key, write.context_key))
        version = (existing.version_number + 1) if existing else 1
        source_ref = write.source_session_id or write.source_trace_id or write.source_node_key
        clean_value = sanitize_variable_value(write.key, write.value)
        value = VariableValue(
            key=write.key,
            value=clean_value,
            context_key=write.context_key,
            source_ref=source_ref,
            version_number=version,
        )
        self.values[(value.key, value.context_key)] = value
        return value

    def set_bindings(
        self,
        binding_set_id: str,
        node_key: str,
        bindings: list[VariableBinding],
        *,
        direction: str = "input",
    ) -> None:
        self.bindings[(binding_set_id, node_key, direction)] = list(bindings)

    def get_bindings(self, binding_set_id: str, node_key: str) -> list[VariableBinding]:
        return list(self.bindings.get((binding_set_id, node_key, "input"), []))

    def get_output_bindings(self, binding_set_id: str, node_key: str) -> list[VariableBinding]:
        return list(self.bindings.get((binding_set_id, node_key, "output"), []))

    def get_value(self, variable_key: str, context_key: str) -> VariableValue | None:
        for scope_key in expand_context_keys(context_key):
            for candidate in variable_key_candidates(variable_key):
                value = self.values.get((candidate, scope_key))
                if value is not None:
                    clean_value = sanitize_variable_value(candidate, value.value)
                    if clean_value != value.value or value.key != variable_key:
                        return VariableValue(
                            key=variable_key,
                            value=clean_value,
                            context_key=value.context_key,
                            source_ref=value.source_ref,
                            version_number=value.version_number,
                        )
                    return value
            if variable_key in {"novel.worldbuilding", "worldbuilding.content"}:
                composed = {}
                version = 1
                for key in WORLD_BUILDING_DIMENSION_KEYS:
                    child = None
                    for candidate in variable_key_candidates(f"worldbuilding.{key}"):
                        child = self.values.get((candidate, scope_key))
                        if child is not None:
                            break
                    if child is None or not isinstance(child.value, Mapping):
                        continue
                    composed[key] = dict(child.value)
                    version = max(version, child.version_number)
                if composed:
                    return VariableValue(
                        key=variable_key,
                        value=composed,
                        context_key=scope_key,
                        source_ref="derived:worldbuilding_dimensions",
                        version_number=version,
                    )
        return None

    def get_definition(self, variable_key: str) -> VariableDefinition | None:
        return self.definitions.get(variable_key)

    def list_current_values(self, context_key: str) -> list[Mapping[str, Any]]:
        rows: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        for scope_key in expand_context_keys(context_key):
            for (key, value_scope), value in self.values.items():
                if value_scope != scope_key or key in seen:
                    continue
                seen.add(key)
                definition = self.definitions.get(key)
                clean_value = sanitize_variable_value(key, value.value)
                rows.append(
                    {
                        "variable_key": key,
                        "display_name": key,
                        "value": clean_value,
                        "value_type": definition.value_type if definition else self._infer_value_type(clean_value),
                        "scope": VariableResolver._infer_scope(key),
                        "stage": VariableResolver._infer_stage(key),
                        "source": "variable_hub",
                        "context_key": value.context_key,
                        "version_number": value.version_number,
                    }
                )
        return rows

    def set_value(self, value: VariableValue | VariableWrite) -> VariableValue | None:  # type: ignore[override]
        if isinstance(value, VariableWrite):
            return self.write_value(value)
        clean_value = sanitize_variable_value(value.key, value.value)
        if clean_value != value.value:
            value = VariableValue(
                key=value.key,
                value=clean_value,
                context_key=value.context_key,
                source_ref=value.source_ref,
                version_number=value.version_number,
            )
        self.values[(value.key, value.context_key)] = value
        return None

    @staticmethod
    def _infer_value_type(value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int) and not isinstance(value, bool):
            return "integer"
        if isinstance(value, float):
            return "float"
        if isinstance(value, list):
            return "list"
        if isinstance(value, dict):
            return "object"
        return "string"


def extract_path_value(source: Any, path: str) -> Any:
    """Extract a value from dict/list data using dotted paths and list indexes.

    Supported examples:
    - ``worldbuilding.core_rules``
    - ``characters[0].name``
    - ``characters[].name`` / ``characters.*.name``
    - ``[0].name``
    """
    normalized = str(path or "").strip()
    if not normalized:
        return source
    if normalized == "$":
        return source
    if normalized.startswith("$."):
        normalized = normalized[2:]
    elif normalized.startswith("$"):
        normalized = normalized[1:].lstrip(".")
    current = source
    for raw_segment in normalized.split("."):
        if current is None:
            return None
        current = _extract_path_segment(current, raw_segment)
    return current


def _extract_path_segment(current: Any, segment: str) -> Any:
    raw = str(segment or "").strip()
    if raw in {"", "$"}:
        return current
    if raw in {"[]", "[*]", "*"}:
        return current if isinstance(current, list) else None
    if isinstance(current, list):
        if raw.startswith("[") and raw.endswith("]"):
            return _extract_list_index(current, raw[1:-1])
        values = [_extract_path_segment(item, raw) for item in current]
        return [value for value in values if value is not None]

    key = raw
    selectors: list[str] = []
    bracket_index = raw.find("[")
    if bracket_index >= 0:
        key = raw[:bracket_index]
        rest = raw[bracket_index:]
        while rest.startswith("["):
            close = rest.find("]")
            if close < 0:
                return None
            selectors.append(rest[1:close])
            rest = rest[close + 1:]
        if rest:
            return None

    value = current
    if key:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    for selector in selectors:
        if selector in {"", "*"}:
            if not isinstance(value, list):
                return None
            continue
        if not isinstance(value, list):
            return None
        value = _extract_list_index(value, selector)
    return value


def _extract_list_index(values: list[Any], selector: str) -> Any:
    try:
        index = int(selector)
    except (TypeError, ValueError):
        return None
    if index < 0:
        index = len(values) + index
    if index < 0 or index >= len(values):
        return None
    return values[index]


class VariableResolver:
    """从显式输入和 Variable Hub 解析最终 alias map。"""

    def __init__(self, repository: VariableHubRepository):
        self._repository = repository

    def resolve(
        self,
        *,
        spec: InvocationSpec,
        explicit_variables: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> VariablePlan:
        context_key = self._context_key(context)
        aliases: dict[str, Any] = {}
        raw_aliases: dict[str, Any] = {}
        lineage: dict[str, str] = {}
        resolved_from_hub: set[str] = set()
        snapshot_values: dict[str, Any] = {}
        diagnostics: list[str] = []
        resolution_items: list[dict[str, Any]] = []
        required_missing: list[str] = []
        snapshot_items: list[dict[str, Any]] = []
        bindings = self._repository.get_bindings(spec.input_binding_set_id, spec.node_key)
        binding_by_alias = {binding.alias: binding for binding in bindings}

        for binding in bindings:
            definition = self._repository.get_definition(binding.variable_key) if binding.variable_key else None
            if not binding.enabled:
                diagnostics.append(f"变量 {binding.alias} 已禁用")
                resolution_items.append(
                    self._resolution_item(
                        binding=binding,
                        display_name=self._public_display_name(binding, definition),
                        status="invalid",
                        value=None,
                        version_number=0,
                        source="disabled",
                        context_key=context_key,
                    )
                )
                continue
            value_found = False
            hub_value = self._repository.get_value(binding.variable_key, context_key) if binding.variable_key else None
            selected_for_resolution = hub_value.value if hub_value is not None else None
            if binding.alias in explicit_variables:
                selected = self._select_binding_value(binding, explicit_variables[binding.alias])
                aliases[binding.alias] = self._render_selected_value(binding, selected)
                raw_aliases[binding.alias] = selected
                lineage[binding.alias] = "explicit"
                if hub_value is not None:
                    resolved_from_hub.add(binding.alias)
                value_found = True
            elif binding.variable_key:
                if hub_value is not None:
                    selected = self._select_binding_value(binding, hub_value.value)
                    aliases[binding.alias] = self._render_selected_value(binding, selected)
                    raw_aliases[binding.alias] = selected
                    snapshot_values[binding.alias] = selected
                    lineage[binding.alias] = hub_value.source_ref or f"variable:{binding.variable_key}"
                    resolved_from_hub.add(binding.alias)
                    value_found = True

            if not value_found:
                default = binding.default
                if default is None and definition is not None:
                    default = definition.default
                if default is not None:
                    selected = self._select_binding_value(binding, default)
                    aliases[binding.alias] = self._render_selected_value(binding, selected)
                    raw_aliases[binding.alias] = selected
                    lineage[binding.alias] = "default"
                    value_found = True

            if not value_found and binding.required:
                required_missing.append(binding.alias)
                diagnostics.append(f"必填变量缺失: {binding.alias}")

            if binding.variable_key:
                resolution_items.append(
                    self._resolution_item(
                        binding=binding,
                        display_name=self._public_display_name(binding, definition),
                        status="resolved" if hub_value is not None else ("missing" if binding.required else "missing"),
                        value=selected_for_resolution,
                        version_number=hub_value.version_number if hub_value is not None else 0,
                        source=hub_value.source_ref if hub_value is not None else "",
                        context_key=hub_value.context_key if hub_value is not None else context_key,
                    )
                )
            else:
                resolution_items.append(
                    self._resolution_item(
                        binding=binding,
                        display_name=self._public_display_name(binding, definition),
                        status="invalid",
                        value=None,
                        version_number=0,
                        source=binding.source or "",
                        context_key=context_key,
                    )
                )

        for alias, value in explicit_variables.items():
            if alias not in aliases:
                aliases[alias] = value
                raw_aliases[alias] = value
                lineage[alias] = "explicit"

        for alias, value in aliases.items():
            binding = binding_by_alias.get(alias)
            if self._is_runtime_only_binding(binding):
                continue
            if alias not in resolved_from_hub:
                continue
            snapshot_value = snapshot_values.get(alias, raw_aliases.get(alias, value))
            if not self._is_snapshot_value_present(snapshot_value):
                continue
            definition = self._repository.get_definition(binding.variable_key) if binding and binding.variable_key else None
            snapshot_items.append(
                self._snapshot_item(
                    alias,
                    snapshot_value,
                    binding,
                    "variable_hub",
                    display_name=self._public_display_name(binding, definition),
                )
            )

        self._append_context_snapshot_items(snapshot_items, context_key)

        snapshot_groups = self._snapshot_groups(snapshot_items)
        snapshot_hash = stable_hash({
            "aliases": aliases,
            "raw_aliases": raw_aliases,
            "lineage": lineage,
            "snapshot_items": snapshot_items,
        })
        return VariablePlan(
            aliases=aliases,
            raw_aliases=raw_aliases,
            bindings=tuple(bindings),
            resolution_items=tuple(resolution_items),
            required_missing=tuple(required_missing),
            diagnostics=tuple(diagnostics),
            lineage=lineage,
            snapshot_items=tuple(snapshot_items),
            snapshot_groups=tuple(snapshot_groups),
            snapshot_hash=snapshot_hash,
        )

    @staticmethod
    def _context_key(context: Mapping[str, Any]) -> str:
        parts = []
        for key in ("novel_id", "act_id", "chapter_id", "chapter_number", "scene_id", "beat_index"):
            value = context.get(key)
            if value not in (None, ""):
                parts.append(f"{key}:{value}")
        return "|".join(parts) if parts else "global"

    @staticmethod
    def _public_display_name(binding: VariableBinding | None, definition: VariableDefinition | None) -> str:
        if definition is not None and definition.display_name:
            return definition.display_name
        variable_key = binding.variable_key if binding and binding.variable_key else ""
        if variable_key:
            return variable_key
        if binding and binding.alias:
            return binding.alias
        return ""

    @staticmethod
    def _snapshot_item(
        alias: str,
        value: Any,
        binding: VariableBinding | None,
        lineage: str,
        *,
        display_name: str,
    ) -> dict[str, Any]:
        variable_key = binding.variable_key if binding else alias
        return {
            "key": alias,
            "display_name": display_name,
            "value": value,
            "type": VariableResolver._infer_type(value),
            "scope": binding.scope if binding and binding.scope else VariableResolver._infer_scope(variable_key),
            "stage": binding.stage if binding and binding.stage else VariableResolver._infer_stage(variable_key),
            "source": "variable_hub" if lineage == "variable_hub" else (binding.source if binding and binding.source else lineage),
            "variable_key": variable_key,
            "required": bool(binding.required) if binding else False,
            "source_path": binding.source_path if binding else "",
            "projection_key": binding.projection_key if binding else "",
            "render_mode": binding.render_mode if binding else "raw",
        }

    @staticmethod
    def _resolution_item(
        *,
        binding: VariableBinding,
        display_name: str,
        status: str,
        value: Any,
        version_number: int,
        source: str,
        context_key: str,
    ) -> dict[str, Any]:
        return {
            "alias": binding.alias,
            "variable_key": binding.variable_key or binding.alias,
            "display_name": display_name,
            "status": status,
            "current_value": value,
            "value_type": binding.value_type or VariableResolver._infer_type(value),
            "version_number": version_number,
            "source": source or "",
            "context_key": context_key,
            "required": bool(binding.required),
        }

    @staticmethod
    def _render_binding_value(binding: VariableBinding, value: Any) -> Any:
        selected = VariableResolver._select_binding_value(binding, value)
        return VariableResolver._render_selected_value(binding, selected)

    @staticmethod
    def _select_binding_value(binding: VariableBinding, value: Any) -> Any:
        selected = value
        if binding.source_path and isinstance(value, (Mapping, list)):
            selected = extract_path_value(value, binding.source_path)
        elif (
            binding.variable_key.startswith("novel.worldbuilding.")
            and isinstance(value, Mapping)
            and not binding.source_path
        ):
            nested_key = binding.variable_key.removeprefix("novel.worldbuilding.")
            if nested_key and nested_key in value:
                selected = extract_path_value(value, nested_key)
        return selected

    @staticmethod
    def _render_selected_value(binding: VariableBinding, selected: Any) -> Any:
        return render_variable_value(
            selected,
            render_mode=binding.render_mode,
            projection_key=binding.projection_key,
        )

    @staticmethod
    def _is_runtime_only_binding(binding: VariableBinding | None) -> bool:
        if binding is None:
            return False
        if binding.source in SNAPSHOT_EXCLUDED_BINDING_SOURCES:
            return True
        return bool(binding.variable_key and str(binding.variable_key).startswith("system."))

    def _append_context_snapshot_items(self, snapshot_items: list[dict[str, Any]], context_key: str) -> None:
        if not hasattr(self._repository, "list_current_values"):
            return
        seen_keys = {
            str(item.get("variable_key") or item.get("key") or "")
            for item in snapshot_items
            if str(item.get("variable_key") or item.get("key") or "")
        }
        try:
            current_values = self._repository.list_current_values(context_key)  # type: ignore[attr-defined]
        except Exception:
            return
        for raw in current_values or []:
            variable_key = str(raw.get("variable_key") or raw.get("key") or "")
            value = raw.get("value")
            if (
                not variable_key
                or variable_key in seen_keys
                or not self._is_snapshot_variable_key(variable_key)
                or not self._is_snapshot_value_present(value)
            ):
                continue
            seen_keys.add(variable_key)
            snapshot_items.append(
                {
                    "key": variable_key,
                    "display_name": str(raw.get("display_name") or variable_key),
                    "value": value,
                    "type": str(raw.get("value_type") or VariableResolver._infer_type(value)),
                    "scope": str(raw.get("scope") or VariableResolver._infer_scope(variable_key)),
                    "stage": str(raw.get("stage") or VariableResolver._infer_stage(variable_key)),
                    "source": "variable_hub",
                    "variable_key": variable_key,
                    "required": False,
                }
            )

    @staticmethod
    def _is_snapshot_variable_key(variable_key: str) -> bool:
        return not variable_key.startswith(("system.", "runtime.", "materialized."))

    @staticmethod
    def _is_snapshot_value_present(value: Any) -> bool:
        return value is not None and value not in ("", [], {})

    @staticmethod
    def _snapshot_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in items:
            grouped.setdefault((str(item.get("scope") or "runtime"), str(item.get("stage") or "runtime")), []).append(item)
        ordered_keys = sorted(grouped, key=lambda key: (VariableResolver._scope_order(key[0]), VariableResolver._stage_order(key[1]), key))
        return [
            {
                "id": f"{scope}:{stage}",
                "scope": scope,
                "stage": stage,
                "title": VariableResolver._group_title(scope, stage),
                "items": grouped[(scope, stage)],
            }
            for scope, stage in ordered_keys
        ]

    @staticmethod
    def _infer_type(value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int) and not isinstance(value, bool):
            return "integer"
        if isinstance(value, float):
            return "float"
        if isinstance(value, list):
            return "list"
        if isinstance(value, dict):
            return "object"
        return "string"

    @staticmethod
    def _infer_scope(variable_key: str) -> str:
        if variable_key.startswith("global."):
            return "global"
        if variable_key.startswith(("novel.", "worldbuilding.", "characters.", "locations.", "plot.")):
            return "novel"
        if variable_key.startswith("chapter."):
            return "chapter"
        if variable_key.startswith("scene."):
            return "scene"
        if variable_key.startswith("beat."):
            return "beat"
        return "runtime"

    @staticmethod
    def _infer_stage(variable_key: str) -> str:
        if ".setup." in variable_key:
            return "setup"
        if variable_key.startswith("worldbuilding.") or ".worldbuilding." in variable_key:
            return "worldbuilding"
        if variable_key.startswith("characters.") or ".characters." in variable_key:
            return "characters"
        if variable_key.startswith("locations.") or ".locations." in variable_key:
            return "locations"
        if variable_key.startswith("plot.") or ".plot." in variable_key or ".planning." in variable_key:
            return "planning"
        if ".writing." in variable_key:
            return "writing"
        if ".review." in variable_key:
            return "review"
        return "runtime"

    @staticmethod
    def _scope_order(scope: str) -> int:
        return {"global": 0, "novel": 1, "chapter": 2, "scene": 3, "beat": 4, "runtime": 9}.get(scope, 8)

    @staticmethod
    def _stage_order(stage: str) -> int:
        return {
            "setup": 0,
            "worldbuilding": 1,
            "characters": 2,
            "locations": 3,
            "planning": 4,
            "writing": 5,
            "review": 6,
            "postprocess": 7,
            "runtime": 9,
        }.get(stage, 8)

    @staticmethod
    def _group_title(scope: str, stage: str) -> str:
        scope_label = {
            "global": "全局变量",
            "novel": "小说变量",
            "chapter": "章节变量",
            "scene": "场景变量",
            "beat": "节拍变量",
            "runtime": "运行时变量",
        }.get(scope, scope)
        stage_label = {
            "setup": "设定",
            "planning": "规划阶段",
            "worldbuilding": "世界观",
            "characters": "人物",
            "locations": "地点",
            "writing": "写作阶段",
            "review": "审阅阶段",
            "postprocess": "后处理",
            "runtime": "运行时",
        }.get(stage, stage)
        return f"{scope_label} · {stage_label}"


def expand_context_keys(context_key: str) -> list[str]:
    """Expand a context key from most specific to least specific."""
    normalized = str(context_key or "").strip() or "global"
    if normalized == "global":
        return ["global"]
    parts = [part for part in normalized.split("|") if part]
    keys = ["|".join(parts[:idx]) for idx in range(len(parts), 0, -1)]
    if "global" not in keys:
        keys.append("global")
    return keys
