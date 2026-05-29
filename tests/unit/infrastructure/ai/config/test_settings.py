"""Settings 配置测试"""
import pytest
from infrastructure.ai.config.settings import Settings


class TestSettings:
    """Settings 配置测试"""

    def test_default_values(self):
        """测试默认值"""
        settings = Settings()

        assert settings.default_model == ""
        assert settings.default_temperature == 0.7
        assert settings.default_max_tokens == 4096
        assert settings.api_key is None

    def test_custom_values(self):
        """测试自定义值"""
        settings = Settings(
            default_model="claude-3-opus-20240229",
            default_temperature=0.5,
            default_max_tokens=2048,
            api_key="test-key"
        )

        assert settings.default_model == "claude-3-opus-20240229"
        assert settings.default_temperature == 0.5
        assert settings.default_max_tokens == 2048
        assert settings.api_key == "test-key"

    def test_temperature_validation(self):
        """测试温度参数验证"""
        with pytest.raises(ValueError, match="Temperature must be between 0.0 and 2.0"):
            Settings(default_temperature=-0.1)

        with pytest.raises(ValueError, match="Temperature must be between 0.0 and 2.0"):
            Settings(default_temperature=2.1)

    def test_max_tokens_validation(self):
        """测试最大 token 数验证"""
        with pytest.raises(ValueError, match="Max tokens must be positive"):
            Settings(default_max_tokens=0)

        with pytest.raises(ValueError, match="Max tokens must be positive"):
            Settings(default_max_tokens=-100)
