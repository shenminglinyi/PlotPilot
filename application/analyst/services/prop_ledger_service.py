"""道具账本服务。"""
from __future__ import annotations

from typing import Any, Optional


class PropLedgerService:
    """管理关键道具的当前状态与历史事件。"""

    def __init__(self, repository):
        self.repository = repository

    def get_overview(self, novel_id: str) -> dict[str, Any]:
        items = self.repository.list_items(novel_id)
        events = self.repository.list_events(novel_id, limit=50)
        return {
            "novel_id": novel_id,
            "items": items,
            "recent_events": events,
            "warnings": self._build_warnings(items),
        }

    def upsert_item(
        self,
        *,
        novel_id: str,
        name: str,
        category: str = "",
        status: str = "",
        current_holder: str = "",
        current_location: str = "",
        first_seen_chapter: Optional[int] = None,
        last_seen_chapter: Optional[int] = None,
        importance: str = "normal",
        description: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("prop name is required")
        first_seen = self._positive_or_none(first_seen_chapter)
        last_seen = self._positive_or_none(last_seen_chapter) or first_seen
        return self.repository.upsert_item(
            novel_id=novel_id,
            name=clean_name,
            category=category.strip(),
            status=status.strip(),
            current_holder=current_holder.strip(),
            current_location=current_location.strip(),
            first_seen_chapter=first_seen,
            last_seen_chapter=last_seen,
            importance=self._normalize_importance(importance),
            description=description.strip(),
            notes=notes.strip(),
        )

    def create_event(
        self,
        *,
        novel_id: str,
        prop_name: str,
        chapter_number: int,
        event_type: str = "mention",
        holder: str = "",
        location: str = "",
        status: str = "",
        evidence: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        clean_name = prop_name.strip()
        if not clean_name:
            raise ValueError("prop name is required")
        chapter = int(chapter_number)
        if chapter < 1:
            raise ValueError("chapter_number must be greater than 0")
        item = self.repository.get_item_by_name(novel_id, clean_name)
        if item is None:
            item = self.upsert_item(
                novel_id=novel_id,
                name=clean_name,
                status=status,
                current_holder=holder,
                current_location=location,
                first_seen_chapter=chapter,
                last_seen_chapter=chapter,
            )
        return self.repository.create_event(
            novel_id=novel_id,
            prop_id=item["id"],
            prop_name=item["name"],
            chapter_number=chapter,
            event_type=event_type.strip() or "mention",
            holder=holder.strip(),
            location=location.strip(),
            status=status.strip(),
            evidence=evidence.strip(),
            notes=notes.strip(),
        )

    @staticmethod
    def _positive_or_none(value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        parsed = int(value)
        return parsed if parsed > 0 else None

    @staticmethod
    def _normalize_importance(value: str) -> str:
        return value if value in {"major", "normal", "minor"} else "normal"

    @staticmethod
    def _build_warnings(items: list[dict[str, Any]]) -> list[dict[str, str]]:
        warnings: list[dict[str, str]] = []
        if not items:
            warnings.append({
                "severity": "info",
                "title": "尚未登记关键道具",
                "message": "把钥匙、信物、武器、证物、一次性底牌等先登记，后续章节更不容易写丢。",
            })
            return warnings
        for item in items:
            if item.get("importance") == "major" and not item.get("last_seen_chapter"):
                warnings.append({
                    "severity": "warning",
                    "title": f"{item.get('name')} 缺少最近章节",
                    "message": "重要道具建议记录首次/最近出现章节，方便后续回收或再次使用。",
                })
            if item.get("importance") == "major" and not item.get("current_holder") and not item.get("current_location"):
                warnings.append({
                    "severity": "warning",
                    "title": f"{item.get('name')} 去向不明",
                    "message": "重要道具最好至少登记持有人或当前位置。",
                })
        return warnings[:8]
