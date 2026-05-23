"""Prop event handler that records canonical narrative events."""
from __future__ import annotations

from domain.prop.entities.prop import Prop
from domain.prop.value_objects.prop_event import PropEvent, PropEventType


_ACTION_LABEL = {
    PropEventType.INTRODUCED: "introduced",
    PropEventType.USED: "used",
    PropEventType.TRANSFERRED: "transferred",
    PropEventType.DAMAGED: "damaged",
    PropEventType.REPAIRED: "repaired",
    PropEventType.UPGRADED: "upgraded",
    PropEventType.RESOLVED: "resolved",
}


class NarrativePropEventHandler:
    """Mirror prop lifecycle events into the shared narrative event stream.

    `prop_events` remains the prop aggregate log. `narrative_events` becomes the
    system-wide fact source that other projections can replay.
    """

    def __init__(self, narrative_event_repository) -> None:
        self._events = narrative_event_repository

    async def handle(self, prop: Prop, event: PropEvent) -> None:
        action = _ACTION_LABEL.get(event.event_type, event.event_type.value.lower())
        mutations = [
            {
                "entity_id": prop.id.value,
                "entity_type": "prop",
                "attribute": "lifecycle_state",
                "action": "add",
                "value": prop.lifecycle_state.value,
            },
            {
                "entity_id": prop.id.value,
                "entity_type": "prop",
                "attribute": "last_event",
                "action": "add",
                "value": {
                    "event_type": event.event_type.value,
                    "chapter_number": event.chapter_number,
                    "source": event.source.value,
                    "description": event.description,
                },
            },
        ]

        holder = event.to_holder_id or event.actor_character_id or prop.holder_character_id
        if holder:
            mutations.append(
                {
                    "entity_id": prop.id.value,
                    "entity_type": "prop",
                    "attribute": "holder_character_id",
                    "action": "add",
                    "value": holder,
                }
            )
            mutations.append(
                {
                    "entity_id": holder,
                    "entity_type": "character",
                    "attribute": "related_props",
                    "action": "append_unique",
                    "value": {
                        "prop_id": prop.id.value,
                        "prop_name": prop.name,
                        "relation": action,
                        "chapter_number": event.chapter_number,
                    },
                }
            )

        self._events.append_event(
            event.novel_id,
            event.chapter_number,
            event.description or f"{prop.name} {action}",
            mutations,
            tags=["prop", f"prop:{action}", f"prop_id:{prop.id.value}"],
        )
