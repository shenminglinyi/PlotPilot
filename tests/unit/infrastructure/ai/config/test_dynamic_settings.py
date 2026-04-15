import json
import os
from pathlib import Path
from infrastructure.ai.config.dynamic_settings import DynamicSettingsManager, LLMConfigDTO

def test_dynamic_settings_read_write(tmp_path):
    config_path = tmp_path / "llm_config.json"
    manager = DynamicSettingsManager(config_path)
    
    # Test default/empty
    config = manager.load_config()
    assert config is None
    
    # Test write
    new_config = LLMConfigDTO(
        provider="openai",
        default_model_provider="openai",
        default_model_api_key="sk-test",
        default_model_base_url="https://api.test.com/v1",
        default_model="gpt-4o",
        cheap_model_provider="openai",
        cheap_model_api_key="sk-test",
        cheap_model_base_url="https://api.test.com/v1",
        cheap_model="gpt-4o-mini",
        fact_review_model_provider="openai",
        fact_review_model_api_key="sk-test",
        fact_review_model_base_url="https://api.test.com/v1",
        fact_review_model="gpt-4o-mini",
    )
    manager.save_config(new_config)
    
    # Test read
    loaded = manager.load_config()
    assert loaded is not None
    assert loaded.provider == "openai"
    assert loaded.default_model == "gpt-4o"


def test_llm_config_dto_includes_reviewer_models():
    cfg = LLMConfigDTO(
        fact_review_model_provider="openai",
        fact_review_model_api_key="sk-test",
        fact_review_model_base_url="http://localhost:1234/v1",
        fact_review_model="gpt-4o-mini",
    )
    dumped = cfg.model_dump()
    assert dumped["fact_review_model"] == "gpt-4o-mini"
