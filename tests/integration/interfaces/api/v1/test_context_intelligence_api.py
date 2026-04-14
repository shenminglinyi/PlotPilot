"""API 端点测试 - 场景导演分析"""
from fastapi.testclient import TestClient

from interfaces.main import app

# API endpoint constant
SCENE_DIRECTOR_ANALYZE_URL = "/api/v1/novels/{novel_id}/scene-director/analyze"


def test_scene_director_analyze_returns_json_shape():
    """Test that scene-director/analyze endpoint returns correct JSON shape"""
    client = TestClient(app)
    r = client.post(
        SCENE_DIRECTOR_ANALYZE_URL.format(novel_id="test-novel"),
        json={"chapter_number": 1, "outline": "主角进入房间。"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "characters" in data and isinstance(data["characters"], list)
    assert "locations" in data and isinstance(data["locations"], list)
    assert "action_types" in data and isinstance(data["action_types"], list)
    assert "trigger_keywords" in data and isinstance(data["trigger_keywords"], list)
    assert "emotional_state" in data and isinstance(data["emotional_state"], str)
    assert "pov" in data and (data["pov"] is None or isinstance(data["pov"], str))


def test_scene_director_analyze_with_longer_outline():
    """Test with a more complex outline"""
    client = TestClient(app)
    outline = """
    第一幕：主角李明进入古老的图书馆。
    第二幕：他发现了一本神秘的日记。
    第三幕：他开始阅读，陷入了沉思。
    """
    r = client.post(
        SCENE_DIRECTOR_ANALYZE_URL.format(novel_id="novel-123"),
        json={"chapter_number": 5, "outline": outline},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Verify all required fields are present
    assert all(k in data for k in [
        "characters", "locations", "action_types",
        "trigger_keywords", "emotional_state", "pov"
    ])


def test_scene_director_analyze_invalid_chapter_number():
    """Test that invalid chapter_number is rejected"""
    client = TestClient(app)
    r = client.post(
        SCENE_DIRECTOR_ANALYZE_URL.format(novel_id="test-novel"),
        json={"chapter_number": 0, "outline": "Some outline"},
    )
    assert r.status_code == 422  # Validation error


def test_scene_director_analyze_empty_outline():
    """Test that empty outline is rejected"""
    client = TestClient(app)
    r = client.post(
        SCENE_DIRECTOR_ANALYZE_URL.format(novel_id="test-novel"),
        json={"chapter_number": 1, "outline": ""},
    )
    assert r.status_code == 422  # Validation error


def test_scene_director_analyze_whitespace_only_outline():
    """Test that whitespace-only outline is rejected"""
    client = TestClient(app)
    r = client.post(
        SCENE_DIRECTOR_ANALYZE_URL.format(novel_id="test-novel"),
        json={"chapter_number": 1, "outline": "   \n\t  "},
    )
    assert r.status_code == 422  # Validation error


def test_scene_director_analyze_service_error_returns_generic_message():
    """Test that 500 error returns generic message, not internal details"""
    from unittest.mock import patch
    from application.engine.services.scene_director_service import SceneDirectorService

    client = TestClient(app)

    # Mock the service method to raise an exception
    with patch.object(SceneDirectorService, "analyze") as mock_analyze:
        mock_analyze.side_effect = RuntimeError("Internal database connection failed")

        r = client.post(
            SCENE_DIRECTOR_ANALYZE_URL.format(novel_id="test-novel"),
            json={"chapter_number": 1, "outline": "Some outline"},
        )

        assert r.status_code == 500
        data = r.json()
        # Verify generic message is returned, not the internal error
        assert data["detail"] == "Failed to analyze scene"
        assert "database" not in data["detail"].lower()
        assert "connection" not in data["detail"].lower()


def test_context_retrieve_returns_layers():
    """Test that context/retrieve endpoint returns correct layered structure"""
    client = TestClient(app)
    r = client.post(
        "/api/v1/novels/test-novel/context/retrieve",
        json={"chapter_number": 1, "outline": "开场。", "max_tokens": 8000},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Verify layer structure
    assert "layer1" in body
    assert "layer2" in body
    assert "layer3" in body
    assert "token_usage" in body

    # Verify each layer has content field
    assert "content" in body["layer1"]
    assert "content" in body["layer2"]
    assert "content" in body["layer3"]

    # Verify token_usage structure
    assert "total" in body["token_usage"]
    assert body["token_usage"]["total"] >= 0


def test_context_retrieve_with_scene_director_hint():
    """Test context/retrieve with optional scene_director_result"""
    client = TestClient(app)
    r = client.post(
        "/api/v1/novels/test-novel/context/retrieve",
        json={
            "chapter_number": 1,
            "outline": "主角进入房间。",
            "scene_director_result": {
                "characters": ["Alice"],
                "locations": ["Room A"],
                "action_types": ["enter"],
                "trigger_keywords": ["door"],
                "emotional_state": "curious",
                "pov": "Alice"
            },
            "max_tokens": 8000
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "layer1" in body
    assert "layer2" in body
    assert "layer3" in body


def test_context_retrieve_invalid_chapter_number():
    """Test that invalid chapter_number is rejected"""
    client = TestClient(app)
    r = client.post(
        "/api/v1/novels/test-novel/context/retrieve",
        json={"chapter_number": 0, "outline": "Some outline"},
    )
    assert r.status_code == 422  # Validation error


def test_context_retrieve_empty_outline():
    """Test that empty outline is rejected"""
    client = TestClient(app)
    r = client.post(
        "/api/v1/novels/test-novel/context/retrieve",
        json={"chapter_number": 1, "outline": ""},
    )
    assert r.status_code == 422  # Validation error


def test_context_retrieve_invalid_max_tokens():
    """Test that invalid max_tokens is rejected"""
    client = TestClient(app)
    r = client.post(
        "/api/v1/novels/test-novel/context/retrieve",
        json={"chapter_number": 1, "outline": "outline", "max_tokens": 1000},
    )
    assert r.status_code == 422  # max_tokens must be >= 4096
