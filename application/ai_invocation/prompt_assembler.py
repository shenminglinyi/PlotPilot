"""CPMS PromptAssembler。"""
from __future__ import annotations

from typing import Mapping, Protocol

from domain.ai.value_objects.prompt import Prompt
from application.ai_invocation.dtos import InvocationSpec, PromptSnapshot, VariablePlan, prompt_hash, stable_hash
from application.ai_invocation.prompt_variables import aliases_with_binding_variable_keys, aliases_with_dotted_variables


class PromptAssemblyError(RuntimeError):
    """Prompt 组装失败。"""


class PromptRegistryLike(Protocol):
    def get_node(self, node_key: str, use_cache: bool = True):
        """读取 CPMS 节点。"""


class PromptTemplateEngineLike(Protocol):
    def render(self, system_template: str, user_template: str, variables: dict, variable_schemas=None):
        """渲染模板。"""


class CPMSPromptAssembler:
    """根据 InvocationSpec 和 VariablePlan 编译冻结 prompt snapshot。

    该类只读 CPMS Registry，不读取 prompt_packages，不直接调用 provider。
    """

    def __init__(self, registry: PromptRegistryLike | None = None, template_engine: PromptTemplateEngineLike | None = None):
        if registry is None:
            from infrastructure.ai.prompt_registry import get_prompt_registry

            registry = get_prompt_registry()
        if template_engine is None:
            from infrastructure.ai.prompt_template_engine import get_template_engine

            template_engine = get_template_engine()
        self._registry = registry
        self._template_engine = template_engine

    def compile(self, *, spec: InvocationSpec, variable_plan: VariablePlan) -> PromptSnapshot:
        node = self._registry.get_node(spec.node_key)
        if node is None:
            raise PromptAssemblyError(f"CPMS 节点未发布: {spec.node_key}")
        node_version_id = getattr(node, "active_version_id", None) or spec.prompt_node_version_id
        if not node_version_id:
            raise PromptAssemblyError(f"CPMS 节点缺少 active version: {spec.node_key}")
        if spec.prompt_node_version_id and spec.prompt_node_version_id != node_version_id:
            raise PromptAssemblyError(
                f"InvocationSpec 绑定的节点版本不是当前 active version: spec={spec.prompt_node_version_id}, active={node_version_id}"
            )

        system_template = node.get_active_system()
        user_template = node.get_active_user_template()
        render_aliases = aliases_with_binding_variable_keys(variable_plan.aliases or {}, variable_plan.bindings)
        for item in variable_plan.snapshot_items or ():
            if isinstance(item, Mapping) and item.get("variable_key"):
                render_aliases.setdefault(str(item.get("variable_key")), item.get("value"))

        render_result = self._template_engine.render(
            system_template=system_template,
            user_template=user_template,
            variables=aliases_with_dotted_variables(render_aliases),
        )
        prompt = Prompt(
            system=render_result.system,
            user=render_result.user,
        )
        asset_version_ids = tuple(str(x) for x in spec.metadata.get("asset_version_ids", []) if x)
        template_hash = stable_hash({"system_template": system_template, "user_template": user_template})
        composition_hash = stable_hash(
            {
                "node_key": spec.node_key,
                "node_version_id": node_version_id,
                "asset_link_set_id": spec.asset_link_set_id,
                "input_binding_set_id": spec.input_binding_set_id,
                "output_binding_set_id": spec.output_binding_set_id,
                "asset_version_ids": asset_version_ids,
            }
        )
        diagnostics = list(variable_plan.diagnostics)
        if getattr(render_result, "warnings", None):
            diagnostics.extend(str(item) for item in render_result.warnings)
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
            missing_variables=tuple(getattr(render_result, "missing_variables", []) or ()),
            diagnostics=tuple(diagnostics),
            asset_version_ids=asset_version_ids,
            template_prompt=Prompt(system=system_template or "", user=user_template or ""),
        )
