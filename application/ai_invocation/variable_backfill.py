"""Backfill existing business facts into Variable Hub."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

from application.ai_invocation.variable_hub import VariableHubRepository, VariableWrite
from application.world.services.bible_setup_invocation import _build_worldbuilding_prompt_fields
from domain.novel.value_objects.novel_id import NovelId

logger = logging.getLogger(__name__)


@dataclass
class VariableHubBackfillResult:
    novels_seen: int = 0
    novels_backfilled: int = 0
    values_written: int = 0
    skipped_existing: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "novels_seen": self.novels_seen,
            "novels_backfilled": self.novels_backfilled,
            "values_written": self.values_written,
            "skipped_existing": self.skipped_existing,
            "errors": list(self.errors),
        }


class VariableHubBackfillService:
    """Idempotently seed Variable Hub from existing read models.

    Backfill never overwrites current Variable Hub values. It only fills missing
    variables so accepted AI outputs remain the newer source of truth.
    """

    def __init__(
        self,
        *,
        variable_hub_repository: VariableHubRepository,
        novel_repository,
        bible_repository=None,
        worldbuilding_repository=None,
    ):
        self._variables = variable_hub_repository
        self._novels = novel_repository
        self._bibles = bible_repository
        self._worldbuilding = worldbuilding_repository

    def backfill_all(self) -> VariableHubBackfillResult:
        result = VariableHubBackfillResult()
        for novel in self._novels.list_all():
            result.novels_seen += 1
            novel_id = self._novel_id(novel)
            if not novel_id:
                continue
            try:
                self.backfill_novel(novel_id=novel_id, result=result, novel=novel)
            except Exception as exc:
                logger.exception("Variable Hub backfill failed for novel=%s", novel_id)
                result.errors.append(f"{novel_id}: {exc}")
        return result

    def backfill_novel(
        self,
        novel_id: str,
        *,
        result: VariableHubBackfillResult | None = None,
        novel: Any = None,
    ) -> VariableHubBackfillResult:
        result = result or VariableHubBackfillResult(novels_seen=1)
        novel = novel if novel is not None else self._novels.get_by_id(NovelId(novel_id))
        if novel is None:
            result.errors.append(f"{novel_id}: novel_not_found")
            return result

        before = result.values_written
        context_key = f"novel_id:{novel_id}"
        self._write_missing(
            result,
            key="novel.setup.title",
            value=str(getattr(novel, "title", "") or ""),
            context_key=context_key,
            value_type="string",
            display_name="名称",
            stage="setup",
        )
        self._write_missing(
            result,
            key="novel.setup.premise",
            value=str(getattr(novel, "premise", "") or ""),
            context_key=context_key,
            value_type="string",
            display_name="设定",
            stage="setup",
        )
        self._write_missing(
            result,
            key="novel.setup.target_chapters",
            value=int(getattr(novel, "target_chapters", 0) or 0),
            context_key=context_key,
            value_type="integer",
            display_name="章节数量",
            stage="setup",
        )
        self._write_missing(
            result,
            key="novel.setup.target_words_per_chapter",
            value=int(getattr(novel, "target_words_per_chapter", 0) or 0),
            context_key=context_key,
            value_type="integer",
            display_name="每章字数",
            stage="setup",
        )

        bible = self._load_bible(novel_id)
        if bible is not None:
            self._backfill_bible(result, novel_id, context_key, bible)
        wb = self._load_worldbuilding(novel_id)
        if wb is not None:
            self._backfill_worldbuilding(result, context_key, wb)

        if result.values_written > before:
            result.novels_backfilled += 1
        return result

    def _backfill_bible(
        self,
        result: VariableHubBackfillResult,
        novel_id: str,
        context_key: str,
        bible: Any,
    ) -> None:
        characters = [self._character_to_dict(item) for item in getattr(bible, "characters", []) or []]
        characters = [item for item in characters if item.get("name")]
        locations = [self._location_to_dict(item) for item in getattr(bible, "locations", []) or []]
        locations = [item for item in locations if item.get("name")]
        style_notes = [
            f"{str(getattr(item, 'category', '') or '').strip()}: {str(getattr(item, 'content', '') or '').strip()}".strip(": ")
            for item in getattr(bible, "style_notes", []) or []
            if str(getattr(item, "content", "") or "").strip()
        ]
        world_lines = [
            f"{str(getattr(item, 'name', '') or '').strip()}: {str(getattr(item, 'description', '') or '').strip()}".strip(": ")
            for item in getattr(bible, "world_settings", []) or []
            if str(getattr(item, "name", "") or getattr(item, "description", "") or "").strip()
        ]

        self._write_missing(
            result,
            key="novel.characters.list",
            value=characters,
            context_key=context_key,
            value_type="list",
            display_name="角色列表",
            stage="characters",
        )
        if characters:
            self._write_missing(
                result,
                key="novel.characters.protagonist",
                value=characters[0],
                context_key=context_key,
                value_type="object",
                display_name="主角",
                stage="characters",
            )
        self._write_missing(
            result,
            key="novel.locations.list",
            value=locations,
            context_key=context_key,
            value_type="list",
            display_name="地点列表",
            stage="locations",
        )
        if style_notes:
            self._write_missing(
                result,
                key="novel.style.guide",
                value="\n".join(style_notes),
                context_key=context_key,
                value_type="string",
                display_name="文风公约",
                stage="setup",
            )
        if world_lines:
            self._write_missing(
                result,
                key="novel.worldbuilding.full",
                value="\n".join(world_lines),
                context_key=context_key,
                value_type="string",
                display_name="世界观全文",
                stage="worldbuilding",
            )

    def _backfill_worldbuilding(self, result: VariableHubBackfillResult, context_key: str, wb: Any) -> None:
        dimensions = wb.normalized_dimensions() if hasattr(wb, "normalized_dimensions") else {}
        if not isinstance(dimensions, Mapping):
            dimensions = {}
        prompt_fields = _build_worldbuilding_prompt_fields(worldbuilding=dimensions)
        self._write_missing(
            result,
            key="novel.worldbuilding.full",
            value=prompt_fields.get("worldbuilding_full", ""),
            context_key=context_key,
            value_type="string",
            display_name="世界观全文",
            stage="worldbuilding",
        )
        for key in ("core_rules", "geography", "society", "culture", "daily_life"):
            value = dimensions.get(key)
            if isinstance(value, Mapping):
                self._write_missing(
                    result,
                    key=f"novel.worldbuilding.{key}",
                    value=dict(value),
                    context_key=context_key,
                    value_type="object",
                    display_name={
                        "core_rules": "核心法则",
                        "geography": "地理生态",
                        "society": "社会结构",
                        "culture": "历史文化",
                        "daily_life": "沉浸感细节",
                    }[key],
                    stage="worldbuilding",
                )

    def _write_missing(
        self,
        result: VariableHubBackfillResult,
        *,
        key: str,
        value: Any,
        context_key: str,
        value_type: str,
        display_name: str,
        stage: str,
    ) -> None:
        if value in (None, "", [], {}):
            return
        if self._variables.get_value(key, context_key) is not None:
            result.skipped_existing += 1
            return
        self._variables.set_value(
            VariableWrite(
                key=key,
                value=value,
                context_key=context_key,
                source_trace_id="historical_backfill",
                source_node_key="variable-hub-backfill",
                lineage={"source": "historical_backfill"},
                value_type=value_type,
                display_name=display_name,
                scope="global",
                stage=stage,
            )
        )
        result.values_written += 1

    def _load_bible(self, novel_id: str) -> Any:
        if self._bibles is None:
            return None
        return self._bibles.get_by_novel_id(NovelId(novel_id))

    def _load_worldbuilding(self, novel_id: str) -> Any:
        if self._worldbuilding is None:
            return None
        return self._worldbuilding.get_by_novel_id(novel_id)

    @staticmethod
    def _novel_id(novel: Any) -> str:
        value = getattr(novel, "novel_id", None)
        if value is not None and hasattr(value, "value"):
            return str(value.value)
        return str(getattr(novel, "id", "") or "")

    @staticmethod
    def _character_to_dict(item: Any) -> dict[str, Any]:
        char_id = getattr(item, "character_id", None)
        return {
            "id": str(getattr(char_id, "value", "") or getattr(item, "id", "") or ""),
            "name": str(getattr(item, "name", "") or ""),
            "description": str(getattr(item, "description", "") or ""),
            "relationships": list(getattr(item, "relationships", []) or []),
            "public_profile": str(getattr(item, "public_profile", "") or ""),
            "hidden_profile": str(getattr(item, "hidden_profile", "") or ""),
            "reveal_chapter": getattr(item, "reveal_chapter", None),
            "mental_state": str(getattr(item, "mental_state", "") or "NORMAL"),
            "mental_state_reason": str(getattr(item, "mental_state_reason", "") or ""),
            "verbal_tic": str(getattr(item, "verbal_tic", "") or ""),
            "idle_behavior": str(getattr(item, "idle_behavior", "") or ""),
            "core_belief": str(getattr(item, "core_belief", "") or ""),
            "moral_taboos": list(getattr(item, "moral_taboos", []) or []),
            "voice_profile": dict(getattr(item, "voice_profile", {}) or {}),
            "active_wounds": list(getattr(item, "active_wounds", []) or []),
        }

    @staticmethod
    def _location_to_dict(item: Any) -> dict[str, Any]:
        return {
            "id": str(getattr(item, "id", "") or ""),
            "name": str(getattr(item, "name", "") or ""),
            "description": str(getattr(item, "description", "") or ""),
            "type": str(getattr(item, "location_type", "") or getattr(item, "type", "") or ""),
            "parent_id": getattr(item, "parent_id", None),
        }
