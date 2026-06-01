import pytest
from unittest.mock import AsyncMock, Mock

from application.world.services import auto_knowledge_generator as module
from application.world.services.auto_knowledge_generator import (
    AutoKnowledgeGenerationError,
    AutoKnowledgeGenerator,
)
from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.prompt_utils import PromptTemplateUnavailable


def _prompt() -> Prompt:
    return Prompt(system="系统提示词", user="小说标题：《测试》")


def _result(content: str) -> GenerationResult:
    return GenerationResult(content=content, token_usage=TokenUsage(1, 1))


@pytest.mark.asyncio
async def test_auto_knowledge_uses_required_cpms_prompt(monkeypatch):
    rendered_prompt = _prompt()
    render = Mock(return_value=rendered_prompt)
    monkeypatch.setattr(module, "render_required_prompt", render)

    llm = Mock()
    llm.generate = AsyncMock(
        return_value=_result(
            '{"premise_lock":"主角必须面对代价完成选择。",'
            '"facts":[{"id":"fact-001","subject":"主角","predicate":"必须","object":"承担代价","note":"核心约束"}]}'
        )
    )
    knowledge_service = Mock()

    data = await AutoKnowledgeGenerator(llm, knowledge_service).generate_and_save(
        "novel-1",
        "测试小说",
        "已有设定",
    )

    render.assert_called_once_with(
        module.KNOWLEDGE_INITIAL,
        {"title": "测试小说", "bible_summary": "已有设定"},
    )
    llm.generate.assert_awaited_once()
    assert llm.generate.await_args.args[0] is rendered_prompt
    assert data["premise_lock"] == "主角必须面对代价完成选择。"
    knowledge_service.update_knowledge.assert_called_once()


@pytest.mark.asyncio
async def test_auto_knowledge_blocks_when_cpms_prompt_missing(monkeypatch):
    monkeypatch.setattr(
        module,
        "render_required_prompt",
        Mock(side_effect=PromptTemplateUnavailable("missing")),
    )
    llm = Mock()
    llm.generate = AsyncMock()

    with pytest.raises(PromptTemplateUnavailable):
        await AutoKnowledgeGenerator(llm, Mock()).generate_and_save("novel-1", "测试小说")

    llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_auto_knowledge_blocks_invalid_llm_contract(monkeypatch):
    monkeypatch.setattr(module, "render_required_prompt", Mock(return_value=_prompt()))
    llm = Mock()
    llm.generate = AsyncMock(return_value=_result('{"facts":[{"id":"fact-001","extra":"bad"}]}'))
    knowledge_service = Mock()

    with pytest.raises(AutoKnowledgeGenerationError):
        await AutoKnowledgeGenerator(llm, knowledge_service).generate_and_save("novel-1", "测试小说")

    knowledge_service.update_knowledge.assert_not_called()
