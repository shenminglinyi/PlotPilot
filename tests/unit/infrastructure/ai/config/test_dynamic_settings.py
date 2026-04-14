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
        openai_api_key="sk-test",
        openai_base_url="https://api.test.com",
        default_model="gpt-4o",
        cheap_model="gpt-4o-mini"
    )
    manager.save_config(new_config)
    
    # Test read
    loaded = manager.load_config()
    assert loaded is not None
    assert loaded.provider == "openai"
    assert loaded.default_model == "gpt-4o"
