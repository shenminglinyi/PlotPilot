"""Beat planning models.

Kept separate from ``ContextBuilder`` so context assembly can stay focused on
retrieval/budgeting while beat planning grows independently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from application.engine.dtos.emotion_beat_card import EmotionBeatCard


@dataclass
class Beat:
    """微观节拍（Beat）.

    ``description`` remains the fallback prose brief; ``emotion_beat_card`` is
    the structured source for generation constraints when present.
    """

    description: str
    target_words: int
    focus: str
    expansion_hints: List[str] = field(default_factory=list)
    scene_goal: str = ""
    transition_from_prev: str = ""
    location_id: str = ""
    emotion_beat_card: Optional["EmotionBeatCard"] = None
    card_prompt_block: str = ""


__all__ = ["Beat"]
