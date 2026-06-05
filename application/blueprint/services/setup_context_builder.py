"""Shared setup-guide context builder backed by Variable Hub."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from application.core.services.novel_service import NovelService
from application.engine.theme.fusion_profile import FusionProfile, get_fusion_profile
from application.world.services.bible_service import BibleService


class SetupContextBuilder:
    def __init__(self, *, bible_service: BibleService, novel_service: NovelService):
        self._bible_service = bible_service
        self._novel_service = novel_service

    def build_context(self, novel_id: str) -> Dict[str, Any]:
        novel = self._novel_service.get_novel(novel_id)
        variable_context = self._load_variable_context(novel_id)

        title = str(variable_context.get("novel_title") or "").strip()
        premise = str(variable_context.get("premise") or "").strip()
        target_chapters = self._as_int(variable_context.get("target_chapters"), default=100)
        target_words_per_chapter = self._as_int(variable_context.get("target_words_per_chapter"), default=0)
        theme_metadata = self._theme_metadata_from_novel(novel)
        theme_metadata.update(variable_context.get("theme_metadata") or {})

        fusion_profile = self._resolve_fusion_profile(theme_metadata)
        fusion_contract = str(variable_context.get("fusion_contract") or "").strip()

        protagonist = self._coerce_dict(variable_context.get("protagonist")) or None
        characters = self._coerce_list(variable_context.get("characters"))
        locations = self._coerce_list(variable_context.get("locations"))
        style_hint = str(variable_context.get("style_hint") or "").strip()

        worldbuilding = self._coerce_dict(variable_context.get("worldbuilding_content"))
        core_rules = self._coerce_dict(variable_context.get("core_rules"))
        geography = self._coerce_dict(variable_context.get("geography"))
        society = self._coerce_dict(variable_context.get("society"))
        culture = self._coerce_dict(variable_context.get("culture"))
        daily_life = self._coerce_dict(variable_context.get("daily_life"))

        if not worldbuilding:
            worldbuilding = {
                key: value
                for key, value in (
                    ("core_rules", core_rules),
                    ("geography", geography),
                    ("society", society),
                    ("culture", culture),
                    ("daily_life", daily_life),
                )
                if value
            }
        if worldbuilding:
            core_rules = self._coerce_dict(worldbuilding.get("core_rules")) or core_rules
            geography = self._coerce_dict(worldbuilding.get("geography")) or geography
            society = self._coerce_dict(worldbuilding.get("society")) or society
            culture = self._coerce_dict(worldbuilding.get("culture")) or culture
            daily_life = self._coerce_dict(worldbuilding.get("daily_life")) or daily_life

        if protagonist is None and characters:
            first = characters[0]
            protagonist = dict(first) if isinstance(first, Mapping) else None
        other_characters = list(characters)
        if protagonist is not None:
            protagonist_name = str(protagonist.get("name") or "").strip()
            other_characters = [
                item
                for item in characters
                if not protagonist_name or str(item.get("name") or "").strip() != protagonist_name
            ]

        worldview_summary = self._worldview_summary(worldbuilding)
        return {
            "novel_title": title,
            "premise": premise,
            "target_chapters": target_chapters,
            "target_words_per_chapter": target_words_per_chapter,
            "theme_metadata": theme_metadata,
            "fusion_axis": self._fusion_axis_payload(fusion_profile),
            "fusion_contract": fusion_contract,
            "protagonist": protagonist,
            "characters": characters[:8],
            "other_characters": other_characters[:8],
            "locations": locations[:10],
            "worldview_summary": worldview_summary,
            "style_hint": style_hint[:1200],
            "worldbuilding": worldbuilding,
            "core_rules": core_rules,
            "geography": geography,
            "society": society,
            "culture": culture,
            "daily_life": daily_life,
        }

    @staticmethod
    def _load_variable_context(novel_id: str) -> Dict[str, Any]:
        try:
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository

            variable_repo = SqliteVariableHubRepository(get_database())
        except Exception:
            return {}

        novel_context_key = f"novel_id:{novel_id}"
        context: Dict[str, Any] = {}
        for key, target in (
            ("novel.title", "novel_title"),
            ("novel.premise", "premise"),
            ("novel.target_chapters", "target_chapters"),
            ("novel.target_words_per_chapter", "target_words_per_chapter"),
            ("novel.genre_label", "theme_metadata.genre_label"),
            ("novel.world_preset", "theme_metadata.world_preset"),
            ("novel.story_structure", "theme_metadata.story_structure"),
            ("novel.pacing_control", "theme_metadata.pacing_control"),
            ("novel.writing_style", "theme_metadata.writing_style"),
            ("novel.special_requirements", "theme_metadata.special_requirements"),
            ("characters.protagonist", "protagonist"),
            ("characters.list", "characters"),
            ("locations.list", "locations"),
            ("plot.fusion_contract", "fusion_contract"),
            ("worldbuilding.style", "style_hint"),
            ("worldbuilding.content", "worldbuilding_content"),
            ("worldbuilding.core_rules", "core_rules"),
            ("worldbuilding.geography", "geography"),
            ("worldbuilding.society", "society"),
            ("worldbuilding.culture", "culture"),
            ("worldbuilding.daily_life", "daily_life"),
        ):
            value = variable_repo.get_value(key, novel_context_key)
            if value is None:
                continue
            if target == "theme_metadata.genre_label":
                context.setdefault("theme_metadata", {})["genre_label"] = str(value.value or "")
            elif target == "theme_metadata.world_preset":
                context.setdefault("theme_metadata", {})["world_preset"] = str(value.value or "")
            elif target == "theme_metadata.story_structure":
                context.setdefault("theme_metadata", {})["story_structure"] = str(value.value or "")
            elif target == "theme_metadata.pacing_control":
                context.setdefault("theme_metadata", {})["pacing_control"] = str(value.value or "")
            elif target == "theme_metadata.writing_style":
                context.setdefault("theme_metadata", {})["writing_style"] = str(value.value or "")
            elif target == "theme_metadata.special_requirements":
                context.setdefault("theme_metadata", {})["special_requirements"] = str(value.value or "")
            else:
                context[target] = value.value
        return context

    @staticmethod
    def _coerce_dict(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _coerce_list(value: Any) -> List[Dict[str, Any]]:
        items = value if isinstance(value, list) else list(value) if isinstance(value, tuple) else []
        return [dict(item) for item in items if isinstance(item, Mapping)]

    @staticmethod
    def _as_int(value: Any, *, default: int) -> int:
        try:
            parsed = int(value or 0)
        except (TypeError, ValueError):
            parsed = 0
        return parsed if parsed > 0 else default

    @staticmethod
    def _worldview_summary(worldbuilding: Mapping[str, Any]) -> List[str]:
        labels = {
            "core_rules": "核心法则",
            "geography": "地理生态",
            "society": "社会结构",
            "culture": "历史文化",
            "daily_life": "沉浸感细节",
        }
        lines: List[str] = []
        for key, label in labels.items():
            value = worldbuilding.get(key)
            if isinstance(value, Mapping) and value:
                lines.append(f"{label}: {str(value)[:500]}")
        return lines[:10]

    @staticmethod
    def _theme_metadata_from_novel(novel: Any) -> Dict[str, Any]:
        if not novel:
            return {}
        secondary = getattr(novel, "secondary_theme_keys", []) or []
        return {
            "genre_label": (getattr(novel, "genre_label", "") or getattr(novel, "locked_genre", "") or "").strip(),
            "world_preset": (getattr(novel, "world_preset", "") or getattr(novel, "locked_world_preset", "") or "").strip(),
            "story_structure": (
                getattr(novel, "story_structure", "") or getattr(novel, "locked_story_structure", "") or ""
            ).strip(),
            "pacing_control": (
                getattr(novel, "pacing_control", "") or getattr(novel, "locked_pacing_control", "") or ""
            ).strip(),
            "writing_style": (
                getattr(novel, "writing_style", "") or getattr(novel, "locked_writing_style", "") or ""
            ).strip(),
            "special_requirements": (
                getattr(novel, "special_requirements", "") or getattr(novel, "locked_special_requirements", "") or ""
            ).strip(),
            "primary_theme_key": (getattr(novel, "primary_theme_key", "") or "").strip(),
            "secondary_theme_keys": [str(x).strip() for x in secondary if str(x).strip()],
            "fusion_profile_key": (getattr(novel, "fusion_profile_key", "") or "").strip(),
            "market_track_label": (getattr(novel, "market_track_label", "") or "").strip(),
        }

    @staticmethod
    def _resolve_fusion_profile(theme_metadata: Dict[str, Any]) -> Optional[FusionProfile]:
        return get_fusion_profile(theme_metadata.get("fusion_profile_key"))

    @staticmethod
    def _fusion_axis_payload(profile: Optional[FusionProfile]) -> Dict[str, Any]:
        if profile is None:
            return {}
        axis = profile.axis_lock
        return {
            "label": profile.label,
            "core_promise": axis.core_promise,
            "central_conflict": axis.central_conflict,
            "false_mystery": axis.false_mystery,
            "true_mystery": axis.true_mystery,
            "forbidden_mainline_competitors": list(axis.forbidden_mainline_competitors),
            "taboos": list(profile.taboos),
        }
