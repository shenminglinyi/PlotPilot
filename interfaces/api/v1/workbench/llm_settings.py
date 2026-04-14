"""Runtime LLM settings endpoints used by the settings modal."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.runtime_settings import (
    DEFAULT_LLM_SETTINGS,
    activate_llm_preset,
    delete_llm_preset,
    get_llm_settings_response,
    load_llm_settings,
    load_llm_store,
    save_llm_preset,
    save_llm_settings,
)
from interfaces.api.dependencies import build_llm_service_from_runtime_settings


router = APIRouter(prefix="/api/v1/settings/llm", tags=["llm-settings"])


class LLMSettingsPayload(BaseModel):
    vendor: str = Field(default=DEFAULT_LLM_SETTINGS["vendor"])
    api_format: str = Field(default=DEFAULT_LLM_SETTINGS["api_format"])
    base_url: str = Field(default="")
    api_key: str = Field(default="")
    model: str = Field(default="")
    fast_model: str = Field(default="")
    review_model: str = Field(default="")
    scene_director_model: str = Field(default="")
    state_extractor_model: str = Field(default="")
    temperature: float = Field(default=DEFAULT_LLM_SETTINGS["temperature"], ge=0.0, le=2.0)
    max_tokens: int = Field(default=DEFAULT_LLM_SETTINGS["max_tokens"], ge=1, le=65536)
    timeout_ms: int = Field(default=DEFAULT_LLM_SETTINGS["timeout_ms"], ge=1000, le=600000)


class TestConnectionPayload(LLMSettingsPayload):
    prompt: Optional[str] = Field(default=None)


class ModelListRequest(LLMSettingsPayload):
    pass


class SavePresetPayload(BaseModel):
    preset_id: Optional[str] = Field(default=None)
    name: str = Field(..., min_length=1, max_length=100)
    set_active: bool = Field(default=False)
    settings: LLMSettingsPayload


@router.get("")
async def get_llm_settings():
    return get_llm_settings_response()


@router.put("")
async def update_llm_settings(payload: LLMSettingsPayload):
    current = load_llm_settings()
    merged = payload.model_dump()
    if not merged.get("api_key"):
        merged["api_key"] = current.get("api_key", "")
    store = load_llm_store()
    save_llm_settings(merged, active_preset_id=store.get("active_preset_id"))
    return get_llm_settings_response()


@router.post("/test")
async def test_llm_settings(payload: TestConnectionPayload):
    candidate = payload.model_dump()
    if not candidate.get("api_key"):
        candidate["api_key"] = load_llm_settings().get("api_key", "")

    try:
        llm_service = build_llm_service_from_runtime_settings(candidate)
        prompt = Prompt(
            system="You are a connection test endpoint. Reply with a short success message.",
            user=payload.prompt or "Return OK and the active model in one short sentence.",
        )
        result = await llm_service.generate(
            prompt,
            GenerationConfig(
                model=candidate.get("model") or None,
                max_tokens=min(candidate.get("max_tokens") or 128, 256),
                temperature=min(candidate.get("temperature") or 0.2, 0.7),
            ),
        )
        return {
            "success": True,
            "vendor": candidate.get("vendor"),
            "api_format": candidate.get("api_format"),
            "model": candidate.get("model"),
            "message": result.content.strip(),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/presets")
async def save_preset(payload: SavePresetPayload):
    settings = payload.settings.model_dump()
    if not settings.get("api_key"):
        settings["api_key"] = load_llm_settings().get("api_key", "")
    save_llm_preset(
        name=payload.name,
        settings=settings,
        preset_id=payload.preset_id,
        set_active=payload.set_active,
    )
    return get_llm_settings_response()


@router.post("/presets/{preset_id}/activate")
async def activate_preset(preset_id: str):
    try:
        activate_llm_preset(preset_id)
        return get_llm_settings_response()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Preset not found") from exc


@router.delete("/presets/{preset_id}")
async def remove_preset(preset_id: str):
    delete_llm_preset(preset_id)
    return get_llm_settings_response()


def _normalize_model_items(data: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()

    if isinstance(data, dict):
        raw_items = data.get("data") or data.get("models") or data.get("items") or []
    elif isinstance(data, list):
        raw_items = data
    else:
        raw_items = []

    for item in raw_items:
        model_id = None
        owned_by = ""
        if isinstance(item, dict):
            model_id = item.get("id") or item.get("name") or item.get("model")
            owned_by = str(item.get("owned_by") or item.get("provider") or "")
        elif isinstance(item, str):
            model_id = item

        if not model_id:
            continue

        model_id = str(model_id).strip()
        if not model_id or model_id in seen:
            continue

        seen.add(model_id)
        items.append({
            "label": f"{model_id} ({owned_by})" if owned_by else model_id,
            "value": model_id,
        })

    items.sort(key=lambda item: item["value"])
    return items


@router.post("/models")
async def list_models(payload: ModelListRequest):
    candidate = payload.model_dump()
    if not candidate.get("api_key"):
        candidate["api_key"] = load_llm_settings().get("api_key", "")

    api_format = (candidate.get("api_format") or "").strip().lower()
    api_key = (candidate.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required to fetch model list")

    base_url = (candidate.get("base_url") or "").strip()
    timeout = max(1.0, (candidate.get("timeout_ms") or 300000) / 1000)

    if api_format == "anthropic_messages":
        url = f"{(base_url or 'https://api.anthropic.com').rstrip('/')}/v1/models"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    else:
        url = f"{(base_url or 'https://api.openai.com/v1').rstrip('/')}/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
        }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
        return {
            "success": True,
            "items": _normalize_model_items(data),
            "count": len(_normalize_model_items(data)),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch model list: {exc}") from exc
