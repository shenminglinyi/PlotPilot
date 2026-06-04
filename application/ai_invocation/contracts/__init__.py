"""Application-level AI invocation contract registration."""

from application.ai_invocation.contracts.registry import InvocationContractRegistry, ensure_invocation_contract

__all__ = ["InvocationContractRegistry", "ensure_invocation_contract"]
