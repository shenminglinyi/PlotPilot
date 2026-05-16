"""WuxiaPipeline — 武侠引擎

武侠引擎的核心差异：
1. 注入修炼体系设定
2. 战斗编排增强（感官+动作焦点）
3. 江湖规矩/门派体系/武功逻辑
4. 命名规范更严格（复姓推荐、古风名字）
5. 节奏：打斗简洁有力，修炼层次分明

继承 BaseStoryPipeline，只改了3个方法。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from engine.pipeline.base import BaseStoryPipeline
from engine.pipeline.context import PipelineContext
from engine.pipeline.steps import StepResult

logger = logging.getLogger(__name__)


class WuxiaPipeline(BaseStoryPipeline):
    """武侠引擎 — 修炼体系 + 战斗编排 + 江湖规矩

    使用方式：
        pipeline = WuxiaPipeline()
        result = await pipeline.run_chapter(ctx)
    """

    # ─── 调参 ───
    DEFAULT_TARGET_WORDS = 3000        # 武侠章回更长
    MIN_PASS_SCORE = 0.55              # 武侠对语言风格更宽容（古白话允许更多变）
    BATCH_WRITE_INTERVAL = 3

    # ─── 武侠专属配置 ───
    COMBAT_SCENE_MAX_WORDS = 800       # 打斗场景不超过800字
    CULTIVATION_DETAIL_LEVEL = "full"  # 修炼描写详细度: minimal / normal / full

    def _step_build_context(self, ctx: PipelineContext) -> StepResult:
        """覆写：注入武侠世界观和修炼体系"""
        result = super()._step_build_context(ctx)

        wuxia_rules = (
            "\n\n【武侠世界观规则】\n"
            "1. 武功境界：炼气→筑基→金丹→元婴→化神（每个境界差距巨大）\n"
            "2. 战斗规则：同境界看功法，跨境界看机缘，绝不以弱胜强（除非有合理铺垫）\n"
            "3. 江湖规矩：师徒如父子，同门不残杀，叛师者天下共诛\n"
            "4. 命名规范：古风名字，复姓推荐（欧阳、司马、慕容），不出现现代名字\n"
            "5. 对白风格：古白话，半文半白，不用现代口语\n"
            "6. 打斗描写：简洁有力，一招一式有名字，不堆砌形容词\n"
        )
        ctx.context_text += wuxia_rules

        # 注入修炼体系设定（如果有）
        if ctx.knowledge_service is not None:
            try:
                knowledge = ctx.knowledge_service.get_knowledge(ctx.novel_id)
                if knowledge and hasattr(knowledge, 'cultivation_system'):
                    ctx.context_text += f"\n\n【修炼体系】\n{knowledge.cultivation_system}"
            except Exception:
                pass

        return result

    def _step_magnify_beats(self, ctx: PipelineContext) -> StepResult:
        """覆写：武侠节拍调整（战斗场景更短更有力）"""
        result = super()._step_magnify_beats(ctx)

        for beat in ctx.beats:
            if not hasattr(beat, 'focus'):
                continue
            # 战斗节拍：字数更少，焦点强制为 action
            if beat.focus == 'action' and '打' in getattr(beat, 'description', ''):
                beat.target_words = min(
                    getattr(beat, 'target_words', self.COMBAT_SCENE_MAX_WORDS),
                    self.COMBAT_SCENE_MAX_WORDS,
                )
            # 修炼节拍：允许更长
            if beat.focus == 'emotion' and '修炼' in getattr(beat, 'description', ''):
                beat.target_words = int(getattr(beat, 'target_words', 800) * 1.5)

        return result

    def _step_validate_content(self, ctx: PipelineContext) -> StepResult:
        """覆写：追加武侠专属验证"""
        result = super()._step_validate_content(ctx)

        content = ctx.chapter_content
        if not content:
            return result

        # 武功逻辑验证：是否出现跨境界碾压但无铺垫
        import re
        # 检测"一招秒杀"类描写（可能违反武功逻辑）
        one_hit_patterns = [
            r'一招.{0,4}(秒杀|击杀|击毙|毙命)',
            r'随手一.{0,2}(毙|杀|灭)',
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

        # 古白话检查：是否混入现代口语
        modern_words = ["搞定", "没毛病", "杠杠的", "绝绝子", "yyds", "666", "离谱"]
        for word in modern_words:
            if word in content:
                ctx.validation_violations.append({
                    "dimension": "wuxia",
                    "type": "modern_slang",
                    "severity": 0.8,
                    "description": f"武侠文中出现现代口语：{word}",
                    "suggestion": f"替换为古白话表达",
                })

        return result
