from unittest.mock import AsyncMock, Mock

import pytest

from application.ai.chapter_state_llm_contract import build_chapter_state_extraction_system_prompt
from application.ai.knowledge_llm_contract import build_initial_knowledge_system_prompt
from application.engine.services.chapter_bridge_service import ChapterBridgeService
from application.engine.services.scene_director_service import SceneDirectorService
from application.audit.services.chapter_ai_review_service import ChapterAIReviewService
from application.audit.dtos.macro_refactor_dto import RefactorProposalRequest
from application.audit.services.macro_refactor_proposal_service import MacroRefactorProposalService
from application.core.services.scene_generation_service import SceneGenerationService
from domain.novel.value_objects.scene import Scene
from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.prompt_utils import PromptTemplateUnavailable


class _MissingRegistry:
    def get_system(self, *_args, **_kwargs):
        return ""

    def render_to_prompt(self, *_args, **_kwargs):
        return None


def _patch_missing_registry(monkeypatch):
    monkeypatch.setattr(
        "infrastructure.ai.prompt_registry.get_prompt_registry",
        lambda: _MissingRegistry(),
    )


def test_chapter_state_prompt_blocks_when_cpms_missing(monkeypatch):
    _patch_missing_registry(monkeypatch)

    with pytest.raises(PromptTemplateUnavailable):
        build_chapter_state_extraction_system_prompt()


@pytest.mark.asyncio
async def test_macro_refactor_proposal_blocks_when_cpms_missing(monkeypatch):
    _patch_missing_registry(monkeypatch)
    llm = Mock()
    llm.generate = AsyncMock()
    svc = MacroRefactorProposalService(llm_service=llm)

    with pytest.raises(PromptTemplateUnavailable):
        await svc.generate_proposal(
            RefactorProposalRequest(
                event_id="evt-1",
                author_intent="修复动机",
                current_event_summary="角色行为与人设冲突",
                current_tags=[],
            )
        )

    llm.generate.assert_not_called()


def test_scene_generation_prompt_blocks_when_cpms_missing(monkeypatch):
    _patch_missing_registry(monkeypatch)
    svc = SceneGenerationService(
        llm_service=Mock(),
        scene_director=Mock(),
    )

    with pytest.raises(PromptTemplateUnavailable):
        svc._build_scene_prompt(
            scene=Scene(
                title="潜入",
                goal="找到证据",
                pov_character="主角",
                location="旧楼",
                tone="紧张",
                estimated_words=800,
                order_index=0,
            ),
            scene_analysis=Mock(characters=[], locations=[], emotional_state=""),
            relevant_context={"foreshadowings": []},
            previous_scenes=[],
            bible_context=None,
        )


def test_initial_knowledge_prompt_blocks_when_cpms_missing(monkeypatch):
    _patch_missing_registry(monkeypatch)

    with pytest.raises(PromptTemplateUnavailable):
        build_initial_knowledge_system_prompt()


@pytest.mark.asyncio
async def test_scene_director_does_not_call_llm_when_cpms_missing(monkeypatch):
    _patch_missing_registry(monkeypatch)
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult("{}", TokenUsage(input_tokens=1, output_tokens=1))
    )
    svc = SceneDirectorService(llm_service=llm)

    with pytest.raises(PromptTemplateUnavailable):
        await svc.analyze(chapter_number=1, outline="outline")

    llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_chapter_bridge_extract_blocks_when_cpms_missing(monkeypatch):
    _patch_missing_registry(monkeypatch)
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult("{}", TokenUsage(input_tokens=1, output_tokens=1))
    )
    svc = ChapterBridgeService(llm_service=llm)

    with pytest.raises(PromptTemplateUnavailable):
        await svc.extract_bridge("novel-1", 1, "tail content")

    llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_chapter_ai_review_blocks_when_cpms_missing(monkeypatch):
    _patch_missing_registry(monkeypatch)
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult("{}", TokenUsage(input_tokens=1, output_tokens=1))
    )
    svc = ChapterAIReviewService(llm_service=llm)

    with pytest.raises(PromptTemplateUnavailable):
        await svc.review(
            chapter_number=1,
            chapter_title="第一章",
            chapter_content="正文",
        )

    llm.generate.assert_not_called()
