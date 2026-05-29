"""上下文构建器 - 双轨融合版

核心设计：
- 使用 ContextBudgetAllocator 进行洋葱模型优先级挤压
- T0: 强制内容（伏笔、角色锚点、当前幕摘要）—— 绝不删减
- T1: 可压缩内容（图谱子网、近期幕摘要）—— 按比例压缩
- T2: 动态内容（最近章节）—— 动态水位线
- T3: 可牺牲内容（向量召回）—— 预算不足时归零

与 AutoNovelGenerationWorkflow 拼接时：Layer1≈T0+T1，Layer2 段名为 RECENT CHAPTERS（T2），
Layer3 段名为 VECTOR RECALL（T3）；见 assemble_chapter_bundle_context_text。
"""
import logging
from typing import Any, Dict, List, Optional

from application.engine.dtos.scene_director_dto import SceneDirectorInput
from application.engine.services.beat_models import Beat
from application.engine.services.beat_planner import (
    generate_expansion_hints,
    infer_focus_from_outline,
    make_minimal_card,
)
from application.engine.services.beat_projection import (
    beat_sheet_to_plan_json,
    beats_from_execution_plan,
)

from application.world.services.bible_service import BibleService
from domain.bible.services.relationship_engine import RelationshipEngine
from domain.novel.services.storyline_manager import StorylineManager
from domain.novel.repositories.novel_repository import NovelRepository
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from domain.ai.services.vector_store import VectorStore
from domain.ai.services.embedding_service import EmbeddingService
from application.engine.services.context_budget_allocator import ContextBudgetAllocator
from application.engine.dag.plan.schema import ChapterExecutionPlan

logger = logging.getLogger(__name__)


class ContextBuilder:
    """上下文构建器（双轨融合版）
    
    智能组装章节生成所需的上下文，使用洋葱模型优先级挤压。
    """

    def __init__(
        self,
        bible_service: BibleService,
        storyline_manager: StorylineManager,
        relationship_engine: RelationshipEngine,
        vector_store: VectorStore,
        novel_repository: NovelRepository,
        chapter_repository: ChapterRepository,
        plot_arc_repository: Optional[PlotArcRepository] = None,
        embedding_service: Optional[EmbeddingService] = None,
        foreshadowing_repository: Optional[ForeshadowingRepository] = None,
        story_node_repository=None,
        bible_repository=None,
        chapter_element_repository=None,
        triple_repository=None,
        # feed-forward 三件套（V8+）：接入后 T0/T1 槽位才会有内容
        causal_edge_repository=None,
        character_state_repository=None,
        narrative_debt_repository=None,
        # 故事线 + 汇流点（供预算分配器使用）
        storyline_repository=None,
        confluence_point_repository=None,
        worldbuilding_repository=None,
        evolution_presenter=None,
        evolution_repository=None,
    ):
        self.bible_service = bible_service
        self.storyline_manager = storyline_manager
        self.relationship_engine = relationship_engine
        self.vector_store = vector_store
        self.novel_repository = novel_repository
        self.chapter_repository = chapter_repository
        self.plot_arc_repository = plot_arc_repository
        self.embedding_service = embedding_service
        self.foreshadowing_repository = foreshadowing_repository
        self.story_node_repository = story_node_repository
        self.bible_repository = bible_repository
        self.chapter_element_repository = chapter_element_repository
        self.triple_repository = triple_repository
        self.storyline_repository = storyline_repository
        self.confluence_point_repository = confluence_point_repository
        self.worldbuilding_repository = worldbuilding_repository
        self.evolution_presenter = evolution_presenter
        self.evolution_repository = evolution_repository

        # ContextAssembler：提供 ANCHOR / SCARS / DEBT_DUE / CAUSAL_CHAINS 槽位
        context_assembler = None
        try:
            from application.engine.services.context_assembler import ContextAssembler
            context_assembler = ContextAssembler(
                causal_edge_repo=causal_edge_repository,
                character_state_repo=character_state_repository,
                debt_repo=narrative_debt_repository,
                foreshadowing_repo=foreshadowing_repository,
                chapter_repo=chapter_repository,
                bible_repo=bible_repository,
                story_node_repo=story_node_repository,
                novel_repository=novel_repository,
                storyline_repo=storyline_repository,
            )
        except Exception as _e:
            logger.warning("ContextAssembler 初始化失败: %s", _e)

        # MemoryEngine：提供 FACT_LOCK / COMPLETED_BEATS / REVEALED_CLUES 槽位
        memory_engine = None
        if bible_repository:
            try:
                from application.engine.services.memory_engine import MemoryEngine
                from infrastructure.persistence.database.connection import get_database
                memory_engine = MemoryEngine(
                    llm_service=None,
                    bible_repository=bible_repository,
                    db_connection=get_database(),
                )
            except Exception as _e:
                logger.warning("MemoryEngine 初始化失败: %s", _e)

        # 预算分配器（核心组件）
        character_kernel = None
        try:
            from application.character.services.character_narrative_kernel import CharacterNarrativeKernel
            character_kernel = CharacterNarrativeKernel(
                bible_service=bible_service,
                bible_repository=bible_repository,
                chapter_element_repository=chapter_element_repository,
                story_node_repository=story_node_repository,
                triple_repository=triple_repository,
                character_state_repository=character_state_repository,
                debt_repository=narrative_debt_repository,
            )
        except Exception as _e:
            logger.warning("CharacterNarrativeKernel 初始化失败: %s", _e)

        self.budget_allocator = ContextBudgetAllocator(
            foreshadowing_repository=foreshadowing_repository,
            chapter_repository=chapter_repository,
            bible_repository=bible_repository,
            story_node_repository=story_node_repository,
            chapter_element_repository=chapter_element_repository,
            triple_repository=triple_repository,
            vector_store=vector_store,
            embedding_service=embedding_service,
            context_assembler=context_assembler,
            memory_engine=memory_engine,
            storyline_repository=storyline_repository,
            confluence_point_repository=confluence_point_repository,
            worldbuilding_repository=worldbuilding_repository,
            evolution_presenter=evolution_presenter,
            evolution_repository=evolution_repository,
            character_narrative_kernel=character_kernel,
        )

    def estimate_tokens(self, text: str) -> int:
        """估算文本 token 数（委托 ContextBudgetAllocator）。"""
        return self.budget_allocator.estimate_tokens(text)

    def build_voice_anchor_system_section(self, novel_id: str) -> str:
        """Bible 角色声线/小动作锚点"""
        return self.bible_service.build_character_voice_anchor_section(novel_id)

    def build_context(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        max_tokens: int = 35000,
        scene_director: SceneDirectorInput = None,
    ) -> str:
        """构建上下文（使用预算分配器）
        
        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            outline: 章节大纲
            max_tokens: 最大 token 数
            scene_director: 场记（模型或 dict；allocator 内统一为 dict）
        
        Returns:
            组装好的上下文字符串
        """
        allocation = self.budget_allocator.allocate(
            novel_id=novel_id,
            chapter_number=chapter_number,
            outline=outline,
            total_budget=max_tokens,
            scene_director=scene_director,
        )
        
        return allocation.get_final_context()

    def build_structured_context(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        max_tokens: int = 35000,
        scene_director: SceneDirectorInput = None,
    ) -> Dict[str, Any]:
        """构建结构化上下文，返回详细信息
        
        Returns:
            {
                "layer1_text": "核心上下文（T0+T1）",
                "layer2_text": "最近章节（T2）",
                "layer3_text": "向量召回（T3）",
                "token_usage": {
                    "layer1": int,
                    "layer2": int,
                    "layer3": int,
                    "total": int,
                },
            }
        """
        allocation = self.budget_allocator.allocate(
            novel_id=novel_id,
            chapter_number=chapter_number,
            outline=outline,
            total_budget=max_tokens,
            scene_director=scene_director,
        )
        
        # 从 BudgetAllocation 中提取三层内容
        layer1_parts = []
        layer2_parts = []
        layer3_parts = []
        
        layer1_tokens = 0
        layer2_tokens = 0
        layer3_tokens = 0
        
        for name, slot in allocation.slots.items():
            if not slot.content.strip():
                continue
            
            if slot.tier.value in ["t0_critical", "t1_compressible"]:
                layer1_parts.append(f"=== {slot.name.upper()} ===\n{slot.content}")
                layer1_tokens += slot.tokens
            elif slot.tier.value == "t2_dynamic":
                layer2_parts.append(f"=== {slot.name.upper()} ===\n{slot.content}")
                layer2_tokens += slot.tokens
            elif slot.tier.value == "t3_sacrificial":
                layer3_parts.append(f"=== {slot.name.upper()} ===\n{slot.content}")
                layer3_tokens += slot.tokens

        bible_layer2 = self._build_layer2_smart_retrieval(
            novel_id=novel_id,
            chapter_number=chapter_number,
            outline=outline,
            budget=max_tokens,
            scene_director=scene_director,
        )
        if bible_layer2:
            layer2_parts.append(bible_layer2)
            layer2_tokens += self.estimate_tokens(bible_layer2)
        
        return {
            "layer1_text": "\n\n".join(layer1_parts),
            "layer2_text": "\n\n".join(layer2_parts),
            "layer3_text": "\n\n".join(layer3_parts),
            "token_usage": {
                "layer1": layer1_tokens,
                "layer2": layer2_tokens,
                "layer3": layer3_tokens,
                "total": allocation.used_tokens,
            },
        }

    def _build_layer2_smart_retrieval(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        budget: int = 35000,
        scene_director: Optional[Any] = None,
    ) -> str:
        """构建轻量 Bible 切片，补足预算分配器之外的兼容入口。

        该方法不写死具体题材词条：角色由 Bible 当前数据筛选，世界设定由
        scene_director.trigger_keywords 与设定名称、类型、描述做通用匹配。
        """
        bible = self._get_bible_dto(novel_id)
        if not bible:
            return ""

        sections: list[str] = []
        character_text = self._format_pov_safe_characters(bible, chapter_number)
        if character_text:
            sections.append(character_text)

        triggered_settings = self._match_triggered_world_settings(
            bible=bible,
            outline=outline,
            scene_director=scene_director,
        )
        if triggered_settings:
            lines = ["=== Triggered World Settings ==="]
            for item in triggered_settings[:8]:
                name = getattr(item, "name", "") or ""
                setting_type = getattr(item, "setting_type", "") or ""
                description = getattr(item, "description", "") or ""
                head = f"- {name}"
                if setting_type:
                    head += f"（{setting_type}）"
                if description:
                    head += f": {description}"
                lines.append(head)
            sections.append("\n".join(lines))

        return "\n\n".join(part for part in sections if part.strip())

    def _get_bible_dto(self, novel_id: str) -> Optional[Any]:
        getter = getattr(self.bible_service, "get_bible_by_novel", None)
        if not getter:
            return None
        try:
            return getter(novel_id)
        except Exception as exc:
            logger.debug("读取 Bible DTO 失败 novel=%s: %s", novel_id, exc)
            return None

    def _format_pov_safe_characters(self, bible: Any, chapter_number: int) -> str:
        characters = list(getattr(bible, "characters", None) or [])
        if not characters:
            return ""

        lines = ["=== Bible Characters ==="]
        for char in characters[:10]:
            name = getattr(char, "name", "") or ""
            if not name:
                continue
            parts: list[str] = []
            public_profile = getattr(char, "public_profile", "") or ""
            description = getattr(char, "description", "") or ""
            if public_profile:
                parts.append(public_profile)
            elif description:
                parts.append(description)

            hidden_profile = getattr(char, "hidden_profile", "") or ""
            reveal_chapter = getattr(char, "reveal_chapter", None)
            if hidden_profile and (reveal_chapter is None or chapter_number >= int(reveal_chapter)):
                parts.append(f"[隐藏面] {hidden_profile}")

            lines.append(f"- {name}: " + " | ".join(parts))
        return "\n".join(lines) if len(lines) > 1 else ""

    def _match_triggered_world_settings(
        self,
        bible: Any,
        outline: str,
        scene_director: Optional[Any],
    ) -> list[Any]:
        triggers = self._extract_scene_triggers(scene_director)
        if not triggers:
            return []
        settings = list(getattr(bible, "world_settings", None) or [])
        matched = []
        for item in settings:
            text = " ".join(
                str(getattr(item, attr, "") or "")
                for attr in ("name", "setting_type", "description")
            )
            if any(trigger and trigger in text for trigger in triggers):
                matched.append(item)
        return matched

    @staticmethod
    def _extract_scene_triggers(scene_director: Optional[Any]) -> list[str]:
        if scene_director is None:
            return []
        if isinstance(scene_director, dict):
            raw = scene_director.get("trigger_keywords") or []
        else:
            raw = getattr(scene_director, "trigger_keywords", None) or []
        return [str(item).strip() for item in raw if str(item).strip()]

    EXPANSION_HINTS: dict = {}

    # 节拍数量上限：2000字章节目标 5-6拍，给足叙事层次
    MAX_BEATS = 12
    # 每拍最低字数：降低到 350，允许 2000字/350 ≈ 5-6 拍
    # 专业小说家每"场景"约300-500字，节拍间CoT桥接保障连贯性
    MIN_BEAT_WORDS = 350

    def magnify_outline_to_beats(
        self,
        chapter_number: int,
        outline: str,
        target_chapter_words: int = 2500,
        beat_sheet: Optional[Any] = None,
        chapter_execution_plan: Optional[ChapterExecutionPlan] = None,
        scene_director: Optional[Any] = None,
    ) -> List[Beat]:
        """节拍放大器：将章节计划投影为微观节拍。

        入口规则：
        1. 运行时 Beat 的唯一计划来源是 ``ChapterExecutionPlan``。
        2. ``BeatSheet`` 与裸章纲只允许先归一成 ``ChapterExecutionPlan``。
        3. ``micro_beats`` 只作为运行快照/复盘数据，不参与本方法的计划来源。
        """
        plan = self._ensure_chapter_execution_plan(
            chapter_number=chapter_number,
            outline=outline,
            target_chapter_words=target_chapter_words,
            beat_sheet=beat_sheet,
            chapter_execution_plan=chapter_execution_plan,
        )
        beats = self._build_beats_from_execution_plan(plan, outline, target_chapter_words)

        beats = self._cap_and_merge_beats(beats, target_chapter_words)
        self._bind_atg_locations_if_present(beats, scene_director)
        self._attach_cards_if_missing(beats)
        return beats

    def _ensure_chapter_execution_plan(
        self,
        *,
        chapter_number: int,
        outline: str,
        target_chapter_words: int,
        beat_sheet: Optional[Any],
        chapter_execution_plan: Optional[ChapterExecutionPlan],
    ) -> ChapterExecutionPlan:
        if chapter_execution_plan is not None and chapter_execution_plan.atoms:
            return chapter_execution_plan

        from application.engine.dag.plan.outline_beat_planner import build_chapter_execution_plan_sync

        return build_chapter_execution_plan_sync(
            outline or "",
            target_chapter_words=target_chapter_words,
            chapter_number=chapter_number,
            beat_sheet_json=beat_sheet_to_plan_json(beat_sheet),
        )

    def _build_beats_from_execution_plan(
        self,
        plan: ChapterExecutionPlan,
        outline: str,
        target_chapter_words: int,
    ) -> List[Beat]:
        """将 ``ChapterExecutionPlan.atoms`` 投影为微观节拍（须落实章纲意图）。"""
        return beats_from_execution_plan(
            plan,
            outline=outline,
            target_chapter_words=target_chapter_words,
            infer_focus=self._infer_focus_from_outline,
            build_expansion_hints=self._generate_expansion_hints,
        )

    def _bind_atg_locations_if_present(self, beats: List[Beat], scene_director: Optional[Any]) -> None:
        """若场记携带 ATG，将 visit_sequence 映射到各节拍。"""
        if not beats or scene_director is None:
            return
        graph_payload = getattr(scene_director, "action_transition_graph", None)
        if graph_payload is None:
            return
        try:
            from application.engine.services.spatial_coherence import assign_visit_locations_to_beats
        except ImportError:
            return
        seq = list(graph_payload.visit_sequence or [])
        if not seq:
            entry_first = [n.location_id for n in graph_payload.nodes if getattr(n, "is_entry_point", False)]
            seen = set(entry_first)
            tail = [n.location_id for n in graph_payload.nodes if n.location_id and n.location_id not in seen]
            seq = entry_first + tail
        if not seq:
            seq = [n.location_id for n in graph_payload.nodes if getattr(n, "location_id", "").strip()]
        assign_visit_locations_to_beats(beats, seq)

    def _attach_cards_if_missing(self, beats: List[Beat]) -> None:
        """为尚未携带 EmotionBeatCard 的 Beat 生成最小卡片并预渲染 card_prompt_block。

        运行时 Beat 统一由 ChapterExecutionPlan 投影而来；此处只负责补齐
        结构化写作义务，保证所有 Beat 都有 card_prompt_block。
        """
        from application.engine.services.beat_card_renderer import BeatCardPromptRenderer
        renderer = BeatCardPromptRenderer()
        for beat in beats:
            if beat.emotion_beat_card is not None:
                if not beat.card_prompt_block:
                    beat.card_prompt_block = renderer.render(beat.emotion_beat_card)
                continue
            card = self._make_minimal_card(
                beat.scene_goal or beat.description,
                beat.focus,
                beat.target_words,
            )
            beat.emotion_beat_card = card
            beat.card_prompt_block = renderer.render(card)

    def _cap_and_merge_beats(self, beats: List[Beat], target_chapter_words: int) -> List[Beat]:
        """控制节拍数量与最低字数。

        策略：
        1. 若 len(beats) > MAX_BEATS，按均分合并使总数降到 MAX_BEATS。
        2. 若某拍 target_words < MIN_BEAT_WORDS，与下一拍合并（最后一拍与前一拍合并）。
        3. 合并后重新均摊 target_words 使总字数维持接近 target_chapter_words。
        """
        if not beats:
            return beats

        # 步骤 1：超过 MAX_BEATS 时按组合并
        while len(beats) > self.MAX_BEATS:
            # 找到相邻两拍中 target_words 之和最小的组合，合并掉一拍
            min_sum = None
            merge_idx = 0
            for i in range(len(beats) - 1):
                s = beats[i].target_words + beats[i + 1].target_words
                if min_sum is None or s < min_sum:
                    min_sum = s
                    merge_idx = i
            beats = self._merge_two_beats(beats, merge_idx)

        # 步骤 2：每拍 < MIN_BEAT_WORDS 时合并
        changed = True
        while changed and len(beats) > 1:
            changed = False
            for i, b in enumerate(beats):
                if b.target_words < self.MIN_BEAT_WORDS:
                    # 与前一拍或后一拍合并（优先后一拍）
                    merge_idx = i if i < len(beats) - 1 else i - 1
                    beats = self._merge_two_beats(beats, merge_idx)
                    changed = True
                    break

        # 步骤 3：重新均摊 target_words（等比缩放保持各拍权重）
        total_assigned = sum(b.target_words for b in beats)
        if total_assigned > 0 and abs(total_assigned - target_chapter_words) > 200:
            ratio = target_chapter_words / total_assigned
            for b in beats:
                b.target_words = max(self.MIN_BEAT_WORDS, int(b.target_words * ratio))

        logger.info(
            "节拍整形：%d 拍，各拍字数=%s，总目标=%d",
            len(beats),
            [b.target_words for b in beats],
            sum(b.target_words for b in beats),
        )
        return beats

    def _merge_two_beats(self, beats: List[Beat], idx: int) -> List[Beat]:
        """将 beats[idx] 与 beats[idx+1] 合并为一拍，并保留结构化写作义务。"""
        from engine.pipeline.beat_contracts import merge_two_beats

        merged = merge_two_beats(beats[idx], beats[idx + 1])
        return beats[:idx] + [merged] + beats[idx + 2:]

    def _infer_focus_from_outline(self, outline: str) -> str:
        """从大纲推断 focus 类型"""
        return infer_focus_from_outline(outline)

    def _generate_expansion_hints(self, focus: str, target_words: int) -> List[str]:
        """根据 focus 类型和目标字数生成扩写维度提示"""
        return generate_expansion_hints(focus, target_words, self.EXPANSION_HINTS)

    def _make_minimal_card(self, segment: str, focus: str, target_words: int) -> "EmotionBeatCard":
        """用规则模板为大纲片段生成最小 EmotionBeatCard（无 LLM）。

        quality 取决于 segment 的信息密度；ExpandedOutlineService 上线后会替换此函数。
        """
        from infrastructure.ai.prompt_registry import get_prompt_registry

        forbidden = ""
        try:
            reg = get_prompt_registry()
            drifts = reg.get_directives_dict(self._BEAT_PROMPT_ID, "_forbidden_drifts")
            forbidden = drifts.get(focus, drifts.get("default", ""))
        except Exception:
            pass
        return make_minimal_card(segment, focus, target_words, forbidden_drift=forbidden)

    # 节拍聚焦指令：CPMS 节点 beat-focus-instructions（prompt_packages）
    # 通过 PromptRegistry 统一读取，不再在此硬编码
    from infrastructure.ai.prompt_keys import BEAT_FOCUS_INSTRUCTIONS as _BEAT_PROMPT_ID

    def build_beat_prompt(
        self,
        beat: Beat,
        beat_index: int,
        total_beats: int,
        beat_bridge: Optional[Any] = None,
    ) -> str:
        """构建单个节拍的生成提示（指令从 CPMS beat-focus-instructions 读取）

        Args:
            beat: 当前节拍配置
            beat_index: 节拍索引（0-based）
            total_beats: 总节拍数
            beat_bridge: 可选的 BeatBridge 对象，由 beat_cot_bridge 计算，注入连贯性指令
        """
        from infrastructure.ai.prompt_registry import get_prompt_registry

        registry = get_prompt_registry()

        # 聚焦指令字典
        focus_instructions = registry.get_directives_dict(self._BEAT_PROMPT_ID, "_focus_instructions")
        instruction = focus_instructions.get(beat.focus, "")

        # 感官锚点轮转
        sensory_rotation = registry.get_list_field(self._BEAT_PROMPT_ID, "_sensory_rotation")
        if not sensory_rotation:
            # 安全降级
            sensory_rotation = [
                "本节拍至少一处环境锚点：光影或空间层次。",
                "本节拍至少一处环境锚点：温度、体感或材质。",
                "本节拍至少一处环境锚点：声音或节奏。",
                "本节拍至少一处环境锚点：气味或味觉细节。",
            ]
        anchor_line = sensory_rotation[beat_index % len(sensory_rotation)]

        # 叙事义务
        obligations = registry.get_field(self._BEAT_PROMPT_ID, "_obligations", {})
        if isinstance(obligations, dict):
            obligation = obligations.get(beat.focus, obligations.get("default", "叙事义务：推进情节或深化人物。"))
        else:
            obligation = "叙事义务：推进情节或深化人物。"

        # 使用 PromptRegistry 渲染 user 模板
        rendered = registry.render(
            self._BEAT_PROMPT_ID,
            variables={
                "beat_index": beat_index + 1,
                "total_beats": total_beats,
                "target_words": beat.target_words,
                "focus": beat.focus,
                "instruction": instruction,
                "description": beat.description,
                "anchor_line": anchor_line,
                "obligation": obligation,
                "card_block": beat.card_prompt_block or "",
            },
        )
        prompt = (rendered.user if rendered else "") or ""

        from engine.pipeline.generation_prompt_builder import build_director_contract

        director_contract = build_director_contract(beat)
        if director_contract:
            prompt = prompt.replace("━━━ 写前三问", director_contract + "\n\n━━━ 写前三问", 1)

        # 若模板未消费 card_block（旧版 user.md），回退到直接注入
        if beat.card_prompt_block and "{card_block}" not in (rendered.user or "") and beat.card_prompt_block not in prompt:
            prompt = prompt.replace(
                "━━━ 写前三问",
                f"{beat.card_prompt_block}\n\n━━━ 写前三问",
                1,
            )

        # V3：CoT 节拍桥接块（优先级最高，首先注入）
        # beat_bridge 由 beat_cot_bridge.compute_beat_bridge() 在上一节拍完成后计算
        if beat_index > 0 and beat_bridge is not None:
            try:
                bridge_block = beat_bridge.to_prompt_block()
                if bridge_block:
                    prompt = bridge_block + "\n\n" + prompt
            except Exception:
                pass  # 桥接块生成失败不影响主流程

        # V2：注入节拍间过渡方式（仅在无 CoT 桥接时使用，作为降级）
        elif beat_index > 0 and hasattr(beat, 'transition_from_prev') and beat.transition_from_prev:
            transition_block = (
                f"\n\n【本节拍过渡方式】{beat.transition_from_prev}\n"
                f"→ 你的第一句话必须遵循此过渡方式与前节拍衔接"
            )
            prompt = transition_block + prompt

        # V2：第一个节拍特殊处理——如果有前章桥段，强调章首衔接
        if beat_index == 0:
            prompt = "\n这是本章第一个节拍——你的开头就是读者翻页后看到的第一段。必须与前章结尾自然衔接，不能像新故事一样重新开始。\n" + prompt

        # 最后一个节拍特殊处理：强调收尾（双重保障——conductor 也会注入更详细的收尾指令）
        if beat_index == total_beats - 1:
            prompt += "\n\n这是本章最后一个节拍！必须：\n" \
                      "1. 给出完整的章节收尾——故事告一段落，读者能感知到「这一章讲完了」\n" \
                      "2. 可以抛出下一章的悬念钩子，但不要强行总结全章\n" \
                      "3. 用有画面感的方式结束——最后一个画面留在读者脑海中\n" \
                      "4. 绝对不能留下悬而未决的对话或行动"

        return prompt
