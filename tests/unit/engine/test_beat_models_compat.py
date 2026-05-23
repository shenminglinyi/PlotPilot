"""Beat model compatibility tests."""


def test_context_builder_reexports_beat_model():
    from application.engine.services.beat_models import Beat as CanonicalBeat
    from application.engine.services.context_builder import Beat as ContextBuilderBeat

    assert ContextBuilderBeat is CanonicalBeat


def test_beat_expansion_hints_are_not_shared():
    from application.engine.services.context_builder import Beat

    a = Beat(description="a", target_words=100, focus="action")
    b = Beat(description="b", target_words=100, focus="action")

    a.expansion_hints.append("only-a")

    assert b.expansion_hints == []
