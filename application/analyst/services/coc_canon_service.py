"""CoC 正典注册表服务。"""
from __future__ import annotations

from typing import Any, Mapping, Optional


class CocCanonService:
    """管理 CoC 正典条目与章节证据。"""

    def __init__(self, repository):
        self.repository = repository

    def get_overview(self, novel_id: str) -> dict[str, Any]:
        entries = self.repository.list_entries(novel_id)
        events = self.repository.list_events(novel_id, limit=100)
        return {
            "novel_id": novel_id,
            "entries": entries,
            "recent_events": events,
            "cognition_layers": self.get_cognition_layers(novel_id),
        }

    def get_cognition_layers(self, novel_id: str) -> dict[str, list[str]]:
        entries = [
            item
            for item in self.repository.list_entries(novel_id)
            if str(item.get("status") or "").strip() != "archived"
        ]
        author_truth: list[str] = []
        reader_known: list[str] = []
        author_truth_snippets: list[str] = []
        for item in entries:
            title = str(item.get("title") or "").strip() or "未命名条目"
            public_facts = str(item.get("public_facts") or "").strip()
            hidden_truth = str(item.get("hidden_truth") or "").strip()
            if public_facts:
                reader_known.append(f"{title}：{public_facts}")
            if hidden_truth:
                author_truth.append(f"{title}：{hidden_truth}")
                if len(hidden_truth) >= 8 and hidden_truth not in author_truth_snippets:
                    author_truth_snippets.append(hidden_truth[:80])
        return {
            "author_truth": author_truth[:24],
            "reader_known": reader_known[:24],
            "author_truth_snippets": author_truth_snippets[:40],
        }

    def upsert_entry(
        self,
        *,
        novel_id: str,
        canon_type: str,
        title: str,
        public_facts: str = "",
        hidden_truth: str = "",
        lock_level: str = "soft",
        mutable_notes: str = "",
        status: str = "active",
        entry_id: Optional[str] = None,
    ) -> dict[str, Any]:
        clean_canon_type = canon_type.strip()
        clean_title = title.strip()
        if not clean_canon_type:
            raise ValueError("canon_type is required")
        if not clean_title:
            raise ValueError("title is required")

        existing = self.repository.get_entry_by_id(entry_id) if entry_id else self.repository.get_entry_by_key(
            novel_id,
            clean_canon_type,
            clean_title,
        )
        if existing is not None and existing.get("novel_id") != novel_id:
            raise ValueError("entry does not belong to novel")

        incoming = {
            "canon_type": clean_canon_type,
            "title": clean_title,
            "public_facts": public_facts.strip(),
            "hidden_truth": hidden_truth.strip(),
            "lock_level": self._normalize_lock_level(lock_level),
            "mutable_notes": mutable_notes.strip(),
            "status": self._normalize_status(status),
        }
        self.lock_guard_validate_patch(existing, incoming)
        return self.repository.upsert_entry(
            entry_id=existing["id"] if existing else None,
            novel_id=novel_id,
            canon_type=incoming["canon_type"],
            title=incoming["title"],
            public_facts=incoming["public_facts"],
            hidden_truth=incoming["hidden_truth"],
            lock_level=incoming["lock_level"],
            mutable_notes=incoming["mutable_notes"],
            status=incoming["status"],
        )

    def create_event(
        self,
        *,
        novel_id: str,
        entry_id: str = "",
        title: str = "",
        chapter_number: int,
        event_type: str = "mention",
        evidence: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        clean_entry_id = str(entry_id or "").strip()
        clean_title = str(title or "").strip()
        chapter = int(chapter_number)
        if chapter < 1:
            raise ValueError("chapter_number must be greater than 0")
        if not clean_entry_id and not clean_title:
            raise ValueError("entry_id or title is required")

        entry = None
        if clean_entry_id:
            entry = self.repository.get_entry_by_id(clean_entry_id)
        elif clean_title:
            entry = self.repository.get_entry_by_title(novel_id, clean_title)
            if entry is None:
                entry = self.upsert_entry(
                    novel_id=novel_id,
                    canon_type="other",
                    title=clean_title,
                    public_facts="",
                    hidden_truth="",
                    lock_level="soft",
                    mutable_notes="自动创建：由事件记录补建条目。",
                    status="draft",
                )
        if entry is None:
            raise ValueError("entry not found")
        if entry.get("novel_id") != novel_id:
            raise ValueError("entry does not belong to novel")
        return self.repository.create_event(
            entry_id=str(entry.get("id") or clean_entry_id),
            chapter_number=chapter,
            event_type=(event_type or "mention").strip() or "mention",
            evidence=evidence.strip(),
            notes=notes.strip(),
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

        protected_fields = ("public_facts", "hidden_truth", "title", "canon_type")
        for field in protected_fields:
            old_value = str(existing.get(field) or "")
            new_value = str(incoming.get(field) or "")
            if old_value != new_value:
                raise ValueError(f"absolute lock forbids changing `{field}`")

    def build_overlay(self, novel_id: str) -> str:
        entries = [
            item
            for item in self.repository.list_entries(novel_id)
            if str(item.get("status") or "active").strip() != "archived"
        ]
        if not entries:
            return "【CoC正典（必须保持一致）】\n- 暂无已登记正典。"

        lines = ["【CoC正典（必须保持一致）】"]
        for item in entries:
            lines.append(
                f"- [{item.get('canon_type', '')}] {item.get('title', '')}（锁定：{item.get('lock_level', 'soft')}）"
            )
            public_facts = str(item.get("public_facts") or "").strip()
            hidden_truth = str(item.get("hidden_truth") or "").strip()
            mutable_notes = str(item.get("mutable_notes") or "").strip()
            if public_facts:
                lines.append(f"  公共事实：{public_facts}")
            if hidden_truth:
                lines.append(f"  隐藏真相：{hidden_truth}")
            if mutable_notes:
                lines.append(f"  可变备注：{mutable_notes}")
        return "\n".join(lines)

    @staticmethod
    def _normalize_lock_level(value: str) -> str:
        normalized = (value or "").strip().lower()
        return normalized if normalized in {"soft", "strict", "absolute"} else "soft"

    @staticmethod
    def _normalize_status(value: str) -> str:
        normalized = (value or "").strip().lower()
        return normalized if normalized in {"active", "draft", "archived"} else "active"
