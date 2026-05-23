import pytest

from application.prop.handlers.narrative_event_handler import NarrativePropEventHandler
from domain.prop.entities.prop import Prop
from domain.prop.value_objects.lifecycle_state import LifecycleState
from domain.prop.value_objects.prop_event import PropEvent, PropEventSource, PropEventType
from domain.prop.value_objects.prop_id import PropId


class _EventRepo:
    def __init__(self):
        self.appended = []

    def append_event(self, novel_id, chapter_number, event_summary, mutations, tags=None):
        self.appended.append(
            {
                "novel_id": novel_id,
                "chapter_number": chapter_number,
                "event_summary": event_summary,
                "mutations": mutations,
                "tags": tags or [],
            }
        )
        return "event-1"


@pytest.mark.asyncio
async def test_prop_event_projects_to_shared_narrative_event_stream():
    repo = _EventRepo()
    handler = NarrativePropEventHandler(repo)
    prop = Prop(
        id=PropId("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
        novel_id="novel-1",
        name="青铜罗盘",
        lifecycle_state=LifecycleState.ACTIVE,
        holder_character_id="char-1",
    )
    event = PropEvent(
        id="prop-event-1",
        prop_id=prop.id.value,
        novel_id="novel-1",
        chapter_number=3,
        event_type=PropEventType.USED,
        source=PropEventSource.AUTO_PATTERN,
        actor_character_id="char-1",
        description="林澈使用青铜罗盘",
    )

    await handler.handle(prop, event)

    assert len(repo.appended) == 1
    appended = repo.appended[0]
    assert appended["event_summary"] == "林澈使用青铜罗盘"
    assert "prop:used" in appended["tags"]
    assert {
        "entity_id": prop.id.value,
        "entity_type": "prop",
        "attribute": "lifecycle_state",
        "action": "add",
        "value": "ACTIVE",
    } in appended["mutations"]
    assert any(
        m["entity_id"] == "char-1"
        and m["attribute"] == "related_props"
        and m["action"] == "append_unique"
        for m in appended["mutations"]
    )
