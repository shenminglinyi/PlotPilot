"""ThemedStoryPipeline — 将 ThemeAgent 注入 BaseStoryPipeline 的桥接基类

老 ThemeAgent 体系（context/audit/beat 指令）通过此类接入新管线，
无需重写 10 步流程。
"""
from __future__ import annotations

import logging
from typing import Optional

from engine.pipeline.base import BaseStoryPipeline
from engine.pipeline.context import PipelineContext
from engine.pipeline.steps import StepResult

logger = logging.getLogger(__name__)


class ThemedStoryPipeline(BaseStoryPipeline):
    """题材感知管线 — 自动注入 ThemeAgent 的上下文与审计规则"""

    _default_genre_key: str = ""

    def __init__(self, genre_key: str = ""):
        super().__init__()
        self._genre_key = genre_key or self._default_genre_key

    @property
    def genre_key(self) -> str:
        return self._genre_key

    def _get_theme_agent(self):
        if not self.genre_key:
            return None
        try:
            from application.engine.theme.theme_registry import ThemeAgentRegistry

            registry = ThemeAgentRegistry()
            if not registry.registered_keys:
                registry.auto_discover()
            return registry.get(self.genre_key)
        except Exception as e:
            logger.debug("加载 ThemeAgent 失败 genre=%s: %s", self.genre_key, e)
            return None

    async def _step_build_context(self, ctx: PipelineContext) -> StepResult:
        result = await super()._step_build_context(ctx)
        if not result.passed:
            return result

        agent = self._get_theme_agent()
        if agent is None:
            return result

        try:
            directives = agent.get_effective_context_directives(
                ctx.novel_id, ctx.chapter_number, ctx.outline or ""
            )
            directive_text = directives.to_context_text()
            if directive_text:
                ctx.context_text += f"\n\n{directive_text}"

            persona = agent.get_effective_system_persona()
            if persona:
                ctx.context_text += f"\n\n【题材人设】\n{persona}"

            rules = agent.get_effective_writing_rules()
            if rules:
                numbered = "\n".join(f"- {rule}" for rule in rules)
                ctx.context_text += f"\n\n【题材写作规则】\n{numbered}"

            skills_text = agent.invoke_skills_context(
                ctx.novel_id,
                ctx.chapter_number,
                ctx.outline or "",
                ctx.context_text,
            )
            if skills_text:
                ctx.context_text += f"\n\n{skills_text}"
        except Exception as e:
            logger.warning("ThemeAgent 上下文注入失败 genre=%s: %s", self.genre_key, e)

        return result

    async def _step_validate_content(self, ctx: PipelineContext) -> StepResult:
        result = await super()._step_validate_content(ctx)
        agent = self._get_theme_agent()
        if agent is None or not ctx.chapter_content:
            return result

        try:
            criteria = agent.get_audit_criteria(ctx.chapter_number, ctx.outline or "")
            for check in criteria.quality_checks:
                ctx.validation_violations.append({
                    "dimension": self.genre_key or "theme",
                    "type": "theme_audit",
                    "severity": 0.5,
                    "description": check,
                    "suggestion": "对照题材审计标准修订本章",
                })

            skill_checks = agent.invoke_skills_audit(
                ctx.chapter_number, ctx.chapter_content, ctx.outline or ""
            )
            for check in skill_checks:
                ctx.validation_violations.append({
                    "dimension": self.genre_key or "theme",
                    "type": "theme_skill_audit",
                    "severity": 0.5,
                    "description": check,
                    "suggestion": "对照题材 Skill 审计项修订本章",
                })
        except Exception as e:
            logger.warning("ThemeAgent 审计注入失败 genre=%s: %s", self.genre_key, e)

        return result

    def _enrich_script_context(self, ctx: PipelineContext) -> None:
        """若大纲命中题材节拍模板，将模板指令注入剧本生成上下文。"""
        agent = self._get_theme_agent()
        if agent is None or not ctx.outline:
            return

        templates = agent.get_beat_templates()
        if not templates:
            return

        outline = ctx.outline
        matched = sorted(templates, key=lambda t: t.priority, reverse=True)
        for template in matched:
            if any(kw in outline for kw in template.keywords):
                beat_instructions = "\n".join(
                    f"- {desc}（约{words}字，聚焦{focus}）"
                    for desc, words, focus in template.beats
                )
                ctx.context_text += (
                    f"\n\n【题材节拍指令（融入导演剧本）】\n"
                    f"在撰写导演剧本时，请确保以下节拍在场景中体现：\n"
                    f"{beat_instructions}"
                )
                break
