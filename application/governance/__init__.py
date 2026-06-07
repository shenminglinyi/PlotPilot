"""Narrative governance layer.

The package owns book-level structure decisions. Text quality guardrails remain
in the engine layer; this layer coordinates promise, storyline, debt and review
state across chapters.
"""

from application.governance.models import (
    CanonicalStoryline,
    ChapterNarrativeBudget,
    GovernanceIssue,
    GovernanceReport,
    NarrativeContract,
)
from application.governance.service import NarrativeGovernanceService

__all__ = [
    "CanonicalStoryline",
    "ChapterNarrativeBudget",
    "GovernanceIssue",
    "GovernanceReport",
    "NarrativeContract",
    "NarrativeGovernanceService",
]
