"""WritingOrchestrator — 写作编排器

核心职责：将新engine组件（质量守门人/Checkpoint/角色灵魂/剧情状态机/情绪账本）
编排成完整的写作流程，接入现有 auto_novel_generation_workflow。

写作流程：
1. 获取/创建Story → PlotStateMachine确定阶段
2. 构建角色面具(CharacterMask) → 注入T0层
3. 调LLM生成章节内容
4. QualityGuardrail六维检查
5. 通过 → 创建Checkpoint + 更新EmotionLedger + 更新伏笔状态
6. 不通过 → 返回修正建议，重写

与现有系统的桥接：
- 复用 auto_novel_generation_workflow 的 LLM 调用能力
- 新增质量守门人拦截、Checkpoint自动保存、角色面具动态计算
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from engine.application.quality_guardrails.quality_guardrail import (
    QualityGuardrail, QualityReport, QualityViolationError,
)
from engine.application.plot_state_machine.state_machine import PlotStateMachine
from engine.core.entities.story import Story, StoryPhase
from engine.core.entities.character import Character
from engine.core.entities.foreshadow import Foreshadow, ForeshadowStatus, ForeshadowBinding
from engine.core.value_objects.character_mask import CharacterMask
from engine.core.value_objects.checkpoint import Checkpoint, CheckpointId, CheckpointType
from engine.core.value_objects.emotion_ledger import (
    EmotionLedger, EmotionalWound, EmotionalBoon, PowerShift, OpenLoop,
)

logger = logging.getLogger(__name__)


@dataclass
class ChapterResult:
    """单章写作结果"""
    chapter_number: int
    content: str = ""
    quality_report: Optional[QualityReport] = None
    checkpoint_id: Optional[CheckpointId] = None
    phase: StoryPhase = StoryPhase.OPENING
    emotion_ledger: Optional[EmotionLedger] = None
    active_foreshadows: List[Foreshadow] = field(default_factory=list)
    character_masks: Dict[str, CharacterMask] = field(default_factory=dict)
    word_count: int = 0
    quality_passed: bool = False
    rewrite_count: int = 0


class WritingOrchestrator:
    """写作编排器

    编排完整的写作流程，是跑文的核心引擎。
    不直接调用LLM，而是接收LLM生成的内容进行后处理。

    使用方式：
    ```python
    orchestrator = WritingOrchestrator()

    # 1. 初始化故事
    story = orchestrator.init_story(title="仙途", premise="...", target_chapters=100)

    # 2. 每章写作
    result = orchestrator.process_chapter(
        story=story,
        chapter_number=1,
        content=llm_generated_content,
        outline="本章大纲...",
    )

    # 3. 检查结果
    if result.quality_passed:
        # 保存Checkpoint，继续下一章
        ...
    else:
        # 获取修正建议，重写
        suggestions = result.quality_report.all_violations
    ```
    """

    MAX_REWRITE_ATTEMPTS = 2  # 最大重写次数

    def __init__(self):
        self.quality_guardrail = QualityGuardrail()
        self.plot_state_machine = PlotStateMachine()

    def init_story(
        self,
        title: str,
        premise: str,
        target_chapters: int = 100,
        characters: List[Character] = None,
    ) -> Story:
        """初始化故事"""
        story = Story.create(
            title=title,
            premise=premise,
            target_chapters=target_chapters,
        )
        if characters:
            for char in characters:
                story.add_character(char)
        return story

    def process_chapter(
        self,
        story: Story,
        chapter_number: int,
        content: str,
        outline: str = "",
        character_names: List[str] = None,
        scene_info: Dict[str, Any] = None,
        foreshadows: List[Dict[str, Any]] = None,
        era: str = "ancient",
        scene_type: str = "auto",
    ) -> ChapterResult:
        """处理单章内容

        完整流程：
        1. 更新Story阶段
        2. 计算角色面具
        3. 质量检查
        4. 生成结果

        Args:
            story: 故事实体
            chapter_number: 章节号
            content: LLM生成的章节内容
            outline: 章节大纲
            character_names: 角色名列表（用于命名检查）
            scene_info: 场景信息（用于视角检查）
            foreshadows: 活跃伏笔列表
            era: 时代背景
            scene_type: 场景类型

        Returns:
            ChapterResult
        """
        # 1. 更新Story阶段
        story.advance_plot(event={
            "type": "chapter_completed",
            "chapter_number": chapter_number,
        })
        story.update_phase()

        # 2. 计算角色面具
        character_masks = self._compute_character_masks(story)

        # 3. 质量检查
        quality_report = self.quality_guardrail.check(
            text=content,
            character_masks=character_masks if character_masks else None,
            chapter_goal=outline,
            character_names=character_names,
            scene_info=scene_info,
            foreshadows=foreshadows,
            era=era,
            scene_type=scene_type,
        )

        # 4. 生成结果
        result = ChapterResult(
            chapter_number=chapter_number,
            content=content,
            quality_report=quality_report,
            phase=story.story_phase,
            character_masks=character_masks,
            word_count=len(content),
            quality_passed=quality_report.passed,
        )

        return result

    def create_checkpoint(
        self,
        story: Story,
        chapter_number: int,
        trigger_type: CheckpointType = CheckpointType.CHAPTER,
        trigger_reason: str = "",
        content: str = "",
        character_masks: Dict[str, CharacterMask] = None,
        emotion_ledger: EmotionLedger = None,
        active_foreshadows: List[str] = None,
        parent_id: CheckpointId = None,
    ) -> Checkpoint:
        """创建Checkpoint"""
        return Checkpoint.create(
            story_id=story.story_id.value,
            trigger_type=trigger_type,
            trigger_reason=trigger_reason or f"第{chapter_number}章完成",
            story_state={
                "chapter": chapter_number,
                "phase": story.story_phase.value,
                "title": story.title,
            },
            character_masks={
                k: {"name": v.name, "core_belief": v.core_belief, "voice_style": v.voice_style}
                for k, v in (character_masks or {}).items()
            } if character_masks else {},
            emotion_ledger=emotion_ledger.to_dict() if emotion_ledger else {},
            active_foreshadows=active_foreshadows or [],
            parent_id=parent_id,
        )

    def build_quality_context(
        self,
        story: Story,
        chapter_number: int,
        character_masks: Dict[str, CharacterMask] = None,
    ) -> Dict[str, Any]:
        """构建质量检查所需的上下文

        将Story和角色信息组装为QualityGuardrail.check所需的参数
        """
        return {
            "character_masks": character_masks,
            "era": "ancient",
            "scene_type": "auto",
            "character_names": [c.name for c in story.characters] if story.characters else None,
        }

    def get_phase_instruction(self, story: Story) -> str:
        """获取当前阶段的T0层注入指令"""
        # 同步PlotStateMachine到Story的阶段
        self.plot_state_machine._current_phase = story.story_phase
        return self.plot_state_machine.get_phase_instruction()

    def get_chapter_budget(self, story: Story) -> Dict[str, Any]:
        """获取当前阶段的章节预算"""
        self.plot_state_machine._current_phase = story.story_phase
        return self.plot_state_machine.get_chapter_budget()

    def should_trigger_act_checkpoint(
        self,
        story: Story,
        chapter_number: int,
    ) -> bool:
        """判断是否应该触发幕切换Checkpoint"""
        if story.target_chapters <= 0:
            return False
        progress = story.compute_progress()
        # 25%和75%是两个关键转折点
        thresholds = [0.25, 0.75]
        for t in thresholds:
            prev_chapter = chapter_number - 1
            prev_progress = prev_chapter / story.target_chapters if story.target_chapters > 0 else 0
            if prev_progress < t <= progress:
                return True
        return False

    def _compute_character_masks(self, story: Story) -> Dict[str, CharacterMask]:
        """计算所有角色的当前面具"""
        masks = {}
        for char in story.characters:
            mask_dict = char.compute_mask()
            mask = CharacterMask.from_character_dict(
                mask_dict,
                chapter_number=story.current_chapter,
            )
            masks[char.character_id.value] = mask
        return masks

    def generate_novelist_assessment(
        self,
        results: List[ChapterResult],
    ) -> Dict[str, Any]:
        """生成小说家角度的评估报告

        从专业小说家视角评估：
        1. 语言风格纯度 — 去AI味程度
        2. 角色辨识度 — 是否各有声线
        3. 情节推进效率 — 每章信息密度
        4. 伏笔管理 — 埋设/苏醒/回收节奏
        5. 叙事节奏 — 张力曲线
        6. 整体文学性 — 白描/暗喻/动作密度
        """
        if not results:
            return {"error": "无章节结果"}

        total_words = sum(r.word_count for r in results)
        passed_count = sum(1 for r in results if r.quality_passed)
        total_violations = sum(
            len(r.quality_report.all_violations) for r in results if r.quality_report
        )

        # 各维度平均分
        avg_style = 0.0
        avg_consistency = 0.0
        avg_density = 0.0
        avg_viewpoint = 0.0
        avg_rhythm = 0.0
        count = len(results)

        for r in results:
            if r.quality_report:
                avg_style += r.quality_report.language_style_score
                avg_consistency += r.quality_report.character_consistency_score
                avg_density += r.quality_report.plot_density_score
                avg_viewpoint += r.quality_report.viewpoint_score
                avg_rhythm += r.quality_report.rhythm_score

        if count > 0:
            avg_style /= count
            avg_consistency /= count
            avg_density /= count
            avg_viewpoint /= count
            avg_rhythm /= count

        # 评级
        overall = (avg_style * 0.25 + avg_consistency * 0.25 +
                   avg_density * 0.20 + avg_viewpoint * 0.10 + avg_rhythm * 0.20)

        grade = "S" if overall >= 0.9 else "A" if overall >= 0.8 else "B" if overall >= 0.7 else "C" if overall >= 0.6 else "D"

        # 收集所有违规类型
        violation_types = {}
        for r in results:
            if r.quality_report:
                for v in r.quality_report.all_violations:
                    dim = v.get("dimension", "unknown")
                    typ = v.get("type", "unknown")
                    key = f"{dim}.{typ}"
                    violation_types[key] = violation_types.get(key, 0) + 1

        return {
            "grade": grade,
            "overall_score": round(overall, 3),
            "total_chapters": count,
            "total_words": total_words,
            "avg_words_per_chapter": total_words // max(count, 1),
            "quality_pass_rate": passed_count / max(count, 1),
            "total_violations": total_violations,
            "scores": {
                "language_style": round(avg_style, 3),
                "character_consistency": round(avg_consistency, 3),
                "plot_density": round(avg_density, 3),
                "viewpoint": round(avg_viewpoint, 3),
                "rhythm": round(avg_rhythm, 3),
            },
            "top_violations": dict(
                sorted(violation_types.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
            "chapters": [
                {
                    "chapter": r.chapter_number,
                    "word_count": r.word_count,
                    "quality_passed": r.quality_passed,
                    "overall_score": r.quality_report.overall_score if r.quality_report else 0,
                    "phase": r.phase.value,
                }
                for r in results
            ],
        }
