"""PromptGateway: CPMS-only prompt rendering entry."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ValidationError

from application.ai.trace_context import (
    content_hash,
    ensure_trace,
    extract_novel_id,
    preview_value,
    prompt_preview,
    prompt_to_hash_payload,
)
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.prompt_contract import PromptContract
from infrastructure.ai.trace_recorder import get_trace_recorder
from infrastructure.ai.variable_registry import get_variable_registry

logger = logging.getLogger(__name__)


class PromptGatewayError(RuntimeError):
    """Base PromptGateway error."""


class PromptGatewayValidationError(PromptGatewayError):
    """Raised when prompt variables or rendered templates are invalid."""


class PromptGatewayNodeMissingError(PromptGatewayError):
    """Raised when the CPMS registry has no published node for the contract."""


# Backward-compatible alias for older imports. Runtime behavior is CPMS-only.
PromptGatewayPackageMissingError = PromptGatewayNodeMissingError


@dataclass(frozen=True)
class PromptGatewayRenderResult:
    """Rendered prompt result."""

    prompt: Prompt
    node_key: str
    contract_version: str
    source: str
    variables: Mapping[str, Any] = field(default_factory=dict)

    def as_text(self) -> str:
        """Return a legacy text view for callers that still need plain text."""
        return f"[System]\n{self.prompt.system}\n\n[User]\n{self.prompt.user}"


class PromptGateway:
    """CPMS-only prompt rendering gateway.

    Runtime order:
    1. Validate variables with the contract schema.
    2. Render only from PromptRegistry / CPMS.
    3. Fast-fail when the CPMS node is missing or unavailable.

    The package directory is accepted only for compatibility with old tests and
    callers. It is not used by runtime rendering.
    """

    def __init__(self, packages_root: Path | None = None):
        self._packages_root = packages_root

    def render(
        self,
        contract: PromptContract,
        variables: Mapping[str, Any] | None = None,
    ) -> PromptGatewayRenderResult:
        raw_vars = dict(variables or {})
        ensure_trace(
            novel_id=extract_novel_id(raw_vars),
            operation="prompt_render",
            metadata={"entry": "PromptGateway.render"},
        )
        try:
            checked_vars = self._validate_variables(contract, raw_vars)
            self._record_variables_validated(contract, checked_vars)
        except Exception as exc:
            self._record_trace_error(
                contract,
                phase="error",
                error=exc,
                variables=raw_vars,
                metadata={"stage": "variables_validation"},
            )
            raise

        try:
            rendered = self._render_from_registry(contract, checked_vars)
            if rendered is not None:
                self._record_prompt_rendered(rendered, registry_error=None)
                return rendered
        except PromptGatewayValidationError as exc:
            self._record_trace_error(
                contract,
                phase="error",
                error=exc,
                variables=checked_vars,
                metadata={"stage": "registry_render_validation"},
            )
            raise
        except Exception as exc:
            self._record_trace_error(
                contract,
                phase="error",
                error=exc,
                variables=checked_vars,
                metadata={"stage": "registry_render"},
            )
            raise

        error = PromptGatewayNodeMissingError(
            f"Prompt node {contract.node_key!r} is not published in CPMS; invocation blocked."
        )
        self._record_trace_error(
            contract,
            phase="error",
            error=error,
            variables=checked_vars,
            metadata={"stage": "prompt_lookup"},
        )
        raise error

    def validate_output(self, contract: PromptContract, payload: Any) -> Any:
        """Validate structured output with the contract schema."""
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
                f"Node {contract.node_key} output validation failed: {messages}"
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
                f"Node {contract.node_key} input validation failed: {messages}"
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
            variables=variables,
        )

    def _record_variables_validated(
        self,
        contract: PromptContract,
        variables: Mapping[str, Any],
    ) -> None:
        variable_sources = self._build_variable_sources(contract.node_key, variables)
        get_trace_recorder().record_span(
            phase="variables_validated",
            node_id=contract.node_key,
            node_type="prompt",
            contract_key=contract.node_key,
            contract_version=contract.version,
            source="config",
            variables_hash=content_hash(variables),
            variables_preview=preview_value(variables),
            variables_full=dict(variables),
            variable_sources=variable_sources,
            metadata={"variables_schema": getattr(contract.variables_schema, "__name__", None)},
        )

    def _record_prompt_rendered(
        self,
        result: PromptGatewayRenderResult,
        *,
        registry_error: Exception | None,
    ) -> None:
        get_trace_recorder().record_span(
            phase="prompt_rendered",
            node_id=result.node_key,
            node_type="prompt",
            contract_key=result.node_key,
            contract_version=result.contract_version,
            source="cpms",
            variables_hash=content_hash(result.variables),
            variables_preview=preview_value(result.variables),
            variables_full=dict(result.variables),
            variable_sources=self._build_variable_sources(result.node_key, result.variables),
            prompt_hash=content_hash(prompt_to_hash_payload(result.prompt)),
            prompt_preview=prompt_preview(result.prompt),
            prompt_full=prompt_to_hash_payload(result.prompt),
            metadata={
                "prompt_source": result.source,
                "registry_error": str(registry_error) if registry_error else "",
                "context_injection": self._infer_context_injection(result.variables),
            },
        )

    def _record_trace_error(
        self,
        contract: PromptContract,
        *,
        phase: str,
        error: Exception,
        variables: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        get_trace_recorder().record_span(
            phase=phase,
            node_id=contract.node_key,
            node_type="prompt",
            contract_key=contract.node_key,
            contract_version=contract.version,
            source="cpms",
            variables_hash=content_hash(variables),
            variables_preview=preview_value(variables),
            variable_sources=self._build_variable_sources(contract.node_key, variables),
            metadata={**dict(metadata or {}), "error": str(error), "error_type": type(error).__name__},
        )

    def _build_variable_sources(self, node_key: str, variables: Mapping[str, Any]) -> list[dict[str, Any]]:
        schemas = get_variable_registry().get_schemas_for_node(node_key)
        items: list[dict[str, Any]] = []
        for name in sorted(variables.keys()):
            schema = schemas.get(str(name))
            if schema is None:
                items.append({"name": str(name), "source": "runtime", "required": False})
                continue
            items.append(
                {
                    "name": str(name),
                    "source": schema.source,
                    "required": schema.required,
                    "scope": schema.scope.value,
                    "type": schema.type.value,
                }
            )
        return items

    @staticmethod
    def _infer_context_injection(variables: Mapping[str, Any]) -> list[dict[str, str]]:
        injected: list[dict[str, str]] = []
        for key in variables.keys():
            key_lower = str(key).lower()
            if "genre" in key_lower:
                source = "GenrePack"
            elif "policy" in key_lower or "rule" in key_lower:
                source = "PolicyPack"
            elif "context" in key_lower or "memory" in key_lower or "outline" in key_lower:
                source = "Context"
            else:
                continue
            injected.append({"name": str(key), "source": source})
        return injected

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
                f"Node {node_key} rendered prompt still has missing variables: {', '.join(missing)}"
            )
        if not system.strip() or not user.strip():
            raise PromptGatewayValidationError(f"Node {node_key} rendered prompt is empty")
        return Prompt(system=system.strip(), user=user.strip())


_prompt_gateway: PromptGateway | None = None


def get_prompt_gateway() -> PromptGateway:
    global _prompt_gateway
    if _prompt_gateway is None:
        _prompt_gateway = PromptGateway()
    return _prompt_gateway
