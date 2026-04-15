"""model_resolution 单元测试"""

from infrastructure.ai.model_resolution import (
    resolve_anthropic_model,
    resolve_openai_chat_model,
)


class TestResolveOpenAIChatModel:
    def test_empty_uses_env_or_gpt4o(self, monkeypatch):
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        assert resolve_openai_chat_model(None) == "gpt-4o"
        assert resolve_openai_chat_model("") == "gpt-4o"

    def test_claude_id_replaced_with_openai_default(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MODEL", "openai/gpt-oss-20b")
        assert resolve_openai_chat_model("claude-sonnet-4-6") == "openai/gpt-oss-20b"

    def test_explicit_openai_compatible_preserved(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
        assert resolve_openai_chat_model("local-model-xyz") == "local-model-xyz"


class TestResolveAnthropicModel:
    def test_empty_uses_env_or_sonnet(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        assert resolve_anthropic_model(None) == "claude-sonnet-4-6"

    def test_gpt_style_replaced(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
        assert resolve_anthropic_model("gpt-4o") == "claude-3-5-haiku-20241022"

    def test_openai_slash_prefix_replaced(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-4-0")
        assert resolve_anthropic_model("openai/gpt-oss-20b") == "claude-opus-4-0"
