"""兼容层 — 请使用 engine.runtime.quality_guardrails"""
from engine.runtime.quality_guardrails import (
    LanguageStyleGuardrail,
    CharacterConsistencyGuardrail,
    PlotDensityGuardrail,
    NamingGuardrail,
    ViewpointGuardrail,
    RhythmGuardrail,
    MacroPacingGuardrail,
    QualityGuardrail,
    QualityViolationError,
)

__all__ = [
    "LanguageStyleGuardrail",
    "CharacterConsistencyGuardrail",
    "PlotDensityGuardrail",
    "NamingGuardrail",
    "ViewpointGuardrail",
    "RhythmGuardrail",
    "MacroPacingGuardrail",
    "QualityGuardrail",
    "QualityViolationError",
]
