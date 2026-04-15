"""LLM 配置管理 API"""
from __future__ import annotations

import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from application.paths import DATA_DIR
from application.settings.llm_config_manager import LLMConfigManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/llm-configs", tags=["settings"])

_manager = LLMConfigManager(DATA_DIR / "llm_configs.json")


# ── schemas ──────────────────────────────────────────────────

class ConfigCreate(BaseModel):
    name: str
    provider: str  # "openai" | "anthropic"
    api_key: str
    base_url: str = ""
    model: str = ""
    system_model: str = ""
    writing_model: str = ""


class ConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    system_model: Optional[str] = None
    writing_model: Optional[str] = None


class FetchModelsRequest(BaseModel):
    provider: str
    api_key: str
    base_url: str


# ── endpoints ────────────────────────────────────────────────

@router.get("/")
def list_configs():
    return _manager.list_configs()


@router.post("/")
def create_config(body: ConfigCreate):
    return _manager.create_config(body.model_dump())


@router.put("/{config_id}")
def update_config(config_id: str, body: ConfigUpdate):
    try:
        return _manager.update_config(config_id, body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404, "Config not found")


@router.delete("/{config_id}")
def delete_config(config_id: str):
    try:
        _manager.delete_config(config_id)
    except KeyError:
        raise HTTPException(404, "Config not found")
    return {"ok": True}


@router.post("/{config_id}/activate")
def activate_config(config_id: str):
    try:
        _manager.set_active(config_id)
    except KeyError:
        raise HTTPException(404, "Config not found")
    return {"ok": True}


@router.post("/fetch-models")
async def fetch_models(body: FetchModelsRequest):
    if body.provider == "anthropic":
        return await _fetch_anthropic_models(body.api_key, body.base_url)

    if not body.base_url:
        return []

    return await _fetch_openai_models(body.api_key, body.base_url)


# ── embedding endpoints ─────────────────────────────────────

embedding_router = APIRouter(prefix="/settings/embedding", tags=["settings"])


class EmbeddingConfigUpdate(BaseModel):
    mode: str = "local"
    api_key: str = ""
    base_url: str = ""
    model: str = "text-embedding-3-small"
    use_gpu: bool = True
    model_path: str = "BAAI/bge-small-zh-v1.5"


@embedding_router.get("/")
def get_embedding_config():
    return _manager.get_embedding_config()


@embedding_router.put("/")
def update_embedding_config(body: EmbeddingConfigUpdate):
    return _manager.update_embedding_config(body.model_dump())


@embedding_router.post("/fetch-models")
async def fetch_embedding_models(body: FetchModelsRequest):
    if not body.base_url:
        return []
    return await _fetch_openai_models(body.api_key, body.base_url)


# ── helpers ─────────────────────────────────────────────────

async def _fetch_openai_models(api_key: str, base_url: str) -> List[str]:
    url = f"{base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            return sorted(m["id"] for m in models if "id" in m)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"API returned {exc.response.status_code}")
    except Exception as exc:
        logger.warning("fetch-models failed: %s", exc)
        raise HTTPException(502, f"Failed to fetch models: {exc}")


async def _fetch_anthropic_models(api_key: str, base_url: str) -> List[str]:
    base = (base_url or "https://api.anthropic.com").rstrip("/")
    if base.endswith("/v1"):
        url = f"{base}/models"
    else:
        url = f"{base}/v1/models"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers, params={"limit": 1000})
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            return sorted(m["id"] for m in models if "id" in m)
    except Exception as exc:
        if not base_url:
            raise HTTPException(502, f"Failed to fetch Anthropic models: {exc}")
        logger.info("Anthropic-style fetch failed, trying OpenAI-style: %s", exc)
        try:
            fallback_base = base_url.rstrip("/")
            if not fallback_base.endswith("/v1"):
                fallback_base += "/v1"
            return await _fetch_openai_models(api_key, fallback_base)
        except Exception:
            raise HTTPException(502, f"Failed to fetch models (tried both Anthropic and OpenAI format): {exc}")
