"""prompt_keys — CPMS unified node key registry.

All prompt node keys are defined here and only here.
Business code must import from this module instead of hardcoding strings.

Design:
- Single source of truth: every node_key used by any service is registered here
- Abstract: no icons, no display text, pure identifiers
- Typed: each key is a string constant with a clear naming convention
- Discoverable: grep-friendly, IDE-autocomplete-friendly

Naming convention:
  <domain>-<capability>[-<variant>]

  domain:     bible, chapter, scene, dialogue, prop, review, memory,
              planning, style, autopilot, theme, skill, knowledge, tension, anti-ai
  capability: generation, extraction, review, audit, sync, bridge,
              scoring, analysis, decomposition, suggest
  variant:    optional disambiguator (e.g. "extract", "check", "fix")
"""
from __future__ import annotations

# ── Bible ────────────────────────────────────────────────────────────────
BIBLE_ALL = "bible-all"
BIBLE_WORLDBUILDING = "bible-worldbuilding"
BIBLE_CHARACTERS = "bible-characters"
BIBLE_LOCATIONS = "bible-locations"
BIBLE_STYLE_CONVENTION = "bible-style-convention"

# ── Chapter generation ───────────────────────────────────────────────────
CHAPTER_GENERATION_MAIN = "chapter-generation-main"
CHAPTER_GENERATION_BASIC = "chapter-generation-basic"
CHAPTER_NARRATIVE_SYNC = "chapter-narrative-sync"
CHAPTER_STATE_EXTRACTION = "chapter-state-extraction"
CHAPTER_SUMMARIZER = "chapter-summarizer"
CHAPTER_BRIDGE_EXTRACT = "chapter-bridge-extract"
CHAPTER_BRIDGE_CHECK = "chapter-bridge-check"
CHAPTER_BRIDGE_FIX = "chapter-bridge-fix"

# ── Scene ────────────────────────────────────────────────────────────────
SCENE_GENERATION = "scene-generation"
SCENE_DIRECTOR = "scene-director"
BEAT_SHEET_DECOMPOSITION = "beat-sheet-decomposition"

# ── Dialogue ─────────────────────────────────────────────────────────────
DIALOGUE_GENERATION = "dialogue-generation"

# ── Prop ─────────────────────────────────────────────────────────────────
PROP_EVENT_EXTRACTION = "prop-event-extraction"

# ── Review / Audit ───────────────────────────────────────────────────────
REVIEW_CHARACTER_CONSISTENCY = "review-character-consistency"
REVIEW_TIMELINE_CONSISTENCY = "review-timeline-consistency"
REVIEW_STORYLINE_CONSISTENCY = "review-storyline-consistency"
REVIEW_FORESHADOWING_USAGE = "review-foreshadowing-usage"
REVIEW_IMPROVEMENT_SUGGESTIONS = "review-improvement-suggestions"
CHAPTER_AI_REVIEW = "chapter-ai-review"
CLICHE_SCAN = "cliche-scan"

# ── Memory ───────────────────────────────────────────────────────────────
MEMORY_EXTRACTION = "memory-extraction"
EMOTION_LEDGER_EXTRACTION = "emotion-ledger-extraction"

# ── Planning ─────────────────────────────────────────────────────────────
MACRO_PLANNING = "macro-planning"
PLANNING_QUICK_MACRO = "planning-quick-macro"
PLANNING_PRECISE_MACRO = "planning-precise-macro"
PLANNING_PRECISE_VOLUME = "planning-precise-volume"
PLANNING_PRECISE_REPAIR = "planning-precise-repair"
PLANNING_ACT = "planning-act"
CONTINUOUS_PLANNING_NEXT_ACT = "continuous-planning-next-act"
OUTLINE_BEAT_PARTITION = "outline-beat-partition"
BEAT_COT_BRIDGE = "beat-cot-bridge"

# ── Style / Voice ────────────────────────────────────────────────────────
STYLE_ANALYSIS = "style-analysis"
VOICE_STYLE_ANALYSIS = "voice-style-analysis"
VOICE_BASELINE_ANALYSIS = "voice-baseline-analysis"
VOICE_REWRITE = "voice-rewrite"
VOICE_DRIFT = "voice-drift"

# ── Tension ──────────────────────────────────────────────────────────────
TENSION_SCORING = "tension-scoring"
TENSION_ANALYSIS_DIAGNOSIS = "tension-analysis-diagnosis"

# ── Summary ──────────────────────────────────────────────────────────────
SUMMARY_CHECKPOINT = "summary-checkpoint"
SUMMARY_ACT = "summary-act"
SUMMARY_VOLUME = "summary-volume"
SUMMARY_PART = "summary-part"

# ── Knowledge ────────────────────────────────────────────────────────────
KNOWLEDGE_INITIAL = "knowledge-initial"
KG_INFERENCE = "kg-inference"

# ── DAG context / gateways ───────────────────────────────────────────────
CONTEXT_BLUEPRINT = "context-blueprint"
CONTEXT_FORESHADOW = "context-foreshadow"
CONTEXT_MEMORY = "context-memory"
CONTEXT_DEBT = "context-debt"
FORESHADOW_CHECK = "foreshadow-check"
CHAPTER_AFTERMATH = "chapter-aftermath"
CIRCUIT_BREAKER = "circuit-breaker"
REVIEW_GATEWAY = "review-gateway"
CONDITION_GATEWAY = "condition-gateway"
RETRY_GATEWAY = "retry-gateway"

# ── Anti-AI defense ──────────────────────────────────────────────────────
ANTI_AI_BEHAVIOR_PROTOCOL = "anti-ai-behavior-protocol"
ANTI_AI_ALLOWLIST_EXPLAIN = "anti-ai-allowlist-explain"
ANTI_AI_CHAPTER_AUDIT = "anti-ai-chapter-audit"
ANTI_AI_CHARACTER_STATE_LOCK = "anti-ai-character-state-lock"
ANTI_AI_FINALE_ENHANCEMENT = "anti-ai-finale-enhancement"
ANTI_AI_MID_GENERATION_REFRESH = "anti-ai-mid-generation-refresh"

# ── Autopilot / Workflow ─────────────────────────────────────────────────
WORKFLOW_CHAPTER_GENERATION = "workflow-chapter-generation"
AUTOPILOT_STREAM_BEAT = "autopilot-stream-beat"
BEAT_FOCUS_INSTRUCTIONS = "beat-focus-instructions"
LIFECYCLE_PHASE_DIRECTIVES = "lifecycle-phase-directives"
REFACTOR_PROPOSAL_MACRO = "refactor-proposal-macro"
PLANNING_MAIN_PLOT_OPTION = "planning-main-plot-option"

# ── Theme ────────────────────────────────────────────────────────────────
# Theme keys follow pattern: theme-{genre}-{method}
# e.g. theme-romance-system_persona, theme-wuxia-writing_rules

# ── Skill ────────────────────────────────────────────────────────────────
# Skill keys follow pattern: skill-{skill_key}-{method}
# e.g. skill-battle_choreography-context


# ── Registry: all known keys for validation ──────────────────────────────

ALL_KEYS: frozenset[str] = frozenset({
    # Bible
    BIBLE_ALL, BIBLE_WORLDBUILDING, BIBLE_CHARACTERS, BIBLE_LOCATIONS,
    BIBLE_STYLE_CONVENTION,
    # Chapter
    CHAPTER_GENERATION_MAIN, CHAPTER_GENERATION_BASIC,
    CHAPTER_NARRATIVE_SYNC, CHAPTER_STATE_EXTRACTION, CHAPTER_SUMMARIZER,
    CHAPTER_BRIDGE_EXTRACT, CHAPTER_BRIDGE_CHECK, CHAPTER_BRIDGE_FIX,
    # Scene
    SCENE_GENERATION, SCENE_DIRECTOR, BEAT_SHEET_DECOMPOSITION,
    # Dialogue
    DIALOGUE_GENERATION,
    # Prop
    PROP_EVENT_EXTRACTION,
    # Review
    REVIEW_CHARACTER_CONSISTENCY, REVIEW_TIMELINE_CONSISTENCY,
    REVIEW_STORYLINE_CONSISTENCY, REVIEW_FORESHADOWING_USAGE,
    REVIEW_IMPROVEMENT_SUGGESTIONS, CHAPTER_AI_REVIEW, CLICHE_SCAN,
    # Memory
    MEMORY_EXTRACTION, EMOTION_LEDGER_EXTRACTION,
    # Planning
    MACRO_PLANNING, PLANNING_QUICK_MACRO, PLANNING_PRECISE_MACRO,
    PLANNING_PRECISE_VOLUME, PLANNING_PRECISE_REPAIR, PLANNING_ACT,
    CONTINUOUS_PLANNING_NEXT_ACT, OUTLINE_BEAT_PARTITION, BEAT_COT_BRIDGE,
    # Style
    STYLE_ANALYSIS, VOICE_STYLE_ANALYSIS, VOICE_BASELINE_ANALYSIS,
    VOICE_REWRITE, VOICE_DRIFT,
    # Tension
    TENSION_SCORING, TENSION_ANALYSIS_DIAGNOSIS,
    # Summary
    SUMMARY_CHECKPOINT, SUMMARY_ACT, SUMMARY_VOLUME, SUMMARY_PART,
    # Knowledge
    KNOWLEDGE_INITIAL, KG_INFERENCE,
    # DAG context / gateways
    CONTEXT_BLUEPRINT, CONTEXT_FORESHADOW, CONTEXT_MEMORY, CONTEXT_DEBT,
    FORESHADOW_CHECK, CHAPTER_AFTERMATH, CIRCUIT_BREAKER, REVIEW_GATEWAY,
    CONDITION_GATEWAY, RETRY_GATEWAY,
    # Anti-AI
    ANTI_AI_BEHAVIOR_PROTOCOL, ANTI_AI_ALLOWLIST_EXPLAIN,
    ANTI_AI_CHAPTER_AUDIT, ANTI_AI_CHARACTER_STATE_LOCK,
    ANTI_AI_FINALE_ENHANCEMENT, ANTI_AI_MID_GENERATION_REFRESH,
    # Autopilot / Workflow
    WORKFLOW_CHAPTER_GENERATION, AUTOPILOT_STREAM_BEAT,
    BEAT_FOCUS_INSTRUCTIONS, LIFECYCLE_PHASE_DIRECTIVES,
    REFACTOR_PROPOSAL_MACRO, PLANNING_MAIN_PLOT_OPTION,
})


def is_valid_key(key: str) -> bool:
    """Check if a key is registered. Dynamic keys (theme-*, skill-*) always pass."""
    if key.startswith("theme-") or key.startswith("skill-"):
        return True
    return key in ALL_KEYS


def validate_key(key: str) -> None:
    """Raise ValueError if key is not registered (excluding dynamic theme/skill keys)."""
    if not is_valid_key(key):
        raise ValueError(
            f"Unknown prompt node key: {key!r}. "
            f"Register it in infrastructure/ai/prompt_keys.py first."
        )
