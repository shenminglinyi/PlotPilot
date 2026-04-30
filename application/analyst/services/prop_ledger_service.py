"""道具账本服务。"""
from __future__ import annotations

import re
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

    def suggest_events_from_chapter(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        content: str,
    ) -> list[dict[str, Any]]:
        """从章节正文中提示可能需要人工确认的道具事件。"""
        chapter = int(chapter_number)
        if chapter < 1:
            raise ValueError("chapter_number must be greater than 0")
        clean_content = (content or "").strip()
        if not clean_content:
            return []

        suggestions: list[dict[str, Any]] = []
        for item in self.repository.list_items(novel_id):
            name = str(item.get("name") or "").strip()
            if not name or name not in clean_content:
                continue
            evidence = self._build_evidence_snippet(clean_content, name)
            event_type, status, reason, confidence = self._classify_event(evidence)
            suggestions.append({
                "prop_name": name,
                "chapter_number": chapter,
                "event_type": event_type,
                "status": status or str(item.get("status") or ""),
                "holder": "",
                "location": self._extract_location(evidence),
                "evidence": evidence,
                "reason": reason,
                "confidence": confidence,
            })
        return suggestions[:12]

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
    def _build_evidence_snippet(content: str, prop_name: str, radius: int = 36) -> str:
        index = content.find(prop_name)
        if index < 0:
            return ""
        start = max(0, index - radius)
        end = min(len(content), index + len(prop_name) + radius)
        return content[start:end].strip()

    @staticmethod
    def _classify_event(evidence: str) -> tuple[str, str, str, float]:
        rules = [
            (
                "sealed",
                "被封存",
                0.82,
                "正文出现已登记道具，并命中封存/证物相关表达。",
                ("封存", "证物袋", "证物柜", "保险柜", "锁进", "收押"),
            ),
            (
                "lost_or_broken",
                "疑似丢失/损坏",
                0.78,
                "正文出现已登记道具，并命中丢失/损坏相关表达。",
                ("丢失", "不见", "遗失", "摔碎", "碎裂", "折断", "损坏", "烧毁"),
            ),
            (
                "transfer",
                "疑似转交",
                0.74,
                "正文出现已登记道具，并命中转交相关表达。",
                ("递给", "交给", "交到", "递到", "塞给", "转交", "给了"),
            ),
            (
                "use",
                "已使用",
                0.70,
                "正文出现已登记道具，并命中使用相关表达。",
                ("使用", "打开", "启动", "点燃", "按下", "照亮", "刺入", "割开", "解开"),
            ),
            (
                "acquire",
                "被取得",
                0.68,
                "正文出现已登记道具，并命中取得/带走相关表达。",
                ("拿到", "拿起", "取出", "接过", "收下", "获得", "捡起", "握住", "攥住", "带走"),
            ),
        ]
        for event_type, status, confidence, reason, keywords in rules:
            if any(keyword in evidence for keyword in keywords):
                return event_type, status, reason, confidence
        return "mention", "", "正文提到已登记道具，建议确认当前状态是否变化。", 0.48

    @staticmethod
    def _extract_location(evidence: str) -> str:
        patterns = [
            r"(警局证物柜|证物柜|保险柜|证物袋)",
            r"(?:锁进|放进|装进|塞进|收入|放入)([^，。；;、\s]{2,20}(?:柜|箱|袋|盒|室|库|房|抽屉))",
        ]
        matches: list[str] = []
        for pattern in patterns:
            matches.extend(match.group(1) for match in re.finditer(pattern, evidence))
        if not matches:
            return ""
        return max(matches, key=len)

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
