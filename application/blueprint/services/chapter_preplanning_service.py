"""Chapter pre-planning service.

Generates the seven-section execution script immediately before prose writing.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from application.ai.llm_json_extract import parse_llm_json_to_dict
from application.blueprint.services.chapter_continuity_ledger import ChapterContinuityLedgerService
from application.blueprint.services.chapter_plan_renderer import render_chapter_execution_plan
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
            return outline

        node = chapter_node or self._get_chapter_node(novel_id, chapter_number)
        act_plan = self._extract_act_plan(node, outline)
        legacy_plan = self._extract_legacy_chapter_plan(node)
        if legacy_plan and has_rendered_chapter_execution_plan(render_chapter_execution_plan(legacy_plan)):
            rendered = render_chapter_execution_plan(legacy_plan)
            await self._persist_outline(novel_id, chapter_number, node, rendered, legacy_plan)
            return rendered

        ledger = self.ledger_service.build_for_chapter(novel_id, chapter_number)
        title = str(getattr(node, "title", "") or f"第{chapter_number}章")
        prompt = get_prompt_gateway().render(
            PLANNING_CHAPTER_PREPLAN_CONTRACT,
            {
                "chapter_number": chapter_number,
                "chapter_title": title,
                "act_chapter_plan": json.dumps(act_plan, ensure_ascii=False) if isinstance(act_plan, dict) else str(act_plan),
                "continuity_ledger": ledger.to_prompt_text(),
                "previous_ending": ledger.previous_ending,
                "recent_chapters": json.dumps(ledger.recent_events, ensure_ascii=False),
                "character_state": "、".join(ledger.character_state),
                "unresolved_threads": "、".join(ledger.unresolved_threads),
                "legacy_chapter_plan": json.dumps(legacy_plan, ensure_ascii=False) if legacy_plan else "",
            },
        ).prompt
        config = generation_config_from_profile("planning_chapter_preplan")
        raw = await self._generate_text(prompt, config)
        data, errors = parse_llm_json_to_dict(raw)
        if errors or not isinstance(data, dict):
            raise ValueError("chapter_preplan_requires_json_object: " + "; ".join(errors))

        chapter_plan = data.get("chapter_plan")
        rendered = render_chapter_execution_plan(chapter_plan)
        outline_from_model = str(data.get("outline") or "").strip()
        if not rendered and has_rendered_chapter_execution_plan(outline_from_model):
            rendered = outline_from_model
        if not has_rendered_chapter_execution_plan(rendered):
            raise ValueError("chapter_preplan_requires_seven_section_execution_plan")

        await self._persist_outline(novel_id, chapter_number, node, rendered, chapter_plan)
        logger.info(
            "[ChapterPreplan] novel=%s chapter=%s generated execution plan chars=%d target_words=%s",
            novel_id,
            chapter_number,
            len(rendered),
            target_words,
        )
        return rendered

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

    async def _persist_outline(self, novel_id: str, chapter_number: int, node: Any, outline: str, chapter_plan: Any) -> None:
        if node is not None:
            try:
                node.outline = outline
                metadata = dict(getattr(node, "metadata", {}) or {})
                metadata["chapter_preplan"] = {
                    "source_node_key": PLANNING_CHAPTER_PREPLAN,
                    "chapter_plan": chapter_plan,
                }
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
        self._write_plan_variables(novel_id, chapter_number, outline)

    def _write_plan_variables(self, novel_id: str, chapter_number: int, outline: str) -> None:
        if not outline:
            return
        try:
            from application.ai_invocation.variable_hub import VariableWrite
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository

            repo = SqliteVariableHubRepository(get_database())
            repo.set_value(
                VariableWrite(
                    key="chapter.outline",
                    value=outline,
                    context_key=f"novel_id:{novel_id}|chapter_number:{chapter_number}",
                    source_node_key=PLANNING_CHAPTER_PREPLAN,
                    source_trace_id=PLANNING_CHAPTER_PREPLAN,
                    display_name="章节执行剧本",
                    scope="chapter",
                    stage="planning",
                )
            )
        except Exception as exc:
            logger.debug("[ChapterPreplan] variable hub persist failed: %s", exc)
