"""AI Invocation 子域公共 DTO。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional

from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage


class InvocationPolicy(str, Enum):
    """AI 调用策略。"""

    DIRECT = "DIRECT"
    REVIEW_BEFORE_CALL = "REVIEW_BEFORE_CALL"
    REVIEW_AFTER_CALL = "REVIEW_AFTER_CALL"
    FULL_INTERACTIVE = "FULL_INTERACTIVE"
    INTERACTIVE_WHEN_AVAILABLE = "INTERACTIVE_WHEN_AVAILABLE"
    AUTOPILOT_PAUSE = "AUTOPILOT_PAUSE"


class InvocationSessionStatus(str, Enum):
    REQUESTED = "requested"
    SPEC_RESOLVED = "spec_resolved"
    CONTEXT_RESOLVED = "context_resolved"
    VARIABLES_RESOLVED = "variables_resolved"
    PROMPT_COMPILED = "prompt_compiled"
    AWAITING_PRE_CALL_REVIEW = "awaiting_pre_call_review"
    GENERATING = "generating"
    AWAITING_ACCEPTANCE = "awaiting_acceptance"
    AWAITING_COMMIT = "awaiting_commit"
    COMMITTING = "committing"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvocationAttemptStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AdoptionCommitStatus(str, Enum):
    """采纳提交编排状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class ContinuationRef:
    """采纳后恢复业务流程的引用。"""

    handler_key: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InvocationRequest:
    """业务调用方提交给 AIInvocationGateway 的统一请求。"""

    operation: str
    node_key: str
    variables: Mapping[str, Any] = field(default_factory=dict)
    config: Optional[GenerationConfig] = None
    policy: Optional[InvocationPolicy] = None
    context: Mapping[str, Any] = field(default_factory=dict)
    continuation: Optional[ContinuationRef] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InvocationSpec:
    """可运行 AI 能力的持久契约。"""

    operation: str
    node_key: str
    prompt_node_version_id: str = ""
    asset_link_set_id: str = ""
    input_binding_set_id: str = ""
    output_binding_set_id: str = ""
    default_policy: InvocationPolicy = InvocationPolicy.DIRECT
    risk_level: str = "low"
    supports_stream: bool = False
    continuation_handler_key: str = ""
    commit_policy_key: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VariableBinding:
    """CPMS 节点变量 alias 与 Variable Hub 变量定义的绑定。"""

    alias: str
    variable_key: str = ""
    required: bool = False
    default: Any = None
    source: str = ""
    enabled: bool = True
    value_type: str = "string"
    scope: str = "runtime"
    stage: str = "runtime"
    display_name: str = ""
    source_path: str = ""
    projection_key: str = ""
    render_mode: str = "raw"


@dataclass(frozen=True)
class VariablePlan:
    """一次调用的变量解析计划和诊断。"""

    aliases: Mapping[str, Any]
    bindings: tuple[VariableBinding, ...] = ()
    required_missing: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)
    snapshot_items: tuple[Mapping[str, Any], ...] = ()
    snapshot_groups: tuple[Mapping[str, Any], ...] = ()
    snapshot_hash: str = ""

    @property
    def ok(self) -> bool:
        return not self.required_missing


@dataclass(frozen=True)
class PromptSnapshot:
    """一次调用冻结后的 prompt 快照。"""

    prompt: Prompt
    node_key: str
    node_version_id: str
    asset_link_set_id: str
    input_binding_set_id: str
    output_binding_set_id: str
    variable_snapshot_hash: str
    template_hash: str
    composition_hash: str
    rendered_prompt_hash: str
    missing_variables: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    asset_version_ids: tuple[str, ...] = ()
    template_prompt: Optional[Prompt] = None
    draft_prompt: Optional[Prompt] = None


@dataclass
class InvocationSession:
    """一次 AI 生成交互会话。"""

    id: str
    operation: str
    node_key: str
    policy: InvocationPolicy
    status: InvocationSessionStatus = InvocationSessionStatus.REQUESTED
    context: Mapping[str, Any] = field(default_factory=dict)
    continuation: Optional[ContinuationRef] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    prompt_snapshot: Optional[PromptSnapshot] = None
    variable_plan: Optional[VariablePlan] = None
    attempts: list[str] = field(default_factory=list)


@dataclass
class InvocationAttempt:
    """一次 LLM 调用尝试。"""

    id: str
    session_id: str
    status: InvocationAttemptStatus
    prompt_snapshot: PromptSnapshot
    content: str = ""
    token_usage: Optional[TokenUsage] = None
    error: str = ""


@dataclass
class AdoptionDecision:
    """一次生成结果的采纳决策。"""

    id: str
    session_id: str
    attempt_id: str
    decision: str = "accepted"
    accept_content: bool = True
    commit_prompt_version: bool = False
    commit_variable_outputs: bool = False
    commit_variable_bindings: bool = False
    accepted_content: str = ""
    accepted_by: str = "system"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class AdoptionCommitStep:
    """采纳提交中的一个幂等步骤。"""

    name: str
    status: AdoptionCommitStatus = AdoptionCommitStatus.PENDING
    result: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class AdoptionCommit:
    """采纳后的提交编排结果。"""

    id: str
    session_id: str
    decision_id: str
    status: AdoptionCommitStatus = AdoptionCommitStatus.PENDING
    steps: list[AdoptionCommitStep] = field(default_factory=list)
    result: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass(frozen=True)
class InvocationResult:
    """AIInvocationGateway.invoke 的返回结果。"""

    session: InvocationSession
    attempt: Optional[InvocationAttempt] = None
    decision: Optional[AdoptionDecision] = None
    commit: Optional[AdoptionCommit] = None
    prompt_snapshot: Optional[PromptSnapshot] = None
    variable_plan: Optional[VariablePlan] = None


def stable_hash(payload: Any) -> str:
    """对可序列化载荷生成稳定 sha256。"""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_hash(prompt: Prompt) -> str:
    return stable_hash({"system": prompt.system, "user": prompt.user})
