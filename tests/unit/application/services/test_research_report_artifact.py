import pytest

from application.world.services.auto_bible_generator import AutoBibleGenerator


class _FakeBibleService:
    def __init__(self):
        self._ext = {}

    def get_extensions(self, novel_id: str) -> dict:
        return self._ext.get(novel_id, {})

    def update_extensions(self, novel_id: str, patch: dict) -> dict:
        current = dict(self._ext.get(novel_id, {}))
        for k, v in (patch or {}).items():
            if isinstance(v, dict) and isinstance(current.get(k), dict):
                merged = dict(current.get(k) or {})
                merged.update(v)
                current[k] = merged
            else:
                current[k] = v
        self._ext[novel_id] = current
        return current


@pytest.mark.asyncio
async def test_ensure_research_report_cached(monkeypatch):
    bible_service = _FakeBibleService()
    gen = AutoBibleGenerator(llm_service=None, bible_service=bible_service)

    calls = {"n": 0}

    async def _fake_research(premise: str) -> dict:
        calls["n"] += 1
        return {
            "version": 1,
            "keywords": ["k1", "k2"],
            "facts": ["f1"],
            "sources": [{"title": "t", "url": "u"}],
            "markdown": "## 事实清单（用于硬约束）\n- f1\n",
        }

    monkeypatch.setattr(gen, "_research_background", _fake_research)

    r1 = await gen._ensure_research_report("novel-1", "premise-1")
    r2 = await gen._ensure_research_report("novel-1", "premise-1")

    assert calls["n"] == 1
    assert r1 == r2
    assert bible_service.get_extensions("novel-1").get("research") is not None
