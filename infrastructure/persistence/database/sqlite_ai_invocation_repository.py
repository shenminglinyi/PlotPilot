"""SQLite repositories for the AI Invocation domain."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from application.ai_invocation.dtos import (
    AdoptionCommit,
    AdoptionCommitStatus,
    AdoptionCommitStep,
    ContinuationRef,
    AdoptionDecision,
    InvocationAttempt,
    InvocationAttemptStatus,
    InvocationPolicy,
    InvocationSession,
    InvocationSessionStatus,
    InvocationSpec,
    PromptSnapshot,
    VariableBinding,
    VariablePlan,
)
from application.ai_invocation.variable_hub import (
    VariableDefinition,
    VariableResolver,
    VariableValue,
    VariableWrite,
    expand_context_keys,
    sanitize_variable_value,
)
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_loads(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _infer_json_value_type(value: Any) -> str:
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


def _policy_value(policy: InvocationPolicy | str) -> str:
    return policy.value if isinstance(policy, InvocationPolicy) else str(policy)


def _status_value(status: InvocationSessionStatus | InvocationAttemptStatus | str) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _continuation_to_dict(ref: ContinuationRef | None) -> dict[str, Any]:
    if ref is None:
        return {}
    return {"handler_key": ref.handler_key, "payload": dict(ref.payload or {})}


def _continuation_from_dict(data: Mapping[str, Any]) -> ContinuationRef | None:
    handler_key = str(data.get("handler_key") or "")
    if not handler_key:
        return None
    payload = data.get("payload")
    return ContinuationRef(handler_key=handler_key, payload=payload if isinstance(payload, Mapping) else {})


def _binding_to_dict(binding: VariableBinding) -> dict[str, Any]:
    return {
        "alias": binding.alias,
        "variable_key": binding.variable_key,
        "required": binding.required,
        "default": binding.default,
        "source": binding.source,
        "enabled": binding.enabled,
        "value_type": binding.value_type,
        "scope": binding.scope,
        "stage": binding.stage,
        "display_name": binding.display_name,
        "source_path": binding.source_path,
        "projection_key": binding.projection_key,
        "render_mode": binding.render_mode,
    }


def _binding_from_dict(data: Mapping[str, Any]) -> VariableBinding:
    return VariableBinding(
        alias=str(data.get("alias") or ""),
        variable_key=str(data.get("variable_key") or ""),
        required=bool(data.get("required")),
        default=data.get("default"),
        source=str(data.get("source") or ""),
        enabled=bool(data.get("enabled", True)),
        value_type=str(data.get("value_type") or "string"),
        scope=str(data.get("scope") or "runtime"),
        stage=str(data.get("stage") or "runtime"),
        display_name=str(data.get("display_name") or ""),
        source_path=str(data.get("source_path") or ""),
        projection_key=str(data.get("projection_key") or ""),
        render_mode=str(data.get("render_mode") or "raw"),
    )


def prompt_snapshot_to_dict(snapshot: PromptSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {}
    return {
        "prompt": {"system": snapshot.prompt.system, "user": snapshot.prompt.user},
        "template_prompt": {
            "system": snapshot.template_prompt.system,
            "user": snapshot.template_prompt.user,
        } if snapshot.template_prompt is not None else {},
        "draft_prompt": {
            "system": snapshot.draft_prompt.system,
            "user": snapshot.draft_prompt.user,
        } if snapshot.draft_prompt is not None else {},
        "node_key": snapshot.node_key,
        "node_version_id": snapshot.node_version_id,
        "asset_link_set_id": snapshot.asset_link_set_id,
        "input_binding_set_id": snapshot.input_binding_set_id,
        "output_binding_set_id": snapshot.output_binding_set_id,
        "variable_snapshot_hash": snapshot.variable_snapshot_hash,
        "template_hash": snapshot.template_hash,
        "composition_hash": snapshot.composition_hash,
        "rendered_prompt_hash": snapshot.rendered_prompt_hash,
        "missing_variables": list(snapshot.missing_variables),
        "diagnostics": list(snapshot.diagnostics),
        "asset_version_ids": list(snapshot.asset_version_ids),
    }


def prompt_snapshot_from_dict(data: Mapping[str, Any]) -> PromptSnapshot | None:
    prompt_data = data.get("prompt")
    if not isinstance(prompt_data, Mapping):
        return None
    system = str(prompt_data.get("system") or "")
    user = str(prompt_data.get("user") or "")
    if not system or not user:
        return None
    template_prompt_data = data.get("template_prompt")
    template_prompt = None
    if isinstance(template_prompt_data, Mapping):
        template_system = str(template_prompt_data.get("system") or "")
        template_user = str(template_prompt_data.get("user") or "")
        if template_system and template_user:
            template_prompt = Prompt(system=template_system, user=template_user)
    draft_prompt_data = data.get("draft_prompt")
    draft_prompt = None
    if isinstance(draft_prompt_data, Mapping):
        draft_system = str(draft_prompt_data.get("system") or "")
        draft_user = str(draft_prompt_data.get("user") or "")
        if draft_system or draft_user:
            draft_prompt = Prompt(system=draft_system, user=draft_user)
    return PromptSnapshot(
        prompt=Prompt(system=system, user=user),
        node_key=str(data.get("node_key") or ""),
        node_version_id=str(data.get("node_version_id") or ""),
        asset_link_set_id=str(data.get("asset_link_set_id") or ""),
        input_binding_set_id=str(data.get("input_binding_set_id") or ""),
        output_binding_set_id=str(data.get("output_binding_set_id") or ""),
        variable_snapshot_hash=str(data.get("variable_snapshot_hash") or ""),
        template_hash=str(data.get("template_hash") or ""),
        composition_hash=str(data.get("composition_hash") or ""),
        rendered_prompt_hash=str(data.get("rendered_prompt_hash") or ""),
        missing_variables=tuple(data.get("missing_variables") or ()),
        diagnostics=tuple(data.get("diagnostics") or ()),
        asset_version_ids=tuple(data.get("asset_version_ids") or ()),
        template_prompt=template_prompt,
        draft_prompt=draft_prompt,
    )


def variable_plan_to_dict(plan: VariablePlan | None) -> dict[str, Any]:
    if plan is None:
        return {}
    return {
        "aliases": dict(plan.aliases),
        "bindings": [_binding_to_dict(item) for item in plan.bindings],
        "required_missing": list(plan.required_missing),
        "diagnostics": list(plan.diagnostics),
        "lineage": dict(plan.lineage),
        "snapshot_items": [dict(item) for item in plan.snapshot_items],
        "snapshot_groups": [dict(group) for group in plan.snapshot_groups],
        "snapshot_hash": plan.snapshot_hash,
    }


def variable_plan_from_dict(data: Mapping[str, Any]) -> VariablePlan | None:
    if not data:
        return None
    bindings = data.get("bindings") or []
    return VariablePlan(
        aliases=data.get("aliases") if isinstance(data.get("aliases"), Mapping) else {},
        bindings=tuple(_binding_from_dict(item) for item in bindings if isinstance(item, Mapping)),
        required_missing=tuple(data.get("required_missing") or ()),
        diagnostics=tuple(data.get("diagnostics") or ()),
        lineage=data.get("lineage") if isinstance(data.get("lineage"), Mapping) else {},
        snapshot_items=tuple(
            item for item in data.get("snapshot_items") or () if isinstance(item, Mapping)
        ),
        snapshot_groups=tuple(
            item for item in data.get("snapshot_groups") or () if isinstance(item, Mapping)
        ),
        snapshot_hash=str(data.get("snapshot_hash") or ""),
    )


def _token_usage_to_dict(token_usage: TokenUsage | None) -> dict[str, int]:
    if token_usage is None:
        return {}
    return {
        "input_tokens": token_usage.input_tokens,
        "output_tokens": token_usage.output_tokens,
        "total_tokens": token_usage.total_tokens,
    }


def _token_usage_from_dict(data: Mapping[str, Any]) -> TokenUsage | None:
    if not data:
        return None
    return TokenUsage(
        input_tokens=int(data.get("input_tokens") or 0),
        output_tokens=int(data.get("output_tokens") or 0),
    )


class SqliteInvocationSpecRepository:
    """SQLite repository for InvocationSpec."""

    def __init__(self, db):
        self._db = db

    def upsert(self, spec: InvocationSpec, *, spec_id: str | None = None, spec_version: int = 1, status: str = "published") -> str:
        row_id = spec_id or _new_id("spec")
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO invocation_specs (
                    id, operation, node_key, spec_version, prompt_node_version_id,
                    asset_link_set_id, input_binding_set_id, output_binding_set_id,
                    default_policy, risk_level, supports_stream, continuation_handler_key,
                    commit_policy_key, status, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(operation, node_key, spec_version) DO UPDATE SET
                    prompt_node_version_id=excluded.prompt_node_version_id,
                    asset_link_set_id=excluded.asset_link_set_id,
                    input_binding_set_id=excluded.input_binding_set_id,
                    output_binding_set_id=excluded.output_binding_set_id,
                    default_policy=excluded.default_policy,
                    risk_level=excluded.risk_level,
                    supports_stream=excluded.supports_stream,
                    continuation_handler_key=excluded.continuation_handler_key,
                    commit_policy_key=excluded.commit_policy_key,
                    status=excluded.status,
                    metadata_json=excluded.metadata_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    row_id,
                    spec.operation,
                    spec.node_key,
                    spec_version,
                    spec.prompt_node_version_id,
                    spec.asset_link_set_id,
                    spec.input_binding_set_id,
                    spec.output_binding_set_id,
                    _policy_value(spec.default_policy),
                    spec.risk_level,
                    1 if spec.supports_stream else 0,
                    spec.continuation_handler_key,
                    spec.commit_policy_key,
                    status,
                    _json_dumps(spec.metadata),
                ),
            )
        return row_id

    def get(self, operation: str, node_key: str) -> InvocationSpec | None:
        row = self._db.fetch_one(
            """
            SELECT * FROM invocation_specs
            WHERE operation = ? AND node_key = ? AND status = 'published'
            ORDER BY spec_version DESC
            LIMIT 1
            """,
            (operation, node_key),
        )
        if row is None:
            return None
        return InvocationSpec(
            operation=row["operation"],
            node_key=row["node_key"],
            prompt_node_version_id=row["prompt_node_version_id"] or "",
            asset_link_set_id=row["asset_link_set_id"] or "",
            input_binding_set_id=row["input_binding_set_id"] or "",
            output_binding_set_id=row["output_binding_set_id"] or "",
            default_policy=InvocationPolicy(row["default_policy"]),
            risk_level=row["risk_level"] or "low",
            supports_stream=bool(row["supports_stream"]),
            continuation_handler_key=row["continuation_handler_key"] or "",
            commit_policy_key=row["commit_policy_key"] or "",
            metadata=_json_loads(row["metadata_json"], {}),
        )


class SqliteInvocationSessionRepository:
    """SQLite repository for InvocationSession."""

    def __init__(self, db):
        self._db = db

    def save(self, session: InvocationSession) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO ai_invocation_sessions (
                    id, operation, node_key, policy, status, context_json,
                    continuation_json, metadata_json, prompt_snapshot_json,
                    variables_snapshot_json, attempts_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    policy=excluded.policy,
                    status=excluded.status,
                    context_json=excluded.context_json,
                    continuation_json=excluded.continuation_json,
                    metadata_json=excluded.metadata_json,
                    prompt_snapshot_json=excluded.prompt_snapshot_json,
                    variables_snapshot_json=excluded.variables_snapshot_json,
                    attempts_json=excluded.attempts_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    session.id,
                    session.operation,
                    session.node_key,
                    _policy_value(session.policy),
                    _status_value(session.status),
                    _json_dumps(session.context),
                    _json_dumps(_continuation_to_dict(session.continuation)),
                    _json_dumps(session.metadata),
                    _json_dumps(prompt_snapshot_to_dict(session.prompt_snapshot)),
                    _json_dumps(variable_plan_to_dict(session.variable_plan)),
                    _json_dumps(session.attempts),
                ),
            )

    def get(self, session_id: str) -> InvocationSession | None:
        row = self._db.fetch_one("SELECT * FROM ai_invocation_sessions WHERE id = ?", (session_id,))
        if row is None:
            return None
        return InvocationSession(
            id=row["id"],
            operation=row["operation"],
            node_key=row["node_key"],
            policy=InvocationPolicy(row["policy"]),
            status=InvocationSessionStatus(row["status"]),
            context=_json_loads(row["context_json"], {}),
            continuation=_continuation_from_dict(_json_loads(row["continuation_json"], {})),
            metadata=_json_loads(row["metadata_json"], {}),
            prompt_snapshot=prompt_snapshot_from_dict(_json_loads(row["prompt_snapshot_json"], {})),
            variable_plan=variable_plan_from_dict(_json_loads(row["variables_snapshot_json"], {})),
            attempts=list(_json_loads(row["attempts_json"], [])),
        )


class SqliteInvocationAttemptRepository:
    """SQLite repository for InvocationAttempt."""

    def __init__(self, db):
        self._db = db

    def save(self, attempt: InvocationAttempt) -> None:
        status = _status_value(attempt.status)
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO ai_invocation_attempts (
                    id, session_id, status, prompt_snapshot_json, content,
                    token_usage_json, error, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CASE WHEN ? IN ('succeeded', 'failed') THEN CURRENT_TIMESTAMP ELSE NULL END)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    prompt_snapshot_json=excluded.prompt_snapshot_json,
                    content=excluded.content,
                    token_usage_json=excluded.token_usage_json,
                    error=excluded.error,
                    finished_at=excluded.finished_at
                """,
                (
                    attempt.id,
                    attempt.session_id,
                    status,
                    _json_dumps(prompt_snapshot_to_dict(attempt.prompt_snapshot)),
                    attempt.content,
                    _json_dumps(_token_usage_to_dict(attempt.token_usage)),
                    attempt.error,
                    status,
                ),
            )

    def get(self, attempt_id: str) -> InvocationAttempt | None:
        row = self._db.fetch_one("SELECT * FROM ai_invocation_attempts WHERE id = ?", (attempt_id,))
        if row is None:
            return None
        snapshot = prompt_snapshot_from_dict(_json_loads(row["prompt_snapshot_json"], {}))
        if snapshot is None:
            raise ValueError(f"attempt has no prompt snapshot: {attempt_id}")
        return InvocationAttempt(
            id=row["id"],
            session_id=row["session_id"],
            status=InvocationAttemptStatus(row["status"]),
            prompt_snapshot=snapshot,
            content=row["content"] or "",
            token_usage=_token_usage_from_dict(_json_loads(row["token_usage_json"], {})),
            error=row["error"] or "",
        )


@dataclass(frozen=True)
class AdoptionDecisionRecord:
    id: str
    session_id: str
    attempt_id: str
    decision: str
    accepted_content: str


@dataclass(frozen=True)
class AdoptionCommitRecord:
    id: str
    session_id: str
    decision_id: str
    status: str
    idempotency_key: str



class SqliteAdoptionRepository:
    """SQLite repository for adoption decisions and commit steps."""

    def __init__(self, db):
        self._db = db

    def create_decision(
        self,
        *,
        session_id: str,
        attempt_id: str,
        accepted_content: str,
        decision: str = "accepted",
        accepted_by: str = "system",
        options: Mapping[str, Any] | None = None,
    ) -> AdoptionDecisionRecord:
        options = dict(options or {})
        decision_id = _new_id("decision")
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO ai_adoption_decisions (
                    id, session_id, attempt_id, decision, accept_content,
                    commit_prompt_version, commit_variable_outputs, commit_variable_bindings,
                    accepted_content, accepted_by, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    session_id,
                    attempt_id,
                    decision,
                    1 if options.get("accept_content", True) else 0,
                    1 if options.get("commit_prompt_version", False) else 0,
                    1 if options.get("commit_variable_outputs", False) else 0,
                    1 if options.get("commit_variable_bindings", False) else 0,
                    accepted_content,
                    accepted_by,
                    _json_dumps(options.get("metadata") or {}),
                ),
            )
        return AdoptionDecisionRecord(
            id=decision_id,
            session_id=session_id,
            attempt_id=attempt_id,
            decision=decision,
            accepted_content=accepted_content,
        )

    def save_decision(self, decision: AdoptionDecision) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO ai_adoption_decisions (
                    id, session_id, attempt_id, decision, accept_content,
                    commit_prompt_version, commit_variable_outputs, commit_variable_bindings,
                    accepted_content, accepted_by, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    decision=excluded.decision,
                    accept_content=excluded.accept_content,
                    commit_prompt_version=excluded.commit_prompt_version,
                    commit_variable_outputs=excluded.commit_variable_outputs,
                    commit_variable_bindings=excluded.commit_variable_bindings,
                    accepted_content=excluded.accepted_content,
                    accepted_by=excluded.accepted_by,
                    metadata_json=excluded.metadata_json
                """,
                (
                    decision.id,
                    decision.session_id,
                    decision.attempt_id,
                    decision.decision,
                    1 if decision.accept_content else 0,
                    1 if decision.commit_prompt_version else 0,
                    1 if decision.commit_variable_outputs else 0,
                    1 if decision.commit_variable_bindings else 0,
                    decision.accepted_content,
                    decision.accepted_by,
                    _json_dumps(decision.metadata),
                ),
            )

    def get_decision(self, decision_id: str) -> AdoptionDecision | None:
        row = self._db.fetch_one("SELECT * FROM ai_adoption_decisions WHERE id = ?", (decision_id,))
        if row is None:
            return None
        return AdoptionDecision(
            id=row["id"],
            session_id=row["session_id"],
            attempt_id=row["attempt_id"],
            decision=row["decision"],
            accept_content=bool(row["accept_content"]),
            commit_prompt_version=bool(row["commit_prompt_version"]),
            commit_variable_outputs=bool(row["commit_variable_outputs"]),
            commit_variable_bindings=bool(row["commit_variable_bindings"]),
            accepted_content=row["accepted_content"] or "",
            accepted_by=row["accepted_by"] or "system",
            metadata=_json_loads(row["metadata_json"], {}),
        )

    def get_latest_decision_for_session(self, session_id: str) -> AdoptionDecision | None:
        row = self._db.fetch_one(
            """
            SELECT *
            FROM ai_adoption_decisions
            WHERE session_id = ?
            ORDER BY accepted_at DESC
            LIMIT 1
            """,
            (session_id,),
        )
        if row is None:
            return None
        return AdoptionDecision(
            id=row["id"],
            session_id=row["session_id"],
            attempt_id=row["attempt_id"],
            decision=row["decision"],
            accept_content=bool(row["accept_content"]),
            commit_prompt_version=bool(row["commit_prompt_version"]),
            commit_variable_outputs=bool(row["commit_variable_outputs"]),
            commit_variable_bindings=bool(row["commit_variable_bindings"]),
            accepted_content=row["accepted_content"] or "",
            accepted_by=row["accepted_by"] or "system",
            metadata=_json_loads(row["metadata_json"], {}),
        )

    def get_latest_decision_for_attempt(self, session_id: str, attempt_id: str) -> AdoptionDecision | None:
        row = self._db.fetch_one(
            """
            SELECT *
            FROM ai_adoption_decisions
            WHERE session_id = ? AND attempt_id = ?
            ORDER BY accepted_at DESC
            LIMIT 1
            """,
            (session_id, attempt_id),
        )
        if row is None:
            return None
        return AdoptionDecision(
            id=row["id"],
            session_id=row["session_id"],
            attempt_id=row["attempt_id"],
            decision=row["decision"],
            accept_content=bool(row["accept_content"]),
            commit_prompt_version=bool(row["commit_prompt_version"]),
            commit_variable_outputs=bool(row["commit_variable_outputs"]),
            commit_variable_bindings=bool(row["commit_variable_bindings"]),
            accepted_content=row["accepted_content"] or "",
            accepted_by=row["accepted_by"] or "system",
            metadata=_json_loads(row["metadata_json"], {}),
        )

    def create_commit(self, *, session_id: str, decision_id: str) -> AdoptionCommitRecord:
        idempotency_key = f"{session_id}:{decision_id}"
        existing = self._db.fetch_one(
            "SELECT * FROM ai_adoption_commits WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        if existing is not None:
            return AdoptionCommitRecord(
                id=existing["id"],
                session_id=existing["session_id"],
                decision_id=existing["decision_id"],
                status=existing["status"],
                idempotency_key=existing["idempotency_key"],
            )
        commit_id = _new_id("commit")
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO ai_adoption_commits (
                    id, session_id, decision_id, status, idempotency_key
                ) VALUES (?, ?, ?, 'pending', ?)
                """,
                (commit_id, session_id, decision_id, idempotency_key),
            )
        return AdoptionCommitRecord(
            id=commit_id,
            session_id=session_id,
            decision_id=decision_id,
            status="pending",
            idempotency_key=idempotency_key,
        )

    def upsert_step(
        self,
        *,
        commit_id: str,
        step_name: str,
        status: str,
        result: Mapping[str, Any] | None = None,
        error: str = "",
    ) -> None:
        step_idempotency_key = f"{commit_id}:{step_name}"
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO ai_adoption_commit_steps (
                    id, commit_id, step_name, status, step_idempotency_key,
                    result_json, error, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP,
                    CASE WHEN ? IN ('succeeded', 'failed', 'blocked') THEN CURRENT_TIMESTAMP ELSE NULL END)
                ON CONFLICT(commit_id, step_name) DO UPDATE SET
                    status=excluded.status,
                    result_json=excluded.result_json,
                    error=excluded.error,
                    finished_at=excluded.finished_at
                """,
                (
                    _new_id("step"),
                    commit_id,
                    step_name,
                    status,
                    step_idempotency_key,
                    _json_dumps(result or {}),
                    error,
                    status,
                ),
            )

    def save_commit(self, commit: AdoptionCommit) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO ai_adoption_commits (
                    id, session_id, decision_id, status, idempotency_key,
                    result_json, error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    result_json=excluded.result_json,
                    error=excluded.error,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    commit.id,
                    commit.session_id,
                    commit.decision_id,
                    commit.status.value if hasattr(commit.status, "value") else str(commit.status),
                    f"{commit.session_id}:{commit.decision_id}",
                    _json_dumps(commit.result),
                    commit.error,
                ),
            )
        for step in commit.steps:
            self.upsert_step(
                commit_id=commit.id,
                step_name=step.name,
                status=step.status.value if hasattr(step.status, "value") else str(step.status),
                result=step.result,
                error=step.error,
            )

    def get_commit_for_decision(self, decision_id: str) -> AdoptionCommit | None:
        row = self._db.fetch_one(
            "SELECT * FROM ai_adoption_commits WHERE decision_id = ? ORDER BY created_at DESC LIMIT 1",
            (decision_id,),
        )
        if row is None:
            return None
        step_rows = self._db.fetch_all(
            """
            SELECT *
            FROM ai_adoption_commit_steps
            WHERE commit_id = ?
            ORDER BY started_at ASC
            """,
            (row["id"],),
        )
        return AdoptionCommit(
            id=row["id"],
            session_id=row["session_id"],
            decision_id=row["decision_id"],
            status=AdoptionCommitStatus(row["status"]),
            steps=[
                AdoptionCommitStep(
                    name=step["step_name"],
                    status=AdoptionCommitStatus(step["status"]),
                    result=_json_loads(step["result_json"], {}),
                    error=step["error"] or "",
                )
                for step in step_rows
            ],
            result=_json_loads(row["result_json"], {}),
            error=row["error"] or "",
        )


class SqliteVariableHubRepository:
    """SQLite repository for Variable Hub input bindings and current values."""

    def __init__(self, db):
        self._db = db

    def get_bindings(self, binding_set_id: str, node_key: str) -> list[VariableBinding]:
        return self._get_bindings(binding_set_id, node_key, direction="input")

    def get_output_bindings(self, binding_set_id: str, node_key: str) -> list[VariableBinding]:
        return self._get_bindings(binding_set_id, node_key, direction="output")

    def set_bindings(
        self,
        binding_set_id: str,
        node_key: str,
        bindings: list[VariableBinding],
        *,
        direction: str = "input",
    ) -> None:
        if not binding_set_id:
            return
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO cpms_variable_binding_sets (
                    id, node_key, direction, version_number, status, is_active, created_by
                ) VALUES (?, ?, ?, 1, 'published', 1, 'system')
                ON CONFLICT(node_key, direction, version_number) DO UPDATE SET
                    status='published',
                    is_active=1
                """,
                (binding_set_id, node_key, direction),
            )
            for binding in bindings:
                conn.execute(
                    """
                    INSERT INTO cpms_variable_bindings (
                        id, binding_set_id, node_key, direction, alias, variable_key, required,
                        default_value_json, source, enabled, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(binding_set_id, direction, alias) DO UPDATE SET
                        variable_key=excluded.variable_key,
                        required=excluded.required,
                        default_value_json=excluded.default_value_json,
                        source=excluded.source,
                        enabled=excluded.enabled,
                        metadata_json=excluded.metadata_json
                    """,
                    (
                        f"{binding_set_id}:{binding.alias}",
                        binding_set_id,
                        node_key,
                        direction,
                        binding.alias,
                        binding.variable_key,
                        1 if binding.required else 0,
                        _json_dumps(binding.default) if binding.default is not None else None,
                        binding.source or ("ai_invocation_output" if direction == "output" else "cpms_template"),
                        1 if binding.enabled else 0,
                        _json_dumps(
                            {
                                "display_name": binding.display_name,
                                "value_type": binding.value_type,
                                "scope": binding.scope,
                                "stage": binding.stage,
                                "source_path": binding.source_path,
                                "projection_key": binding.projection_key,
                                "render_mode": binding.render_mode,
                            }
                        ),
                    ),
                )

    def _get_bindings(self, binding_set_id: str, node_key: str, *, direction: str) -> list[VariableBinding]:
        if not binding_set_id:
            return []
        rows = self._db.fetch_all(
            """
            SELECT *
            FROM cpms_variable_bindings
            WHERE binding_set_id = ? AND node_key = ? AND direction = ?
            ORDER BY alias
            """,
            (binding_set_id, node_key, direction),
        )
        return [
            VariableBinding(
                alias=row["alias"],
                variable_key=row["variable_key"] or "",
                required=bool(row["required"]),
                default=_json_loads(row["default_value_json"], None),
                source=row["source"] or "",
                enabled=bool(row["enabled"]),
                value_type=str(_json_loads(row["metadata_json"], {}).get("value_type") or "string") if row["metadata_json"] else "string",
                scope=str(_json_loads(row["metadata_json"], {}).get("scope") or "runtime") if row["metadata_json"] else "runtime",
                stage=str(_json_loads(row["metadata_json"], {}).get("stage") or "runtime") if row["metadata_json"] else "runtime",
                display_name=str(_json_loads(row["metadata_json"], {}).get("display_name") or "") if row["metadata_json"] else "",
                source_path=str(_json_loads(row["metadata_json"], {}).get("source_path") or "") if row["metadata_json"] else "",
                projection_key=str(_json_loads(row["metadata_json"], {}).get("projection_key") or "") if row["metadata_json"] else "",
                render_mode=str(_json_loads(row["metadata_json"], {}).get("render_mode") or "raw") if row["metadata_json"] else "raw",
            )
            for row in rows
        ]

    def get_value(self, variable_key: str, context_key: str) -> VariableValue | None:
        scope_keys = expand_context_keys(context_key)
        for scope_key in scope_keys:
            row = self._db.fetch_one(
                """
                SELECT *
                FROM variable_values
                WHERE variable_key = ? AND scope_key = ? AND is_current = 1
                ORDER BY version_number DESC
                LIMIT 1
                """,
                (variable_key, scope_key),
            )
            if row is not None:
                return VariableValue(
                    key=row["variable_key"],
                    value=sanitize_variable_value(variable_key, _json_loads(row["value_json"], None)),
                    context_key=row["scope_key"] or "global",
                    source_ref=row["source_session_id"] or row["source_node_key"] or "",
                    version_number=int(row["version_number"] or 1),
                )
        return None

    def list_current_values(self, context_key: str) -> list[dict[str, Any]]:
        scope_keys = expand_context_keys(context_key)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for scope_key in scope_keys:
            rows = self._db.fetch_all(
                """
                SELECT vv.*, vd.display_name, vd.value_type, vd.scope_level AS definition_scope_level,
                       vd.metadata_json AS definition_metadata_json
                FROM variable_values vv
                LEFT JOIN variable_definitions vd ON vd.variable_key = vv.variable_key
                WHERE vv.scope_key = ? AND vv.is_current = 1
                ORDER BY vv.variable_key
                """,
                (scope_key,),
            )
            for row in rows:
                variable_key = row["variable_key"]
                if variable_key in seen:
                    continue
                seen.add(variable_key)
                metadata = _json_loads(row["definition_metadata_json"], {}) if row["definition_metadata_json"] else {}
                value_metadata = _json_loads(row["metadata_json"], {}) if row["metadata_json"] else {}
                value = sanitize_variable_value(variable_key, _json_loads(row["value_json"], None))
                stage = str(metadata.get("stage") or value_metadata.get("stage") or "")
                if not stage or stage == "runtime":
                    stage = VariableResolver._infer_stage(variable_key)
                out.append(
                    {
                        "variable_key": variable_key,
                        "display_name": row["display_name"] or variable_key,
                        "value": value,
                        "value_type": row["value_type"] or _infer_json_value_type(value),
                        "scope": row["definition_scope_level"] or row["scope_level"] or "global",
                        "stage": stage,
                        "source": "variable_hub",
                        "context_key": row["scope_key"] or "global",
                        "version_number": int(row["version_number"] or 1),
                    }
                )
        return out

    def get_definition(self, variable_key: str) -> VariableDefinition | None:
        row = self._db.fetch_one(
            "SELECT * FROM variable_definitions WHERE variable_key = ? AND status = 'active'",
            (variable_key,),
        )
        if row is None:
            return None
        return VariableDefinition(
            key=row["variable_key"],
            value_type=row["value_type"] or "string",
            required=bool(row["required"]),
            default=_json_loads(row["default_value_json"], None),
            description=row["description"] or "",
        )

    def set_value(self, value: VariableValue | VariableWrite) -> VariableValue | None:
        if isinstance(value, VariableValue):
            write = VariableWrite(
                key=value.key,
                value=value.value,
                context_key=value.context_key,
                source_trace_id=value.source_ref,
            )
        else:
            write = value
        scope_key = write.context_key or "global"
        scope_level = "novel" if scope_key != "global" else "global"
        clean_value = sanitize_variable_value(write.key, write.value)
        value_json = _json_dumps(clean_value)
        value_hash = _json_dumps({"value": clean_value})
        existing = self._db.fetch_one(
            """
            SELECT version_number
            FROM variable_values
            WHERE variable_key = ? AND scope_level = ? AND scope_key = ?
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (write.key, scope_level, scope_key),
        )
        version = int(existing["version_number"] or 0) + 1 if existing else 1
        value_id = _new_id("var_value")
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO variable_definitions (
                    id, variable_key, display_name, value_type, scope_level,
                    required, default_value_json, description, status, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, NULL, '', 'active', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(variable_key) DO UPDATE SET
                    display_name=CASE
                        WHEN excluded.display_name != '' THEN excluded.display_name
                        ELSE variable_definitions.display_name
                    END,
                    value_type=excluded.value_type,
                    scope_level=excluded.scope_level,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    _new_id("var_def"),
                    write.key,
                    write.display_name,
                    write.value_type or "string",
                    scope_level,
                    _json_dumps({"stage": write.stage, "source": "ai_invocation"}),
                ),
            )
            conn.execute(
                """
                UPDATE variable_values
                SET is_current = 0
                WHERE variable_key = ? AND scope_level = ? AND scope_key = ? AND is_current = 1
                """,
                (write.key, scope_level, scope_key),
            )
            conn.execute(
                """
                INSERT INTO variable_values (
                    id, variable_key, scope_level, scope_key, value_json, value_hash,
                    version_number, is_current, source_session_id, source_attempt_id,
                    source_trace_id, source_node_key, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    value_id,
                    write.key,
                    scope_level,
                    scope_key,
                    value_json,
                    value_hash,
                    version,
                    write.source_session_id,
                    write.source_attempt_id,
                    write.source_trace_id,
                    write.source_node_key,
                    _json_dumps({"source_commit_id": write.source_commit_id, "stage": write.stage}),
                ),
            )
            conn.execute(
                """
                INSERT INTO variable_lineage (
                    id, variable_value_id, source_session_id, source_attempt_id,
                    source_trace_id, source_node_key, source_commit_id, lineage_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id("var_lineage"),
                    value_id,
                    write.source_session_id,
                    write.source_attempt_id,
                    write.source_trace_id,
                    write.source_node_key,
                    write.source_commit_id,
                    _json_dumps(write.lineage),
                ),
            )
        return VariableValue(
            key=write.key,
            value=clean_value,
            context_key=scope_key,
            source_ref=write.source_session_id or write.source_node_key or write.source_trace_id,
            version_number=version,
        )
