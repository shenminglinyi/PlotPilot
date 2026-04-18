"""ForeshadowingRegistry 数据映射器"""
from typing import Dict, Any
from datetime import datetime
from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
from domain.novel.entities.subtext_ledger_entry import SubtextLedgerEntry
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.foreshadowing import (
    Foreshadowing,
    ForeshadowingStatus,
    ImportanceLevel,
)


class ForeshadowingMapper:
    """ForeshadowingRegistry 实体与字典数据之间的映射器"""

    @staticmethod
    def _to_int(value: Any, field_name: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{field_name} must be an integer")
        try:
            return int(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{field_name} must be an integer, got {value!r}") from e

    @staticmethod
    def _to_optional_int(value: Any, field_name: str) -> Any:
        if value in (None, ""):
            return None
        return ForeshadowingMapper._to_int(value, field_name)

    @staticmethod
    def to_dict(registry: ForeshadowingRegistry) -> Dict[str, Any]:
        return {
            "id": registry.id,
            "novel_id": registry.novel_id.value,
            "foreshadowings": [
                {
                    "id": f.id,
                    "planted_in_chapter": f.planted_in_chapter,
                    "description": f.description,
                    "importance": f.importance.value,
                    "status": f.status.value,
                    "suggested_resolve_chapter": f.suggested_resolve_chapter,
                    "resolved_in_chapter": f.resolved_in_chapter,
                }
                for f in registry.foreshadowings
            ],
            "subtext_entries": [
                {
                    "id": e.id,
                    "chapter": e.chapter,
                    "character_id": e.character_id,
                    "question": e.question,
                    "status": e.status,
                    "consumed_at_chapter": e.consumed_at_chapter,
                    "created_at": e.created_at.isoformat(),
                    "suggested_resolve_chapter": getattr(e, "suggested_resolve_chapter", None),
                    "resolve_chapter_window": getattr(e, "resolve_chapter_window", None),
                    "importance": getattr(e, "importance", "medium"),
                }
                for e in registry.subtext_entries
            ],
        }

    @staticmethod
    def _subtext_question_from_row(e_data: Dict[str, Any]) -> str:
        """兼容旧 JSON：hidden_clue / question。"""
        q = e_data.get("question")
        if q is not None and str(q).strip():
            return str(q).strip()
        legacy = e_data.get("hidden_clue")
        if legacy is not None:
            return str(legacy).strip()
        return ""

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> ForeshadowingRegistry:
        required_fields = ["id", "novel_id", "foreshadowings"]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        try:
            registry = ForeshadowingRegistry(
                id=data["id"],
                novel_id=NovelId(data["novel_id"]),
            )

            for f_data in data["foreshadowings"]:
                foreshadowing = Foreshadowing(
                    id=f_data["id"],
                    planted_in_chapter=ForeshadowingMapper._to_int(
                        f_data["planted_in_chapter"], "planted_in_chapter"
                    ),
                    description=f_data["description"],
                    importance=ImportanceLevel(f_data["importance"]),
                    status=ForeshadowingStatus(f_data["status"]),
                    suggested_resolve_chapter=ForeshadowingMapper._to_optional_int(
                        f_data.get("suggested_resolve_chapter"), "suggested_resolve_chapter"
                    ),
                    resolved_in_chapter=ForeshadowingMapper._to_optional_int(
                        f_data.get("resolved_in_chapter"), "resolved_in_chapter"
                    ),
                )
                registry.register(foreshadowing)

            if "subtext_entries" in data:
                for e_data in data["subtext_entries"]:
                    entry = SubtextLedgerEntry(
                        id=e_data["id"],
                        chapter=ForeshadowingMapper._to_int(e_data["chapter"], "chapter"),
                        character_id=e_data["character_id"],
                        question=ForeshadowingMapper._subtext_question_from_row(e_data),
                        status=e_data["status"],
                        consumed_at_chapter=ForeshadowingMapper._to_optional_int(
                            e_data.get("consumed_at_chapter"), "consumed_at_chapter"
                        ),
                        suggested_resolve_chapter=ForeshadowingMapper._to_optional_int(
                            e_data.get("suggested_resolve_chapter"), "suggested_resolve_chapter"
                        ),
                        resolve_chapter_window=ForeshadowingMapper._to_optional_int(
                            e_data.get("resolve_chapter_window"), "resolve_chapter_window"
                        ),
                        importance=e_data.get("importance", "medium"),
                        created_at=datetime.fromisoformat(e_data["created_at"]),
                    )
                    registry.add_subtext_entry(entry)

            return registry
        except (ValueError, KeyError) as e:
            raise ValueError(f"Invalid foreshadowing registry data format: {str(e)}") from e
