import json
from dataclasses import dataclass

import pytest

from application.narrative.entity_resolver import EntityResolver
from application.prop.extractors.llm_extractor import LlmExtractor
from domain.prop.value_objects.prop_event import PropEventType
from infrastructure.ai.prompt_utils import PromptTemplateUnavailable


@dataclass
class _Id:
    value: str


@dataclass
class _Character:
    id: _Id
    name: str


class _Repo:
    def __init__(self, rows):
        self.rows = rows

    def list_by_novel(self, novel_id):
        return self.rows


class _Result:
    def __init__(self, content):
        self.content = content


class _Llm:
    def __init__(self):
        self.calls = 0

    async def generate(self, prompt, config):
        self.calls += 1
        return _Result(
            json.dumps(
                [
                    {
                        "prop_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "event_type": "TRANSFERRED",
                        "actor_character": "林澈",
                        "from_holder": "林澈",
                        "to_holder": "秦鸢",
                        "description": "林澈把青铜罗盘交给秦鸢",
                    }
                ],
                ensure_ascii=False,
            )
        )


@pytest.mark.asyncio
async def test_llm_extractor_resolves_character_names_to_ids():
    resolver = EntityResolver(
        character_repo=_Repo(
            [
                _Character(_Id("char-lin"), "林澈"),
                _Character(_Id("char-qin"), "秦鸢"),
            ]
        )
    )
    extractor = LlmExtractor(_Llm(), resolver)

    events = await extractor.extract(
        "novel-1",
        3,
        "正文" * 200,
        [
            {
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "name": "青铜罗盘",
                "aliases": ["罗盘"],
                "holder": "char-lin",
                "state": "ACTIVE",
            }
        ],
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == PropEventType.TRANSFERRED
    assert event.actor_character_id == "char-lin"
    assert event.from_holder_id == "char-lin"
    assert event.to_holder_id == "char-qin"


@pytest.mark.asyncio
async def test_llm_extractor_blocks_when_cpms_template_missing(monkeypatch):
    llm = _Llm()

    def _missing_prompt(*args, **kwargs):
        raise PromptTemplateUnavailable("missing prop-event-extraction")

    monkeypatch.setattr(
        "infrastructure.ai.prompt_utils.render_required_prompt",
        _missing_prompt,
    )

    extractor = LlmExtractor(llm)

    with pytest.raises(PromptTemplateUnavailable):
        await extractor.extract(
            "novel-1",
            3,
            "正文" * 200,
            [
                {
                    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "name": "青铜罗盘",
                    "holder": "char-lin",
                }
            ],
        )

    assert llm.calls == 0
