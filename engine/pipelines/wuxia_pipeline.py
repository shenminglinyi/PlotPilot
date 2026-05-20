"""WuxiaPipeline — 武侠引擎（正式版）

继承 ThemedStoryPipeline，自动注入 WuxiaThemeAgent 的上下文/审计规则，
并追加武侠专属的节拍与内容验证逻辑。
"""
from __future__ import annotations

import logging
import re
from typing import Any

from engine.pipelines.themed_pipeline import ThemedStoryPipeline
from engine.pipeline.context import PipelineContext
from engine.pipeline.steps import StepResult

logger = logging.getLogger(__name__)


class WuxiaPipeline(ThemedStoryPipeline):
    """武侠引擎 — 修炼体系 + 战斗编排 + 江湖规矩"""

    _default_genre_key = "wuxia"

    DEFAULT_TARGET_WORDS = 3000
    MIN_PASS_SCORE = 0.55
    BATCH_WRITE_INTERVAL = 3

    COMBAT_SCENE_MAX_WORDS = 800
    CULTIVATION_DETAIL_LEVEL = "full"

    async def _step_build_context(self, ctx: PipelineContext) -> StepResult:
        """注入 ThemeAgent 规则 + 武侠补充约束"""
        result = await super()._step_build_context(ctx)

        wuxia_rules = (
            "\n\n【武侠补充规则】\n"
            "1. 同境界看功法，跨境界需有合理铺垫，禁止无铺垫一招秒杀\n"
            "2. 对白半文半白，禁止现代网络用语\n"
            "3. 打斗一招一式有名字，简洁有力，不堆砌形容词\n"
        )
        ctx.context_text += wuxia_rules

        if ctx.knowledge_service is not None:
            try:
                knowledge = ctx.knowledge_service.get_knowledge(ctx.novel_id)
                if knowledge and hasattr(knowledge, "cultivation_system"):
                    ctx.context_text += f"\n\n【修炼体系】\n{knowledge.cultivation_system}"
            except Exception:
                pass

        return result

    async def _step_magnify_beats(self, ctx: PipelineContext) -> StepResult:
        result = await super()._step_magnify_beats(ctx)
        self._apply_theme_beat_templates(ctx)

        for beat in ctx.beats:
            if not hasattr(beat, "focus"):
                continue
            description = getattr(beat, "description", "")
            if beat.focus == "action" and "打" in description:
                beat.target_words = min(
                    getattr(beat, "target_words", self.COMBAT_SCENE_MAX_WORDS),
                    self.COMBAT_SCENE_MAX_WORDS,
                )
            if beat.focus == "emotion" and "修炼" in description:
                beat.target_words = int(getattr(beat, "target_words", 800) * 1.5)

        return result

    async def _step_validate_content(self, ctx: PipelineContext) -> StepResult:
        result = await super()._step_validate_content(ctx)

        content = ctx.chapter_content
        if not content:
            return result

        one_hit_patterns = [
            r"一招.{0,4}(秒杀|击杀|击毙|毙命)",
            r"随手一.{0,2}(毙|杀|灭)",
        ]
        for pattern in one_hit_patterns:
            if re.search(pattern, content):
                ctx.validation_violations.append({
                    "dimension": "wuxia",
                    "type": "combat_logic",
                    "severity": 0.7,
                    "description": "出现无铺垫的一招秒杀，可能违反武功逻辑",
                    "suggestion": "如确需秒杀，前面应有充分铺垫（暗器/毒/偷袭/境界碾压）",
                })
                break

        modern_words = ["搞定", "没毛病", "杠杠的", "绝绝子", "yyds", "666", "离谱"]
        for word in modern_words:
            if word in content:
                ctx.validation_violations.append({
                    "dimension": "wuxia",
                    "type": "modern_slang",
                    "severity": 0.8,
                    "description": f"武侠文中出现现代口语：{word}",
                    "suggestion": "替换为古白话表达",
                })

        return result
