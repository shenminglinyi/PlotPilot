"""Setup-guide plot outline service."""
from __future__ import annotations

from typing import Any, Dict

from application.blueprint.services.setup_context_builder import SetupContextBuilder
from application.core.services.novel_service import NovelService
from application.world.services.bible_service import BibleService
from domain.ai.services.llm_service import LLMService


class SetupPlotOutlineService:
    def __init__(
        self,
        llm_service: LLMService,
        bible_service: BibleService,
        novel_service: NovelService,
    ):
        self._llm = llm_service
        self._context_builder = SetupContextBuilder(
            bible_service=bible_service,
            novel_service=novel_service,
        )

    def build_context(self, novel_id: str) -> Dict[str, Any]:
        return self._context_builder.build_context(novel_id)

    @property
    def llm_service(self) -> LLMService:
        return self._llm
