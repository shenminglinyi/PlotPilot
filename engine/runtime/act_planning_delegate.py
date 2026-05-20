"""幕级规划委托 — Phase 5 从 AutopilotDaemon 迁入 engine/runtime"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from domain.novel.entities.novel import Novel, NovelStage, AutopilotStatus
from domain.structure.story_node import StoryNode, NodeType, PlanningStatus, PlanningSource

logger = logging.getLogger(__name__)


async def run_act_planning(host: Any, novel: Novel) -> None:
    """处理幕级规划（插入缓冲章策略 + 动态幕生成）"""
    if not host._is_still_running(novel):
        return

    host._update_shared_state(
        novel.novel_id.value,
        writing_substep="act_planning",
        writing_substep_label=f"第 {novel.current_act + 1} 幕规划",
    )

    novel_id = novel.novel_id.value
    target_act_number = novel.current_act + 1

    from application.blueprint.services.continuous_planning_service import calculate_structure_params

    target_chapters = novel.target_chapters or 100
    struct_params = calculate_structure_params(target_chapters)
    rec_chapters_per_act = struct_params["chapters_per_act"]
    rec_acts_per_volume = struct_params["acts_per_volume"]

    all_nodes = await host.story_node_repo.get_by_novel(novel_id)
    act_nodes = sorted(
        [n for n in all_nodes if n.node_type.value == "act"],
        key=lambda n: n.number,
    )

    target_act = next((n for n in act_nodes if n.number == target_act_number), None)

    if not target_act:
        volume_nodes = sorted(
            [n for n in all_nodes if n.node_type.value == "volume"],
            key=lambda n: n.number,
        )

        if not volume_nodes:
            logger.error(
                "[%s] 宏观规划缺少卷节点！无法进行幕级规划。"
                "parts=%s, volumes=0, acts=%s. 触发重新规划...",
                novel_id,
                len([n for n in all_nodes if n.node_type.value == "part"]),
                len(act_nodes),
            )
            novel.current_stage = NovelStage.MACRO_PLANNING
            novel.current_act = 0
            host._flush_novel(novel)
            return

        parent_volume = host._find_parent_volume_for_new_act(
            volume_nodes=volume_nodes,
            act_nodes=act_nodes,
            current_auto_chapters=novel.current_auto_chapters or 0,
            target_chapters=target_chapters,
            rec_acts_per_volume=rec_acts_per_volume,
            novel_id=novel.novel_id,
        )

        if parent_volume:
            logger.info(
                "[%s] 动态生成第 %s 幕（父卷：第 %s 卷，每幕建议 %s 章）",
                novel.novel_id,
                target_act_number,
                parent_volume.number,
                rec_chapters_per_act,
            )
            try:
                last_act = act_nodes[-1] if act_nodes else None
                if last_act:
                    await host.planning_service.create_next_act_auto(
                        novel_id=novel_id,
                        current_act_id=last_act.id,
                    )
                else:
                    logger.info("[%s] 创建首幕", novel.novel_id)
                    first_act = StoryNode(
                        id=f"act-{novel_id}-1",
                        novel_id=novel_id,
                        parent_id=parent_volume.id,
                        node_type=NodeType.ACT,
                        number=1,
                        title="第一幕 · 开端",
                        description="故事起始，建立世界观与主角目标",
                        order_index=0,
                        planning_status=PlanningStatus.CONFIRMED,
                        planning_source=PlanningSource.AI_MACRO,
                        suggested_chapter_count=rec_chapters_per_act,
                    )
                    await host.story_node_repo.save(first_act)

                all_nodes = await host.story_node_repo.get_by_novel(novel_id)
                act_nodes = sorted(
                    [n for n in all_nodes if n.node_type.value == "act"],
                    key=lambda n: n.number,
                )
                target_act = next((n for n in act_nodes if n.number == target_act_number), None)
            except Exception as e:
                logger.warning("[%s] 动态幕生成失败: %s", novel.novel_id, e)

        if not target_act:
            logger.error(
                "[%s] 找不到第 %s 幕，且动态生成失败，回退到宏观规划",
                novel.novel_id,
                target_act_number,
            )
            novel.current_stage = NovelStage.MACRO_PLANNING
            novel.current_act = 0
            host._flush_novel(novel)
            return

    act_children = host.story_node_repo.get_children_sync(target_act.id)
    confirmed_chapters = [n for n in act_children if n.node_type.value == "chapter"]

    just_created_chapter_plan = False
    if not confirmed_chapters:
        chapter_budget = target_act.suggested_chapter_count or rec_chapters_per_act
        if not target_act.suggested_chapter_count:
            logger.info(
                "[%s] 幕 %s 无 suggested_chapter_count，使用引擎推荐值 %s",
                novel.novel_id,
                target_act_number,
                rec_chapters_per_act,
            )
        plan_result: Dict[str, Any] = {}
        try:
            plan_result = await host.planning_service.plan_act_chapters(
                act_id=target_act.id,
                custom_chapter_count=chapter_budget,
            )
        except Exception as e:
            logger.warning("[%s] plan_act_chapters 未捕获异常: %s", novel.novel_id, e, exc_info=True)
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

        await host.planning_service.confirm_act_planning(
            act_id=target_act.id,
            chapters=chapters_data,
        )
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
