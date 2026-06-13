from typing import List
from pydantic import BaseModel, Field
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.gemini_provider import GeminiProvider

class SubModel(BaseModel):
    name: str = Field(..., max_length=10)

class DummyPayload(BaseModel):
    title: str = Field(default="", max_length=100)
    items: List[SubModel] = Field(default_factory=list)

def test_to_gemini_schema():
    settings = Settings(api_key="dummy_key")
    provider = GeminiProvider(settings)
    
    schema = provider._to_gemini_schema(DummyPayload)
    
    # Assert output is clean and has resolved definitions/refs
    assert "$defs" not in schema
    assert "$ref" not in schema
    assert "properties" in schema
    assert "title" not in schema.get("properties", {}).get("title", {})
    
    # Assert array items sub-model is correctly inlined
    facts_schema = schema["properties"]["items"]
    assert facts_schema["type"] == "array"
    
    sub_model_schema = facts_schema["items"]
    assert sub_model_schema["type"] == "object"
    assert "name" in sub_model_schema["properties"]
    assert sub_model_schema["properties"]["name"]["maxLength"] == 10

def test_build_payload_gemini_3():
    from domain.ai.value_objects.prompt import Prompt
    from domain.ai.services.llm_service import GenerationConfig
    settings = Settings(
        api_key="dummy_key",
        extra_body={
            "thinking_level": "high",
            "top_p": 0.9,
            "top_k": 40,
            "temperature": 0.5
        }
    )
    provider = GeminiProvider(settings)
    prompt = Prompt(system="System Prompt", user="User Prompt")
    config = GenerationConfig(model="gemini-3.5-flash", max_tokens=1000, temperature=0.7)
    
    payload = provider._build_payload(prompt, config, model_id="gemini-3.5-flash")
    
    generation_config = payload.get("generationConfig", {})
    # Temperature and other sampling parameters should be removed for Gemini 3
    assert "temperature" not in generation_config
    assert "top_p" not in generation_config
    assert "top_k" not in generation_config
    
    # thinkingConfig should be set to uppercase 'HIGH'
    assert generation_config.get("thinkingConfig") == {"thinkingLevel": "HIGH"}
    # maxOutputTokens should be scaled up (max(1000 + 8192, 16384) = 16384)
    assert generation_config.get("maxOutputTokens") == 16384

    # Test when thinking_level is MINIMAL
    settings_minimal = Settings(
        api_key="dummy_key",
        extra_body={
            "thinking_level": "minimal"
        }
    )
    provider_minimal = GeminiProvider(settings_minimal)
    payload_minimal = provider_minimal._build_payload(prompt, config, model_id="gemini-3.5-flash")
    generation_config_minimal = payload_minimal.get("generationConfig", {})
    assert generation_config_minimal.get("thinkingConfig") == {"thinkingLevel": "MINIMAL"}
    # maxOutputTokens should NOT be scaled up, keeping the original 1000
    assert generation_config_minimal.get("maxOutputTokens") == 1000


def test_build_payload_legacy():
    from domain.ai.value_objects.prompt import Prompt
    from domain.ai.services.llm_service import GenerationConfig
    settings = Settings(
        api_key="dummy_key",
        extra_body={
            "top_p": 0.9,
            "top_k": 40
        }
    )
    provider = GeminiProvider(settings)
    prompt = Prompt(system="System Prompt", user="User Prompt")
    config = GenerationConfig(model="gemini-1.5-flash", max_tokens=1000, temperature=0.7)
    
    payload = provider._build_payload(prompt, config, model_id="gemini-1.5-flash")
    
    generation_config = payload.get("generationConfig", {})
    # Temperature and extra_body params should remain for legacy models
    assert generation_config.get("temperature") == 0.7
    assert payload.get("top_p") == 0.9
    assert payload.get("top_k") == 40


def test_gemini_provider_http_timeout_uses_settings():
    provider = GeminiProvider(
        Settings(
            api_key="test-api-key",
            connect_timeout=4,
            read_timeout=40,
            write_timeout=8,
            pool_timeout=2,
        )
    )

    timeout = provider._http_client.timeout
    assert timeout.connect == 4
    assert timeout.read == 40
    assert timeout.write == 8
    assert timeout.pool == 2
