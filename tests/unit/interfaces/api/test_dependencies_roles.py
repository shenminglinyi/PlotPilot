from interfaces.api.dependencies import _build_provider_for_role
from infrastructure.ai.config.dynamic_settings import LLMConfigDTO


def test_build_provider_for_fact_review_role():
    cfg = LLMConfigDTO(
        fact_review_model_provider="openai",
        fact_review_model_api_key="sk-test",
        fact_review_model_base_url="http://localhost:1234/v1",
        fact_review_model="gpt-4o-mini",
    )
    provider = _build_provider_for_role(cfg, "fact_review")
    assert provider is not None

