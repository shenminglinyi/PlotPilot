"""Reuse configured providers, with pilot limits at the actual HTTP boundary."""
import asyncio
import hashlib
import json

from application.ai.llm_control_service import LLMControlService
from application.plugin_pilot.contracts import (
    MAX_INPUT_TOKENS, MAX_OUTPUT_BYTES, MAX_OUTPUT_TOKENS, TIMEOUT_SECONDS, PilotError,
)
from domain.ai.services.llm_service import GenerationConfig
from infrastructure.ai.provider_factory import LLMProviderFactory


class PilotGenerationConfig(GenerationConfig):
    """Keep the legacy engine's minimum untouched; pilot permits small caps."""
    def __post_init__(self):
        if not 0 <= self.temperature <= 2 or not 0 < self.max_tokens <= MAX_OUTPUT_TOKENS:
            raise ValueError("Invalid pilot generation bounds")


class RequestBudget:
    def __init__(self, protocol):
        self.protocol = protocol
        self.requests = 0

    async def before_request(self, request):
        # Includes SDK retries, provider retries, schema fallback and stream fallback.
        if self.requests >= 1:
            raise PilotError("Pilot HTTP call budget exhausted", 422)
        body = json.loads(request.content)
        if self.protocol == "gemini":
            cap = body.get("generationConfig", {}).get("maxOutputTokens")
        else:
            cap = body.get("max_tokens", body.get("max_output_tokens"))
        if type(cap) is not int or not 0 < cap <= MAX_OUTPUT_TOKENS or body.get("stream"):
            raise PilotError("Provider request exceeded pilot output limit", 422)
        if len(request.content) > MAX_INPUT_TOKENS * 6:
            raise PilotError("Provider request too large", 422)
        self.requests += 1


class ConfiguredPilotModel:
    def __init__(self, control=None, factory=None):
        self.control = control or LLMControlService()
        self.factory = factory or LLMProviderFactory(self.control)

    def _profile(self):
        profile = self.control.resolve_active_profile()
        if profile is None or not profile.api_key.strip() or not profile.model.strip():
            raise PilotError("Configure an active model profile before running the pilot", 422)
        # Profiles may override prompts, tokens or the request body in legacy
        # providers. Refuse those overrides rather than silently changing consent.
        if profile.extra_body or profile.extra_query:
            raise PilotError("Pilot requires a profile without extra_body/extra_query overrides", 422)
        return profile

    @staticmethod
    def _identity(profile):
        # Secret/endpoint changes invalidate consent, but keys never leave host.
        signature = hashlib.sha256(profile.model_dump_json().encode()).hexdigest()
        return {"profile_id": profile.id, "name": profile.name, "model": profile.model,
                "protocol": profile.protocol, "signature": signature}

    async def identity(self):
        return self._identity(await asyncio.to_thread(self._profile))

    async def generate(self, prompt, expected_signature):
        profile = await asyncio.to_thread(self._profile)
        identity = self._identity(profile)
        if identity["signature"] != expected_signature:
            raise PilotError("Model configuration changed; review scope and consent again")
        provider = self.factory.create_from_profile(profile)
        budget = RequestBudget(profile.protocol)
        clients = []
        for name in ("_http_client", "_http_client_async", "_stream_http_client"):
            client = getattr(provider, name, None)
            if client is not None and client not in clients:
                clients.append(client)
                client.event_hooks.setdefault("request", []).insert(0, budget.before_request)
        if not clients:
            raise PilotError("Provider has no verified request-budget boundary", 503)
        sdk = getattr(provider, "async_client", None)
        if sdk is not None and hasattr(sdk, "with_options"):
            provider.async_client = sdk.with_options(max_retries=0)
        config = PilotGenerationConfig(model=profile.model, temperature=profile.temperature,
                                       max_tokens=MAX_OUTPUT_TOKENS,
                                       response_format={"type": "json_object"})
        try:
            result = await asyncio.wait_for(provider.generate(prompt, config), TIMEOUT_SECONDS)
            if len(result.content.encode("utf-8")) > MAX_OUTPUT_BYTES:
                raise PilotError("Model output exceeds byte limit", 422)
            if (result.token_usage.input_tokens > MAX_INPUT_TOKENS or
                    result.token_usage.output_tokens > MAX_OUTPUT_TOKENS):
                raise PilotError("Provider reported usage above pilot token limit", 422)
            return result, identity
        finally:
            await provider.aclose()
