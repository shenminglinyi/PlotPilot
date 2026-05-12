from __future__ import annotations
from typing import Protocol
from domain.prop.entities.prop import Prop
from domain.prop.value_objects.prop_event import PropEvent


class PropEventHandler(Protocol):
    """道具事件副作用处理器 — 解耦事件与副作用（知识库写入、通知等）。"""

    async def handle(self, prop: Prop, event: PropEvent) -> None:
        """处理单个事件的副作用。失败不应阻断主流程。"""
        ...
