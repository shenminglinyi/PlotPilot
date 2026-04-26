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
from typing import List, Optional, TYPE_CHECKING, Dict, Any
from dataclasses import dataclass

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

if TYPE_CHECKING:
    from application.engine.dtos.scene_director_dto import SceneDirectorAnalysis

logger = logging.getLogger(__name__)


@dataclass
class Beat:
    """微观节拍（Beat）
    
    将章节大纲拆分为多个微观节拍，强制 AI 放慢节奏，增加感官细节。
    """
    description: str  # 节拍描述
    target_words: int  # 目标字数
    focus: str  # 聚焦点：sensory（感官）、dialogue（对话）、action（动作）、emotion（情绪）


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

        # 预算分配器（核心组件）
        self.budget_allocator = ContextBudgetAllocator(
            foreshadowing_repository=foreshadowing_repository,
            chapter_repository=chapter_repository,
            bible_repository=bible_repository,
            story_node_repository=story_node_repository,
            chapter_element_repository=chapter_element_repository,
            triple_repository=triple_repository,
            vector_store=vector_store,
            embedding_service=embedding_service,
        )

    def build_voice_anchor_system_section(self, novel_id: str) -> str:
        """Bible 角色声线/小动作锚点"""
        return self.bible_service.build_character_voice_anchor_section(novel_id)

    def build_context(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        max_tokens: int = 35000,
        scene_director: Optional[Dict[str, Any]] = None,
    ) -> str:
        """构建上下文（使用预算分配器）
        
        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            outline: 章节大纲
            max_tokens: 最大 token 数
            scene_director: 场记分析结果（可选）
        
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
        scene_director: Optional[Dict[str, Any]] = None,
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

    def magnify_outline_to_beats(self, chapter_number: int, outline: str, target_chapter_words: int = 2500) -> List[Beat]:
        """节拍放大器：将章节大纲拆分为微观节拍
        
        核心策略：
        1. 识别大纲中的关键动作/事件
        2. 为每个动作分配节拍，强制增加感官细节
        3. 控制单章推进速度，避免节奏过载
        """
        beats = []

        # 开篇黄金法则前三章特殊拦截
        if chapter_number == 1:
            beats = [
                Beat(description="开篇黄金法则：展现核心冲突，介绍主角出场，建立情感冲击（前300字内必须抓住读者）", target_words=500, focus="hook"),
                Beat(description="剧情引入及人物初步互动：展现主角特质并暗示即将发生的事件", target_words=1000, focus="character_intro"),
                Beat(description="世界观或当前场景细节：通过具体行动展现，不用抽象叙述", target_words=800, focus="sensory"),
                Beat(description="埋下后续剧情伏笔或抛出首个悬念：铺垫第二章", target_words=700, focus="suspense"),
            ]
        elif chapter_number == 2:
            beats = [
                Beat(description="承接首章悬念：深化关键人物关系，展现性格差异", target_words=800, focus="dialogue"),
                Beat(description="推进主要情节线：引入新的次要冲突或阻碍", target_words=1200, focus="action"),
                Beat(description="情绪细节及内心活动：展示人物面对变故的真实反映", target_words=600, focus="emotion"),
                Beat(description="为第三章冲突高潮做气氛铺垫", target_words=400, focus="suspense"),
            ]
        elif chapter_number == 3:
            beats = [
                Beat(description="前三章的剧情小结或高潮前奏：紧张气氛描写", target_words=600, focus="sensory"),
                Beat(description="冲突爆发/悬念高潮：激烈的动作或对峙", target_words=1200, focus="action"),
                Beat(description="暴露深层问题或引出更高层面人物背景", target_words=800, focus="emotion"),
                Beat(description="建立长线悬念结局：为整卷后续发展铺设巨大好奇心", target_words=400, focus="suspense"),
            ]
        # 根据常规关键词回退
        elif "争吵" in outline or "冲突" in outline or "质问" in outline:
            beats = [
                Beat(description="场景氛围描写：压抑的环境、紧张的气氛、人物的微表情", target_words=500, focus="sensory"),
                Beat(description="冲突爆发：主角的质问、对方的反应、情绪的升级", target_words=800, focus="dialogue"),
                Beat(description="情绪细节：内心独白、回忆闪回、痛苦的挣扎", target_words=700, focus="emotion"),
                Beat(description="冲突结果：决裂、离开、或暂时妥协（不要轻易和好）", target_words=500, focus="action"),
            ]
        elif "战斗" in outline or "打斗" in outline or "对决" in outline:
            beats = [
                Beat(description="战前准备：环境描写、双方对峙、紧张的气氛", target_words=400, focus="sensory"),
                Beat(description="第一回合：试探性攻击、展示能力、观察弱点", target_words=600, focus="action"),
                Beat(description="战斗升级：全力以赴、招式碰撞、环境破坏", target_words=700, focus="action"),
                Beat(description="转折点：意外发生、底牌揭露、或受伤", target_words=500, focus="emotion"),
                Beat(description="战斗结束：胜负揭晓、战后状态、后续影响", target_words=300, focus="action"),
            ]
        elif "发现" in outline or "真相" in outline or "揭露" in outline:
            beats = [
                Beat(description="线索汇聚：主角回忆之前的疑点、逐步推理", target_words=700, focus="emotion"),
                Beat(description="真相揭露：关键证据出现、震惊的反应、世界观崩塌", target_words=1000, focus="dialogue"),
                Beat(description="情绪余波：接受现实、决定下一步行动", target_words=800, focus="emotion"),
            ]
        else:
            # 默认：四章拍「起承转合」，用信息义务占满篇幅，减少空泛水词
            beats = [
                Beat(
                    description="起：交代场景与人物状态，抛出本章要处理的具体麻烦或悬念（可小但须清晰）。",
                    target_words=500,
                    focus="sensory",
                ),
                Beat(
                    description="承：阻碍升级或对手施压，人物关系或信息出现新变化。",
                    target_words=500,
                    focus="dialogue",
                ),
                Beat(
                    description="转：主角做出选择、亮出底牌或发现盲点，情节出现可感知的转折。",
                    target_words=500,
                    focus="action",
                ),
                Beat(
                    description="合：阶段性结果落地，同时抛出下一章钩子（勿提前剧透全书谜底）。",
                    target_words=500,
                    focus="suspense",
                ),
            ]

        # 调整字数分配（保守策略）
        # LLM 倾向于超出字数要求，因此 prompt 中只要求目标的 75%
        # 配合 max_tokens = target × 1.1（硬性上限），强制控制字数
        total_words = sum(b.target_words for b in beats)
        prompt_target_ratio = 0.75  # prompt 中只要求 75%
        if total_words != target_chapter_words:
            ratio = (target_chapter_words * prompt_target_ratio) / total_words
            for beat in beats:
                beat.target_words = int(beat.target_words * ratio)

        logger.info(
            f"节拍放大器：将大纲拆分为 {len(beats)} 个节拍，"
            f"prompt 目标 {sum(b.target_words for b in beats)} 字（实际目标 {target_chapter_words} 字的 {int(prompt_target_ratio * 100)}%）"
        )
        return beats

    # 节拍聚焦指令已迁移至 prompts_defaults.json (id=beat-focus-instructions)
    # 通过 PromptLoader 统一读取，不再在此硬编码
    _BEAT_PROMPT_ID = "beat-focus-instructions"

    def build_beat_prompt(self, beat: Beat, beat_index: int, total_beats: int) -> str:
        """构建单个节拍的生成提示（指令从 prompts_defaults.json 统一读取）"""
        from infrastructure.ai.prompt_loader import get_prompt_loader

        loader = get_prompt_loader()

        # 聚焦指令字典
        focus_instructions = loader.get_directives_dict(self._BEAT_PROMPT_ID, "_focus_instructions")
        instruction = focus_instructions.get(beat.focus, "")

        # 感官锚点轮转
        sensory_rotation = loader.get_list_field(self._BEAT_PROMPT_ID, "_sensory_rotation")
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
        obligations = loader.get_field(self._BEAT_PROMPT_ID, "_obligations", {})
        if isinstance(obligations, dict):
            obligation = obligations.get(beat.focus, obligations.get("default", "叙事义务：推进情节或深化人物。"))
        else:
            obligation = "叙事义务：推进情节或深化人物。"

        # 使用 PromptLoader 渲染模板
        return loader.render(self._BEAT_PROMPT_ID, template_field="user_template", variables={
            "beat_index": beat_index + 1,
            "total_beats": total_beats,
            "target_words": beat.target_words,
            "focus": beat.focus,
            "instruction": instruction,
            "description": beat.description,
            "anchor_line": anchor_line,
            "obligation": obligation,
        })
