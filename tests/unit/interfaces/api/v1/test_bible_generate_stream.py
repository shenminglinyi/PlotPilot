from types import SimpleNamespace

import pytest

from interfaces.api.v1.world import bible


class _FakeBibleService:
    def __init__(self):
        self._bible = SimpleNamespace(
            style_notes=[],
            characters=[],
            locations=[],
        )

    def get_bible_by_novel(self, _novel_id):
        return self._bible

    def create_bible(self, _bible_id, _novel_id):
        return self._bible

    def add_location(self, *, name, description, location_type, **_kwargs):
        self._bible.locations.append(
            SimpleNamespace(name=name, description=description, location_type=location_type)
        )


class _FakeBibleGenerator:
    def __init__(self):
        self.bible_service = _FakeBibleService()
        self.triple_repository = None

    def _load_worldbuilding(self, _novel_id):
        return {"core_rules": {"power_system": "灵能"}}

    def _load_characters(self, _novel_id):
        return [{"name": "阿澄", "description": "主角"}]

    async def _stream_generate_locations(self, *_args, **_kwargs):
        yield {"type": "chunk", "text": '{"locations":['}
        yield {
            "type": "location",
            "index": 0,
            "content": {
                "name": "旧港城",
                "description": "被潮汐与旧秩序共同压住的核心城邦。",
                "location_type": "city",
            },
        }
        yield {"type": "done", "count": 1}

    def _prepare_locations_for_save(self, novel_id, locations):
        return [
            {
                "location_id": f"{novel_id}-loc-{index + 1}",
                "name": item["name"],
                "description": item.get("description", ""),
                "location_type": item.get("location_type") or item.get("type") or "地点",
                "connections": [],
                "parent_id": None,
            }
            for index, item in enumerate(locations)
        ]


class _FakeKnowledgeGenerator:
    async def generate_and_save(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_bible_locations_stream_emits_incremental_location(monkeypatch):
    from interfaces.api import dependencies

    monkeypatch.setattr(
        dependencies,
        "get_novel_service",
        lambda: SimpleNamespace(
            get_novel=lambda _novel_id: SimpleNamespace(
                id="novel-1",
                title="测试小说",
                premise="旧港城少年破局",
                target_chapters=100,
            )
        ),
    )

    chunks = [
        chunk
        async for chunk in bible._sse_bible_generator(
            "novel-1",
            "locations",
            _FakeBibleGenerator(),
            _FakeKnowledgeGenerator(),
        )
    ]
    body = "".join(chunks)

    assert '"type": "approval_required"' not in body
    assert "event: data" in body
    assert '"type": "location"' in body
    assert '"name": "旧港城"' in body
    assert '"phase": "locations_done"' in body
