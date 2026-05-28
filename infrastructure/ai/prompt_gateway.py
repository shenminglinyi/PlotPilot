"""PromptGateway：统一渲染、校验与回退观测入口。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ValidationError

from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.prompt_contract import PromptContract

logger = logging.getLogger(__name__)


class PromptGatewayError(RuntimeError):
    """PromptGateway 基础异常。"""


class PromptGatewayValidationError(PromptGatewayError):
    """变量或模板渲染校验失败。"""


class PromptGatewayPackageMissingError(PromptGatewayError):
    """CPMS 与本地 package 均找不到指定节点。"""


@dataclass(frozen=True)
class PromptGatewayRenderResult:
    """提示词渲染结果，保留来源信息便于观测。"""

    prompt: Prompt
    node_key: str
    contract_version: str
    source: str
    fallback_used: bool = False
    variables: Mapping[str, Any] = field(default_factory=dict)

    def as_text(self) -> str:
        """给只接受字符串的旧 LLM 客户端使用。"""
        return f"【系统指令】\n{self.prompt.system}\n\n【用户输入】\n{self.prompt.user}"


class PromptGateway:
    """AI 能力提示词统一入口。

    渲染顺序：
    1. Pydantic 校验 variables，失败即 fast-fail；
    2. 优先读取 PromptRegistry（提示词广场/DB）；
    3. Registry 不可用或节点未落库时，回退读取 prompt_packages 文件；
    4. 所有回退都会记录来源，避免静默走硬编码。
    """

    def __init__(self, packages_root: Path | None = None):
        self._packages_root = packages_root or (
            Path(__file__).resolve().parent / "prompt_packages" / "nodes"
        )

    def render(
        self,
        contract: PromptContract,
        variables: Mapping[str, Any] | None = None,
    ) -> PromptGatewayRenderResult:
        """渲染契约对应的 Prompt。"""
        checked_vars = self._validate_variables(contract, variables or {})

        registry_error: Exception | None = None
        try:
            rendered = self._render_from_registry(contract, checked_vars)
            if rendered is not None:
                return rendered
        except PromptGatewayValidationError:
            raise
        except Exception as exc:  # Registry/DB 不可用时允许 package 文件回退
            registry_error = exc
            logger.debug("PromptRegistry 渲染失败，准备读取本地 package: %s", exc)

        package_result = self._render_from_package(contract, checked_vars)
        if package_result is not None:
            logger.warning(
                "PromptGateway 使用本地 package 回退: node=%s registry_error=%s",
                contract.node_key,
                registry_error,
            )
            return package_result

        raise PromptGatewayPackageMissingError(
            f"提示词节点 {contract.node_key!r} 不存在：PromptRegistry 未命中，"
            f"且本地 prompt_packages 未找到。"
        )

    def validate_output(self, contract: PromptContract, payload: Any) -> Any:
        """按契约校验结构化输出；无 output_schema 时原样返回。"""
        if contract.output_schema is None:
            return payload
        try:
            return contract.output_schema.model_validate(payload)
        except ValidationError as exc:
            messages = "; ".join(
                f"{'/'.join(str(x) for x in err.get('loc', ()))}: {err.get('msg', '')}"
                for err in exc.errors()[:10]
            )
            raise PromptGatewayValidationError(
                f"节点 {contract.node_key} 输出校验失败: {messages}"
            ) from exc

    def _validate_variables(
        self,
        contract: PromptContract,
        variables: Mapping[str, Any],
    ) -> dict[str, Any]:
        if contract.variables_schema is None:
            return dict(variables)
        try:
            model: BaseModel = contract.variables_schema.model_validate(dict(variables))
        except ValidationError as exc:
            messages = "; ".join(
                f"{'/'.join(str(x) for x in err.get('loc', ()))}: {err.get('msg', '')}"
                for err in exc.errors()[:10]
            )
            raise PromptGatewayValidationError(
                f"节点 {contract.node_key} 输入变量校验失败: {messages}"
            ) from exc
        return model.model_dump()

    def _render_from_registry(
        self,
        contract: PromptContract,
        variables: dict[str, Any],
    ) -> PromptGatewayRenderResult | None:
        from infrastructure.ai.prompt_registry import get_prompt_registry

        registry = get_prompt_registry()
        result = registry.render(contract.node_key, variables)
        if result is None:
            return None
        prompt = self._prompt_from_rendered(
            node_key=contract.node_key,
            system=result.system,
            user=result.user,
            missing_variables=result.missing_variables,
        )
        return PromptGatewayRenderResult(
            prompt=prompt,
            node_key=contract.node_key,
            contract_version=contract.version,
            source="registry",
            fallback_used=False,
            variables=variables,
        )

    def _render_from_package(
        self,
        contract: PromptContract,
        variables: dict[str, Any],
    ) -> PromptGatewayRenderResult | None:
        node_dir = self._packages_root / contract.node_key
        if not node_dir.is_dir():
            return None

        system_template = self._read_optional(node_dir / "system.md")
        user_template = self._read_optional(node_dir / "user.md")
        from infrastructure.ai.prompt_template_engine import get_template_engine

        result = get_template_engine().render(
            system_template=system_template,
            user_template=user_template,
            variables=variables,
        )
        prompt = self._prompt_from_rendered(
            node_key=contract.node_key,
            system=result.system,
            user=result.user,
            missing_variables=result.missing_variables,
        )
        return PromptGatewayRenderResult(
            prompt=prompt,
            node_key=contract.node_key,
            contract_version=contract.version,
            source="package_file",
            fallback_used=True,
            variables=variables,
        )

    @staticmethod
    def _read_optional(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    @staticmethod
    def _prompt_from_rendered(
        node_key: str,
        system: str,
        user: str,
        missing_variables: list[str] | tuple[str, ...] | None = None,
    ) -> Prompt:
        missing = sorted(set(missing_variables or []))
        if missing:
            raise PromptGatewayValidationError(
                f"节点 {node_key} 模板变量未提供: {', '.join(missing)}"
            )
        if not system or not system.strip():
            raise PromptGatewayValidationError(f"节点 {node_key} 的 system prompt 为空")
        if not user or not user.strip():
            raise PromptGatewayValidationError(f"节点 {node_key} 的 user prompt 为空")
        return Prompt(system=system.strip(), user=user.strip())


_GATEWAY: PromptGateway | None = None


def get_prompt_gateway() -> PromptGateway:
    """获取进程内 PromptGateway 单例。"""
    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = PromptGateway()
    return _GATEWAY
