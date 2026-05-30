"""Variable Hub 最小解析底座。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from application.ai_invocation.dtos import InvocationSpec, VariableBinding, VariablePlan, stable_hash


@dataclass(frozen=True)
class VariableDefinition:
    key: str
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


class VariableHubRepository(Protocol):
    def get_bindings(self, binding_set_id: str, node_key: str) -> list[VariableBinding]:
        """读取节点输入变量绑定。"""

    def get_value(self, variable_key: str, context_key: str) -> VariableValue | None:
        """读取变量值。"""

    def get_definition(self, variable_key: str) -> VariableDefinition | None:
        """读取变量定义。"""


@dataclass
class InMemoryVariableHubRepository:
    """内存 Variable Hub 仓储。"""

    definitions: dict[str, VariableDefinition] = field(default_factory=dict)
    values: dict[tuple[str, str], VariableValue] = field(default_factory=dict)
    bindings: dict[tuple[str, str], list[VariableBinding]] = field(default_factory=dict)

    def add_definition(self, definition: VariableDefinition) -> None:
        self.definitions[definition.key] = definition

    def set_value(self, value: VariableValue) -> None:
        self.values[(value.key, value.context_key)] = value

    def set_bindings(self, binding_set_id: str, node_key: str, bindings: list[VariableBinding]) -> None:
        self.bindings[(binding_set_id, node_key)] = list(bindings)

    def get_bindings(self, binding_set_id: str, node_key: str) -> list[VariableBinding]:
        return list(self.bindings.get((binding_set_id, node_key), []))

    def get_value(self, variable_key: str, context_key: str) -> VariableValue | None:
        return self.values.get((variable_key, context_key)) or self.values.get((variable_key, "global"))

    def get_definition(self, variable_key: str) -> VariableDefinition | None:
        return self.definitions.get(variable_key)


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
        lineage: dict[str, str] = {}
        diagnostics: list[str] = []
        required_missing: list[str] = []
        bindings = self._repository.get_bindings(spec.input_binding_set_id, spec.node_key)

        for binding in bindings:
            if not binding.enabled:
                diagnostics.append(f"变量 {binding.alias} 已禁用")
                continue
            value_found = False
            if binding.alias in explicit_variables:
                aliases[binding.alias] = explicit_variables[binding.alias]
                lineage[binding.alias] = "explicit"
                value_found = True
            elif binding.variable_key:
                stored = self._repository.get_value(binding.variable_key, context_key)
                if stored is not None:
                    aliases[binding.alias] = stored.value
                    lineage[binding.alias] = stored.source_ref or f"variable:{binding.variable_key}"
                    value_found = True

            if not value_found:
                definition = self._repository.get_definition(binding.variable_key) if binding.variable_key else None
                default = binding.default
                if default is None and definition is not None:
                    default = definition.default
                if default is not None:
                    aliases[binding.alias] = default
                    lineage[binding.alias] = "default"
                    value_found = True

            if not value_found and binding.required:
                required_missing.append(binding.alias)
                diagnostics.append(f"必填变量缺失: {binding.alias}")

        for alias, value in explicit_variables.items():
            if alias not in aliases:
                aliases[alias] = value
                lineage[alias] = "explicit"

        snapshot_hash = stable_hash({"aliases": aliases, "lineage": lineage})
        return VariablePlan(
            aliases=aliases,
            bindings=tuple(bindings),
            required_missing=tuple(required_missing),
            diagnostics=tuple(diagnostics),
            lineage=lineage,
            snapshot_hash=snapshot_hash,
        )

    @staticmethod
    def _context_key(context: Mapping[str, Any]) -> str:
        parts = []
        for key in ("novel_id", "chapter_id", "chapter_number", "scene_id"):
            value = context.get(key)
            if value not in (None, ""):
                parts.append(f"{key}:{value}")
        return "|".join(parts) if parts else "global"
