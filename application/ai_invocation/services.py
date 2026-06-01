"""AI Invocation 会话与 attempt 服务。"""
from __future__ import annotations

import logging
import json
import uuid
from dataclasses import replace
from typing import Any, Mapping

from domain.ai.services.llm_service import GenerationConfig, LLMService
from application.ai_invocation.continuation import ContinuationContext, execute_continuation
from application.ai_invocation.dtos import (
    AdoptionCommit,
    AdoptionCommitStatus,
    AdoptionCommitStep,
    AdoptionDecision,
    InvocationAttempt,
    InvocationAttemptStatus,
    InvocationPolicy,
    InvocationSession,
    InvocationSessionStatus,
    PromptSnapshot,
    prompt_hash,
    stable_hash,
)
from domain.ai.value_objects.prompt import Prompt
from application.ai_invocation.variable_hub import VariableHubRepository, VariableWrite

logger = logging.getLogger(__name__)


class InvocationSessionService:
    """管理 invocation session 的最小服务。"""

    def __init__(self):
        self._sessions: dict[str, InvocationSession] = {}

    def create(
        self,
        *,
        operation: str,
        node_key: str,
        policy: InvocationPolicy,
        context,
        continuation=None,
        metadata=None,
    ) -> InvocationSession:
        session = InvocationSession(
            id=str(uuid.uuid4()),
            operation=operation,
            node_key=node_key,
            policy=policy,
            context=dict(context or {}),
            continuation=continuation,
            metadata=dict(metadata or {}),
        )
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> InvocationSession:
        return self._sessions[session_id]

    def update_status(self, session: InvocationSession, status: InvocationSessionStatus) -> None:
        session.status = status

    def attach_prompt(self, session: InvocationSession, snapshot: PromptSnapshot, variable_plan) -> None:
        session.prompt_snapshot = snapshot
        session.variable_plan = variable_plan
        session.status = InvocationSessionStatus.PROMPT_COMPILED


class AttemptService:
    """创建 attempt 并统一调用 LLMService。"""

    def __init__(self, llm_service: LLMService):
        self._llm_service = llm_service
        self._attempts: dict[str, InvocationAttempt] = {}

    async def generate(
        self,
        *,
        session: InvocationSession,
        prompt_snapshot: PromptSnapshot,
        config: GenerationConfig | None = None,
    ) -> InvocationAttempt:
        attempt = InvocationAttempt(
            id=str(uuid.uuid4()),
            session_id=session.id,
            status=InvocationAttemptStatus.RUNNING,
            prompt_snapshot=prompt_snapshot,
        )
        self._attempts[attempt.id] = attempt
        session.attempts.append(attempt.id)
        session.status = InvocationSessionStatus.GENERATING
        try:
            result = await self._llm_service.generate(prompt_snapshot.prompt, config or GenerationConfig())
            attempt.content = result.content
            attempt.token_usage = result.token_usage
            attempt.status = InvocationAttemptStatus.SUCCEEDED
            return attempt
        except Exception as exc:
            attempt.status = InvocationAttemptStatus.FAILED
            attempt.error = str(exc)
            session.status = InvocationSessionStatus.FAILED
            raise

    def get(self, attempt_id: str) -> InvocationAttempt:
        return self._attempts[attempt_id]


class AdoptionService:
    """形成采纳或拒绝决策，不执行提交副作用。"""

    def __init__(self):
        self._decisions: dict[str, AdoptionDecision] = {}

    def accept(
        self,
        *,
        session: InvocationSession,
        attempt: InvocationAttempt,
        accepted_by: str = "system",
        commit_prompt_version: bool = False,
        commit_variable_outputs: bool = False,
        commit_variable_bindings: bool = False,
        metadata: dict | None = None,
    ) -> AdoptionDecision:
        if attempt.session_id != session.id:
            raise ValueError("attempt 不属于当前 invocation session")
        if attempt.status != InvocationAttemptStatus.SUCCEEDED:
            raise ValueError("只有成功的 attempt 可以被采纳")
        decision = AdoptionDecision(
            id=str(uuid.uuid4()),
            session_id=session.id,
            attempt_id=attempt.id,
            accept_content=True,
            commit_prompt_version=commit_prompt_version,
            commit_variable_outputs=commit_variable_outputs,
            commit_variable_bindings=commit_variable_bindings,
            accepted_content=attempt.content,
            accepted_by=accepted_by,
            metadata=dict(metadata or {}),
        )
        self._decisions[decision.id] = decision
        session.status = InvocationSessionStatus.AWAITING_COMMIT
        return decision

    def reject(self, *, session: InvocationSession, attempt: InvocationAttempt, accepted_by: str = "system") -> AdoptionDecision:
        if attempt.session_id != session.id:
            raise ValueError("attempt 不属于当前 invocation session")
        decision = AdoptionDecision(
            id=str(uuid.uuid4()),
            session_id=session.id,
            attempt_id=attempt.id,
            decision="rejected",
            accept_content=False,
            accepted_content="",
            accepted_by=accepted_by,
        )
        self._decisions[decision.id] = decision
        session.status = InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW
        return decision

    def get(self, decision_id: str) -> AdoptionDecision:
        return self._decisions[decision_id]


class AdoptionCommitService:
    """幂等提交采纳结果。

    当前只实现最小内容提交步骤；CPMS 版本、变量绑定、变量输出和 continuation
    后续通过独立 step 扩展，不能再绕回 Gateway 或业务层硬编码。
    """

    def __init__(self, prompt_manager=None, variable_hub_repository: VariableHubRepository | None = None):
        self._commits_by_key: dict[str, AdoptionCommit] = {}
        self._prompt_manager = prompt_manager
        self._variable_hub_repository = variable_hub_repository

    def _get_prompt_manager(self):
        if self._prompt_manager is None:
            from infrastructure.ai.prompt_manager import get_prompt_manager

            self._prompt_manager = get_prompt_manager()
        return self._prompt_manager

    def _get_variable_hub_repository(self):
        if self._variable_hub_repository is None:
            try:
                from infrastructure.persistence.database.connection import get_database
                from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository

                self._variable_hub_repository = SqliteVariableHubRepository(get_database())
            except Exception:
                self._variable_hub_repository = None
        return self._variable_hub_repository

    def _commit_prompt_version(self, *, session: InvocationSession, decision: AdoptionDecision) -> dict:
        snapshot = session.prompt_snapshot
        if snapshot is None:
            return {"skipped": True, "reason": "missing_prompt_snapshot"}
        if snapshot.draft_prompt is None:
            return {"skipped": True, "reason": "missing_draft_prompt"}
        if snapshot.template_prompt is not None and snapshot.draft_prompt == snapshot.template_prompt:
            return {"skipped": True, "reason": "draft_unchanged"}

        mgr = self._get_prompt_manager()
        mgr.ensure_seeded()
        node = mgr.get_node(snapshot.node_key or session.node_key, by_key=True)
        if node is None:
            raise ValueError(f"CPMS 节点不存在，无法写回提示词版本: {snapshot.node_key or session.node_key}")

        previous_version_id = node.active_version_id or ""
        updated = mgr.update_node(
            node.id,
            system_prompt=snapshot.draft_prompt.system,
            user_template=snapshot.draft_prompt.user,
            change_summary=f"AI Invocation 采纳写回: {session.operation}",
        )
        if updated is None:
            raise ValueError(f"CPMS 节点更新失败: {snapshot.node_key or session.node_key}")

        updated_system = (
            getattr(updated, "get_active_system", lambda: "")()
            or snapshot.draft_prompt.system
        )
        updated_user = (
            getattr(updated, "get_active_user_template", lambda: "")()
            or snapshot.draft_prompt.user
        )
        refreshed_template = Prompt(system=updated_system, user=updated_user)
        rendered_prompt = refreshed_template
        if session.variable_plan is not None:
            from infrastructure.ai.prompt_template_engine import get_template_engine

            render_result = get_template_engine().render(
                system_template=updated_system,
                user_template=updated_user,
                variables=dict(session.variable_plan.aliases or {}),
            )
            rendered_prompt = Prompt(
                system=render_result.system or "",
                user=render_result.user or "",
            )

        session.prompt_snapshot = replace(
            snapshot,
            prompt=rendered_prompt,
            template_prompt=refreshed_template,
            draft_prompt=refreshed_template,
            template_hash=stable_hash(
                {
                    "system_template": refreshed_template.system,
                    "user_template": refreshed_template.user,
                }
            ),
            rendered_prompt_hash=prompt_hash(rendered_prompt),
        )
        logger.info(
            "refreshed invocation prompt snapshot after cpms commit: session=%s node=%s version=%s",
            session.id,
            updated.node_key,
            updated.active_version_id,
        )

        return {
            "skipped": False,
            "node_key": updated.node_key,
            "node_id": updated.id,
            "previous_version_id": previous_version_id,
            "active_version_id": updated.active_version_id,
            "template_hash": stable_hash(
                {
                    "system_template": snapshot.draft_prompt.system,
                    "user_template": snapshot.draft_prompt.user,
                }
            ),
            "accepted_by": decision.accepted_by,
        }

    def _materialize_output_value(self, alias: str, value: Any) -> Any:
        if isinstance(value, Mapping) and alias in value and len(value) == 1:
            return value[alias]
        return value

    def _commit_variable_outputs(
        self,
        *,
        session: InvocationSession,
        decision: AdoptionDecision,
        commit_id: str,
        output_payload: Mapping[str, Any] | None = None,
    ) -> dict:
        snapshot = session.prompt_snapshot
        if snapshot is None:
            return {"skipped": True, "reason": "missing_prompt_snapshot"}
        repo = self._get_variable_hub_repository()
        if repo is None:
            return {"skipped": True, "reason": "missing_variable_hub_repository"}

        bindings = []
        if snapshot.output_binding_set_id:
            try:
                bindings = repo.get_output_bindings(snapshot.output_binding_set_id, snapshot.node_key)
            except Exception as exc:
                return {"skipped": True, "reason": "output_bindings_unavailable", "error": str(exc)}

        if not bindings:
            return {"skipped": True, "reason": "no_output_bindings"}

        payload = dict(output_payload or {})
        if not payload:
            try:
                parsed = json.loads(decision.accepted_content)
            except Exception:
                parsed = {}
            payload = dict(parsed) if isinstance(parsed, Mapping) else {}

        written: list[dict[str, Any]] = []
        for binding in bindings:
            if not binding.enabled or not binding.variable_key:
                continue
            raw_value = payload.get(binding.alias)
            if raw_value is None:
                continue
            write = VariableWrite(
                key=binding.variable_key,
                value=self._materialize_output_value(binding.alias, raw_value),
                context_key=self._context_key(session.context),
                source_session_id=session.id,
                source_attempt_id=decision.attempt_id,
                source_trace_id=str(session.metadata.get("trace_id") or session.id),
                source_node_key=session.node_key,
                source_commit_id=commit_id,
                lineage={
                    "alias": binding.alias,
                    "binding_set_id": snapshot.output_binding_set_id,
                    "operation": session.operation,
                },
                value_type=binding.value_type,
                display_name=binding.display_name,
                scope=binding.scope,
                stage=binding.stage,
            )
            stored = repo.set_value(write)
            written.append(
                {
                    "alias": binding.alias,
                    "variable_key": binding.variable_key,
                    "context_key": write.context_key,
                    "version_number": getattr(stored, "version_number", 1),
                }
            )
        if not written:
            return {"skipped": True, "reason": "no_matching_output_values"}
        return {
            "skipped": False,
            "written": written,
            "binding_set_id": snapshot.output_binding_set_id,
        }

    @staticmethod
    def _context_key(context: Mapping[str, Any]) -> str:
        novel_id = str(context.get("novel_id") or "").strip()
        if novel_id:
            return f"novel_id:{novel_id}"
        return "global"

    def commit(self, *, session: InvocationSession, decision: AdoptionDecision) -> AdoptionCommit:
        if decision.session_id != session.id:
            raise ValueError("decision 不属于当前 invocation session")
        key = f"{session.id}:{decision.id}"
        existing = self._commits_by_key.get(key)
        if existing is not None:
            return existing
        if decision.decision != "accepted" or not decision.accept_content:
            session.status = InvocationSessionStatus.CANCELLED
            commit = AdoptionCommit(
                id=str(uuid.uuid4()),
                session_id=session.id,
                decision_id=decision.id,
                status=AdoptionCommitStatus.SUCCEEDED,
                steps=[
                    AdoptionCommitStep(
                        name="commit_content_patch",
                        status=AdoptionCommitStatus.SUCCEEDED,
                        result={"skipped": True, "reason": "decision_not_accepted"},
                    )
                ],
            )
            self._commits_by_key[key] = commit
            return commit

        session.status = InvocationSessionStatus.COMMITTING
        commit = AdoptionCommit(
            id=str(uuid.uuid4()),
            session_id=session.id,
            decision_id=decision.id,
            status=AdoptionCommitStatus.RUNNING,
        )
        try:
            commit.steps.append(
                AdoptionCommitStep(
                    name="commit_content_patch",
                    status=AdoptionCommitStatus.SUCCEEDED,
                    result={
                        "content_hash": stable_hash({"content": decision.accepted_content}),
                        "content_length": len(decision.accepted_content),
                    },
                )
            )
            prompt_version_result = self._commit_prompt_version(session=session, decision=decision)
            commit.steps.append(
                AdoptionCommitStep(
                    name="commit_prompt_version",
                    status=AdoptionCommitStatus.SUCCEEDED,
                    result=prompt_version_result,
                )
            )
            if not prompt_version_result.get("skipped"):
                commit.result = {**commit.result, "prompt_version": prompt_version_result}
            continuation_result = execute_continuation(ContinuationContext(session=session, decision=decision))
            if continuation_result:
                commit.steps.append(
                    AdoptionCommitStep(
                        name="continuation_handler",
                        status=AdoptionCommitStatus.SUCCEEDED,
                        result=continuation_result,
                    )
                )
                commit.result = {**commit.result, "continuation": continuation_result}
            variable_output_result = self._commit_variable_outputs(
                session=session,
                decision=decision,
                commit_id=commit.id,
                output_payload=continuation_result,
            )
            commit.steps.append(
                AdoptionCommitStep(
                    name="commit_variable_outputs",
                    status=AdoptionCommitStatus.SUCCEEDED,
                    result=variable_output_result,
                )
            )
            if not variable_output_result.get("skipped"):
                commit.result = {**commit.result, "variable_outputs": variable_output_result}
            commit.status = AdoptionCommitStatus.SUCCEEDED
            commit.result = {**commit.result, "accepted_content": decision.accepted_content}
            session.status = InvocationSessionStatus.COMPLETED
        except Exception as exc:
            commit.status = AdoptionCommitStatus.FAILED
            commit.error = str(exc)
            session.status = InvocationSessionStatus.FAILED
            raise
        finally:
            self._commits_by_key[key] = commit
        return commit
