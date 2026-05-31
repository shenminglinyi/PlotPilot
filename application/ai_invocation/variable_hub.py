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
        snapshot_items: list[dict[str, Any]] = []
        bindings = self._repository.get_bindings(spec.input_binding_set_id, spec.node_key)
        binding_by_alias = {binding.alias: binding for binding in bindings}

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

        for alias, value in aliases.items():
            binding = binding_by_alias.get(alias)
            snapshot_items.append(self._snapshot_item(alias, value, binding, lineage.get(alias, "")))

        snapshot_groups = self._snapshot_groups(snapshot_items)
        snapshot_hash = stable_hash({"aliases": aliases, "lineage": lineage, "snapshot_items": snapshot_items})
        return VariablePlan(
            aliases=aliases,
            bindings=tuple(bindings),
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
        for key in ("novel_id", "chapter_id", "chapter_number", "scene_id"):
            value = context.get(key)
            if value not in (None, ""):
                parts.append(f"{key}:{value}")
        return "|".join(parts) if parts else "global"

    @staticmethod
    def _snapshot_item(alias: str, value: Any, binding: VariableBinding | None, lineage: str) -> dict[str, Any]:
        variable_key = binding.variable_key if binding else alias
        return {
            "key": alias,
            "display_name": binding.display_name if binding and binding.display_name else alias,
            "value": value,
            "type": binding.value_type if binding and binding.value_type else VariableResolver._infer_type(value),
            "scope": binding.scope if binding and binding.scope else VariableResolver._infer_scope(variable_key),
            "stage": binding.stage if binding and binding.stage else VariableResolver._infer_stage(variable_key),
            "source": binding.source if binding and binding.source else lineage,
            "variable_key": variable_key,
            "required": bool(binding.required) if binding else False,
        }

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
        if variable_key.startswith(("novel.", "global.")):
            return "global"
        if variable_key.startswith("chapter."):
            return "chapter"
        if variable_key.startswith("scene."):
            return "scene"
        if variable_key.startswith("beat."):
            return "beat"
        return "runtime"

    @staticmethod
    def _infer_stage(variable_key: str) -> str:
        if ".setup." in variable_key or variable_key.startswith("novel."):
            return "setup"
        if ".planning." in variable_key:
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
        return {"setup": 0, "planning": 1, "writing": 2, "review": 3, "runtime": 9}.get(stage, 8)

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
            "writing": "写作阶段",
            "review": "审阅阶段",
            "runtime": "运行时",
        }.get(stage, stage)
        return f"{scope_label} · {stage_label}"
