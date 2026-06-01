import json

import pytest

from application.audit.services.chapter_ai_review_service import (
    ChapterAIReviewContractError,
    ChapterAIReviewService,
)
from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def generate(self, prompt, config):
        self.calls.append((prompt, config))
        return GenerationResult(
            json.dumps(self.payload, ensure_ascii=False),
            TokenUsage(input_tokens=1, output_tokens=1),
        )


@pytest.mark.asyncio
async def test_chapter_ai_review_service_builds_memo_from_cpms_result():
    llm = FakeLLM(
        {
            "status": "approved",
            "score": 91,
            "summary": "推进完整，人物行动可信。",
            "issues": [],
            "suggestions": ["保留当前冲突链，只微调个别长句。"],
        }
    )
    service = ChapterAIReviewService(llm)

    result = await service.review(
        chapter_number=3,
        chapter_title="雨夜追问",
        chapter_content="雨声压在窗沿。沈岚把证据推到灯下。",
    )

    assert result.status == "approved"
    assert result.score == 91
    assert result.suggestions == ["保留当前冲突链，只微调个别长句。"]
    assert "综合评分：91" in result.memo
    assert llm.calls[0][1].response_format == {"type": "json_object"}


@pytest.mark.asyncio
async def test_chapter_ai_review_service_critical_issue_forces_draft():
    llm = FakeLLM(
        {
            "status": "approved",
            "score": 88,
            "summary": "模型误判为可通过。",
            "issues": [
                {
                    "severity": "critical",
                    "location": "结尾",
                    "description": "章节明显截断。",
                    "suggestion": "补完关键行动结果。",
                }
            ],
            "suggestions": ["补完关键行动结果。"],
        }
    )
    service = ChapterAIReviewService(llm)

    result = await service.review(
        chapter_number=4,
        chapter_title="断点",
        chapter_content="他刚推开门，",
    )

    assert result.status == "draft"
    assert "[critical] 结尾：章节明显截断" in result.memo


@pytest.mark.asyncio
async def test_chapter_ai_review_service_blocks_when_suggestions_missing():
    llm = FakeLLM({"status": "approved", "score": 90, "summary": "可通过"})
    service = ChapterAIReviewService(llm)

    with pytest.raises(ChapterAIReviewContractError, match="缺少可执行建议"):
        await service.review(
            chapter_number=1,
            chapter_title="空建议",
            chapter_content="这是一段正文。",
        )
