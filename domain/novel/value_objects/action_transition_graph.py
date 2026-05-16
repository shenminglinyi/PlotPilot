"""动作过场流转图（Action Transition Graph）— 章节级空间拓扑的领域模型。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple


@dataclass(frozen=True)
class SceneNode:
    """微观场景节点。"""

    location_id: str
    initial_props: Tuple[str, ...] = ()
    is_entry_point: bool = False


@dataclass(frozen=True)
class TransitionEdge:
    """空间转移边：携带可校验的过场动作锚点。"""

    source_location: str
    target_location: str
    required_action: str
    trigger_characters: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionTransitionGraph:
    """当前章节大纲对应的 ATG（内存态值对象）。"""

    nodes: Mapping[str, SceneNode]
    transitions: Tuple[TransitionEdge, ...]
    visit_sequence: Tuple[str, ...] = ()

    def get_transition_path(self, current_loc: str, next_loc: str) -> Optional[TransitionEdge]:
        if current_loc == next_loc:
            return None
        for edge in self.transitions:
            if edge.source_location == current_loc and edge.target_location == next_loc:
                return edge
        return None

    def node(self, location_id: str) -> Optional[SceneNode]:
        return self.nodes.get(location_id)
