from infrastructure.ai.url_utils import should_trust_env_proxy_for_openai_base


def test_should_trust_env_proxy_for_official_openai():
    assert should_trust_env_proxy_for_openai_base("https://api.openai.com/v1") is True


def test_should_not_trust_env_proxy_for_compatible_gateway():
    assert should_trust_env_proxy_for_openai_base("https://api.deepseek.com/v1") is False
    assert should_trust_env_proxy_for_openai_base("https://coding-intl.dashscope.aliyuncs.com/v1") is False
