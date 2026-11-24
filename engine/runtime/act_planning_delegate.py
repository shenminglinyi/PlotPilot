"""幕级规划委托 — Phase 5 从 AutopilotDaemon 迁入 engine/runtime"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping

from domain.novel.entities.novel import Novel, NovelStage, AutopilotStatus
from domain.structure.act_continuation import decide_act_continuation
from domain.structure.narrative_progress import NarrativeProgressError
from domain.structure.writing_target import plan_revision, select_writing_target
from domain.structure.story_node import StoryNode, NodeType, PlanningStatus, PlanningSource

logger = logging.getLogger(__name__)


def _read_shared_state(novel_id: str) -> dict[str, Any]:
    from application.ai_invocation.autopilot.shared_state import read_autopilot_shared_state

    return read_autopilot_shared_state(novel_id)


def _consume_pending_act_plan(host: Any, *, novel_id: str, act_id: str) -> dict[str, Any] | None:
    shared = _read_shared_state(novel_id)
    pending_act_id = str(shared.get("autopilot_pending_act_plan_id") or "")
    pending = shared.get("autopilot_pending_act_chapters")
    if pending_act_id != str(act_id) or not isinstance(pending, list):
        return None
    host._update_shared_state(
        novel_id,
        autopilot_pending_act_plan_id=None,
        autopilot_pending_act_chapters=None,
        autopilot_pending_act_revision=None,
        active_invocation_session_id="",
        active_invocation_operation="",
        active_invocation_node_key="",
        active_invocation_status="completed",
        active_invocation_policy="",
        has_active_invocation=False,
        requires_ai_review=False,
        autopilot_pause_reason="",
    )
    return {"success": True, "act_id": act_id, "chapters": list(pending),
            "plan_revision": shared.get("autopilot_pending_act_revision")}


def _write_act_variables(*, novel_id: str, act_id: str, context: str, chapter_count: int, node_key: str) -> None:
    from application.ai_invocation.variable_hub import VariableWrite
    from infrastructure.persistence.database.connection import get_database
    from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository

    repo = SqliteVariableHubRepository(get_database())
    context_key = f"novel_id:{novel_id}|act_id:{act_id}"
    for key, value, value_type in (
        ("novel.planning.act.context", context, "string"),
        ("novel.planning.act.chapter_count", int(chapter_count or 0), "integer"),
    ):
        repo.set_value(
            VariableWrite(
                key=key,
                value=value,
                context_key=context_key,
                source_node_key=node_key,
                source_trace_id=node_key,
                scope="novel",
                stage="planning",
                display_name=key,
                value_type=value_type,
            )
        )


def _pause_for_invocation(host: Any, novel: Novel, outcome) -> None:
    session = outcome.payload.get("session") if isinstance(outcome.payload, Mapping) else None
    policy_value = getattr(getattr(session, "policy", ""), "value", "") or "AUTOPILOT_PAUSE"
    host._update_shared_state(
        novel.novel_id.value,
        active_invocation_session_id=outcome.session_id,
        active_invocation_operation=outcome.operation,
        active_invocation_node_key=outcome.node_key,
        active_invocation_status=outcome.status,
        active_invocation_policy=policy_value,
        has_active_invocation=True,
        requires_ai_review=True,
        autopilot_pause_reason=outcome.autopilot_pause_reason or "awaiting_ai_review",
    )
    novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
    novel.autopilot_status = AutopilotStatus.RUNNING
    host._flush_novel(novel)


async def _request_act_invocation(
    host: Any,
    novel: Novel,
    *,
    target_act: StoryNode,
    chapter_budget: int,
    checked_revision: str,
) -> Any:
    from application.ai_invocation.autopilot.factory import get_or_create_autopilot_orchestrator
    from application.ai_invocation.autopilot.intents import AutopilotInvocationIntent
    from application.ai_invocation.autopilot.policy import AutopilotInvocationPolicyResolver
    from application.ai_invocation.contracts import ensure_invocation_contract
    from infrastructure.ai.generation_profiles import generation_config_from_profile
    from infrastructure.ai.prompt_keys import PLANNING_ACT
    from infrastructure.persistence.database.connection import get_database

    bible_context = host.planning_service._get_bible_context(novel.novel_id.value)
    from engine.runtime.narrative_progress_guard import progress_policy
    policy = await progress_policy(host, novel)
    if plan_revision(policy) != checked_revision:
        raise NarrativeProgressError("请求模型前大纲已变化，请重新规划")
    volume = next(v for v in policy.volumes if v.node.id == target_act.parent_id)
    bible_context = {**bible_context, 'target_volume': {
        'title': volume.node.title, 'description': volume.node.description or '',
        'narrative_progress': policy.contract(volume.node),
        'remaining_chapters': volume.remaining,
    }}
    previous_summary = await host.planning_service._get_previous_acts_summary(target_act)
    prompt = host.planning_service._build_act_planning_prompt(
        target_act,
        bible_context,
        previous_summary,
        int(chapter_budget or 0),
    )
    variables = {
        "context": prompt.user,
        "chapter_count": int(chapter_budget or 0),
    }
    ensure_invocation_contract("autopilot.act.plan", PLANNING_ACT, get_database())
    _write_act_variables(
        novel_id=novel.novel_id.value,
        act_id=target_act.id,
        context=prompt.user,
        chapter_count=int(chapter_budget or 0),
        node_key=PLANNING_ACT,
    )
    policy = AutopilotInvocationPolicyResolver().resolve(
        operation="autopilot.act.plan",
        node_key=PLANNING_ACT,
        novel=novel,
        context={"novel_id": novel.novel_id.value, "act_id": target_act.id},
    )
    config = generation_config_from_profile("planning_act")
    return await get_or_create_autopilot_orchestrator(host).request(
        AutopilotInvocationIntent(
            novel_id=novel.novel_id.value,
            stage="planning",
            operation="autopilot.act.plan",
            node_key=PLANNING_ACT,
            context={
                "novel_id": novel.novel_id.value,
                "act_id": target_act.id,
                "chapter_count": int(chapter_budget or 0),
                "plan_revision": checked_revision,
            },
            explicit_variables=variables,
            continuation_handler_key="autopilot_act_plan",
            policy_hint=policy,
            metadata={"source": "act_planning_delegate"},
            config=config,
        )
    )


async def run_act_planning(host: Any, novel: Novel) -> None:
    """处理幕级规划（插入缓冲章策略 + 动态幕生成）"""
    if not host._is_still_running(novel):
        return
    from engine.runtime.narrative_progress_guard import enforce_progress, progress_policy, pause_for_progress
    policy = await progress_policy(host, novel)
    if await enforce_progress(host, novel, policy=policy):
        return
    novel_id = novel.novel_id.value
    if not policy.volumes:
        novel.current_stage = NovelStage.MACRO_PLANNING
        novel.current_act = 0
        host._flush_novel(novel)
        return

    from application.blueprint.services.continuous_planning_service import calculate_structure_params
    recommended = calculate_structure_params(novel.target_chapters)["chapters_per_act"]
    try:
        pending = select_writing_target(policy)
        if pending:
            novel.current_act = policy.by_id[pending.act_id].number - 1
            novel.current_stage = NovelStage.WRITING
            host._flush_novel(novel)
            return
        acts = [n for n in policy.nodes if n.node_type == NodeType.ACT]
        last_chapter = max((n for n in policy.nodes if n.node_type == NodeType.CHAPTER and n.number in policy.written),
                           key=lambda n: n.number, default=None)
        previous = policy.by_id.get(last_chapter.parent_id) if last_chapter else None
        if previous:
            decision = decide_act_continuation(policy, previous.id, recommended)
            target_act_number = previous.number + 1
            rec_chapters_per_act = decision.chapter_budget
            target_act = policy.by_id.get(decision.existing_id)
            if target_act is None:
                await host.planning_service.create_next_act_auto(
                    novel_id=novel_id, current_act_id=previous.id, target_volume_id=decision.volume_id,
                    chapter_budget=decision.chapter_budget, expected_plan_revision=decision.plan_revision)
                refreshed = await progress_policy(host, novel)
                target_act = next((n for n in refreshed.nodes
                                   if n.node_type == NodeType.ACT and n.number == target_act_number
                                   and n.parent_id == decision.volume_id), None)
                if not target_act:
                    raise NarrativeProgressError("新幕尚未保存，请重新检查")
        else:
            target_act_number = 1
            destination = policy.next_volume(None)
            rec_chapters_per_act = min(recommended, destination.remaining)
            target_act = next((n for n in acts if n.number == target_act_number), None)
            if target_act and target_act.parent_id != destination.node.id:
                raise NarrativeProgressError("首幕不属于开篇卷，请先调整大纲")
            if target_act is None:
                target_act = StoryNode(
                    id=f"act-{novel_id}-1", novel_id=novel_id, parent_id=destination.node.id,
                    node_type=NodeType.ACT, number=1, title="第一幕 · 开端",
                    description="故事起始，建立世界观与主角目标", order_index=0,
                    planning_status=PlanningStatus.CONFIRMED, planning_source=PlanningSource.AI_MACRO,
                    suggested_chapter_count=rec_chapters_per_act)
                await host.story_node_repo.save(target_act)
    except NarrativeProgressError as exc:
        pause_for_progress(host, novel, str(exc))
        return

    host._update_shared_state(novel_id, writing_substep="act_planning",
                              writing_substep_label=f"第 {target_act_number} 幕规划")
    act_children = host.story_node_repo.get_children_sync(target_act.id)
    confirmed_chapters = [n for n in act_children if n.node_type.value == "chapter"]

    just_created_chapter_plan = False
    if not confirmed_chapters:
        chapter_budget = target_act.suggested_chapter_count or rec_chapters_per_act
        try:
            policy = await progress_policy(host, novel)
            volume = next(v for v in policy.volumes if v.node.id == target_act.parent_id)
            checked_revision = plan_revision(policy)
            chapter_budget = min(chapter_budget, volume.remaining,
                                 novel.target_chapters - len(policy.written))
            if chapter_budget <= 0:
                raise ValueError('本卷或全书篇幅预算已用尽，需要验收或重规划')
        except Exception as error:
            pause_for_progress(host, novel, str(error))
            return
        if not target_act.suggested_chapter_count:
            logger.info(
                "[%s] 幕 %s 无 suggested_chapter_count，使用引擎推荐值 %s",
                novel.novel_id,
                target_act_number,
                rec_chapters_per_act,
            )
        plan_result: Dict[str, Any] = _consume_pending_act_plan(
            host,
            novel_id=novel_id,
            act_id=target_act.id,
        ) or {}
        if not plan_result:
            shared_state = _read_shared_state(novel_id)
            if shared_state.get("active_invocation_session_id") and shared_state.get("has_active_invocation"):
                logger.info(
                    "[%s] 幕级规划已有待处理 invocation session=%s，等待面板处理",
                    novel.novel_id,
                    shared_state.get("active_invocation_session_id"),
                )
                novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
                novel.autopilot_status = AutopilotStatus.RUNNING
                host._flush_novel(novel)
                return
            try:
                outcome = await _request_act_invocation(
                    host,
                    novel,
                    target_act=target_act,
                    chapter_budget=chapter_budget,
                    checked_revision=checked_revision,
                )
                if outcome.status in {
                    "awaiting_pre_call_review",
                    "awaiting_acceptance",
                    "awaiting_commit",
                    "blocked",
                    "failed",
                    "cancelled",
                }:
                    _pause_for_invocation(host, novel, outcome)
                    return
                commit = outcome.payload.get("commit") if isinstance(outcome.payload, Mapping) else None
                commit_result = getattr(commit, "result", None) if commit is not None else None
                continuation = commit_result.get("continuation") if isinstance(commit_result, Mapping) else None
                plan_result = dict((continuation or {}).get("act_plan") or {})
            except NarrativeProgressError as exc:
                pause_for_progress(host, novel, str(exc))
                return
            except Exception as e:
                logger.warning("[%s] autopilot.act.plan 未捕获异常: %s", novel.novel_id, e, exc_info=True)
                plan_result = {}

        if not host._is_still_running(novel):
            logger.info("[%s] 幕级规划返回后检测到停止，不再落库", novel.novel_id)
            return

        raw = plan_result.get("chapters")
        chapters_data: List[Dict[str, Any]] = raw if isinstance(raw, list) else []
        if not chapters_data:
            logger.error("[%s] 幕 %s 规划失败：未得到有效章节规划", novel.novel_id, target_act_number)
            novel.consecutive_error_count = (novel.consecutive_error_count or 0) + 1
            if novel.consecutive_error_count >= 3:
                novel.autopilot_status = AutopilotStatus.ERROR
                logger.error("[%s] 连续失败达3次，已挂起", novel.novel_id)
            host._flush_novel(novel)
            return

        if (len(chapters_data) > chapter_budget or plan_result.get("plan_revision") != checked_revision
                or plan_revision(await progress_policy(host, novel)) != checked_revision):
            pause_for_progress(host, novel, "返回的章节规划超过预算，或生成期间大纲已变化，请重新检查")
            return
        try:
            await host.planning_service.confirm_act_planning(
                act_id=target_act.id, chapters=chapters_data, expected_revision=checked_revision)
        except NarrativeProgressError as exc:
            pause_for_progress(host, novel, str(exc))
            return
        just_created_chapter_plan = True

    act_children = host.story_node_repo.get_children_sync(target_act.id)
    confirmed_chapters = [n for n in act_children if n.node_type.value == "chapter"]

    novel.current_act = target_act_number - 1

    if not confirmed_chapters:
        logger.error("[%s] 幕 %s 仍无章节节点，下轮继续幕级规划", novel.novel_id, target_act_number)
        novel.current_stage = NovelStage.ACT_PLANNING
        return

    if just_created_chapter_plan:
        if getattr(novel, "auto_approve_mode", False):
            novel.current_stage = NovelStage.WRITING
            host._flush_novel(novel)
            logger.info("[%s] 全自动模式：第 %s 幕规划完成，直接进入写作", novel.novel_id, target_act_number)
        else:
            novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
            host._flush_novel(novel)
            logger.info("[%s] 第 %s 幕规划完成，进入审阅等待", novel.novel_id, target_act_number)
    else:
        novel.current_stage = NovelStage.WRITING
        host._flush_novel(novel)
        logger.info("[%s] 第 %s 幕章节节点已存在，进入写作", novel.novel_id, target_act_number)
