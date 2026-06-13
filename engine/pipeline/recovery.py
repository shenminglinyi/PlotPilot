"""StoryPipeline step commit boundary definitions."""
from __future__ import annotations

from dataclasses import dataclass


class StepCommitKind:
    TRANSIENT = "transient"
    STABLE = "stable"


class InterruptedAction:
    RETRY_STEP = "retry_step"
    PRESERVE_RESULT = "preserve_result"
    PAUSE_REVIEW = "pause_review"


@dataclass(frozen=True)
class PipelineStepBoundary:
    step_name: str
    stable_stage: str
    commit_kind: str = StepCommitKind.TRANSIENT
    on_interrupted: str = InterruptedAction.RETRY_STEP


PIPELINE_STEP_BOUNDARIES: dict[str, PipelineStepBoundary] = {
    "find_next_chapter": PipelineStepBoundary("find_next_chapter", "writing"),
    "prepare_governance": PipelineStepBoundary("prepare_governance", "writing"),
    "prepare_chapter_plan": PipelineStepBoundary(
        "prepare_chapter_plan",
        "writing",
        StepCommitKind.STABLE,
        InterruptedAction.RETRY_STEP,
    ),
    "build_context": PipelineStepBoundary("build_context", "writing"),
    "generate": PipelineStepBoundary("generate", "writing", StepCommitKind.TRANSIENT, InterruptedAction.RETRY_STEP),
    "save_chapter": PipelineStepBoundary(
        "save_chapter",
        "auditing",
        StepCommitKind.STABLE,
        InterruptedAction.PRESERVE_RESULT,
    ),
    "validate_voice": PipelineStepBoundary("validate_voice", "auditing"),
    "run_post_commit": PipelineStepBoundary("run_post_commit", "auditing", StepCommitKind.STABLE),
    "score_tension": PipelineStepBoundary("score_tension", "auditing", StepCommitKind.STABLE),
    "finalize": PipelineStepBoundary("finalize", "auditing", StepCommitKind.STABLE),
}


def boundary_for(step_name: str) -> PipelineStepBoundary:
    return PIPELINE_STEP_BOUNDARIES.get(
        step_name,
        PipelineStepBoundary(step_name=step_name, stable_stage="writing"),
    )

