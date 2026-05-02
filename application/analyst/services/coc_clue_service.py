"""CoC 线索账本服务。"""
from __future__ import annotations

from typing import Any, Mapping, Optional


class CocClueService:
    """管理 CoC 线索条目与章节证据。"""

    def __init__(self, repository):
        self.repository = repository

    def get_overview(self, novel_id: str) -> dict[str, Any]:
        return {
            "novel_id": novel_id,
            "items": self.repository.list_items(novel_id),
            "recent_events": self.repository.list_events(novel_id, limit=100),
            "cognition_layers": self.get_cognition_layers(novel_id),
        }

    def get_cognition_layers(self, novel_id: str) -> dict[str, list[str]]:
        items = self.repository.list_items(novel_id)
        author_truth: list[str] = []
        character_known: list[str] = []
        reader_known: list[str] = []
        for item in items:
            clue_key = str(item.get("clue_key") or "").strip() or "未命名线索"
            clue_text = str(item.get("clue_text") or "").strip() or "（待补充）"
            visibility = str(item.get("visibility") or "").strip().lower()
            known_by = self._normalize_known_by(item.get("known_by") or "")
            suffix = f"（已知角色：{known_by or '未记录'}）"
            line = f"{clue_key}：{clue_text}{suffix}"
            if visibility == "author_only":
                author_truth.append(line)
            elif visibility == "protagonist_known":
                character_known.append(line)
            else:
                reader_known.append(line)
        return {
            "author_truth": author_truth[:24],
            "character_known": character_known[:24],
            "reader_known": reader_known[:24],
        }

    def upsert_item(
        self,
        *,
        novel_id: str,
        clue_key: str,
        clue_text: str = "",
        visibility: str = "reader_known",
        reveal_chapter: Optional[int] = None,
        known_by: Any = "",
        confidence: float = 0.5,
        lock_level: str = "soft",
        status: str = "active",
        notes: str = "",
        entry_id: Optional[str] = None,
    ) -> dict[str, Any]:
        clean_key = clue_key.strip()
        if not clean_key:
            raise ValueError("clue_key is required")

        existing = self.repository.get_item_by_id(entry_id) if entry_id else self.repository.get_item_by_key(
            novel_id,
            clean_key,
        )
        if existing is not None and existing.get("novel_id") != novel_id:
            raise ValueError("entry does not belong to novel")

        incoming = {
            "clue_key": clean_key,
            "clue_text": (clue_text or "").strip(),
            "visibility": self._normalize_visibility(visibility),
            "reveal_chapter": self._normalize_reveal_chapter(reveal_chapter),
            "known_by": self._normalize_known_by(known_by),
            "confidence": self._normalize_confidence(confidence),
            "lock_level": self._normalize_lock_level(lock_level),
            "status": self._normalize_status(status),
            "notes": (notes or "").strip(),
        }
        self.lock_guard_validate_patch(existing, incoming)
        return self.repository.upsert_item(
            item_id=existing["id"] if existing else None,
            novel_id=novel_id,
            clue_key=incoming["clue_key"],
            clue_text=incoming["clue_text"],
            visibility=incoming["visibility"],
            reveal_chapter=incoming["reveal_chapter"],
            known_by=incoming["known_by"],
            confidence=incoming["confidence"],
            lock_level=incoming["lock_level"],
            status=incoming["status"],
            notes=incoming["notes"],
        )

    def create_event(
        self,
        *,
        novel_id: str,
        entry_id: str = "",
        clue_key: str = "",
        chapter_number: int,
        event_type: str = "mention",
        evidence: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        clean_entry_id = str(entry_id or "").strip()
        clean_clue_key = str(clue_key or "").strip()
        chapter = int(chapter_number)
        if chapter < 1:
            raise ValueError("chapter_number must be greater than 0")
        if bool(clean_entry_id) == bool(clean_clue_key):
            raise ValueError("entry_id or clue_key is required (choose one)")

        item = None
        if clean_entry_id:
            item = self.repository.get_item_by_id(clean_entry_id)
        elif clean_clue_key:
            item = self.repository.get_item_by_key(novel_id, clean_clue_key)
            if item is None:
                item = self.upsert_item(
                    novel_id=novel_id,
                    clue_key=clean_clue_key,
                    clue_text="",
                    visibility="reader_known",
                    reveal_chapter=chapter,
                    known_by="",
                    confidence=0.4,
                    lock_level="soft",
                    status="active",
                    notes="自动创建：由线索事件补建 draft 线索。",
                )

        if item is None:
            raise ValueError("clue item not found")
        if item.get("novel_id") != novel_id:
            raise ValueError("entry does not belong to novel")

        return self.repository.create_event(
            clue_id=str(item.get("id") or clean_entry_id),
            chapter_number=chapter,
            event_type=(event_type or "mention").strip() or "mention",
            evidence=(evidence or "").strip(),
            notes=(notes or "").strip(),
        )

    @staticmethod
    def lock_guard_validate_patch(
        existing: Optional[Mapping[str, Any]],
        incoming: Mapping[str, Any],
    ) -> None:
        if not existing:
            return
        if str(existing.get("lock_level") or "").strip() != "absolute":
            return
        for field in ("clue_key", "clue_text", "reveal_chapter"):
            old_value = str(existing.get(field) or "")
            new_value = str(incoming.get(field) or "")
            if old_value != new_value:
                raise ValueError(f"absolute lock forbids changing `{field}`")

    def build_overlay(self, novel_id: str) -> str:
        items = self.repository.list_items(novel_id)
        if not items:
            return "【CoC线索账本（已知信息边界）】\n- 暂无已登记线索。"

        prioritized = [
            item
            for item in items
            if str(item.get("status") or "").strip() == "active"
            and str(item.get("visibility") or "").strip() != "author_only"
        ]
        others = [
            item
            for item in items
            if item not in prioritized
            and str(item.get("visibility") or "").strip() != "author_only"
        ]

        if not prioritized and not others:
            return "【CoC线索账本（已知信息边界）】\n- 当前仅有作者私有线索（author_only）。"

        lines = ["【CoC线索账本（已知信息边界）】"]
        for item in prioritized + others:
            reveal_chapter = item.get("reveal_chapter")
            reveal_text = f"第{reveal_chapter}章" if reveal_chapter else "待揭示"
            lines.append(
                f"- {item.get('clue_key', '')}: {item.get('clue_text', '') or '（待补充）'}"
                f"（可见={item.get('visibility', 'reader_known')}，状态={item.get('status', 'active')}，揭示={reveal_text}）"
            )
        return "\n".join(lines)

    @staticmethod
    def _normalize_visibility(value: str) -> str:
        normalized = (value or "").strip().lower()
        return normalized if normalized in {"reader_known", "protagonist_known", "author_only"} else "reader_known"

    @staticmethod
    def _normalize_lock_level(value: str) -> str:
        normalized = (value or "").strip().lower()
        return normalized if normalized in {"soft", "strict", "absolute"} else "soft"

    @staticmethod
    def _normalize_status(value: str) -> str:
        normalized = (value or "").strip().lower()
        return normalized if normalized in {"active", "resolved", "refuted"} else "active"

    @staticmethod
    def _normalize_reveal_chapter(value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        chapter = int(value)
        return chapter if chapter > 0 else None

    @staticmethod
    def _normalize_confidence(value: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.5
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _normalize_known_by(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(item).strip() for item in value if str(item).strip())
        return str(value or "").strip()
