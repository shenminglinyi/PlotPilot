"""Tests for MacroRefactorProposalService"""
import pytest
from unittest.mock import AsyncMock, Mock
from application.audit.services.macro_refactor_proposal_service import MacroRefactorProposalService
from application.audit.dtos.macro_refactor_dto import RefactorProposalRequest, RefactorProposal
from domain.ai.value_objects.prompt import Prompt
from domain.ai.services.llm_service import GenerationResult, GenerationConfig
from domain.ai.value_objects.token_usage import TokenUsage


@pytest.fixture
def mock_llm_service():
    """Mock LLM service"""
    return AsyncMock()


@pytest.fixture
def proposal_service(mock_llm_service):
    """Create proposal service with mock LLM"""
    return MacroRefactorProposalService(mock_llm_service)


@pytest.mark.asyncio
async def test_generate_proposal_returns_structured_data(proposal_service, mock_llm_service):
    """测试生成提案返回结构化数据"""
    # Arrange
    request = RefactorProposalRequest(
        event_id="evt_001",
        author_intent="让角色表现得更冷酷",
        current_event_summary="角色冲动地救了一个陌生人",
        current_tags=["动机:冲动", "情感:同情"]
    )

    # Mock LLM response with JSON
    llm_response = """
    {
        "natural_language_suggestion": "建议修改角色的动机，从冲动改为理性计算",
        "suggested_mutations": [
            {"type": "replace_tag", "old": "动机:冲动", "new": "动机:理性"},
            {"type": "remove_tag", "tag": "情感:同情"}
        ],
        "suggested_tags": ["动机:理性", "性格:冷酷"],
        "reasoning": "冷酷的角色不会冲动行事，应该基于理性判断"
    }
    """

    mock_llm_service.generate.return_value = GenerationResult(
        content=llm_response,
        token_usage=TokenUsage(input_tokens=100, output_tokens=200)
    )

    # Act
    proposal = await proposal_service.generate_proposal(request)

    # Assert
    assert isinstance(proposal, RefactorProposal)
    assert proposal.natural_language_suggestion == "建议修改角色的动机，从冲动改为理性计算"
    assert len(proposal.suggested_mutations) == 2
    assert proposal.suggested_mutations[0]["type"] == "replace_tag"
    assert proposal.suggested_tags == ["动机:理性", "性格:冷酷"]
    assert "冷酷的角色不会冲动行事" in proposal.reasoning

    # Verify LLM was called with correct prompt
    mock_llm_service.generate.assert_called_once()
    call_args = mock_llm_service.generate.call_args
    prompt = call_args[0][0]
    assert isinstance(prompt, Prompt)
    assert "小说编辑助手" in prompt.system
    assert "让角色表现得更冷酷" in prompt.user


@pytest.mark.asyncio
async def test_generate_proposal_handles_llm_error(proposal_service, mock_llm_service):
    """测试处理 LLM 错误时优雅降级"""
    # Arrange
    request = RefactorProposalRequest(
        event_id="evt_001",
        author_intent="让角色表现得更冷酷",
        current_event_summary="角色冲动地救了一个陌生人",
        current_tags=["动机:冲动"]
    )

    # Mock LLM to raise exception
    mock_llm_service.generate.side_effect = Exception("LLM service unavailable")

    # Act
    proposal = await proposal_service.generate_proposal(request)

    # Assert - should return fallback proposal
    assert isinstance(proposal, RefactorProposal)
    assert "无法生成具体建议" in proposal.natural_language_suggestion
    assert proposal.suggested_mutations == []
    assert proposal.suggested_tags == []
    assert "LLM 服务暂时不可用" in proposal.reasoning


@pytest.mark.asyncio
async def test_generate_proposal_parses_mutations(proposal_service, mock_llm_service):
    """测试正确解析 suggested_mutations 格式"""
    # Arrange
    request = RefactorProposalRequest(
        event_id="evt_001",
        author_intent="修复人设冲突",
        current_event_summary="事件摘要",
        current_tags=["tag1"]
    )

    # Mock LLM response with various mutation types
    llm_response = """
    {
        "natural_language_suggestion": "建议",
        "suggested_mutations": [
            {"type": "add_tag", "tag": "新标签"},
            {"type": "remove_tag", "tag": "旧标签"},
            {"type": "replace_tag", "old": "旧", "new": "新"}
        ],
        "suggested_tags": ["新标签"],
        "reasoning": "推理"
    }
    """

    mock_llm_service.generate.return_value = GenerationResult(
        content=llm_response,
        token_usage=TokenUsage(input_tokens=100, output_tokens=200)
    )

    # Act
    proposal = await proposal_service.generate_proposal(request)

    # Assert
    assert len(proposal.suggested_mutations) == 3
    assert proposal.suggested_mutations[0]["type"] == "add_tag"
    assert proposal.suggested_mutations[1]["type"] == "remove_tag"
    assert proposal.suggested_mutations[2]["type"] == "replace_tag"
    assert "old" in proposal.suggested_mutations[2]
    assert "new" in proposal.suggested_mutations[2]


@pytest.mark.asyncio
async def test_generate_proposal_handles_invalid_json(proposal_service, mock_llm_service):
    """测试处理无效 JSON 响应"""
    # Arrange
    request = RefactorProposalRequest(
        event_id="evt_001",
        author_intent="修复",
        current_event_summary="摘要",
        current_tags=["tag1"]
    )

    # Mock LLM to return invalid JSON
    mock_llm_service.generate.return_value = GenerationResult(
        content="This is not valid JSON",
        token_usage=TokenUsage(input_tokens=100, output_tokens=50)
    )

    # Act
    proposal = await proposal_service.generate_proposal(request)

    # Assert - should return fallback proposal
    assert isinstance(proposal, RefactorProposal)
    assert "无法生成具体建议" in proposal.natural_language_suggestion
    assert proposal.suggested_mutations == []
