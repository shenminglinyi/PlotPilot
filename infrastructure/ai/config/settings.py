"""AI 配置设置"""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Settings:
    """AI 配置设置

    管理 LLM 提供商的配置参数。
    """

    default_model: str = ""
    default_temperature: float = 0.7
    default_max_tokens: int = 4096
    api_key: Optional[str] = None
    #: 兼容自建/转发网关，与官方 provider base_url 一致；未设则走官方默认
    base_url: Optional[str] = None
    timeout_seconds: float = 300.0
    extra_headers: dict[str, str] = field(default_factory=dict)
    extra_query: dict[str, Any] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)
    provider_name: Optional[str] = None
    protocol: Optional[str] = None
    use_legacy_chat_completions: bool = False

    def __post_init__(self):
        """验证配置参数"""
        if not (0.0 <= self.default_temperature <= 2.0):
            raise ValueError("Temperature must be between 0.0 and 2.0")

        if self.default_max_tokens <= 0:
            raise ValueError("Max tokens must be positive")

        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
