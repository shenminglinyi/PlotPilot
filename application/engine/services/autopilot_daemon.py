"""自动驾驶守护进程 v2 - 全托管写作引擎（事务最小化 + 节拍幂等）

核心设计：
1. 死循环轮询数据库，捞出所有 autopilot_status=RUNNING 的小说
2. 根据 current_stage 执行对应的状态机逻辑
3. 事务最小化：DB 写操作只在读状态和更新状态两个瞬间，LLM 请求期间不持有锁
4. 节拍级幂等：每写完一个节拍立刻落库，断点续写从 current_beat_index 恢复
5. 熔断保护：连续失败 3 次挂起单本小说，全局熔断器防止 API 雪崩
"""
import time
import logging
import asyncio
import sqlite3
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from domain.novel.entities.novel import Novel, NovelStage, AutopilotStatus
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.repositories.novel_repository import NovelRepository
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from application.engine.services.context_builder import ContextBuilder
from application.engine.services.background_task_service import BackgroundTaskService, TaskType
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
from application.engine.services.style_constraint_builder import build_style_summary
from application.engine.services.word_control_service import effective_length
from application.config import AppConfig
from domain.novel.value_objects.chapter_id import ChapterId

logger = logging.getLogger(__name__)

VOICE_REWRITE_MAX_ATTEMPTS = 2
VOICE_REWRITE_THRESHOLD = 0.68
VOICE_WARNING_THRESHOLD_FALLBACK = 0.75


class AutopilotDaemon:
    """自动驾驶守护进程（v2 完整实现）"""

    def __init__(
        self,
        novel_repository,
        llm_service,
        context_builder,
        background_task_service,
        planning_service,
        story_node_repo,
        chapter_repository,
        poll_interval: int = 5,
        voice_drift_service=None,
        circuit_breaker=None,
        chapter_workflow: Optional[AutoNovelGenerationWorkflow] = None,
        aftermath_pipeline: Optional[ChapterAftermathPipeline] = None,
        volume_summary_service=None,
        foreshadowing_repository=None,
        chapter_generation_metrics_repository=None,
    ):
        self.novel_repository = novel_repository
        self.llm_service = llm_service
        self.context_builder = context_builder
        self.background_task_service = background_task_service
        self.planning_service = planning_service
        self.story_node_repo = story_node_repo
        self.chapter_repository = chapter_repository
        self.poll_interval = poll_interval
        self.voice_drift_service = voice_drift_service
        self.circuit_breaker = circuit_breaker
        self.chapter_workflow = chapter_workflow
        self.aftermath_pipeline = aftermath_pipeline
        self.volume_summary_service = volume_summary_service
        self.foreshadowing_repository = foreshadowing_repository
        self.theme_agent = None  # ThemeAgent 插槽，由外部注入
        self.chapter_generation_metrics_repository = chapter_generation_metrics_repository
        
        # 惰性初始化 VolumeSummaryService
        if not self.volume_summary_service and llm_service and story_node_repo:
            from application.blueprint.services.volume_summary_service import VolumeSummaryService
            self.volume_summary_service = VolumeSummaryService(
                llm_service=llm_service,
                story_node_repository=story_node_repo,
                chapter_repository=chapter_repository,
                foreshadowing_repository=foreshadowing_repository,
            )

    def run_forever(self):
        """守护进程主循环（事务最小化原则）"""
        logger.info("=" * 80)
        logger.info("🚀 Autopilot Daemon Started")
        logger.info(f"   Poll Interval: {self.poll_interval}s")
        logger.info(f"   Circuit Breaker: {'Enabled' if self.circuit_breaker else 'Disabled'}")
        logger.info(f"   Voice Drift Service: {'Enabled' if self.voice_drift_service else 'Disabled'}")
        logger.info(f"   Volume Summary Service: {'Enabled' if self.volume_summary_service else 'Disabled'}")
        logger.info("=" * 80)

        loop_count = 0
        while True:
            loop_count += 1
            loop_start = time.time()

            # 熔断器检查
            if self.circuit_breaker and self.circuit_breaker.is_open():
                wait = self.circuit_breaker.wait_seconds()
                logger.warning(f"⚠️  熔断器打开，暂停 {wait:.0f}s")
                time.sleep(min(wait, self.poll_interval))
                continue

            try:
                active_novels = self._get_active_novels()  # 快速只读查询

                if loop_count % 10 == 1:  # 每10轮（约50秒）记录一次状态
                    logger.info(f"🔄 Loop #{loop_count}: 发现 {len(active_novels)} 本活跃小说")

                if active_novels:
                    for novel in active_novels:
                        novel_start = time.time()
                        asyncio.run(self._process_novel(novel))
                        novel_elapsed = time.time() - novel_start
                        logger.debug(f"   [{novel.novel_id}] 处理耗时: {novel_elapsed:.2f}s")

            except Exception as e:
                logger.error(f"❌ Daemon 顶层异常: {e}", exc_info=True)

            loop_elapsed = time.time() - loop_start
            if loop_elapsed > self.poll_interval * 2:
                logger.warning(f"⏱️  Loop #{loop_count} 耗时过长: {loop_elapsed:.2f}s")

            time.sleep(self.poll_interval)

    def _get_active_novels(self) -> List[Novel]:
        """获取所有活跃小说（快速只读）"""
        return self.novel_repository.find_by_autopilot_status(AutopilotStatus.RUNNING.value)

    def _read_autopilot_status_ephemeral(self, novel_id: NovelId) -> Optional[AutopilotStatus]:
        """用独立 SQLite 连接读 autopilot_status。

        主仓储连接在 asyncio 与 asyncio.to_thread、或后台线程里并发用时，同一 sqlite3 连接
        跨线程未定义行为，且长连接可能看不到他处已提交的 STOPPED。短连接每次打开可读 WAL 最新提交。
        """
        from application.paths import get_db_path

        path = get_db_path()
        conn = sqlite3.connect(path, timeout=10.0)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT autopilot_status FROM novels WHERE id = ?",
                (novel_id.value,),
            )
            row = cur.fetchone()
            if not row:
                return None
            raw = row["autopilot_status"]
            try:
                return AutopilotStatus(raw)
            except ValueError:
                return AutopilotStatus.STOPPED
        finally:
            conn.close()

    def _merge_autopilot_status_from_db(self, novel: Novel) -> None:
        """用户点「停止」只改 DB；写库前必须合并，否则会覆盖 STOPPED。"""
        status = self._read_autopilot_status_ephemeral(novel.novel_id)
        if status is not None:
            novel.autopilot_status = status

    def _is_still_running(self, novel: Novel) -> bool:
        """从 DB 同步自动驾驶状态；非 RUNNING 时应立即结束本段处理。"""
        self._merge_autopilot_status_from_db(novel)
        return novel.autopilot_status == AutopilotStatus.RUNNING

    def _novel_is_running_in_db(self, novel_id: NovelId) -> bool:
        """流式轮询用：不修改内存 novel；独立连接读是否仍为 RUNNING。"""
        status = self._read_autopilot_status_ephemeral(novel_id)
        return status == AutopilotStatus.RUNNING

    def _flush_novel(self, novel: Novel) -> None:
        """关键阶段立即写库，避免下一轮轮询仍读到旧 stage（重复幕级规划 / 重复日志）。"""
        self._merge_autopilot_status_from_db(novel)
        self.novel_repository.save(novel)

    def _save_novel_state(self, novel: Novel) -> None:
        """与 _flush_novel 相同语义：任意 save 前合并停止标志。"""
        self._merge_autopilot_status_from_db(novel)
        self.novel_repository.save(novel)

    def _load_theme_agent_for_novel(self, novel: Novel) -> None:
        """根据 novel.genre 动态加载题材 Agent 到管线各组件

        每轮 _process_novel 调用一次，确保 genre 变更能实时生效。
        如果 genre 为空或无对应 Agent，则清除已有的 theme_agent（退化为通用模式）。
        仅在 novel.theme_agent_enabled 为 True 时才加载，否则走原有通用路线。

        同时根据 novel.enabled_theme_skills 列表，为 Agent 注入用户选择的增强技能。
        """
        genre = getattr(novel, 'genre', '') or ''
        enabled = getattr(novel, 'theme_agent_enabled', False)
        agent = None

        if enabled and genre and self._theme_registry:
            agent = self._theme_registry.get(genre)
            if agent:
                logger.debug(f"[{novel.novel_id}] 已加载题材 Agent：{agent}")
                # 加载用户启用的增强技能
                self._inject_skills_to_agent(agent, novel)
            else:
                logger.debug(f"[{novel.novel_id}] 未找到 genre='{genre}' 对应的题材 Agent，走通用路线")
        elif not enabled and genre:
            logger.debug(f"[{novel.novel_id}] 专项题材 Agent 未启用（genre='{genre}'），走通用路线")

        # 注入到管线各组件（幂等设置，无 agent 时清 None）
        self.theme_agent = agent
        if self.chapter_workflow:
            self.chapter_workflow.theme_agent = agent
        if self.context_builder:
            self.context_builder.theme_agent = agent
            if hasattr(self.context_builder, 'budget_allocator') and self.context_builder.budget_allocator:
                self.context_builder.budget_allocator.theme_agent = agent

    def _inject_skills_to_agent(self, agent, novel: Novel) -> None:
        """根据 novel.enabled_theme_skills 将技能注入 Agent

        通过覆盖 agent 的 _injected_skills 属性实现动态技能加载，
        并 monkey-patch get_skills() 方法使其返回注入的技能列表。
        同时加载用户自定义技能（custom_theme_skills 表）。
        """
        skill_keys = getattr(novel, 'enabled_theme_skills', []) or []
        if not skill_keys:
            # 无技能配置时，清除之前可能注入的技能
            if hasattr(agent, '_injected_skills'):
                delattr(agent, '_injected_skills')
                # 恢复原始 get_skills
                if hasattr(agent, '_original_get_skills'):
                    agent.get_skills = agent._original_get_skills
                    delattr(agent, '_original_get_skills')
            return

        try:
            skills = []

            # 1. 从内置 SkillRegistry 加载
            skill_registry = self._skill_registry
            if skill_registry:
                builtin_keys = [k for k in skill_keys if not k.startswith("custom_")]
                skills.extend(skill_registry.get_skills_by_keys(builtin_keys))

            # 2. 从 DB 加载自定义技能
            custom_keys = [k for k in skill_keys if k.startswith("custom_")]
            if custom_keys:
                try:
                    from infrastructure.persistence.database.sqlite_custom_skill_repository import SqliteCustomSkillRepository
                    from application.engine.theme.skills.custom_skill_wrapper import CustomThemeSkillWrapper
                    custom_repo = SqliteCustomSkillRepository(self.novel_repository.db)
                    novel_id = novel.novel_id.value if hasattr(novel.novel_id, 'value') else str(novel.novel_id)
                    custom_rows = custom_repo.list_by_novel(novel_id)
                    for row in custom_rows:
                        if row["skill_key"] in custom_keys:
                            skills.append(CustomThemeSkillWrapper(row))
                except Exception as e:
                    logger.warning(f"[{novel.novel_id}] 加载自定义技能失败：{e}")

            if skills:
                agent._injected_skills = skills
                # 保存原始 get_skills 并 monkey-patch
                if not hasattr(agent, '_original_get_skills'):
                    agent._original_get_skills = agent.get_skills
                agent.get_skills = lambda: agent._injected_skills
                logger.debug(
                    f"[{novel.novel_id}] 已注入 {len(skills)} 个增强技能: "
                    f"{[s.skill_key for s in skills]}"
                )
        except Exception as e:
            logger.warning(f"[{novel.novel_id}] 加载增强技能失败：{e}")

    @property
    def _theme_registry(self):
        """惰性获取 ThemeAgentRegistry（首次调用时初始化）"""
        if not hasattr(self, '_registry_instance'):
            try:
                from application.engine.theme.theme_registry import ThemeAgentRegistry
                registry = ThemeAgentRegistry()
                registry.auto_discover()
                self._registry_instance = registry
                logger.info(f"ThemeAgentRegistry 初始化完成：{registry}")
            except Exception as e:
                logger.warning(f"ThemeAgentRegistry 初始化失败（题材功能不可用）：{e}")
                self._registry_instance = None
        return self._registry_instance

    @property
    def _skill_registry(self):
        """惰性获取 ThemeSkillRegistry（首次调用时初始化）"""
        if not hasattr(self, '_skill_registry_instance'):
            try:
                from application.engine.theme.skill_registry import ThemeSkillRegistry
                registry = ThemeSkillRegistry()
                registry.auto_discover()
                self._skill_registry_instance = registry
                logger.info(f"ThemeSkillRegistry 初始化完成：{registry}")
            except Exception as e:
                logger.warning(f"ThemeSkillRegistry 初始化失败（增强技能不可用）：{e}")
                self._skill_registry_instance = None
        return self._skill_registry_instance

    async def _process_novel(self, novel: Novel):
        """处理单个小说（全流程）"""
        try:
            if not self._is_still_running(novel):
                logger.info(f"[{novel.novel_id}] 用户已停止自动驾驶，跳过本轮")
                return

            # 根据 novel.genre 动态加载题材 Agent
            self._load_theme_agent_for_novel(novel)

            stage_name = novel.current_stage.value
            logger.debug(f"[{novel.novel_id}] 当前阶段: {stage_name}")

            if novel.current_stage == NovelStage.MACRO_PLANNING:
                logger.info(f"[{novel.novel_id}] 📋 开始宏观规划")
                await self._handle_macro_planning(novel)
            elif novel.current_stage == NovelStage.ACT_PLANNING:
                logger.info(f"[{novel.novel_id}] 📝 开始幕级规划 (第 {novel.current_act + 1} 幕)")
                await self._handle_act_planning(novel)
            elif novel.current_stage == NovelStage.WRITING:
                logger.info(f"[{novel.novel_id}] ✍️  开始写作 (第 {novel.current_act + 1} 幕)")
                await self._handle_writing(novel)
            elif novel.current_stage == NovelStage.AUDITING:
                logger.info(f"[{novel.novel_id}] 🔍 开始审计")
                await self._handle_auditing(novel)
            elif novel.current_stage == NovelStage.PAUSED_FOR_REVIEW:
                # 全自动模式：跳过审阅，直接进入下一阶段
                if getattr(novel, 'auto_approve_mode', False):
                    logger.info(f"[{novel.novel_id}] 🚀 全自动模式：跳过人工审阅")
                    # 根据当前状态自动进入下一阶段
                    # 宏观规划完成后 -> 幕级规划
                    # 幕级规划完成后 -> 写作
                    # 写作完成后 -> 审计
                    novel.current_stage = NovelStage.ACT_PLANNING
                    self._save_novel_state(novel)
                    return
                else:
                    logger.debug(f"[{novel.novel_id}] ⏸️  等待人工审阅")
                    return  # 人工干预点：不处理，等前端确认
            elif novel.current_stage == NovelStage.PAUSED_FOR_SEAM_REVIEW:
                # 接缝复检失败暂停，无论是否全自动模式都等待人工修订
                logger.warning(f"[{novel.novel_id}] ⏸️  接缝复检未通过，等待人工修订章节开头")
                return  # 人工干预点：不处理，等前端确认

            # ✅ 收尾写库（合并 DB 停止标志，避免把用户「停止」写回 RUNNING）
            self._merge_autopilot_status_from_db(novel)
            if novel.autopilot_status == AutopilotStatus.RUNNING:
                if self.circuit_breaker:
                    self.circuit_breaker.record_success()
                novel.consecutive_error_count = 0
            else:
                logger.info(f"[{novel.novel_id}] 💾 本轮结束（用户已停止，不再计成功/重置熔断）")
            self._save_novel_state(novel)
            logger.debug(f"[{novel.novel_id}] 💾 状态已保存")

        except Exception as e:
            logger.error(f"❌ [{novel.novel_id}] 处理失败: {e}", exc_info=True)

            self._merge_autopilot_status_from_db(novel)
            if novel.autopilot_status != AutopilotStatus.RUNNING:
                logger.info(f"[{novel.novel_id}] 处理异常但用户已停止，不累计熔断/失败次数")
                self._save_novel_state(novel)
                return

            # 熔断器：记录失败
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            novel.consecutive_error_count = (novel.consecutive_error_count or 0) + 1

            if novel.consecutive_error_count >= 3:
                # 单本小说连续 3 次错误 → 挂起（不影响其他小说）
                logger.error(f"🚨 [{novel.novel_id}] 连续失败 {novel.consecutive_error_count} 次，挂起等待急救")
                novel.autopilot_status = AutopilotStatus.ERROR
            else:
                logger.warning(f"⚠️  [{novel.novel_id}] 连续失败 {novel.consecutive_error_count}/3 次")
            self._save_novel_state(novel)

    async def _handle_macro_planning(self, novel: Novel):
        """处理宏观规划（规划部/卷/幕）- 使用极速模式让 AI 自主推断结构"""
        if not self._is_still_running(novel):
            return

        target_chapters = novel.target_chapters or 30

        # 使用极速模式：structure_preference=None，让 AI 根据目标章节数智能决定结构
        # 这样 30 章、100 章、300 章、500 章会自动生成不同规模的叙事骨架
        result = await self.planning_service.generate_macro_plan(
            novel_id=novel.novel_id.value,
            target_chapters=target_chapters,
            structure_preference=None  # 极速模式：AI 自主决定最优结构
        )

        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 宏观规划 LLM 返回后检测到停止，不再落库")
            return

        struct = result.get("structure") if isinstance(result, dict) else None
        # 注意：structure 为 [] 时不能写 `if result.get("structure")`，否则会被当成失败分支且不落库
        if result.get("success") and isinstance(struct, list) and len(struct) > 0:
            await self._confirm_macro_structure(novel, struct)
        else:
            logger.warning(
                f"[{novel.novel_id}] 宏观规划未返回有效结构（success={result.get('success')!r}），使用最小占位结构"
            )
            await self._create_minimal_structure(novel)

        # ⏸ 幕级大纲已就绪，进入人工审阅点（先落库再记日志，防止未保存导致下轮仍跑宏观规划）
        # 全自动模式：跳过审阅，直接进入幕级规划
        if getattr(novel, 'auto_approve_mode', False):
            novel.current_stage = NovelStage.ACT_PLANNING
            self._flush_novel(novel)
            logger.info(f"[{novel.novel_id}] 🚀 全自动模式：宏观规划完成，直接进入幕级规划")
        else:
            novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
            self._flush_novel(novel)
            logger.info(f"[{novel.novel_id}] 宏观规划完成，进入审阅等待")

    async def _confirm_macro_structure(self, novel: Novel, structure: list):
        """落库宏观结构；安全合并失败时回退为一次性写入（新书通常为无冲突）。"""
        novel_id = novel.novel_id.value
        try:
            await self.planning_service.confirm_macro_plan_safe(
                novel_id=novel_id,
                structure=structure
            )
        except Exception as e:
            logger.warning(f"[{novel_id}] confirm_macro_plan_safe 失败，回退 confirm_macro_plan：{e}")
            await self.planning_service.confirm_macro_plan(
                novel_id=novel_id,
                structure=structure
            )

    async def _create_minimal_structure(self, novel: Novel):
        """LLM 无输出或解析为空时，落库最小部-卷-幕树，避免审阅点侧栏仍为空。"""
        novel_id = novel.novel_id.value
        target = novel.target_chapters or 30
        per_act = max(target // 3, 5)
        structure = [{
            "title": "第一部",
            "description": "全托管自动生成的占位结构（可在审阅后于结构树中调整）",
            "volumes": [{
                "title": "第一卷",
                "description": "",
                "acts": [
                    {
                        "title": "第一幕 · 开端",
                        "description": "故事建立与主线引出",
                        "suggested_chapter_count": per_act,
                    },
                    {
                        "title": "第二幕 · 发展",
                        "description": "冲突升级与转折",
                        "suggested_chapter_count": per_act,
                    },
                    {
                        "title": "第三幕 · 高潮与收尾",
                        "description": "决战与结局",
                        "suggested_chapter_count": per_act,
                    },
                ],
            }],
        }]
        logger.warning(f"[{novel.novel_id}] 使用最小占位宏观结构（{len(structure[0]['volumes'][0]['acts'])} 幕）")
        await self._confirm_macro_structure(novel, structure)

    def _fallback_act_chapters_plan(self, act_node, count: int) -> List[Dict[str, Any]]:
        """LLM 幕级规划失败或 chapters 为空时，生成可落库的占位章节（避免抛错导致连续失败计数）。"""
        n = max(int(count or 5), 1)
        act_num = getattr(act_node, "number", None) or 1
        act_label = (getattr(act_node, "title", None) or f"第{act_num}幕").strip()
        rows: List[Dict[str, Any]] = []
        for i in range(n):
            rows.append({
                "title": f"{act_label} · 第{i + 1}章（占位）",
                "outline": (
                    f"【占位】{act_label} 第 {i + 1} 章：推进本幕叙事；"
                    "可在结构树中修改或重新运行幕级规划。"
                ),
            })
        return rows

    async def _handle_act_planning(self, novel: Novel):
        """处理幕级规划（插入缓冲章策略 + 动态幕生成）"""
        if not self._is_still_running(novel):
            return

        novel_id = novel.novel_id.value
        target_act_number = novel.current_act + 1  # 1-indexed

        all_nodes = await self.story_node_repo.get_by_novel(novel_id)
        act_nodes = sorted(
            [n for n in all_nodes if n.node_type.value == "act"],
            key=lambda n: n.number
        )

        target_act = next((n for n in act_nodes if n.number == target_act_number), None)

        # 动态幕生成：超长篇可能只规划了部/卷框架，幕节点需要动态创建
        if not target_act:
            # 先尝试找到父卷节点
            volume_nodes = sorted(
                [n for n in all_nodes if n.node_type.value == "volume"],
                key=lambda n: n.number
            )
            
            # 计算应该在第几卷
            chapters_per_volume = max((novel.target_chapters or 100) // max(len(volume_nodes), 1), 50)
            estimated_volume_number = max(1, (novel.current_auto_chapters or 0) // chapters_per_volume + 1)
            
            parent_volume = next((v for v in volume_nodes if v.number == estimated_volume_number), None)
            
            if parent_volume:
                logger.info(f"[{novel.novel_id}] 🎯 动态生成第 {target_act_number} 幕（父卷：第 {parent_volume.number} 卷）")
                try:
                    # 使用最后一个幕作为参考（如果有）
                    last_act = act_nodes[-1] if act_nodes else None
                    if last_act:
                        await self.planning_service.create_next_act_auto(
                            novel_id=novel_id,
                            current_act_id=last_act.id
                        )
                    else:
                        # 完全没有幕节点，创建第一个幕
                        logger.info(f"[{novel.novel_id}] 创建首幕")
                        from domain.structure.story_node import StoryNode, NodeType, PlanningStatus, PlanningSource
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
                            suggested_chapter_count=chapters_per_volume // 3,
                        )
                        await self.story_node_repo.save(first_act)
                    
                    # 重新加载
                    all_nodes = await self.story_node_repo.get_by_novel(novel_id)
                    act_nodes = sorted(
                        [n for n in all_nodes if n.node_type.value == "act"],
                        key=lambda n: n.number
                    )
                    target_act = next((n for n in act_nodes if n.number == target_act_number), None)
                except Exception as e:
                    logger.warning(f"[{novel.novel_id}] 动态幕生成失败: {e}")

            if not target_act:
                logger.error(f"[{novel.novel_id}] 找不到第 {target_act_number} 幕，且动态生成失败")
                novel.current_stage = NovelStage.WRITING
                return

        # 检查该幕下是否已有章节节点（避免重复规划）
        act_children = self.story_node_repo.get_children_sync(target_act.id)
        confirmed_chapters = [n for n in act_children if n.node_type.value == "chapter"]

        just_created_chapter_plan = False
        if not confirmed_chapters:
            chapter_budget = target_act.suggested_chapter_count or 5
            plan_result: Dict[str, Any] = {}
            try:
                plan_result = await self.planning_service.plan_act_chapters(
                    act_id=target_act.id,
                    custom_chapter_count=chapter_budget
                )
            except Exception as e:
                logger.warning(
                    f"[{novel.novel_id}] plan_act_chapters 未捕获异常: {e}",
                    exc_info=True,
                )
                plan_result = {}

            if not self._is_still_running(novel):
                logger.info(f"[{novel.novel_id}] 幕级规划返回后检测到停止，不再落库")
                return

            raw = plan_result.get("chapters")
            chapters_data: List[Dict[str, Any]] = raw if isinstance(raw, list) else []
            if not chapters_data:
                logger.warning(
                    f"[{novel.novel_id}] 幕 {target_act_number} 未得到有效章节规划，使用占位章节落库"
                )
                chapters_data = self._fallback_act_chapters_plan(target_act, chapter_budget)

            await self.planning_service.confirm_act_planning(
                act_id=target_act.id,
                chapters=chapters_data
            )
            just_created_chapter_plan = True

        act_children = self.story_node_repo.get_children_sync(target_act.id)
        confirmed_chapters = [n for n in act_children if n.node_type.value == "chapter"]

        # current_act 为 0-based 幕索引（与 Novel 实体一致），勿写入 1-based 的 target_act_number
        novel.current_act = target_act_number - 1

        if not confirmed_chapters:
            logger.error(
                f"[{novel.novel_id}] 幕 {target_act_number} 仍无章节节点，下轮继续幕级规划"
            )
            novel.current_stage = NovelStage.ACT_PLANNING
            return

        # 仅在本轮「新落库」幕级章节规划时暂停审阅；用户确认后同幕已有节点则直接写作，避免反复弹审批
        # 全自动模式：跳过审阅，直接进入写作
        if just_created_chapter_plan:
            if getattr(novel, 'auto_approve_mode', False):
                novel.current_stage = NovelStage.WRITING
                self._flush_novel(novel)
                logger.info(f"[{novel.novel_id}] 🚀 全自动模式：第 {target_act_number} 幕规划完成，直接进入写作")
            else:
                novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
                self._flush_novel(novel)
                logger.info(f"[{novel.novel_id}] 第 {target_act_number} 幕规划完成，进入审阅等待")
        else:
            novel.current_stage = NovelStage.WRITING
            self._flush_novel(novel)
            logger.info(
                f"[{novel.novel_id}] 第 {target_act_number} 幕章节节点已存在，进入写作"
            )

    async def _handle_writing(self, novel: Novel):
        """处理写作（节拍级幂等落库）"""
        if not self._is_still_running(novel):
            return

        # 1. 目标控制：达到目标章节数则自动停止（允许用户设置更高的 max_auto_chapters 作为保护上限）
        target_chapters = novel.target_chapters or 50
        max_chapters = novel.max_auto_chapters or 9999  # 保护上限，默认几乎无限制
        current_chapters = novel.current_auto_chapters or 0

        if current_chapters >= target_chapters:
            logger.info(f"[{novel.novel_id}] 已达到目标章节数 {target_chapters} 章，全托管完成")
            novel.autopilot_status = AutopilotStatus.STOPPED
            novel.current_stage = NovelStage.COMPLETED
            return

        if current_chapters >= max_chapters:
            logger.info(f"[{novel.novel_id}] 已达保护上限 {max_chapters} 章，自动暂停（目标为 {target_chapters} 章）")
            novel.autopilot_status = AutopilotStatus.STOPPED
            novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
            return

        # 2. 缓冲章判断（高潮后插入日常章）
        needs_buffer = (novel.last_chapter_tension or 0) >= 8
        if needs_buffer:
            logger.info(f"[{novel.novel_id}] 上章张力≥8，强制生成缓冲章")

        # 3. 找下一个未写章节
        next_chapter_node = await self._find_next_unwritten_chapter_async(novel)
        if not next_chapter_node:
            if await self._current_act_fully_written(novel):
                novel.current_act += 1
                novel.current_chapter_in_act = 0
                novel.current_stage = NovelStage.ACT_PLANNING
            else:
                novel.current_stage = NovelStage.AUDITING
            return

        chapter_num = next_chapter_node.number
        outline = next_chapter_node.outline or next_chapter_node.description or next_chapter_node.title
        target_word_count = max(1, int(getattr(novel, "target_words_per_chapter", AppConfig.DEFAULT_WORDS_PER_CHAPTER) or AppConfig.DEFAULT_WORDS_PER_CHAPTER))

        if needs_buffer:
            # 优先使用题材专项缓冲章模板
            buffer_outline = ""
            if self.theme_agent:
                try:
                    buffer_outline = self.theme_agent.get_buffer_chapter_template(outline)
                except Exception as e:
                    logger.warning(f"ThemeAgent.get_buffer_chapter_template 失败（降级默认）：{e}")
            if buffer_outline:
                outline = buffer_outline
            else:
                outline = f"【缓冲章：日常过渡】{outline}。主角战后休整，与配角闲聊，展示收获，节奏轻松。"

        outline = self._merge_seam_requirements_into_outline(
            novel.novel_id.value,
            chapter_num,
            outline,
        )

        logger.info(f"[{novel.novel_id}] 📖 开始写第 {chapter_num} 章：{outline[:60]}...")
        logger.info(f"[{novel.novel_id}]    进度: {current_chapters}/{target_chapters} 章（目标）")

        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止，跳过本章（上下文组装前）")
            return

        # 4. 组装上下文（与「写一章 / 流式」同源：结构化上下文 + 故事线 + 张力 + 文风）
        bundle = None
        context = ""
        if self.chapter_workflow:
            try:
                bundle = self.chapter_workflow.prepare_chapter_generation(
                    novel.novel_id.value, chapter_num, outline, scene_director=None
                )
                context = bundle["context"]
                logger.info(
                    f"[{novel.novel_id}]    上下文（workflow）: {len(context)} 字符, "
                    f"约 {bundle['context_tokens']} tokens"
                )
            except Exception as e:
                logger.warning(f"prepare_chapter_generation 失败，降级 build_context：{e}")
                bundle = None
        if bundle is None and self.context_builder:
            try:
                context = self.context_builder.build_context(
                    novel_id=novel.novel_id.value,
                    chapter_number=chapter_num,
                    outline=outline,
                    max_tokens=20000
                )
            except Exception as e:
                logger.warning(f"ContextBuilder 失败，降级：{e}")

        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止（上下文组装后）")
            return

        voice_anchors = ""
        if bundle is not None:
            voice_anchors = bundle.get("voice_anchors") or ""
        elif self.context_builder:
            try:
                voice_anchors = self.context_builder.build_voice_anchor_system_section(
                    novel.novel_id.value
                )
            except Exception:
                voice_anchors = ""

        # 5. 节拍放大
        beats = []
        if self.context_builder:
            beats = self.context_builder.magnify_outline_to_beats(
                chapter_num,
                outline,
                target_chapter_words=target_word_count,
            )

        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止（节拍拆分后）")
            return

        # 6. 🔑 节拍级幂等生成 + 增量落库
        start_beat = novel.current_beat_index or 0  # 断点续写：从上次中断的节拍继续

        chapter_content = await self._get_existing_chapter_content(novel, chapter_num) or ""

        use_wf = self.chapter_workflow is not None and bundle is not None

        if beats:
            for i, beat in enumerate(beats):
                if i < start_beat:
                    continue  # 跳过已生成的节拍

                if not self._is_still_running(novel):
                    logger.info(f"[{novel.novel_id}] 用户已停止，中断本章（节拍 {i + 1}/{len(beats)} 前）")
                    return

                beat_prompt = self.context_builder.build_beat_prompt(beat, i, len(beats))
                if use_wf:
                    prompt = self.chapter_workflow.build_chapter_prompt(
                        bundle["context"],
                        outline,
                        storyline_context=bundle["storyline_context"],
                        plot_tension=bundle["plot_tension"],
                        style_summary=bundle["style_summary"],
                        beat_prompt=beat_prompt,
                        beat_index=i,
                        total_beats=len(beats),
                        beat_target_words=int(beat.target_words),
                        voice_anchors=voice_anchors,
                    )
                    prompt = self.chapter_workflow.word_control_service.inject_length_requirements(
                        prompt,
                        target=target_word_count,
                    )
                    max_tokens = int(beat.target_words * 1.5)
                    cfg = GenerationConfig(max_tokens=max_tokens, temperature=0.85)
                    beat_content = await self._stream_llm_with_stop_watch(prompt, cfg, novel=novel)
                else:
                    beat_content = await self._stream_one_beat(
                        outline, context, beat_prompt, beat, novel=novel, voice_anchors=voice_anchors
                    )

                if beat_content.strip():
                    chapter_content += ("\n\n" if chapter_content else "") + beat_content
                    await self._upsert_chapter_content(novel, next_chapter_node, chapter_content, status="draft")

                if not self._is_still_running(novel):
                    novel.current_beat_index = i
                    self._flush_novel(novel)
                    logger.info(
                        f"[{novel.novel_id}] 用户已停止，中断节拍 {i + 1}/{len(beats)}"
                        + ("（已保存已输出片段）" if beat_content.strip() else "（未产生文本）")
                    )
                    return

                novel.current_beat_index = i + 1
                self._flush_novel(novel)

                logger.info(f"[{novel.novel_id}]    ✅ 节拍 {i+1}/{len(beats)} 完成: {len(beat_content)} 字")
        else:
            # 降级：无节拍，一次生成
            if not self._is_still_running(novel):
                logger.info(f"[{novel.novel_id}] 用户已停止，跳过单段生成")
                return
            if use_wf:
                prompt = self.chapter_workflow.build_chapter_prompt(
                    bundle["context"],
                    outline,
                    storyline_context=bundle["storyline_context"],
                    plot_tension=bundle["plot_tension"],
                    style_summary=bundle["style_summary"],
                    voice_anchors=voice_anchors,
                )
                prompt = self.chapter_workflow.word_control_service.inject_length_requirements(
                    prompt,
                    target=target_word_count,
                )
                cfg = GenerationConfig(max_tokens=3000, temperature=0.85)
                beat_content = await self._stream_llm_with_stop_watch(prompt, cfg, novel=novel)
            else:
                beat_content = await self._stream_one_beat(
                    outline, context, None, None, novel=novel, voice_anchors=voice_anchors
                )
            if not self._is_still_running(novel):
                logger.info(f"[{novel.novel_id}] 用户已停止，单段生成已中断")
                novel.current_beat_index = 0
                self._flush_novel(novel)
                return
            chapter_content += beat_content
            await self._upsert_chapter_content(novel, next_chapter_node, chapter_content, status="draft")

        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止，本章不标记完成")
            self._flush_novel(novel)
            return

        word_control_metrics = None
        if use_wf and chapter_content.strip():
            try:
                chapter_content, word_control = await self.chapter_workflow._apply_word_control(
                    content=chapter_content,
                    outline=outline,
                    target_word_count=target_word_count,
                )
                if word_control is not None:
                    serialized = self.chapter_workflow._serialize_word_control(word_control)
                    word_control_metrics = serialized.to_dict() if serialized is not None else None
                    if word_control_metrics is not None:
                        word_control_metrics["generated_via"] = "autopilot"
            except Exception as e:
                logger.warning(f"字数控制闭环失败（仍继续写作流程）：{e}")
        elif chapter_content.strip() and self.chapter_workflow:
            try:
                check = self.chapter_workflow.word_control_service.check_word_count(
                    chapter_content,
                    target_word_count,
                )
                word_control_metrics = {
                    "generated_via": "autopilot",
                    "target": check.target,
                    "actual": check.actual,
                    "tolerance": check.tolerance,
                    "delta": check.delta,
                    "status": check.status,
                    "within_tolerance": check.within_tolerance,
                    "action": "none",
                    "expansion_attempts": 0,
                    "trim_applied": False,
                    "fallback_used": False,
                    "min_allowed": check.min_allowed,
                    "max_allowed": check.max_allowed,
                }
            except Exception:
                word_control_metrics = None

        if use_wf and chapter_content.strip():
            try:
                post = await self.chapter_workflow.post_process_generated_chapter(
                    novel.novel_id.value, chapter_num, outline, chapter_content, scene_director=None
                )
                if isinstance(post, dict):
                    chapter_content = post.get("content") or chapter_content
                    seam_rewrite_info = post.get("seam_rewrite_info") or {}
                    await self._upsert_chapter_content(novel, next_chapter_node, chapter_content, status="draft")
                    logger.info(f"[{novel.novel_id}]    ✅ post_process_generated_chapter 完成")
                    if getattr(self.chapter_workflow, "_requires_manual_seam_revision", None) and \
                            self.chapter_workflow._requires_manual_seam_revision(seam_rewrite_info):
                        logger.warning(
                            "[%s] 第 %s 章接缝复检未通过，进入人工修订: attempts=%s status=%s",
                            novel.novel_id,
                            chapter_num,
                            seam_rewrite_info.get("attempts"),
                            seam_rewrite_info.get("status"),
                        )
                        await self._upsert_chapter_content(novel, next_chapter_node, chapter_content, status="reviewing")
                        novel.current_stage = NovelStage.PAUSED_FOR_SEAM_REVIEW
                        novel.last_audit_chapter_number = chapter_num
                        novel.last_audit_narrative_ok = False
                        novel.last_audit_at = datetime.now(timezone.utc).isoformat()
                        novel.last_audit_issues = [{
                            "type": "seam_check_failed",
                            "message": "章节接缝复检未通过，需要人工修订开头后再继续。",
                        }]
                        self._flush_novel(novel)
                        return
                else:
                    logger.debug(
                        "[%s] post_process_generated_chapter 返回非 dict，跳过后处理落库: %s",
                        novel.novel_id,
                        type(post).__name__,
                    )
            except Exception as e:
                logger.warning(f"post_process_generated_chapter 失败（仍落库）：{e}")

        # 7. 章节完成，标记 completed
        await self._upsert_chapter_content(
            novel,
            next_chapter_node,
            chapter_content,
            status="completed",
            generation_metrics=word_control_metrics,
        )

        try:
            await self._maybe_rewrite_next_chapter_outline(
                novel=novel,
                current_chapter_node=next_chapter_node,
                current_outline=outline,
                current_content=chapter_content,
            )
        except Exception as e:
            logger.warning(
                "[%s] 第 %s 章完成后自动修正下一章大纲失败：%s",
                novel.novel_id,
                chapter_num,
                e,
                exc_info=True,
            )

        # 8. 更新计数器，重置节拍索引
        novel.current_auto_chapters = (novel.current_auto_chapters or 0) + 1
        novel.current_chapter_in_act += 1
        novel.current_beat_index = 0
        novel.current_stage = NovelStage.AUDITING
        self._flush_novel(novel)

        logger.info(f"[{novel.novel_id}] 🎉 第 {chapter_num} 章完成：{len(chapter_content)} 字 (共 {novel.current_auto_chapters}/{novel.target_chapters} 章)")

    def _merge_seam_requirements_into_outline(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        """将上一章接缝卡注入本章大纲，防止规划层另起新场。"""
        if chapter_number <= 1:
            return outline

        seam = self._get_previous_chapter_seam(novel_id, chapter_number)
        if not seam:
            return outline

        parts = []
        if seam.get("ending_state"):
            parts.append(f"上一章章末状态：{seam['ending_state']}")
        if seam.get("ending_emotion"):
            parts.append(f"上一章章末情绪：{seam['ending_emotion']}")
        if seam.get("carry_over_question"):
            parts.append(f"本章必须承接：{seam['carry_over_question']}")
        if seam.get("next_opening_hint"):
            parts.append(f"建议开场提示：{seam['next_opening_hint']}")
        if not parts:
            return outline

        seam_block = (
            "【章节接缝硬约束】\n"
            + "\n".join(parts)
            + "\n要求：本章开头必须直接承接以上接缝，不得跳成次日新事件或无关新场面。\n"
        )
        if seam.get("carry_over_question"):
            normalized_outline = self._normalize_seam_text(outline)
            normalized_question = self._normalize_seam_text(str(seam["carry_over_question"]))
            if normalized_question and normalized_question not in normalized_outline:
                logger.info("[%s] 第 %s 章大纲已注入接缝硬约束", novel_id, chapter_number)
        return f"{seam_block}\n【本章规划】\n{outline}"

    def _get_previous_chapter_seam(
        self,
        novel_id: str,
        chapter_number: int,
    ) -> Optional[Dict[str, str]]:
        knowledge_repo = getattr(self.context_builder, "knowledge_repository", None)
        if knowledge_repo is None:
            return None
        try:
            knowledge = knowledge_repo.get_by_novel_id(novel_id)
        except Exception as e:
            logger.debug("读取上一章接缝卡失败: %s", e)
            return None
        if not knowledge:
            return None
        previous = next(
            (ch for ch in knowledge.chapters if getattr(ch, "chapter_id", None) == chapter_number - 1),
            None,
        )
        if previous is None:
            return None
        return {
            "ending_state": getattr(previous, "ending_state", "") or "",
            "ending_emotion": getattr(previous, "ending_emotion", "") or "",
            "carry_over_question": getattr(previous, "carry_over_question", "") or "",
            "next_opening_hint": getattr(previous, "next_opening_hint", "") or "",
        }

    @staticmethod
    def _normalize_seam_text(text: str) -> str:
        return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", (text or "").lower())

    async def _maybe_rewrite_next_chapter_outline(
        self,
        novel: Novel,
        current_chapter_node,
        current_outline: str,
        current_content: str,
    ) -> None:
        """最小版重规划：当前章与下一章大纲冲突时，仅重写下一章 outline。"""
        next_chapter_node = await self._find_chapter_node_after(
            novel.novel_id.value,
            current_chapter_node.number,
        )
        if not next_chapter_node:
            return

        seam = self._build_chapter_seam_snapshot(
            novel.novel_id.value,
            current_chapter_node.number,
            current_content,
        )
        has_seam_signal = any(seam.get(key) for key in (
            "ending_state",
            "ending_emotion",
            "carry_over_question",
            "next_opening_hint",
        ))
        if not has_seam_signal:
            return

        original_outline = (
            next_chapter_node.outline
            or next_chapter_node.description
            or next_chapter_node.title
            or ""
        ).strip()
        if not original_outline:
            return

        conflict, reason = self._outline_conflicts_with_previous_seam(original_outline, seam)
        if not conflict:
            return

        rewritten_outline = await self._rewrite_next_chapter_outline(
            novel=novel,
            current_chapter_number=current_chapter_node.number,
            current_outline=current_outline,
            next_chapter_node=next_chapter_node,
            seam=seam,
            reason=reason,
        )
        rewritten_outline = (rewritten_outline or "").strip()
        if not rewritten_outline or rewritten_outline == original_outline:
            return

        next_chapter_node.outline = rewritten_outline
        metadata = dict(getattr(next_chapter_node, "metadata", {}) or {})
        metadata["auto_replanned_from_chapter"] = current_chapter_node.number
        metadata["auto_replanned_reason"] = reason
        metadata["auto_replanned_at"] = datetime.now(timezone.utc).isoformat()
        next_chapter_node.metadata = metadata
        await self.story_node_repo.update(next_chapter_node)
        logger.warning(
            "[%s] 第 %s 章与第 %s 章大纲冲突，已自动重写下一章大纲：%s",
            novel.novel_id,
            current_chapter_node.number,
            next_chapter_node.number,
            reason,
        )

    async def _find_chapter_node_after(self, novel_id: str, chapter_number: int):
        all_nodes = await self.story_node_repo.get_by_novel(novel_id)
        chapter_nodes = sorted(
            [n for n in all_nodes if n.node_type.value == "chapter"],
            key=lambda n: n.number,
        )
        for node in chapter_nodes:
            if node.number > chapter_number:
                return node
        return None

    def _build_chapter_seam_snapshot(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
    ) -> Dict[str, str]:
        knowledge_repo = getattr(self.context_builder, "knowledge_repository", None)
        if knowledge_repo is not None:
            try:
                knowledge = knowledge_repo.get_by_novel_id(novel_id)
                if knowledge:
                    current = next(
                        (
                            ch for ch in knowledge.chapters
                            if getattr(ch, "chapter_id", None) == chapter_number
                        ),
                        None,
                    )
                    if current and any(
                        getattr(current, field, "") for field in (
                            "ending_state",
                            "ending_emotion",
                            "carry_over_question",
                            "next_opening_hint",
                        )
                    ):
                        return {
                            "ending_state": getattr(current, "ending_state", "") or "",
                            "ending_emotion": getattr(current, "ending_emotion", "") or "",
                            "carry_over_question": getattr(current, "carry_over_question", "") or "",
                            "next_opening_hint": getattr(current, "next_opening_hint", "") or "",
                        }
            except Exception as e:
                logger.debug("读取当前章接缝卡失败，回退正文尾部启发式: %s", e)
        return self._derive_seam_snapshot_from_content(content)

    def _derive_seam_snapshot_from_content(self, content: str) -> Dict[str, str]:
        paragraphs = [p.strip() for p in re.split(r"\n+", content or "") if p.strip()]
        tail_paragraphs = paragraphs[-2:] if paragraphs else []
        ending_state = "\n".join(tail_paragraphs)[-160:].strip()
        ending_emotion = ""
        carry_over_question = ""
        next_opening_hint = ""

        question_candidates = re.findall(r"[^。！？!?]{4,40}[？?]", content or "")
        if question_candidates:
            carry_over_question = question_candidates[-1].strip()

        if tail_paragraphs:
            tail_text = " ".join(tail_paragraphs)
            emotion_markers = [
                "愤怒", "痛苦", "震惊", "恐惧", "悲伤", "苦涩", "清醒",
                "决绝", "迟疑", "紧张", "压抑", "复杂", "不安",
            ]
            hits = [marker for marker in emotion_markers if marker in tail_text]
            if hits:
                ending_emotion = "、".join(hits[:3])

            opening_candidates = re.findall(
                r"(?:去|前往|赶往|潜入|进入|返回|追查|查|寻找|赶去)[^。！？!?]{0,18}",
                tail_text,
            )
            if opening_candidates:
                next_opening_hint = opening_candidates[-1].strip("，,；; ")

        if not carry_over_question and ending_state:
            sentences = [s.strip() for s in re.split(r"[。！？!?]", ending_state) if s.strip()]
            if sentences:
                carry_over_question = sentences[-1][:40]

        if not next_opening_hint and ending_state:
            next_opening_hint = ending_state[-40:]

        return {
            "ending_state": ending_state,
            "ending_emotion": ending_emotion,
            "carry_over_question": carry_over_question,
            "next_opening_hint": next_opening_hint,
        }

    def _outline_conflicts_with_previous_seam(
        self,
        outline: str,
        seam: Dict[str, str],
    ) -> tuple[bool, str]:
        """检查下一章大纲是否与上一章接缝存在冲突

        Args:
            outline: 下一章大纲文本
            seam: 上一章接缝数据，包含 ending_state, ending_emotion, carry_over_question, next_opening_hint

        Returns:
            tuple: (是否有冲突, 冲突描述)
        """
        normalized_outline = self._normalize_seam_text(outline)
        anchor_score, carryover_hint_score = self._calculate_outline_anchor_score(normalized_outline, seam)
        reset_markers = (
            "次日", "翌日", "第二天", "天亮", "清晨", "黎明", "晨光", "早晨",
        )
        has_reset_marker = any(marker in outline for marker in reset_markers)

        if anchor_score >= 2 and carryover_hint_score >= 1:
            return False, ""
        if has_reset_marker and anchor_score == 0:
            return True, "下一章大纲另起时间场景，且未承接上一章接缝"
        if carryover_hint_score == 0 and (seam.get("carry_over_question") or seam.get("next_opening_hint")):
            return True, "下一章大纲未覆盖上一章必须回应的问题或行动"
        return False, ""

    def _calculate_outline_anchor_score(self, normalized_outline: str, seam: Dict[str, str]) -> tuple[int, int]:
        """计算大纲与接缝的锚点匹配分数

        修复问题 10：分离 carryover_hint 分数，确保当 carry_over_question 存在时，
        必须至少有一个来自该字段或 next_opening_hint 的锚点命中。

        Args:
            normalized_outline: 规范化后的大纲文本
            seam: 接缝数据

        Returns:
            tuple: (总分数, carryover_hint分数)
        """
        score = 0
        carryover_hint_score = 0
        seen = set()
        for field in ("carry_over_question", "next_opening_hint", "ending_state", "ending_emotion"):
            keywords = self._extract_seam_keywords(seam.get(field, ""))
            field_hits = 0
            for keyword in keywords:
                if keyword in seen:
                    continue
                if keyword in normalized_outline:
                    seen.add(keyword)
                    field_hits += 1
            score += min(field_hits, 2)
            # 单独计算 carryover_hint 分数，用于检测 carry_over_question 是否被回应
            if field in ("carry_over_question", "next_opening_hint"):
                carryover_hint_score += min(field_hits, 2)
        return score, carryover_hint_score

    def _extract_seam_keywords(self, text: str) -> List[str]:
        normalized = self._normalize_seam_text(text)
        if len(normalized) < 2:
            return []
        stop_keywords = {
            "上一", "一章", "本章", "状态", "情绪", "问题", "提示",
            "必须", "承接", "建议", "开场", "然后", "自己", "他们",
            "因为", "如果", "没有", "不是", "一个",
        }
        keywords: List[str] = []
        for size in (4, 3, 2):
            if len(normalized) < size:
                continue
            for i in range(0, len(normalized) - size + 1):
                token = normalized[i:i + size]
                if token in stop_keywords:
                    continue
                if token not in keywords:
                    keywords.append(token)
                if len(keywords) >= 10:
                    return keywords
        return keywords

    async def _rewrite_next_chapter_outline(
        self,
        novel: Novel,
        current_chapter_number: int,
        current_outline: str,
        next_chapter_node,
        seam: Dict[str, str],
        reason: str,
    ) -> Optional[str]:
        if not self.llm_service:
            return None

        prompt = self._build_next_chapter_outline_replan_prompt(
            current_chapter_number=current_chapter_number,
            current_outline=current_outline,
            next_chapter_node=next_chapter_node,
            seam=seam,
            reason=reason,
        )
        config = GenerationConfig(max_tokens=280, temperature=0.45)
        try:
            result = await self.llm_service.generate(prompt, config)
        except Exception as e:
            logger.warning(
                "[%s] 自动重写第 %s 章大纲失败：%s",
                novel.novel_id,
                next_chapter_node.number,
                e,
            )
            return None
        return (result.content or "").strip()

    def _build_next_chapter_outline_replan_prompt(
        self,
        current_chapter_number: int,
        current_outline: str,
        next_chapter_node,
        seam: Dict[str, str],
        reason: str,
    ) -> Prompt:
        current_outline = (current_outline or "").strip() or "无"
        next_outline = (
            next_chapter_node.outline
            or next_chapter_node.description
            or next_chapter_node.title
            or "无"
        ).strip()
        system = """你是长篇小说续写规划编辑。你的任务是只重写“下一章大纲”，让它严格承接上一章已写成的剧情事实。

必须遵守：
1. 以上一章已发生的事实为最高优先级，不得推翻。
2. 只重写下一章大纲，不要重写正文，不要解释原因。
3. 开头必须直接承接上一章结尾，不得另起“次日/清晨/突然收到新线索”式新开局，除非上一章结尾本身明确切到了那里。
4. 尽量保留原下一章大纲里仍然兼容的主线目标，但可以调整入口场景、推进顺序和信息揭露时机。
5. 只输出一段 100-180 字的中文章节大纲，不要加标题、序号、引号或说明。"""
        user = f"""上一章：第 {current_chapter_number} 章
上一章原大纲：
{current_outline}

上一章接缝信息：
- 章末状态：{seam.get("ending_state", "") or "无"}
- 章末情绪：{seam.get("ending_emotion", "") or "无"}
- 必须回应：{seam.get("carry_over_question", "") or "无"}
- 开场提示：{seam.get("next_opening_hint", "") or "无"}

待修正章节：第 {next_chapter_node.number} 章《{next_chapter_node.title}》
原下一章大纲：
{next_outline}

触发重写原因：
{reason}

现在请直接输出修正后的下一章大纲。"""
        return Prompt(system=system, user=user)

    async def _handle_auditing(self, novel: Novel):
        """处理审计（含张力打分）"""
        if not self._is_still_running(novel):
            return

        from domain.novel.value_objects.novel_id import NovelId
        from domain.novel.value_objects.chapter_id import ChapterId

        chapters = self.chapter_repository.list_by_novel(NovelId(novel.novel_id.value))
        chapter = self._get_latest_completed_chapter(chapters)
        if not chapter:
            novel.current_stage = NovelStage.WRITING
            return
        chapter_num = chapter.number

        content = chapter.content or ""
        chapter_id = ChapterId(chapter.id)

        # 1. 先做文风预检；若严重偏离则定向改写，最多两轮，再执行章后管线，避免分析结果与最终正文错位
        drift_result = await self._score_voice_only(
            novel.novel_id.value,
            chapter_num,
            content,
        )
        content, drift_result = await self._apply_voice_rewrite_loop(
            novel,
            chapter,
            content,
            drift_result,
        )
        if self.chapter_generation_metrics_repository:
            existing_metrics = self.chapter_generation_metrics_repository.get(
                novel.novel_id.value,
                chapter_num,
            )
            if existing_metrics:
                existing_metrics["actual"] = effective_length(content)
                existing_metrics["delta"] = existing_metrics["actual"] - int(existing_metrics.get("target") or 0)
                existing_metrics["status"] = (
                    "too_short" if existing_metrics["actual"] < existing_metrics["min_allowed"]
                    else "too_long" if existing_metrics["actual"] > existing_metrics["max_allowed"]
                    else "ok"
                )
                existing_metrics["within_tolerance"] = existing_metrics["status"] == "ok"
                self.chapter_generation_metrics_repository.upsert(
                    novel.novel_id.value,
                    chapter_num,
                    existing_metrics,
                )

        # 2. 统一章后管线：叙事/向量、文风（一次）、KG 推断；三元组与伏笔在叙事同步单次 LLM 中落库
        if self.aftermath_pipeline:
            try:
                drift_result = await self.aftermath_pipeline.run_after_chapter_saved(
                    novel.novel_id.value,
                    chapter_num,
                    content,
                )
                logger.info(
                    f"[{novel.novel_id}] 章后管线完成: 相似度={drift_result.get('similarity_score')}, "
                    f"drift_alert={drift_result.get('drift_alert')}"
                )
            except Exception as e:
                logger.warning(f"[{novel.novel_id}] 章后管线失败（降级旧逻辑）：{e}")
                drift_result = self._legacy_auditing_tasks_and_voice(
                    novel, chapter_num, content, chapter_id
                )
        else:
            drift_result = self._legacy_auditing_tasks_and_voice(
                novel, chapter_num, content, chapter_id
            )

        # 2. 张力打分（轻量 LLM 调用，~200 token）
        tension = await self._score_tension(content)
        novel.last_chapter_tension = tension
        # 保存张力值到章节（用于张力曲线图）
        chapter.update_tension_score(tension * 10)  # 转换为 0-100 范围
        self.chapter_repository.save(chapter)
        logger.info(f"[{novel.novel_id}] 章节 {chapter_num} 张力值：{tension}/10")

        # 章末审阅快照（写入 novels，供 /autopilot/status 与前台「章节状态 / 章节元素」）
        previous_same_chapter_drift = (
            novel.last_audit_chapter_number == chapter_num
            and bool(novel.last_audit_drift_alert)
        )
        novel.last_audit_chapter_number = chapter_num
        novel.last_audit_similarity = drift_result.get("similarity_score")
        novel.last_audit_drift_alert = bool(drift_result.get("drift_alert", False))
        novel.last_audit_narrative_ok = bool(drift_result.get("narrative_sync_ok", True))
        novel.last_audit_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        drift_too_high = bool(drift_result.get("drift_alert", False))
        similarity_score = drift_result.get("similarity_score")
        similarity_below_threshold = self._similarity_below_warning_threshold(similarity_score)
        if drift_result.get("similarity_score") is not None:
            logger.info(
                f"[{novel.novel_id}] 文风相似度：{drift_result.get('similarity_score')}，"
                f"告警：{drift_too_high}"
            )

        # 3. 文风漂移仅保留告警，不再删章回滚
        if drift_too_high and similarity_below_threshold:
            logger.warning(
                f"[{novel.novel_id}] 章节 {chapter_num} 文风仍偏离，但已完成有限次定向修正，保留本章继续推进"
            )
        elif drift_too_high and previous_same_chapter_drift:
            logger.info(
                f"[{novel.novel_id}] 同章文风告警持续存在，但已从删除回滚切换为保留并继续"
            )
        elif drift_too_high and not similarity_below_threshold:
            logger.info(
                f"[{novel.novel_id}] 文风告警来自历史窗口，当前章节相似度未低于阈值，保留本章"
            )

        novel.current_stage = NovelStage.WRITING

        # 5. 全书完成检测
        chapters = self.chapter_repository.list_by_novel(NovelId(novel.novel_id.value))
        completed = [c for c in chapters if c.status.value == "completed"]
        if len(completed) >= novel.target_chapters:
            logger.info(f"[{novel.novel_id}] 🎉 全书完成！共 {len(completed)} 章")
            novel.autopilot_status = AutopilotStatus.STOPPED
            novel.current_stage = NovelStage.COMPLETED

        # 6. 自动触发宏观诊断（每10章或幕完成时）
        await self._auto_trigger_macro_diagnosis(novel, len(completed))
        
        # 7. 🆕 摘要生成钩子（双轨融合 - 轨道一）
        await self._maybe_generate_summaries(novel, len(completed))

    @staticmethod
    def _get_latest_completed_chapter(chapters):
        """从章节列表中找到最新的已完成章节。

        审计阶段不能依赖 current_act/current_chapter_in_act 反推章节号，
        因为幕内缓冲章、重规划和断点续写会让该值偏离真实章节编号。
        """
        completed = [
            chapter for chapter in chapters
            if getattr(chapter.status, "value", chapter.status) == "completed"
        ]
        if not completed:
            return None
        return max(completed, key=lambda chapter: int(chapter.number))

    def _get_voice_service(self):
        """优先复用章后管线里的 voice service，避免配置分叉。"""
        if self.aftermath_pipeline and getattr(self.aftermath_pipeline, "_voice", None):
            return getattr(self.aftermath_pipeline, "_voice")
        return self.voice_drift_service

    def _similarity_below_warning_threshold(self, similarity_score: Any) -> bool:
        """展示告警阈值：宽松，用于提示。"""
        if similarity_score is None:
            return False
        try:
            from application.analyst.services.voice_drift_service import DRIFT_ALERT_THRESHOLD
            return float(similarity_score) < float(DRIFT_ALERT_THRESHOLD)
        except Exception:
            return float(similarity_score) < VOICE_WARNING_THRESHOLD_FALLBACK

    def _should_attempt_voice_rewrite(self, drift_result: Dict[str, Any]) -> bool:
        """自动修文阈值：严格，仅对明显偏离的当前章触发。"""
        similarity = drift_result.get("similarity_score")
        if similarity is None:
            return False
        try:
            return float(similarity) < VOICE_REWRITE_THRESHOLD
        except Exception:
            return False

    async def _score_voice_only(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
    ) -> Dict[str, Any]:
        """仅做文风评分，用于决定是否先修文。"""
        voice_service = self._get_voice_service()
        if not voice_service or not content or not str(content).strip():
            return {"drift_alert": False, "similarity_score": None}

        try:
            if getattr(voice_service, "use_llm_mode", False):
                return await voice_service.score_chapter_async(
                    novel_id=novel_id,
                    chapter_number=chapter_number,
                    content=content,
                )
            return voice_service.score_chapter(
                novel_id=novel_id,
                chapter_number=chapter_number,
                content=content,
            )
        except Exception as e:
            logger.warning("[%s] 文风预检失败，跳过自动修文：%s", novel_id, e)
            return {"drift_alert": False, "similarity_score": None}

    def _build_voice_rewrite_prompt(
        self,
        novel: Novel,
        chapter,
        content: str,
        similarity_score: float,
        attempt: int,
    ) -> Prompt:
        """构建定向修正文风的改写提示。"""
        style_summary = ""
        voice_anchors = ""
        voice_service = self._get_voice_service()
        try:
            fingerprint_repo = getattr(voice_service, "fingerprint_repo", None)
            if fingerprint_repo:
                fingerprint = fingerprint_repo.get_by_novel(novel.novel_id.value, None)
                style_summary = build_style_summary(fingerprint)
        except Exception as e:
            logger.debug("[%s] style_summary 获取失败: %s", novel.novel_id, e)

        if self.context_builder:
            try:
                voice_anchors = self.context_builder.build_voice_anchor_system_section(
                    novel.novel_id.value
                )
            except Exception as e:
                logger.debug("[%s] voice anchors 获取失败: %s", novel.novel_id, e)

        style_block = style_summary.strip() or "暂无明确统计摘要，优先保持既有作者语气与句式节奏。"
        anchor_block = voice_anchors.strip() or "无额外角色声线锚点。"
        outline = (getattr(chapter, "outline", "") or "").strip() or "无单独大纲，必须严格保留现有剧情事实。"

        system = f"""你是小说文风修订编辑。你的任务不是重写剧情，而是在不改变故事事实的前提下，修正文风偏移。

必须遵守：
1. 保留所有剧情事件、因果顺序、角色关系、伏笔信息、地点与关键信息。
2. 保留章节的主要段落结构、对话功能与情绪走向，不要扩写新支线。
3. 只调整叙述口吻、句式节奏、措辞密度、描写轻重，使文本更贴近既有作者文风。
4. 输出只能是修订后的完整章节正文，不要解释，不要加标题，不要加批注。

风格约束：
{style_block}

角色声线锚点：
{anchor_block}
"""
        user = f"""当前为第 {chapter.number} 章，第 {attempt} 次文风定向修正。

当前相似度：{similarity_score:.4f}
自动修文触发阈值：{VOICE_REWRITE_THRESHOLD:.2f}

章节大纲：
{outline}

请在不改变剧情事实的前提下，修订以下正文的叙述语气、句式节奏与措辞，使其更贴近既有文风：

{content}
"""
        return Prompt(system=system, user=user)

    async def _rewrite_chapter_for_voice(
        self,
        novel: Novel,
        chapter,
        content: str,
        similarity_score: float,
        attempt: int,
    ) -> Optional[str]:
        """执行一次定向修文。"""
        if not self.llm_service:
            return None

        prompt = self._build_voice_rewrite_prompt(
            novel,
            chapter,
            content,
            similarity_score,
            attempt,
        )
        config = GenerationConfig(
            max_tokens=max(4096, min(8192, int(len(content) * 1.5))),
            temperature=0.35,
        )
        try:
            result = await self.llm_service.generate(prompt, config)
        except Exception as e:
            logger.warning("[%s] 文风定向修文失败（attempt=%d）：%s", novel.novel_id, attempt, e)
            return None

        rewritten = (result.content or "").strip()
        if not rewritten:
            return None
        return rewritten

    async def _apply_voice_rewrite_loop(
        self,
        novel: Novel,
        chapter,
        content: str,
        initial_drift_result: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any]]:
        """严重漂移时做有限次定向修文，并即时复评分。"""
        current_content = content
        current_result = initial_drift_result or {"drift_alert": False, "similarity_score": None}

        for attempt in range(1, VOICE_REWRITE_MAX_ATTEMPTS + 1):
            if not self._should_attempt_voice_rewrite(current_result):
                break
            if not self._is_still_running(novel):
                logger.info("[%s] 用户已停止，终止文风修文", novel.novel_id)
                break

            similarity = current_result.get("similarity_score")
            logger.warning(
                "[%s] 章节 %s 文风偏离严重（similarity=%s），开始第 %d/%d 次定向修文",
                novel.novel_id,
                chapter.number,
                similarity,
                attempt,
                VOICE_REWRITE_MAX_ATTEMPTS,
            )
            rewritten = await self._rewrite_chapter_for_voice(
                novel,
                chapter,
                current_content,
                float(similarity),
                attempt,
            )
            if not rewritten or rewritten.strip() == current_content.strip():
                logger.warning("[%s] 定向修文未产生有效变化，停止继续重试", novel.novel_id)
                break

            current_content = rewritten
            chapter.update_content(current_content)
            self.chapter_repository.save(chapter)
            current_result = await self._score_voice_only(
                novel.novel_id.value,
                chapter.number,
                current_content,
            )
            logger.info(
                "[%s] 第 %d 次定向修文后相似度=%s drift_alert=%s",
                novel.novel_id,
                attempt,
                current_result.get("similarity_score"),
                current_result.get("drift_alert"),
            )

        return current_content, current_result

    def _legacy_auditing_tasks_and_voice(
        self,
        novel: Novel,
        chapter_num: int,
        content: str,
        chapter_id: ChapterId,
    ) -> Dict[str, Any]:
        """无统一管线时：VOICE + extract_bundle（单次 LLM 叙事/三元组/伏笔）入队 + 同步文风（可能与队列内 VOICE 重复）。"""
        for task_type in [TaskType.VOICE_ANALYSIS, TaskType.EXTRACT_BUNDLE]:
            self.background_task_service.submit_task(
                task_type=task_type,
                novel_id=novel.novel_id,
                chapter_id=chapter_id,
                payload={"content": content, "chapter_number": chapter_num},
            )
        if self.voice_drift_service and content:
            try:
                return self.voice_drift_service.score_chapter(
                    novel_id=novel.novel_id.value,
                    chapter_number=chapter_num,
                    content=content,
                )
            except Exception as e:
                logger.warning("文风检测失败（跳过）：%s", e)
        return {"drift_alert": False, "similarity_score": None}

    async def _auto_trigger_macro_diagnosis(self, novel: Novel, completed_count: int) -> None:
        """自动触发宏观诊断（每10章或幕完成时）

        触发条件：
        1. 每10章触发一次
        2. 每幕完成时触发一次
        """
        try:
            # 判断是否需要触发
            should_trigger = False
            trigger_reason = ""

            # 条件1：每10章
            if completed_count > 0 and completed_count % 10 == 0:
                should_trigger = True
                trigger_reason = f"每10章检查点（当前{completed_count}章）"

            # 条件2：幕完成（current_chapter_in_act回到0表示新幕开始）
            if novel.current_chapter_in_act == 0 and novel.current_act > 0:
                should_trigger = True
                trigger_reason = f"第{novel.current_act}幕完成"

            if not should_trigger:
                return

            logger.info(f"[{novel.novel_id}] 📊 自动触发宏观诊断：{trigger_reason}")

            # 调用宏观诊断服务（后台异步执行，不阻塞写作流程）
            asyncio.create_task(self._run_macro_diagnosis_background(novel.novel_id.value))

        except Exception as e:
            logger.warning(f"[{novel.novel_id}] 自动触发宏观诊断失败: {e}")

    async def _run_macro_diagnosis_background(self, novel_id: str) -> None:
        """后台执行宏观诊断
        
        流程：
        1. 初始化 MacroDiagnosisService（惰性加载）
        2. 执行全人设扫描
        3. 结果自动存储到 macro_diagnosis_results 表
        """
        try:
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_narrative_event_repository import SqliteNarrativeEventRepository
            from application.audit.services.macro_refactor_scanner import MacroRefactorScanner
            from application.audit.services.macro_diagnosis_service import MacroDiagnosisService
            
            logger.info(f"[{novel_id}] 📊 宏观诊断后台任务已启动")
            
            # 初始化服务
            db = get_database()
            narrative_event_repo = SqliteNarrativeEventRepository(db)
            scanner = MacroRefactorScanner(narrative_event_repo)
            diagnosis_service = MacroDiagnosisService(db, scanner)
            
            # 执行全人设扫描（使用内置规则）
            result = diagnosis_service.run_full_diagnosis(
                novel_id=novel_id,
                trigger_reason=f"自动触发（检查点）",
                traits=None  # 使用默认的内置人设标签
            )
            
            if result.status == "completed":
                logger.info(
                    f"[{novel_id}] ✅ 宏观诊断完成："
                    f"扫描 {result.trait} 人设，发现 {len(result.breakpoints)} 个冲突断点"
                )
            else:
                logger.warning(f"[{novel_id}] ⚠️ 宏观诊断失败：{result.error_message}")

        except Exception as e:
            logger.warning(f"[{novel_id}] 宏观诊断后台任务失败: {e}", exc_info=True)

    async def _score_tension(self, content: str) -> int:
        """给章节打张力分（1-10），用于判断是否插入缓冲章"""
        if not content or len(content) < 200:
            return 5  # 默认中等张力

        snippet = content[:500]  # 只取前 500 字，节省 token

        try:
            prompt = Prompt(
                system="你是小说节奏分析师，只输出一个 1-10 的整数，不要解释。",
                user=f"""根据以下章节开头，打分当前剧情的张力值（1=日常/轻松，10=生死对决/高潮）：

{snippet}

张力分（只输出数字）："""
            )
            config = GenerationConfig(max_tokens=5, temperature=0.1)
            result = await self.llm_service.generate(prompt, config)
            raw = result.content.strip() if hasattr(result, "content") else str(result).strip()
            score = int(''.join(filter(str.isdigit, raw[:3])))
            return max(1, min(10, score))
        except Exception:
            return 5  # 解析失败，返回默认值

    async def _stream_llm_with_stop_watch(
        self, prompt: Prompt, config: GenerationConfig, novel=None
    ) -> str:
        """与 workflow 共用同一套 Prompt + LLM；novel 传入时并行轮询 DB 是否已停止。
        
        流式生成时会实时推送增量文字到 streaming_callback（如果设置）。
        """
        content = ""
        stop_detected = asyncio.Event()
        watch_task = None
        nid = getattr(novel.novel_id, "value", novel.novel_id) if novel else None

        if novel is not None:
            novel_id_ref = novel.novel_id

            async def _watch_stop_from_db() -> None:
                while not stop_detected.is_set():
                    await asyncio.sleep(0.35)
                    if not self._novel_is_running_in_db(novel_id_ref):
                        logger.info(f"[{nid}] 后台轮询：DB 已为停止，结束流式")
                        stop_detected.set()
                        return

            watch_task = asyncio.create_task(_watch_stop_from_db())

        try:
            async for chunk in self.llm_service.stream_generate(prompt, config):
                if novel is not None and stop_detected.is_set():
                    break
                content += chunk
                
                # 实时推送增量文字到全局流式队列
                if novel is not None and chunk:
                    await self._push_streaming_chunk(novel.novel_id.value, chunk)
                
                if novel is not None and stop_detected.is_set():
                    break
        finally:
            stop_detected.set()
            if watch_task is not None:
                watch_task.cancel()
                try:
                    await watch_task
                except asyncio.CancelledError:
                    pass

        if novel is not None:
            self._merge_autopilot_status_from_db(novel)

        return content

    async def _push_streaming_chunk(self, novel_id: str, chunk: str):
        """推送增量文字到全局流式队列，供 SSE 接口消费"""
        from application.engine.services.streaming_bus import streaming_bus
        streaming_bus.publish(novel_id, chunk)

    async def _stream_one_beat(
        self, outline, context, beat_prompt, beat, novel=None, voice_anchors: str = ""
    ) -> str:
        """无 AutoNovelGenerationWorkflow 时的降级：爽文短 Prompt + 流式。"""
        va = (voice_anchors or "").strip()
        voice_block = ""
        if va:
            voice_block = (
                "【角色声线与肢体语言（Bible 锚点，必须遵守）】\n"
                f"{va}\n\n"
            )
        system = f"""你是一位资深网文作家，擅长写爽文。
{voice_block}写作要求：
1. 严格按节拍字数和聚焦点写作
2. 必须有对话和人物互动，保持人物性格一致
3. 增加感官细节：视觉、听觉、触觉、情绪
4. 节奏控制：不要一章推进太多剧情
5. 不要写章节标题"""

        user_parts = []
        if context:
            user_parts.append(context)
        user_parts.append(f"\n【本章大纲】\n{outline}")
        if beat_prompt:
            user_parts.append(f"\n{beat_prompt}")
        user_parts.append("\n\n开始撰写：")

        max_tokens = int(beat.target_words * 1.5) if beat else 3000

        prompt = Prompt(system=system, user="\n".join(user_parts))
        config = GenerationConfig(max_tokens=max_tokens, temperature=0.85)
        return await self._stream_llm_with_stop_watch(prompt, config, novel=novel)

    async def _upsert_chapter_content(
        self,
        novel,
        chapter_node,
        content: str,
        status: str,
        generation_metrics: Optional[Dict[str, Any]] = None,
    ):
        """最小事务：只更新章节内容，不涉及其他表"""
        from domain.novel.entities.chapter import Chapter, ChapterStatus
        from domain.novel.value_objects.novel_id import NovelId

        existing = self.chapter_repository.get_by_novel_and_number(
            NovelId(novel.novel_id.value), chapter_node.number
        )
        if existing:
            # 防御：避免意外用空串覆盖已有正文（例如并发/异常分支写入空内容）
            if (not (content or "").strip()) and (existing.content or "").strip():
                existing.status = ChapterStatus(status)
                self.chapter_repository.save(existing)
                return
            existing.update_content(content)
            existing.status = ChapterStatus(status)
            self.chapter_repository.save(existing)
        else:
            chapter = Chapter(
                id=chapter_node.id,
                novel_id=NovelId(novel.novel_id.value),
                number=chapter_node.number,
                title=chapter_node.title,
                content=content,
                outline=chapter_node.outline or "",
                status=ChapterStatus(status)
            )
            self.chapter_repository.save(chapter)
        if generation_metrics and self.chapter_generation_metrics_repository:
            self.chapter_generation_metrics_repository.upsert(
                novel.novel_id.value,
                chapter_node.number,
                generation_metrics,
            )

    async def _find_next_unwritten_chapter_async(self, novel):
        """找到下一个未写的章节节点"""
        novel_id = novel.novel_id.value
        all_nodes = await self.story_node_repo.get_by_novel(novel_id)
        chapter_nodes = sorted(
            [n for n in all_nodes if n.node_type.value == "chapter"],
            key=lambda n: n.number
        )

        for node in chapter_nodes:
            chapter = self.chapter_repository.get_by_novel_and_number(
                NovelId(novel_id), node.number
            )
            if not chapter or chapter.status.value != "completed":
                return node
        return None

    async def _current_act_fully_written(self, novel) -> bool:
        """检查当前幕是否已全部写完"""
        novel_id = novel.novel_id.value
        all_nodes = await self.story_node_repo.get_by_novel(novel_id)
        act_nodes = sorted(
            [n for n in all_nodes if n.node_type.value == "act"],
            key=lambda n: n.number
        )

        current_act_node = next(
            (n for n in act_nodes if n.number == novel.current_act + 1),
            None
        )
        if not current_act_node:
            return True

        act_children = self.story_node_repo.get_children_sync(current_act_node.id)
        chapter_nodes = [n for n in act_children if n.node_type.value == "chapter"]

        for node in chapter_nodes:
            chapter = self.chapter_repository.get_by_novel_and_number(
                NovelId(novel_id), node.number
            )
            if not chapter or chapter.status.value != "completed":
                return False
        return True

    async def _get_existing_chapter_content(self, novel, chapter_num) -> Optional[str]:
        """获取已存在的章节内容（用于断点续写）"""
        chapter = self.chapter_repository.get_by_novel_and_number(
            NovelId(novel.novel_id.value), chapter_num
        )
        return chapter.content if chapter else None

    async def _maybe_generate_summaries(self, novel: Novel, completed_count: int) -> None:
        """摘要生成钩子（双轨融合 - 轨道一）
        
        触发时机：
        1. 检查点摘要：每 20 章
        2. 幕摘要：幕完成时
        3. 卷摘要：卷完成时
        4. 部摘要：部完成时
        """
        if not self.volume_summary_service:
            return
        
        try:
            novel_id = novel.novel_id.value
            
            # 1. 检查点摘要（每 20 章）
            if await self.volume_summary_service.should_generate_checkpoint(novel_id, completed_count):
                logger.info(f"[{novel_id}] 📝 生成检查点摘要（第 {completed_count} 章）")
                result = await self.volume_summary_service.generate_checkpoint_summary(novel_id, completed_count)
                if result.success:
                    logger.info(f"[{novel_id}] ✅ 检查点摘要生成成功")
                else:
                    logger.warning(f"[{novel_id}] 检查点摘要生成失败: {result.error}")
            
            # 2. 幕摘要（幕完成时）
            all_nodes = await self.story_node_repo.get_by_novel(novel_id)
            act_nodes = sorted(
                [n for n in all_nodes if n.node_type.value == "act"],
                key=lambda x: x.number
            )
            
            if act_nodes:
                # 找到最近完成的幕
                for act in reversed(act_nodes):
                    if act.chapter_end and act.chapter_end <= completed_count:
                        # 检查是否已生成摘要
                        has_summary = act.metadata.get("summary") if act.metadata else None
                        if not has_summary:
                            logger.info(f"[{novel_id}] 📝 生成幕摘要: {act.title}")
                            result = await self.volume_summary_service.generate_act_summary(novel_id, act.id)
                            if result.success:
                                logger.info(f"[{novel_id}] ✅ 幕摘要生成成功: {act.title}")
                            break
            
            # 3. 卷摘要（检测卷是否完成）
            volume_nodes = sorted(
                [n for n in all_nodes if n.node_type.value == "volume"],
                key=lambda x: x.number
            )
            
            for vol in volume_nodes:
                if vol.chapter_end and vol.chapter_end <= completed_count:
                    has_summary = vol.metadata.get("summary") if vol.metadata else None
                    if not has_summary:
                        logger.info(f"[{novel_id}] 📝 生成卷摘要: {vol.title}")
                        result = await self.volume_summary_service.generate_volume_summary(novel_id, vol.number)
                        if result.success:
                            logger.info(f"[{novel_id}] ✅ 卷摘要生成成功: {vol.title}")
                        break
            
            # 4. 部摘要（检测部是否完成）
            part_nodes = sorted(
                [n for n in all_nodes if n.node_type.value == "part"],
                key=lambda x: x.number
            )
            
            for part in part_nodes:
                # 部完成的判断：最后一个卷已完成
                child_volumes = [v for v in volume_nodes if v.parent_id == part.id]
                if child_volumes:
                    last_vol = max(child_volumes, key=lambda x: x.number)
                    if last_vol.chapter_end and last_vol.chapter_end <= completed_count:
                        has_summary = part.metadata.get("summary") if part.metadata else None
                        if not has_summary:
                            logger.info(f"[{novel_id}] 📝 生成部摘要: {part.title}")
                            result = await self.volume_summary_service.generate_part_summary(novel_id, part.number)
                            if result.success:
                                logger.info(f"[{novel_id}] ✅ 部摘要生成成功: {part.title}")
                            break
        
        except Exception as e:
            logger.warning(f"[{novel.novel_id}] 摘要生成失败: {e}")

