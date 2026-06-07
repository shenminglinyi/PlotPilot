from application.engine.services.context_budget_models import ContextSlot, PriorityTier
from application.engine.services.context_budget_policy import allocate_tier, truncate_t0_slots


def _slot(content, tokens, priority=0, max_tokens=100, min_tokens=0):
    return ContextSlot(
        name="slot",
        tier=PriorityTier.T1_COMPRESSIBLE,
        content=content,
        tokens=tokens,
        max_tokens=max_tokens,
        min_tokens=min_tokens,
        priority=priority,
    )


def test_allocate_tier_keeps_high_priority_and_logs_original_tokens():
    slots = {
        "high": _slot("高" * 20, tokens=10, priority=100),
        "low": _slot("低" * 30, tokens=30, priority=1, max_tokens=30),
    }
    log = []

    used = allocate_tier(slots, 20, log, chars_per_token_zh=1.0)

    assert used == 20
    assert slots["high"].tokens == 10
    assert slots["low"].tokens == 10
    assert log == ["压缩 low: 30 → 10 tokens"]


def test_allocate_tier_discards_when_remaining_below_minimum():
    slots = {
        "high": _slot("高" * 20, tokens=10, priority=100),
        "low": _slot("低" * 30, tokens=30, priority=1, max_tokens=30, min_tokens=12),
    }
    log = []

    used = allocate_tier(slots, 20, log, chars_per_token_zh=1.0)

    assert used == 10
    assert slots["low"].content == ""
    assert slots["low"].tokens == 0
    assert log == ["舍弃 low（预算不足）"]


def test_truncate_t0_slots_stops_at_first_overflowing_slot():
    slots = {
        "first": ContextSlot(
            name="first",
            tier=PriorityTier.T0_CRITICAL,
            content="一" * 20,
            tokens=10,
        ),
        "second": ContextSlot(
            name="second",
            tier=PriorityTier.T0_CRITICAL,
            content="二" * 20,
            tokens=10,
        ),
    }

    used = truncate_t0_slots(slots, 15, chars_per_token_zh=1.0)

    assert used == 15
    assert slots["first"].tokens == 10
    assert slots["second"].tokens == 5
    assert slots["second"].content.endswith("...")
