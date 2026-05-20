"""StoryDomainEvent 统一来源测试"""
from domain.shared.story_events import (
    StoryDomainEvent,
    DomainEvent,
    ChapterCompletedEvent,
    PhaseTransitionEvent,
)
from engine.core.ports import DomainEvent as PortDomainEvent
from engine.infrastructure.events.event_bus import (
    ChapterCompletedEvent as BusChapterCompletedEvent,
    DomainEvent as BusDomainEvent,
)


def test_port_and_shared_domain_event_are_same_class():
    assert PortDomainEvent is StoryDomainEvent
    assert DomainEvent is StoryDomainEvent


def test_event_bus_reexports_same_classes():
    assert BusDomainEvent is StoryDomainEvent
    assert BusChapterCompletedEvent is ChapterCompletedEvent


def test_chapter_completed_inherits_from_base():
    event = ChapterCompletedEvent(story_id="novel-1", chapter_number=3, word_count=2500)
    assert isinstance(event, StoryDomainEvent)
    assert event.event_type == "chapter_completed"
    assert event.story_id == "novel-1"
    assert event.chapter_number == 3


def test_chapter_completed_to_dict():
    event = ChapterCompletedEvent(
        story_id="novel-1",
        chapter_number=1,
        chapter_title="开篇",
        word_count=3000,
        source="pipeline",
        trace_id="trace-abc",
    )
    d = event.to_dict()
    assert d["event_type"] == "chapter_completed"
    assert d["story_id"] == "novel-1"
    assert d["chapter_number"] == 1
    assert d["source"] == "pipeline"
    assert d["trace_id"] == "trace-abc"


def test_phase_transition_event():
    event = PhaseTransitionEvent(
        story_id="novel-1",
        from_phase="development",
        to_phase="convergence",
        reason="chapter_ratio",
    )
    assert event.event_type == "phase_transition"
    assert event.to_phase == "convergence"
