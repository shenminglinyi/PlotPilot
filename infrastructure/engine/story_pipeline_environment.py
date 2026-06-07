"""Environment-backed StoryPipeline runtime mode configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


STORY_PIPELINE_MODE_ENV = "PLOTPILOT_USE_STORY_PIPELINE"
StoryPipelineMode = Literal["off", "writing", "full"]


@dataclass(frozen=True)
class StoryPipelineEnvironmentSettings:
    """Typed view of the StoryPipeline runtime mode flag."""

    raw_mode: str = ""

    @classmethod
    def from_env(cls) -> "StoryPipelineEnvironmentSettings":
        return cls(raw_mode=(os.getenv(STORY_PIPELINE_MODE_ENV, "") or "").strip())

    @property
    def normalized_mode(self) -> str:
        return self.raw_mode.lower()

    @property
    def mode(self) -> StoryPipelineMode:
        value = self.normalized_mode
        if value in {"off", "legacy", "false", "0", "no"}:
            return "off"
        if value in {"full", "all", "engine"}:
            return "full"
        return "writing"

    @property
    def is_unset(self) -> bool:
        return not self.normalized_mode

    @property
    def is_unknown(self) -> bool:
        value = self.normalized_mode
        if not value:
            return False
        known = {
            "off",
            "legacy",
            "false",
            "0",
            "no",
            "full",
            "all",
            "engine",
            "1",
            "true",
            "yes",
            "on",
            "writing",
        }
        return value not in known
