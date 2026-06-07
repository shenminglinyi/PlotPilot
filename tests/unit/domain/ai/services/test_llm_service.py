# tests/unit/domain/ai/services/test_llm_service.py
import pytest
from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage


class TestGenerationConfig:
    """测试 GenerationConfig 验证"""

    def test_generation_config_creation(self):
        """测试创建 GenerationConfig"""
        config = GenerationConfig(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4096,
            temperature=1.0
        )
        assert config.model == "claude-3-5-sonnet-20241022"
        assert config.max_tokens == 4096
        assert config.temperature == 1.0

    def test_generation_config_default_values(self):
        """测试默认值"""
        config = GenerationConfig()
        assert config.model == ""
        assert config.max_tokens == 4096
        assert config.temperature == 1.0

    def test_generation_config_temperature_below_zero_raises_error(self):
        """测试温度小于 0 抛出异常"""
        with pytest.raises(ValueError, match="Temperature must be between 0.0 and 2.0"):
            GenerationConfig(temperature=-0.1)

    def test_generation_config_temperature_above_two_raises_error(self):
        """测试温度大于 2.0 抛出异常"""
        with pytest.raises(ValueError, match="Temperature must be between 0.0 and 2.0"):
            GenerationConfig(temperature=2.1)

    def test_generation_config_max_tokens_zero_raises_error(self):
        """测试 max_tokens 为 0 抛出异常"""
        with pytest.raises(ValueError, match="max_tokens must be greater than 0"):
            GenerationConfig(max_tokens=0)

    def test_generation_config_max_tokens_negative_raises_error(self):
        """测试 max_tokens 为负数抛出异常"""
        with pytest.raises(ValueError, match="max_tokens must be greater than 0"):
            GenerationConfig(max_tokens=-1)

    def test_generation_config_valid_temperature_boundaries(self):
        """测试温度边界值"""
        config_min = GenerationConfig(temperature=0.0)
        assert config_min.temperature == 0.0

        config_max = GenerationConfig(temperature=2.0)
        assert config_max.temperature == 2.0


class TestGenerationResult:
    """测试 GenerationResult 验证"""

    def test_generation_result_creation(self):
        """测试创建 GenerationResult"""
        token_usage = TokenUsage(input_tokens=100, output_tokens=200)
        result = GenerationResult(content="生成的内容", token_usage=token_usage)
        assert result.content == "生成的内容"
        assert result.token_usage.input_tokens == 100
        assert result.token_usage.output_tokens == 200

    def test_generation_result_empty_content_raises_error(self):
        """测试空内容抛出异常"""
        token_usage = TokenUsage(input_tokens=100, output_tokens=200)
        with pytest.raises(ValueError, match="Content cannot be empty"):
            GenerationResult(content="", token_usage=token_usage)

    def test_generation_result_whitespace_only_content_raises_error(self):
        """测试仅空白字符的内容抛出异常"""
        token_usage = TokenUsage(input_tokens=100, output_tokens=200)
        with pytest.raises(ValueError, match="Content cannot be empty"):
            GenerationResult(content="   ", token_usage=token_usage)

    def test_generation_result_negative_input_tokens_raises_error(self):
        """测试负数 input_tokens 抛出异常"""
        with pytest.raises(ValueError, match="Token counts cannot be negative"):
            token_usage = TokenUsage(input_tokens=-1, output_tokens=200)
            GenerationResult(content="内容", token_usage=token_usage)

    def test_generation_result_negative_output_tokens_raises_error(self):
        """测试负数 output_tokens 抛出异常"""
        with pytest.raises(ValueError, match="Token counts cannot be negative"):
            token_usage = TokenUsage(input_tokens=100, output_tokens=-1)
            GenerationResult(content="内容", token_usage=token_usage)

