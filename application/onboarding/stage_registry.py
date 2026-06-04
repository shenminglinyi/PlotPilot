"""Registry for setup-guide onboarding stages.

The setup guide is a composition of AI Invocation stages.  This registry keeps
operation/node/input/context/continuation contracts in application code so API
routes do not accumulate stage-specific CPMS rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from application.ai_invocation.dtos import InvocationSpec, VariableBinding

InputContractProvider = Callable[[], list[VariableBinding]]
SpecProvider = Callable[[], InvocationSpec]
ContractEnsurer = Callable[[Any], InvocationSpec]
ContextProvider = Callable[..., Mapping[str, Any]]


@dataclass(frozen=True)
class OnboardingStageDefinition:
    stage: str
    operation: str
    node_key: str
    input_contract: InputContractProvider
    context_provider: ContextProvider
    continuation_handler: str
    spec_provider: SpecProvider
    contract_ensurer: ContractEnsurer
    output_contract: InputContractProvider | None = None
    ui_events: Mapping[str, Any] = field(default_factory=dict)

    @property
    def input_binding_set_id(self) -> str:
        return self.spec_provider().input_binding_set_id

    @property
    def output_binding_set_id(self) -> str:
        return self.spec_provider().output_binding_set_id


class OnboardingStageRegistry:
    def __init__(self, definitions: list[OnboardingStageDefinition]):
        self._by_stage = {definition.stage: definition for definition in definitions}
        self._by_operation_node = {
            (definition.operation, definition.node_key): definition
            for definition in definitions
        }

    def get(self, stage: str) -> OnboardingStageDefinition:
        definition = self._by_stage.get(stage)
        if definition is None:
            raise ValueError(f"unsupported onboarding stage: {stage}")
        return definition

    def find(self, *, operation: str, node_key: str) -> OnboardingStageDefinition | None:
        return self._by_operation_node.get((operation, node_key))

    def ensure_contract(self, *, operation: str, node_key: str, db: Any) -> InvocationSpec:
        definition = self.find(operation=operation, node_key=node_key)
        if definition is None:
            raise ValueError(f"unsupported onboarding contract: operation={operation}, node_key={node_key}")
        return definition.contract_ensurer(db)

    def stages(self) -> list[str]:
        return list(self._by_stage)

