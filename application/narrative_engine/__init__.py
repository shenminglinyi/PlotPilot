"""叙事引擎（Novelist-facing read surface）

本包从**职业小说家工作流**抽象只读聚合面，底层仍复用既有仓储与
`QueryService` / `SandboxDialogueService` / Bible 等实现，避免重复业务逻辑。

维度与 HTTP 能力族见 `catalog.NarrativeLens`、`api_catalog.API_SURFACE_FAMILIES`；
运行时目录可 GET `/api/v1/narrative-engine/surface-catalog`。

HTTP 入口：`interfaces.api.v1.engine.narrative_engine_routes`
"""

from application.narrative_engine.api_catalog import build_surface_catalog_payload
from application.narrative_engine.read_facade import NarrativeEngineReadFacade
from application.narrative_engine.story_phase_resolution import resolve_story_phase_payload

__all__ = [
    "NarrativeEngineReadFacade",
    "resolve_story_phase_payload",
    "build_surface_catalog_payload",
]
