import os
from unittest.mock import MagicMock
import pytest
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.vertex_ai_provider import VertexAIProvider, HAS_GENAI

@pytest.mark.skipif(not HAS_GENAI, reason="google-genai SDK not installed")
def test_build_genai_config_gemini_3():
    settings = Settings(
        api_key="dummy_key",
        extra_body={
            "thinking_level": "high",
            "top_p": 0.9,
            "top_k": 40
        }
    )
    provider = VertexAIProvider(settings)
    from domain.ai.services.llm_service import GenerationConfig
    config = GenerationConfig(model="gemini-3.5-flash", max_tokens=1000, temperature=0.7)
    
    gen_config = provider._build_genai_config(config, "System instruction", model_id="gemini-3.5-flash")
    
    # Assert temperature and other sampling parameters are removed for Gemini 3
    assert gen_config.temperature is None
    assert gen_config.top_p is None
    assert gen_config.top_k is None
    
    # Assert thinking config is mapped
    assert gen_config.thinking_config is not None
    assert gen_config.thinking_config.thinking_level == "high"
    assert gen_config.thinking_config.thinking_budget_tokens is None

@pytest.mark.skipif(not HAS_GENAI, reason="google-genai SDK not installed")
def test_build_genai_config_legacy():
    settings = Settings(
        api_key="dummy_key",
        extra_body={
            "top_p": 0.9,
            "top_k": 40
        }
    )
    provider = VertexAIProvider(settings)
    from domain.ai.services.llm_service import GenerationConfig
    config = GenerationConfig(model="gemini-1.5-flash", max_tokens=1000, temperature=0.7)
    
    gen_config = provider._build_genai_config(config, "System instruction", model_id="gemini-1.5-flash")
    
    # Legacy parameters should be kept
    assert gen_config.temperature == 0.7
    assert gen_config.top_p == 0.9
    assert gen_config.top_k == 40
