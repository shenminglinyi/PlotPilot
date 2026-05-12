"""PropLifecycleSyncer 单元测试 — 验证领域层状态机和编排逻辑"""
import asyncio
import pytest
from unittest.mock import MagicMock
from domain.prop.entities.prop import Prop
from domain.prop.value_objects.prop_id import PropId
from domain.prop.value_objects.lifecycle_state import LifecycleState, LifecycleTransitionError
from domain.prop.value_objects.prop_event import PropEvent, PropEventType, PropEventSource
from application.prop.services.lifecycle_syncer import PropLifecycleSyncer

# 固定UUID，满足 PatternExtractor 的36字符UUID正则
_PROP_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def make_prop(pid=_PROP_UUID, state=LifecycleState.ACTIVE):
    return Prop(
        id=PropId(pid),
        novel_id="n1",
        name="测试剑",
        lifecycle_state=state,
        introduced_chapter=1,
    )


def test_lifecycle_active_to_damaged():
    prop = make_prop(state=LifecycleState.ACTIVE)
    event = PropEvent(
        id="e1", prop_id="p1", novel_id="n1", chapter_number=3,
        event_type=PropEventType.DAMAGED, source=PropEventSource.MANUAL,
    )
    prop.apply_event(event)
    assert prop.lifecycle_state == LifecycleState.DAMAGED


def test_lifecycle_damaged_to_repaired():
    prop = make_prop(state=LifecycleState.DAMAGED)
    event = PropEvent(
        id="e2", prop_id="p1", novel_id="n1", chapter_number=5,
        event_type=PropEventType.REPAIRED, source=PropEventSource.MANUAL,
    )
    prop.apply_event(event)
    assert prop.lifecycle_state == LifecycleState.ACTIVE


def test_illegal_transition_raises():
    prop = make_prop(state=LifecycleState.RESOLVED)
    event = PropEvent(
        id="e3", prop_id="p1", novel_id="n1", chapter_number=6,
        event_type=PropEventType.USED, source=PropEventSource.MANUAL,
    )
    with pytest.raises(LifecycleTransitionError):
        prop.apply_event(event)


def test_dormant_can_only_go_to_introduced():
    prop = make_prop(state=LifecycleState.DORMANT)
    # Legal: DORMANT → INTRODUCED
    event = PropEvent(
        id="e4", prop_id="p1", novel_id="n1", chapter_number=1,
        event_type=PropEventType.INTRODUCED, source=PropEventSource.MANUAL,
    )
    prop.apply_event(event)
    assert prop.lifecycle_state == LifecycleState.INTRODUCED
    assert prop.introduced_chapter == 1


def test_transfer_updates_holder():
    prop = make_prop(state=LifecycleState.ACTIVE)
    prop.holder_character_id = "char_a"
    event = PropEvent(
        id="e5", prop_id="p1", novel_id="n1", chapter_number=3,
        event_type=PropEventType.TRANSFERRED, source=PropEventSource.MANUAL,
        from_holder_id="char_a", to_holder_id="char_b",
    )
    prop.apply_event(event)
    assert prop.holder_character_id == "char_b"


def test_resolved_is_terminal():
    prop = make_prop(state=LifecycleState.ACTIVE)
    event = PropEvent(
        id="e6", prop_id="p1", novel_id="n1", chapter_number=10,
        event_type=PropEventType.RESOLVED, source=PropEventSource.MANUAL,
    )
    prop.apply_event(event)
    assert prop.lifecycle_state == LifecycleState.RESOLVED
    assert prop.resolved_chapter == 10


def test_pop_pending_events():
    prop = make_prop(state=LifecycleState.ACTIVE)
    event = PropEvent(
        id="e7", prop_id="p1", novel_id="n1", chapter_number=3,
        event_type=PropEventType.USED, source=PropEventSource.MANUAL,
    )
    prop.apply_event(event)
    popped = prop.pop_pending_events()
    assert len(popped) == 1
    assert prop.pop_pending_events() == []


@pytest.mark.asyncio
async def test_syncer_applies_pattern_events():
    prop = make_prop(state=LifecycleState.ACTIVE)
    prop_repo = MagicMock()
    prop_repo.list_active.return_value = [prop]
    prop_repo.list_by_novel.return_value = [prop]
    event_repo = MagicMock()

    from application.prop.extractors.pattern_extractor import PatternExtractor
    extractor = PatternExtractor()
    syncer = PropLifecycleSyncer(prop_repo, event_repo, [extractor])

    content = f"主角使用了[[prop:{prop.id.value}|测试剑]]斩杀敌人。"
    result = await syncer.sync("n1", 3, content)
    assert result["events_applied"] >= 1
    prop_repo.save.assert_called()
    event_repo.save.assert_called()


@pytest.mark.asyncio
async def test_syncer_deduplication():
    """同一道具同类事件只应用一次。"""
    prop = make_prop(state=LifecycleState.ACTIVE)
    prop_repo = MagicMock()
    prop_repo.list_active.return_value = [prop]
    prop_repo.list_by_novel.return_value = [prop]
    event_repo = MagicMock()

    from application.prop.extractors.pattern_extractor import PatternExtractor

    class DuplicateExtractor:
        priority = 5
        name = "duplicate"
        async def extract(self, novel_id, chapter_number, content, active_props):
            from domain.prop.value_objects.prop_event import PropEvent, PropEventType, PropEventSource
            import uuid
            return [PropEvent(
                id=str(uuid.uuid4()), prop_id=prop.id.value, novel_id=novel_id,
                chapter_number=chapter_number, event_type=PropEventType.USED,
                source=PropEventSource.MANUAL,
            )]

    extractor1 = PatternExtractor()
    extractor2 = DuplicateExtractor()
    syncer = PropLifecycleSyncer(prop_repo, event_repo, [extractor1, extractor2])

    content = f"[[prop:{prop.id.value}|测试剑]]"
    result = await syncer.sync("n1", 3, content)
    # Despite two extractors returning USED events, only one should be applied
    assert result["events_applied"] == 1


@pytest.mark.asyncio
async def test_syncer_no_props_skips():
    prop_repo = MagicMock()
    prop_repo.list_active.return_value = []
    prop_repo.list_by_novel.return_value = []
    event_repo = MagicMock()

    syncer = PropLifecycleSyncer(prop_repo, event_repo)
    result = await syncer.sync("n1", 3, "some content")
    assert result.get("skipped") is True
