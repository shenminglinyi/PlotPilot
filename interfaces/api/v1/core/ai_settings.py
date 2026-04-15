"""AI provider settings routes.

Local development helper for editing `.env` without opening files by hand.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.anthropic_provider import AnthropicProvider
from infrastructure.ai.providers.openai_provider import OpenAIProvider


router = APIRouter(prefix="/settings/ai", tags=["ai-settings"])

ProviderName = Literal["ark", "anthropic", "openai"]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_PATH = PROJECT_ROOT / ".env"

DEFAULTS: Dict[ProviderName, Dict[str, str]] = {
    "ark": {
        "model": "doubao-seed-2-0-mini-260215",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    },
    "anthropic": {
        "model": "claude-sonnet-4-6",
        "base_url": "",
    },
    "openai": {
        "model": "gpt-4o",
        "base_url": "",
    },
}


class AISettingsResponse(BaseModel):
    provider: ProviderName
    model: str
    base_url: str
    has_api_key: bool
    api_key_hint: str = ""


class AISettingsUpdate(BaseModel):
    provider: ProviderName
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None


class AIConnectionTestResponse(BaseModel):
    ok: bool
    provider: ProviderName
    model: str
    latency_ms: int
    message: str
    sample: str = ""


def _parse_env_file() -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if "#" in value:
            value = value.split("#", 1)[0].strip()
        values[key] = value.strip("\"'")
    return values


def _env_value(key: str, file_values: Optional[Dict[str, str]] = None) -> str:
    if key in os.environ:
        return os.environ[key].strip()
    values = file_values if file_values is not None else _parse_env_file()
    return values.get(key, "").strip()


def _mask_secret(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if len(value) <= 10:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _normalize_openai_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    suffix = "/chat/completions"
    if normalized.endswith(suffix):
        normalized = normalized[: -len(suffix)]
    return normalized


def _provider_keys(provider: ProviderName) -> Dict[str, str]:
    if provider == "anthropic":
        return {
            "api_key": "ANTHROPIC_API_KEY",
            "model": "ANTHROPIC_MODEL",
            "base_url": "ANTHROPIC_BASE_URL",
        }
    if provider == "openai":
        return {
            "api_key": "OPENAI_API_KEY",
            "model": "OPENAI_MODEL",
            "base_url": "OPENAI_BASE_URL",
        }
    return {
        "api_key": "ARK_API_KEY",
        "model": "ARK_MODEL",
        "base_url": "ARK_BASE_URL",
    }


def _active_provider(file_values: Optional[Dict[str, str]] = None) -> ProviderName:
    raw = (_env_value("LLM_PROVIDER", file_values) or "").lower()
    if raw in {"ark", "anthropic", "openai"}:
        return raw  # type: ignore[return-value]
    if _env_value("ANTHROPIC_API_KEY", file_values) or _env_value("ANTHROPIC_AUTH_TOKEN", file_values):
        return "anthropic"
    if _env_value("ARK_API_KEY", file_values):
        return "ark"
    if _env_value("OPENAI_API_KEY", file_values):
        return "openai"
    return "ark"


def _settings_for(provider: ProviderName, file_values: Optional[Dict[str, str]] = None) -> AISettingsResponse:
    keys = _provider_keys(provider)
    api_key = _env_value(keys["api_key"], file_values)
    if provider == "anthropic" and not api_key:
        api_key = _env_value("ANTHROPIC_AUTH_TOKEN", file_values)
    model = _env_value(keys["model"], file_values) or DEFAULTS[provider]["model"]
    base_url = _env_value(keys["base_url"], file_values) or DEFAULTS[provider]["base_url"]
    if provider == "ark":
        base_url = _normalize_openai_base_url(base_url)
    return AISettingsResponse(
        provider=provider,
        model=model,
        base_url=base_url,
        has_api_key=bool(api_key),
        api_key_hint=_mask_secret(api_key),
    )


def _format_env_line(key: str, value: str) -> str:
    return f"{key}={value.strip()}\n"


def _write_env(updates: Dict[str, str]) -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = ENV_PATH.read_text(encoding="utf-8").splitlines(keepends=True) if ENV_PATH.exists() else []
    seen = set()
    out = []
    for line in existing:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            out.append(_format_env_line(key, updates[key]))
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(_format_env_line(key, value))
    ENV_PATH.write_text("".join(out), encoding="utf-8")
    for key, value in updates.items():
        os.environ[key] = value


def _merged_settings(update: Optional[AISettingsUpdate] = None) -> AISettingsResponse:
    provider = update.provider if update else _active_provider()
    current = _settings_for(provider)
    if not update:
        return current
    return AISettingsResponse(
        provider=provider,
        model=(update.model or current.model).strip() or DEFAULTS[provider]["model"],
        base_url=_normalize_openai_base_url(update.base_url or current.base_url)
        if provider == "ark"
        else (update.base_url if update.base_url is not None else current.base_url).strip(),
        has_api_key=bool((update.api_key or "").strip()) or current.has_api_key,
        api_key_hint=_mask_secret((update.api_key or "").strip()) or current.api_key_hint,
    )


@router.get("", response_model=AISettingsResponse)
async def get_ai_settings() -> AISettingsResponse:
    return _settings_for(_active_provider())


@router.put("", response_model=AISettingsResponse)
async def update_ai_settings(payload: AISettingsUpdate) -> AISettingsResponse:
    provider = payload.provider
    keys = _provider_keys(provider)
    updates: Dict[str, str] = {
        "LLM_PROVIDER": provider,
        keys["model"]: (payload.model or DEFAULTS[provider]["model"]).strip(),
        keys["base_url"]: _normalize_openai_base_url(payload.base_url or DEFAULTS[provider]["base_url"])
        if provider == "ark"
        else (payload.base_url or "").strip(),
    }
    if payload.api_key is not None and payload.api_key.strip():
        updates[keys["api_key"]] = payload.api_key.strip()
    _write_env(updates)
    return _settings_for(provider)


@router.post("/test", response_model=AIConnectionTestResponse)
async def test_ai_connection(payload: Optional[AISettingsUpdate] = None) -> AIConnectionTestResponse:
    settings = _merged_settings(payload)
    provider = settings.provider
    keys = _provider_keys(provider)
    api_key = (payload.api_key or "").strip() if payload and payload.api_key else _env_value(keys["api_key"])
    if provider == "anthropic" and not api_key:
        api_key = _env_value("ANTHROPIC_AUTH_TOKEN")

    started = time.monotonic()
    if not api_key:
        return AIConnectionTestResponse(
            ok=False,
            provider=provider,
            model=settings.model,
            latency_ms=0,
            message="未填写 API Key",
        )

    try:
        prompt = Prompt(system="You are a connectivity checker.", user="Reply with OK.")
        config = GenerationConfig(model=settings.model, max_tokens=16, temperature=0)
        if provider == "anthropic":
            llm = AnthropicProvider(Settings(api_key=api_key, base_url=settings.base_url or None))
        else:
            llm = OpenAIProvider(
                Settings(api_key=api_key, base_url=settings.base_url or None),
                default_model=settings.model,
            )
        result = await llm.generate(prompt, config)
        latency_ms = int((time.monotonic() - started) * 1000)
        return AIConnectionTestResponse(
            ok=True,
            provider=provider,
            model=settings.model,
            latency_ms=latency_ms,
            message="连接成功",
            sample=result.content.strip()[:80],
        )
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        return AIConnectionTestResponse(
            ok=False,
            provider=provider,
            model=settings.model,
            latency_ms=latency_ms,
            message=str(exc)[:500],
        )
