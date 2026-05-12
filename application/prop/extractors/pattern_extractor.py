"""零 token 模式提取器：扫描正文中的 [[prop:id|名称]] 标记。"""
from __future__ import annotations
import re
import uuid
from datetime import datetime
from typing import List

from domain.prop.value_objects.prop_event import PropEvent, PropEventType, PropEventSource

# 匹配 [[prop:uuid|名称]] 或仅 [[prop:uuid]]
_PATTERN = re.compile(r'\[\[prop:([a-f0-9\-]{36})(?:\|[^\]]+)?\]\]')


class PatternExtractor:
    """[[prop:id]] 标记扫描提取器（零 token，优先级最高）。"""

    priority: int = 0
    name: str = "pattern"

    async def extract(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        active_props: List[dict],
    ) -> List[PropEvent]:
        found_ids = set(_PATTERN.findall(content))
        valid_ids = {p["id"] for p in active_props}
        events: List[PropEvent] = []
        now = datetime.utcnow().isoformat()
        for prop_id in found_ids & valid_ids:
            events.append(PropEvent(
                id=str(uuid.uuid4()),
                prop_id=prop_id,
                novel_id=novel_id,
                chapter_number=chapter_number,
                event_type=PropEventType.USED,
                source=PropEventSource.AUTO_PATTERN,
                description=f"第{chapter_number}章正文标记命中",
                created_at=now,
            ))
        return events
