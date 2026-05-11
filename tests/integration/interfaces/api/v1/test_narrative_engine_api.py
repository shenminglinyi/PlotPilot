"""叙事引擎聚合 API 冒烟测试"""

from fastapi.testclient import TestClient

from interfaces.main import app

client = TestClient(app)


def test_narrative_engine_story_evolution_route():
    r = client.get("/api/v1/novels/test-novel/narrative-engine/story-evolution")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        data = r.json()
        assert data.get("schema_version") == "1"
        assert "life_cycle" in data
        assert "plot_spine" in data
        assert "storylines" in data["plot_spine"]
        assert "chronotope" in data
        assert "rows" in data["chronotope"]


def test_narrative_engine_persona_voice_route():
    r = client.get("/api/v1/novels/test-novel/narrative-engine/persona-voice/char-1")
    assert r.status_code in (200, 404, 422)
    if r.status_code == 200:
        data = r.json()
        assert data.get("schema_version") == "1"
        assert "voice_anchor" in data
        assert "dialogue_corpus" in data


def test_narrative_engine_surface_catalog():
    r = client.get("/api/v1/narrative-engine/surface-catalog")
    assert r.status_code == 200
    data = r.json()
    assert data.get("schema_version") == "1"
    assert isinstance(data.get("lenses"), list)
    assert isinstance(data.get("families"), list)
    assert len(data["families"]) >= 5
    lens_ids = {x["id"] for x in data["lenses"]}
    assert "narrative_engine" in lens_ids
