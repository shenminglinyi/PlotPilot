from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.gemini_provider import GeminiProvider


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
