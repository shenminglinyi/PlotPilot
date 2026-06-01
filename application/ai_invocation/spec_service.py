"""InvocationSpec 加载服务。"""
from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from application.ai_invocation.dtos import InvocationRequest, InvocationSpec


class InvocationSpecNotFoundError(LookupError):
    """未发布指定 AI 能力契约。"""


class InvocationSpecRepository(Protocol):
    def get(self, operation: str, node_key: str) -> InvocationSpec | None:
        """按 operation + node_key 查询 spec。"""


class InMemoryInvocationSpecRepository:
    """内存 spec 仓储，供单元测试和早期接入使用。"""

    def __init__(self, specs: list[InvocationSpec] | None = None):
        self._items: dict[tuple[str, str], InvocationSpec] = {}
        for spec in specs or []:
            self.add(spec)

    def add(self, spec: InvocationSpec) -> None:
        self._items[(spec.operation, spec.node_key)] = spec

    def get(self, operation: str, node_key: str) -> InvocationSpec | None:
        return self._items.get((operation, node_key))


class InvocationSpecService:
    """加载并校验可运行 AI 能力契约。"""

    def __init__(self, repository: InvocationSpecRepository):
        self._repository = repository

    def load(self, request: InvocationRequest) -> InvocationSpec:
        spec = self._repository.get(request.operation, request.node_key)
        if spec is None:
            raise InvocationSpecNotFoundError(
                f"AI 调用能力未发布: operation={request.operation}, node_key={request.node_key}"
            )
        if spec.operation != request.operation or spec.node_key != request.node_key:
            raise ValueError("InvocationSpec 与请求不匹配")
        if request.policy is not None:
            return replace(spec, default_policy=request.policy)
        return spec
