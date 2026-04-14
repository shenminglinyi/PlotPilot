from fastapi.testclient import TestClient
from interfaces.main import app

client = TestClient(app)

def test_get_llm_config():
    response = client.get("/api/v1/system/llm/config")
    assert response.status_code in [200, 404]

def test_verify_models_mock():
    # Test validation failure without keys
    payload = {"provider": "openai", "base_url": ""}
    response = client.post("/api/v1/system/llm/verify", json=payload)
    assert response.status_code == 422 or response.status_code == 400
