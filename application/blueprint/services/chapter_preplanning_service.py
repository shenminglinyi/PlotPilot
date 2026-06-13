"""Chapter pre-planning service.

Generates the seven-section execution script immediately before prose writing.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from application.ai.llm_json_extract import parse_llm_json_to_dict
from application.blueprint.services.chapter_continuity_ledger import ChapterContinuityLedgerService
from application.blueprint.services.chapter_plan_renderer import render_chapter_execution_plan, stringify_plan_value
from application.blueprint.services.chapter_planning_policy import (
    DEFAULT_CHAPTER_PLANNING_POLICY,
    ChapterPlanningPolicy,
    has_rendered_chapter_execution_plan,
)
from domain.ai.services.llm_service import LLMService
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.ai.generation_profiles import generation_config_from_profile
from infrastructure.ai.prompt_contracts.continuous_planning import PLANNING_CHAPTER_PREPLAN_CONTRACT
from infrastructure.ai.prompt_gateway import get_prompt_gateway
from infrastructure.ai.prompt_keys import PLANNING_CHAPTER_PREPLAN

logger = logging.getLogger(__name__)


class ChapterPreplanningService:
    def __init__(
        self,
        *,
        llm_service: LLMService,
        chapter_repository: Any = None,
        story_node_repo: Any = None,
        policy: ChapterPlanningPolicy = DEFAULT_CHAPTER_PLANNING_POLICY,
    ) -> None:
        self.llm_service = llm_service
        self.chapter_repository = chapter_repository
        self.story_node_repo = story_node_repo
        self.policy = policy
        self.ledger_service = ChapterContinuityLedgerService(
            chapter_repository=chapter_repository,
            story_node_repo=story_node_repo,
            policy=policy,
        )

    async def ensure_execution_plan(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        chapter_node: Any = None,
        current_outline: str = "",
        target_words: int | None = None,
    ) -> str:
        """Return a seven-section execution plan, generating it when needed."""
        outline = (current_outline or "").strip()
        if has_rendered_chapter_execution_plan(outline):
            continuity_context = self.ledger_service.build_for_chapter(novel_id, chapter_number).to_planning_context_text()
            self._write_plan_variables(
                novel_id,
                chapter_number,
                outline,
                continuity_context=continuity_context,
            )
            return outline

        node = chapter_node or self._get_chapter_node(novel_id, chapter_number)
        act_plan = self._extract_act_plan(node, outline)
        legacy_plan = self._extract_legacy_chapter_plan(node)
        ledger = self.ledger_service.build_for_chapter(novel_id, chapter_number)
        continuity_context = ledger.to_planning_context_text()
        if legacy_plan and has_rendered_chapter_execution_plan(render_chapter_execution_plan(legacy_plan)):
            rendered = render_chapter_execution_plan(legacy_plan)
            await self._persist_outline(
                novel_id,
                chapter_number,
                node,
                rendered,
                legacy_plan,
                continuity_context=continuity_context,
            )
            return rendered

        title = str(getattr(node, "title", "") or f"第{chapter_number}章")
        prompt = get_prompt_gateway().render(
            PLANNING_CHAPTER_PREPLAN_CONTRACT,
            {
                "chapter_number": chapter_number,
                "chapter_title": title,
                "act_chapter_plan": json.dumps(act_plan, ensure_ascii=False) if isinstance(act_plan, dict) else str(act_plan),
                "continuity_context": continuity_context,
            },
        ).prompt
        config = generation_config_from_profile("planning_chapter_preplan")
        raw = await self._generate_text(prompt, config)
        data, errors = parse_llm_json_to_dict(raw)
        if errors or not isinstance(data, dict):
            raise ValueError("chapter_preplan_requires_json_object: " + "; ".join(errors))

        chapter_plan = data.get("chapter_plan")
        if not isinstance(chapter_plan, dict):
            raise ValueError("chapter_preplan_requires_chapter_plan_object")
        rendered = render_chapter_execution_plan(chapter_plan)
        if not has_rendered_chapter_execution_plan(rendered):
            raise ValueError("chapter_preplan_requires_seven_section_execution_plan")

        key_plot_points = self._normalize_string_list(
            data.get("key_plot_points")
            or data.get("key_points")
            or data.get("critical_plot_points")
        ) or self._derive_key_plot_points(chapter_plan)
        chapter_characters = self._normalize_string_list(
            data.get("chapter_characters")
            or data.get("characters")
            or data.get("cast")
        ) or self._derive_chapter_characters(chapter_plan, act_plan)
        detail_title = str(data.get("detail_title") or title).strip() or title

        await self._persist_outline(
            novel_id,
            chapter_number,
            node,
            rendered,
            chapter_plan,
            detail_title=detail_title,
            key_plot_points=key_plot_points,
            chapter_characters=chapter_characters,
            continuity_context=continuity_context,
        )
        logger.info(
            "[ChapterPreplan] novel=%s chapter=%s generated execution plan chars=%d target_words=%s",
            novel_id,
            chapter_number,
            len(rendered),
            target_words,
        )
        return rendered

    def build_continuity_context(self, novel_id: str, chapter_number: int) -> str:
        return self.ledger_service.build_for_chapter(novel_id, chapter_number).to_planning_context_text()

    async def _generate_text(self, prompt, config) -> str:
        import inspect

        stream = self.llm_service.stream_generate(prompt, config)
        if hasattr(stream, "__aiter__"):
            parts: list[str] = []
            async for chunk in stream:
                parts.append(chunk)
            return "".join(parts)
        close = getattr(stream, "close", None)
        if callable(close):
            close()
        result = self.llm_service.generate(prompt, config)
        if inspect.isawaitable(result):
            result = await result
        return result.content if hasattr(result, "content") else str(result or "")

    def _extract_act_plan(self, node: Any, outline: str) -> dict[str, Any] | str:
        metadata = getattr(node, "metadata", {}) if node is not None else {}
        if isinstance(metadata, dict):
            act_plan = metadata.get("act_chapter_plan")
            if isinstance(act_plan, dict) and act_plan:
                return act_plan
        return {
            "main_event": outline or str(getattr(node, "description", "") or getattr(node, "title", "") or ""),
            "handoff_from_previous": "",
            "handoff_to_next": "",
            "required_threads": [],
            "location_hint": "",
            "cast_hint": [],
        }

    def _extract_legacy_chapter_plan(self, node: Any) -> Any:
        metadata = getattr(node, "metadata", {}) if node is not None else {}
        if isinstance(metadata, dict):
            legacy = metadata.get("chapter_plan")
            if legacy:
                return legacy
            act_plan = metadata.get("act_chapter_plan")
            if isinstance(act_plan, dict) and act_plan.get("chapter_plan"):
                return act_plan.get("chapter_plan")
        return None

    def _get_chapter_node(self, novel_id: str, chapter_number: int):
        if self.story_node_repo is None:
            return None
        try:
            nodes = self.story_node_repo.get_tree(novel_id).nodes
            return next(
                (
                    node for node in nodes
                    if getattr(getattr(node, "node_type", None), "value", "") == "chapter"
                    and int(getattr(node, "number", 0) or 0) == int(chapter_number)
                ),
                None,
            )
        except Exception:
            return None

    async def _persist_outline(
        self,
        novel_id: str,
        chapter_number: int,
        node: Any,
        outline: str,
        chapter_plan: Any,
        *,
        detail_title: str = "",
        key_plot_points: list[str] | None = None,
        chapter_characters: list[str] | None = None,
        continuity_context: str = "",
    ) -> None:
        key_plot_points = key_plot_points or self._derive_key_plot_points(chapter_plan)
        chapter_characters = chapter_characters or self._derive_chapter_characters(chapter_plan, self._extract_act_plan(node, outline))
        preplan_payload = {
            "source_node_key": PLANNING_CHAPTER_PREPLAN,
            "detail_title": detail_title or str(getattr(node, "title", "") or f"第{chapter_number}章"),
            "detail_outline": outline,
            "key_plot_points": key_plot_points,
            "chapter_characters": chapter_characters,
            "continuity_context": continuity_context,
            "chapter_plan": chapter_plan,
        }
        if node is not None:
            try:
                node.outline = outline
                metadata = dict(getattr(node, "metadata", {}) or {})
                metadata["chapter_preplan"] = preplan_payload
                node.metadata = metadata
                update = getattr(self.story_node_repo, "update", None) if self.story_node_repo is not None else None
                if callable(update):
                    await update(node)
            except Exception as exc:
                logger.debug("[ChapterPreplan] story node outline persist failed: %s", exc)

        if self.chapter_repository is not None:
            try:
                novel_id_vo = NovelId(novel_id)
                existing = self.chapter_repository.get_by_novel_and_number(novel_id_vo, chapter_number)
                if existing is not None:
                    existing.outline = outline
                    self.chapter_repository.save(existing)
                elif node is not None:
                    self.chapter_repository.save(
                        Chapter(
                            id=str(getattr(node, "id", f"chapter-{novel_id}-{chapter_number}")),
                            novel_id=novel_id_vo,
                            number=chapter_number,
                            title=str(getattr(node, "title", "") or f"第{chapter_number}章"),
                            content="",
                            outline=outline,
                        )
                    )
            except Exception as exc:
                logger.debug("[ChapterPreplan] chapter outline persist failed: %s", exc)
        self._write_plan_variables(
            novel_id,
            chapter_number,
            outline,
            continuity_context=continuity_context,
        )

    def _write_plan_variables(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        *,
        continuity_context: str,
    ) -> None:
        if not outline:
            return
        try:
            from application.ai_invocation.variable_hub import VariableWrite
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository

            repo = SqliteVariableHubRepository(get_database())
            context_key = f"novel_id:{novel_id}|chapter_number:{chapter_number}"
            writes = [
                VariableWrite(
                    key="chapter.outline",
                    value=outline,
                    context_key=context_key,
                    source_node_key=PLANNING_CHAPTER_PREPLAN,
                    source_trace_id=PLANNING_CHAPTER_PREPLAN,
                    display_name="章节执行剧本",
                    scope="chapter",
                    stage="planning",
                ),
                VariableWrite(
                    key="chapter.continuity_context",
                    value=continuity_context,
                    context_key=context_key,
                    source_node_key=PLANNING_CHAPTER_PREPLAN,
                    source_trace_id=PLANNING_CHAPTER_PREPLAN,
                    display_name="连续性上下文",
                    scope="chapter",
                    stage="planning",
                ),
            ]
            for write in writes:
                repo.set_value(write)
        except Exception as exc:
            logger.debug("[ChapterPreplan] variable hub persist failed: %s", exc)

    @staticmethod
    def _normalize_string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                text = stringify_plan_value(item)
                if text and text not in out:
                    out.append(text)
            return out
        text = stringify_plan_value(value)
        return [text] if text else []

    @classmethod
    def _derive_key_plot_points(cls, chapter_plan: Any) -> list[str]:
        if not isinstance(chapter_plan, dict):
            return []
        events = chapter_plan.get("event_chain") or chapter_plan.get("events") or []
        if not isinstance(events, list):
            return cls._normalize_string_list(events)
        points: list[str] = []
        for item in events:
            text = stringify_plan_value(item)
            if text and text not in points:
                points.append(text)
        return points

    @classmethod
    def _derive_chapter_characters(cls, chapter_plan: Any, act_plan: Any = None) -> list[str]:
        characters: list[str] = []

        def add_many(value: Any) -> None:
            for text in cls._normalize_string_list(value):
                if text and text not in characters:
                    characters.append(text)

        if isinstance(act_plan, dict):
            add_many(act_plan.get("cast_hint") or act_plan.get("characters"))
        if isinstance(chapter_plan, dict):
            for scene in chapter_plan.get("scene_transitions") or chapter_plan.get("scenes") or []:
                if isinstance(scene, dict):
                    add_many(scene.get("cast") or scene.get("characters") or scene.get("roles"))
            for dialogue in chapter_plan.get("key_dialogues") or chapter_plan.get("dialogues") or []:
                if isinstance(dialogue, dict):
                    add_many(dialogue.get("speaker") or dialogue.get("from") or dialogue.get("role"))
                    add_many(dialogue.get("reply_actor"))
        return characters
