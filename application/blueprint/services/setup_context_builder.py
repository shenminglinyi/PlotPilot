"""Shared setup-guide context builder for planning-stage invocations."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional

from application.ai_invocation.variable_hub import VariableWrite
from application.core.services.novel_service import NovelService
from application.core.taxonomy.opening_profiles import resolve_opening_profile
from application.world.services.bible_service import BibleService
from application.engine.theme.fusion_profile import FusionProfile, get_fusion_profile

logger = logging.getLogger(__name__)


class SetupContextBuilder:
    def __init__(self, *, bible_service: BibleService, novel_service: NovelService):
        self._bible_service = bible_service
        self._novel_service = novel_service

    def build_context(self, novel_id: str) -> Dict[str, Any]:
        novel = self._novel_service.get_novel(novel_id)
        bible_dto = self._bible_service.get_bible_by_novel(novel_id)
        variable_context = self._load_variable_context(novel_id)
        self._backfill_worldbuilding_context_from_table(novel_id, variable_context)

        premise = str(variable_context.get("premise") or "").strip()
        title = str(variable_context.get("novel_title") or "").strip()
        target_chapters = int(variable_context.get("target_chapters") or 0)
        target_words_per_chapter = int(variable_context.get("target_words_per_chapter") or 0)
        if not premise and novel:
            premise = (novel.premise or "").strip()
        if not title and novel:
            title = (novel.title or "").strip()
        if target_chapters <= 0 and novel:
            target_chapters = int(novel.target_chapters or 100)
        if target_chapters <= 0:
            target_chapters = 100
        theme_metadata = self._theme_metadata_from_novel(novel)
        theme_metadata.update(variable_context.get("theme_metadata") or {})
        genre_profile = {
            "genre_opening_profile": self._coerce_dict(variable_context.get("genre_opening_profile")),
            "genre_reader_contract": self._coerce_dict(variable_context.get("genre_reader_contract")),
            "genre_rhythm_constraints": self._coerce_dict(variable_context.get("genre_rhythm_constraints")),
        }
        if not all(genre_profile.values()):
            resolved_profile = resolve_opening_profile(str(theme_metadata.get("genre_label") or ""), strict=False)
            if resolved_profile is not None:
                genre_profile = resolved_profile.as_variables()
        fusion_profile = self._resolve_fusion_profile(theme_metadata, title, premise)
        fusion_contract = str(variable_context.get("fusion_contract") or "").strip()
        if not fusion_contract:
            fusion_contract = self._fusion_storyline_contract(fusion_profile)

        protagonist = self._coerce_dict(variable_context.get("protagonist")) or None
        characters = self._coerce_list(variable_context.get("characters"))
        other_chars = self._coerce_list(variable_context.get("other_characters")) or list(characters)
        locations = self._coerce_list(variable_context.get("locations"))
        worldview_summary = self._coerce_list(variable_context.get("worldview_summary"))
        world_lines: List[str] = [str(item).strip() for item in worldview_summary if str(item).strip()]
        core_rules = self._coerce_dict(variable_context.get("core_rules"))
        geography = self._coerce_dict(variable_context.get("geography"))
        society = self._coerce_dict(variable_context.get("society"))
        culture = self._coerce_dict(variable_context.get("culture"))
        daily_life = self._coerce_dict(variable_context.get("daily_life"))
        style_hint = str(variable_context.get("style_hint") or "").strip()

        if bible_dto:
            chars = bible_dto.characters or []
            if protagonist is None:
                prot_idx: Optional[int] = None
                for i, c in enumerate(chars):
                    role = (getattr(c, "role", None) or "").strip()
                    if "主角" in role or role.lower() in ("protagonist", "main", "mc", "主人公"):
                        prot_idx = i
                        break
                if prot_idx is None and chars:
                    prot_idx = 0
                if prot_idx is not None and chars:
                    c = chars[prot_idx]
                    protagonist = {
                        "name": (c.name or "").strip(),
                        "role": (getattr(c, "role", None) or "").strip(),
                        "description": (c.description or "")[:800],
                    }
                    for j, ch in enumerate(chars):
                        if j == prot_idx:
                            continue
                        other_chars.append(
                            {
                                "name": (ch.name or "").strip(),
                                "role": (getattr(ch, "role", None) or "").strip(),
                                "description": (ch.description or "")[:800],
                            }
                        )

            if not locations:
                for loc in (bible_dto.locations or [])[:8]:
                    locations.append(
                        {
                            "name": (loc.name or "").strip(),
                            "type": (
                                getattr(loc, "location_type", None)
                                or getattr(loc, "type", None)
                                or ""
                            ).strip(),
                            "description": (loc.description or "")[:400],
                        }
                    )

            if not world_lines:
                for ws in bible_dto.world_settings or []:
                    name = (ws.name or "").strip()
                    description = (ws.description or "").strip()
                    if name or description:
                        world_lines.append(f"{name}: {description}"[:500])

            if not style_hint:
                notes = bible_dto.style_notes or []
                if notes:
                    style_hint = "；".join((f"{n.category}: {n.content}"[:200] for n in notes[:5] if n.content))

        try:
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository

            variable_repo = SqliteVariableHubRepository(get_database())
            novel_context_key = f"novel_id:{novel_id}"
            for key, target in (
                ("novel.characters.protagonist", "protagonist"),
                ("novel.characters.list", "characters"),
                ("novel.locations.list", "locations"),
                ("novel.plot.fusion_contract", "fusion_contract"),
                ("novel.worldbuilding.core_rules", "core_rules"),
                ("novel.worldbuilding.geography", "geography"),
                ("novel.worldbuilding.society", "society"),
                ("novel.worldbuilding.culture", "culture"),
                ("novel.worldbuilding.daily_life", "daily_life"),
                ("novel.style.guide", "style_hint"),
            ):
                value = variable_repo.get_value(key, novel_context_key)
                if value is None:
                    continue
                if target == "protagonist" and isinstance(value.value, dict) and protagonist is None:
                    protagonist = dict(value.value)
                elif target == "characters" and isinstance(value.value, list):
                    hub_characters = [dict(item) for item in value.value if isinstance(item, dict)]
                    if not characters:
                        characters = hub_characters
                    if not other_chars:
                        other_chars = list(hub_characters)
                elif target == "locations" and isinstance(value.value, list) and not locations:
                    locations = [dict(item) for item in value.value if isinstance(item, dict)]
                elif target == "fusion_contract" and not fusion_contract:
                    fusion_contract = str(value.value or "").strip()
                elif target == "core_rules" and isinstance(value.value, dict) and not core_rules:
                    core_rules = dict(value.value)
                elif target == "geography" and isinstance(value.value, dict) and not geography:
                    geography = dict(value.value)
                elif target == "society" and isinstance(value.value, dict) and not society:
                    society = dict(value.value)
                elif target == "culture" and isinstance(value.value, dict) and not culture:
                    culture = dict(value.value)
                elif target == "daily_life" and isinstance(value.value, dict) and not daily_life:
                    daily_life = dict(value.value)
                elif target == "style_hint" and not style_hint:
                    style_hint = str(value.value or "").strip()
        except Exception:
            pass

        if not style_hint and bible_dto:
            notes = bible_dto.style_notes or []
            if notes:
                style_hint = "；".join((f"{n.category}: {n.content}"[:200] for n in notes[:5] if n.content))

        if not characters:
            characters = list(other_chars)
            if protagonist:
                protagonist_name = str(protagonist.get("name") or "").strip()
                if protagonist_name and not any(
                    str(item.get("name") or "").strip() == protagonist_name for item in characters
                ):
                    characters = [protagonist, *characters]

        return {
            "novel_title": title,
            "premise": premise,
            "target_chapters": target_chapters,
            "target_words_per_chapter": target_words_per_chapter,
            "theme_metadata": theme_metadata,
            "fusion_axis": self._fusion_axis_payload(fusion_profile),
            "fusion_contract": fusion_contract,
            **genre_profile,
            "protagonist": protagonist,
            "characters": characters[:8],
            "other_characters": other_chars[:6],
            "locations": locations,
            "worldview_summary": world_lines[:24],
            "style_hint": style_hint[:1200],
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
            ("novel.setup.title", "novel_title"),
            ("novel.setup.premise", "premise"),
            ("novel.setup.target_chapters", "target_chapters"),
            ("novel.setup.target_words_per_chapter", "target_words_per_chapter"),
            ("novel.setup.genre_label", "theme_metadata.genre_label"),
            ("novel.setup.world_preset", "theme_metadata.world_preset"),
            ("novel.characters.protagonist", "protagonist"),
            ("novel.characters.list", "characters"),
            ("novel.locations.list", "locations"),
            ("novel.plot.fusion_contract", "fusion_contract"),
            ("novel.worldbuilding.core_rules", "core_rules"),
            ("novel.worldbuilding.geography", "geography"),
            ("novel.worldbuilding.society", "society"),
            ("novel.worldbuilding.culture", "culture"),
            ("novel.worldbuilding.daily_life", "daily_life"),
            ("novel.style.guide", "style_hint"),
        ):
            value = variable_repo.get_value(key, novel_context_key)
            if value is None:
                continue
            if target == "theme_metadata.genre_label":
                context.setdefault("theme_metadata", {})["genre_label"] = str(value.value or "")
            elif target == "theme_metadata.world_preset":
                context.setdefault("theme_metadata", {})["world_preset"] = str(value.value or "")
            else:
                context[target] = value.value
        return context

    @staticmethod
    def _backfill_worldbuilding_context_from_table(novel_id: str, context: Dict[str, Any]) -> None:
        if all(
            isinstance(context.get(key), Mapping) and context.get(key)
            for key in ("core_rules", "geography", "society", "culture", "daily_life")
        ):
            return
        try:
            from application.paths import get_db_path
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository
            from infrastructure.persistence.database.worldbuilding_repository import WorldbuildingRepository

            wb = WorldbuildingRepository(get_db_path()).get_by_novel_id(novel_id)
            if wb is None:
                return
            dimensions = wb.normalized_dimensions() if hasattr(wb, "normalized_dimensions") else {}
            if not isinstance(dimensions, Mapping):
                return
            updates: dict[str, tuple[Any, str, str]] = {
                "core_rules": (dict(dimensions.get("core_rules") or {}), "novel.worldbuilding.core_rules", "object"),
                "geography": (dict(dimensions.get("geography") or {}), "novel.worldbuilding.geography", "object"),
                "society": (dict(dimensions.get("society") or {}), "novel.worldbuilding.society", "object"),
                "culture": (dict(dimensions.get("culture") or {}), "novel.worldbuilding.culture", "object"),
                "daily_life": (dict(dimensions.get("daily_life") or {}), "novel.worldbuilding.daily_life", "object"),
            }
            display_names = {
                "core_rules": "核心法则",
                "geography": "地理生态",
                "society": "社会结构",
                "culture": "历史文化",
                "daily_life": "沉浸感细节",
            }
            variable_repo = SqliteVariableHubRepository(get_database())
            context_key = f"novel_id:{novel_id}"
            for alias, (value, variable_key, value_type) in updates.items():
                if value in (None, "", [], {}):
                    continue
                if not isinstance(context.get(alias), Mapping) or not context.get(alias):
                    context[alias] = value
                stored = variable_repo.get_value(variable_key, context_key)
                if stored is None or stored.value in (None, "", [], {}):
                    variable_repo.set_value(
                        VariableWrite(
                            key=variable_key,
                            value=value,
                            context_key=context_key,
                            source_trace_id="setup_context_backfill",
                            source_node_key="worldbuilding-table",
                            lineage={"source": "worldbuilding_table", "alias": alias},
                            value_type=value_type,
                            display_name=display_names[alias],
                            scope="global",
                            stage="worldbuilding",
                        )
                    )
        except Exception:
            logger.exception("Failed to backfill worldbuilding context from table: novel=%s", novel_id)

    @staticmethod
    def _coerce_dict(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _coerce_list(value: Any) -> List[Any]:
        if isinstance(value, list):
            return list(value)
        if isinstance(value, tuple):
            return list(value)
        return []

    @staticmethod
    def _theme_metadata_from_novel(novel: Any) -> Dict[str, Any]:
        if not novel:
            return {}
        secondary = getattr(novel, "secondary_theme_keys", []) or []
        return {
            "genre_label": (getattr(novel, "genre_label", "") or getattr(novel, "locked_genre", "") or "").strip(),
            "world_preset": (getattr(novel, "world_preset", "") or getattr(novel, "locked_world_preset", "") or "").strip(),
            "primary_theme_key": (getattr(novel, "primary_theme_key", "") or "").strip(),
            "secondary_theme_keys": [str(x).strip() for x in secondary if str(x).strip()],
            "fusion_profile_key": (getattr(novel, "fusion_profile_key", "") or "").strip(),
            "market_track_label": (getattr(novel, "market_track_label", "") or "").strip(),
        }

    @staticmethod
    def _resolve_fusion_profile(
        theme_metadata: Dict[str, Any],
        title: str,
        premise: str,
    ) -> Optional[FusionProfile]:
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

    @staticmethod
    def _fusion_storyline_contract(profile: Optional[FusionProfile]) -> str:
        if profile is None:
            return ""
        return (
            profile.to_context_text()
            + "\n\n【故事线推演硬约束】\n"
            + "1. 三条主线候选都必须围绕叙事主轴锁展开，不能把表层谜团抬成第一主线。\n"
            + "2. 每条候选都要写清：主角如果不行动，会失去什么具体东西。\n"
            + "3. 支线只能作为主线的误导、证据链、人物代价或阶段性阻碍，不能另起炉灶。\n"
            + "4. 角色功能锁优先于临时爽点，不能为了反转让角色无铺垫换阵营/换功能。"
        )
