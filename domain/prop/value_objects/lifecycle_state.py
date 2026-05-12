from enum import Enum
from typing import FrozenSet, Dict

class LifecycleState(str, Enum):
    DORMANT     = "DORMANT"
    INTRODUCED  = "INTRODUCED"
    ACTIVE      = "ACTIVE"
    DAMAGED     = "DAMAGED"
    RESOLVED    = "RESOLVED"

VALID_TRANSITIONS: Dict[LifecycleState, FrozenSet[LifecycleState]] = {
    LifecycleState.DORMANT:    frozenset({LifecycleState.INTRODUCED}),
    LifecycleState.INTRODUCED: frozenset({LifecycleState.ACTIVE, LifecycleState.RESOLVED}),
    LifecycleState.ACTIVE:     frozenset({LifecycleState.DAMAGED, LifecycleState.RESOLVED, LifecycleState.ACTIVE}),
    LifecycleState.DAMAGED:    frozenset({LifecycleState.ACTIVE, LifecycleState.RESOLVED}),
    LifecycleState.RESOLVED:   frozenset(),
}

class LifecycleTransitionError(Exception):
    """非法状态转换"""

def validate_transition(current: LifecycleState, target: LifecycleState) -> None:
    allowed = VALID_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise LifecycleTransitionError(
            f"非法状态转换: {current.value} → {target.value}，"
            f"允许: {[s.value for s in allowed]}"
        )
