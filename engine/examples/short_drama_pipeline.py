"""ShortDramaPipeline — 短剧引擎

短剧引擎的核心差异：
1. 每章更短（1500字 vs 默认2500字）
2. 节拍更紧凑（每拍最多500字）
3. 强制3分钟反转
4. 对话占比>60%
5. 对声线更宽容（阈值0.5 vs 默认0.68）

继承 BaseStoryPipeline，只改了4个方法和几个类属性。
"""
from __future__ import annotations

import logging
from typing import Any

from engine.pipeline.base import BaseStoryPipeline
from engine.pipeline.context import PipelineContext
from engine.pipeline.steps import StepResult

logger = logging.getLogger(__name__)


class ShortDramaPipeline(BaseStoryPipeline):
    """短剧引擎 — 每3分钟一个反转，节奏极快

    使用方式：
        pipeline = ShortDramaPipeline()
        result = await pipeline.run_chapter(ctx)
    """

    # ─── 调参（覆盖基类属性） ───
    DEFAULT_TARGET_WORDS = 1500
    VOICE_REWRITE_THRESHOLD = 0.5      # 短剧对声线更宽容
    VOICE_REWRITE_MAX_ATTEMPTS = 1     # 改写轮数少（快）
    MIN_PASS_SCORE = 0.5               # 短剧质量门槛更低
    BATCH_WRITE_INTERVAL = 2           # 更频繁地写库

    # ─── 短剧专属规则 ───
    FORCE_REVERSAL_INTERVAL = 3        # 每3个节拍必须有一个反转
    MIN_DIALOGUE_RATIO = 0.6           # 对话占比下限
    MAX_BEAT_WORDS = 500               # 每拍最多500字

    def _step_build_context(self, ctx: PipelineContext) -> StepResult:
        """覆写：注入短剧强制规则"""
        result = super()._step_build_context(ctx)

        short_drama_rules = (
            "\n\n【短剧强制规则】\n"
            "1. 每3分钟必须有一个反转（读者永远猜不到下一步）\n"
            "2. 对话占比必须>60%（少描写，多说话）\n"
            "3. 任何场景不超过500字（快节奏）\n"
            "4. 每章必须以悬念结尾（钩子）\n"
            "5. 角色情绪转换要快（一秒变脸）\n"
        )
        ctx.context_text += short_drama_rules
        return result

    def _step_magnify_beats(self, ctx: PipelineContext) -> StepResult:
        """覆写：缩短每拍字数，增加反转节拍"""
        result = super()._step_magnify_beats(ctx)

        # 限制每拍字数
        for beat in ctx.beats:
            if hasattr(beat, 'target_words'):
                beat.target_words = min(beat.target_words, self.MAX_BEAT_WORDS)
            if hasattr(beat, 'focus'):
                # 每隔3拍强制一个反转焦点
                beat_index = ctx.beats.index(beat)
                if (beat_index + 1) % self.FORCE_REVERSAL_INTERVAL == 0:
                    beat.focus = 'action'  # 反转用动作焦点
                    if hasattr(beat, 'description'):
                        beat.description = f"【反转】{beat.description}"

        return result

    def _build_generation_prompt(self, ctx: PipelineContext, beat: Any, beat_index: int) -> str:
        """覆写：短剧 prompt 模板"""
        prompt = super()._build_generation_prompt(ctx, beat, beat_index)

        # 在反转节拍注入额外指令
        if (beat_index + 1) % self.FORCE_REVERSAL_INTERVAL == 0:
            prompt += (
                "\n\n⚠️【反转节拍】这是第{}拍，必须是反转！"
                "读者的预期必须被打破。上一拍建立的认知必须被颠覆。".format(beat_index + 1)
            )

        # 最后一拍：强制悬念结尾
        if beat_index == len(ctx.beats) - 1:
            prompt += "\n\n⚠️【章节结尾】必须以悬念结尾！让读者忍不住点下一章！"

        return prompt

    def _step_validate_content(self, ctx: PipelineContext) -> StepResult:
        """覆写：追加短剧专属验证"""
        result = super()._step_validate_content(ctx)

        # 对话占比检查
        content = ctx.chapter_content
        if content:
            dialogue_chars = sum(1 for c in content if c in '""「」『』')
            dialogue_ratio = dialogue_chars / max(len(content), 1)
            if dialogue_ratio < self.MIN_DIALOGUE_RATIO * 0.5:  # 宽松检查
                ctx.validation_violations.append({
                    "dimension": "short_drama",
                    "type": "low_dialogue_ratio",
                    "severity": 0.5,
                    "description": f"对话占比仅{dialogue_ratio:.0%}，短剧要求>{self.MIN_DIALOGUE_RATIO:.0%}",
                    "suggestion": "增加角色对话，减少心理描写和环境描写",
                })

        return result
