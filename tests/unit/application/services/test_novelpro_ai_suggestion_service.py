import json

import pytest

from application.analyst.services.novelpro_ai_suggestion_service import (
    NovelProAISuggestionService,
)


class FakeLLMResult:
    def __init__(self, content):
        self.content = content


class FakeLLMService:
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    async def generate(self, prompt, config):
        self.prompts.append(prompt)
        return FakeLLMResult(json.dumps(self.payload, ensure_ascii=False))


class FakeKnowledgeService:
    def get_knowledge(self, novel_id):
        return type(
            "Knowledge",
            (),
            {
                "premise_lock": "主角每次越级都必须付出代价。",
                "facts": [],
                "chapters": [],
            },
        )()


class FakeBibleService:
    def get_bible_by_novel(self, novel_id):
        return type("Bible", (), {"theme": "黑塔城复仇", "genre": "系统文"})()


class FakeContinuityService:
    def get_overview(self, novel_id, chapter_number=None):
        return {
            "chapter_number": chapter_number or 3,
            "character_dropouts": [{"character_name": "林夜", "chapters_absent": 6}],
            "outline_deviation": {"status": "warning", "warning_reasons": ["黑塔潜入节点缺失"]},
        }


class FakePowerSystemService:
    def get_overview(self, novel_id):
        return {
            "rules": {"tier_schema": "黑铁 < 青铜 < 白银"},
            "warnings": [{"title": "疑似无代价越级"}],
        }


@pytest.mark.asyncio
async def test_suggest_fields_returns_json_fields_with_context():
    llm = FakeLLMService({
        "fields": {
            "mental_state": "压抑怒意但保持冷静",
            "verbal_tic": "别急，账要一笔一笔算",
            "idle_behavior": "拇指摩挲刀柄",
            "ooc_guardrails": "不要写成轻浮话痨。",
        },
        "rationale": "根据复仇基调和掉线提醒生成。",
    })
    service = NovelProAISuggestionService(
        llm_service=llm,
        knowledge_service=FakeKnowledgeService(),
        bible_service=FakeBibleService(),
        continuity_service=FakeContinuityService(),
        power_system_service=FakePowerSystemService(),
    )

    result = await service.suggest_fields(
        novel_id="novel-ai-suggest",
        suggestion_type="voice_anchor",
        fields=["mental_state", "verbal_tic", "idle_behavior", "ooc_guardrails"],
        chapter_number=3,
        target={"character_name": "林夜"},
        current_values={},
    )

    assert result["fields"]["mental_state"] == "压抑怒意但保持冷静"
    assert result["fields"]["ooc_guardrails"] == "不要写成轻浮话痨。"
    assert result["rationale"] == "根据复仇基调和掉线提醒生成。"
    assert "主角每次越级都必须付出代价" in llm.prompts[0].user
