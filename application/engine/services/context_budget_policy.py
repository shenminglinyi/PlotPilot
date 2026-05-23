"""Budget compression policy for context slots."""
from __future__ import annotations

from typing import Dict, List

from application.engine.services.context_budget_models import ContextSlot


def truncate_t0_slots(
    t0_slots: Dict[str, ContextSlot],
    budget: int,
    *,
    chars_per_token_zh: float,
) -> int:
    """Keep T0 slots in insertion order and truncate the first overflowing slot."""
    total = 0
    for slot in t0_slots.values():
        if total + slot.tokens <= budget:
            total += slot.tokens
            continue

        remaining = budget - total
        if remaining > 0:
            target_chars = int(remaining * chars_per_token_zh)
            slot.content = slot.content[:target_chars] + "..."
            slot.tokens = remaining
            total += remaining
        break
    return total


def allocate_tier(
    tier_slots: Dict[str, ContextSlot],
    budget: int,
    compression_log: List[str],
    *,
    chars_per_token_zh: float,
) -> int:
    """Allocate a budget for one tier by priority, mutating overflowing slots."""
    sorted_slots = sorted(
        tier_slots.items(),
        key=lambda item: item[1].priority,
        reverse=True,
    )

    total_used = 0
    for name, slot in sorted_slots:
        if total_used + slot.tokens <= budget:
            total_used += slot.tokens
            continue

        remaining = budget - total_used
        original_tokens = slot.tokens
        if slot.max_tokens and slot.max_tokens > 0:
            if remaining > slot.min_tokens:
                target_chars = int(remaining * chars_per_token_zh)
                slot.content = slot.content[:target_chars] + "..."
                slot.tokens = remaining
                total_used += remaining
                compression_log.append(f"压缩 {name}: {original_tokens} → {remaining} tokens")
            else:
                slot.content = ""
                slot.tokens = 0
                compression_log.append(f"舍弃 {name}（预算不足）")
            continue

        if remaining > 0:
            target_chars = int(remaining * chars_per_token_zh)
            slot.content = slot.content[:target_chars] + "..."
            slot.tokens = remaining
            total_used += remaining
            compression_log.append(f"截断 {name}: {original_tokens} → {remaining} tokens")
        else:
            slot.content = ""
            slot.tokens = 0

    return total_used
