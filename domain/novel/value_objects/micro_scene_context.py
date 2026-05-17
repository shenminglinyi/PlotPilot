"""微观场景运行时上下文 — 节拍管线内的充血状态载体（非持久化配置）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Set


@dataclass
class MicroSceneContext:
    """微观场景状态：在场实体与道具集合随节拍演进。"""

    location_id: str = ""
    active_characters: Set[str] = field(default_factory=set)
    active_props: Set[str] = field(default_factory=set)
    parent_zone: Optional[str] = None
