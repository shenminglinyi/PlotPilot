"""LLM 配置管理 API（兼容旧路由，底层委托给 LLMControlService）。"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from application.ai.llm_control_service import LLMControlService, LLMProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/llm-configs", tags=["settings"])

_service = LLMControlService()


# ── schemas (兼容旧接口) ──────────────────────────────

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


def _profile_to_dict(p: LLMProfile) -> dict:
    """将 LLMProfile 转换为旧接口的 dict 格式。"""
    return {
        "id": p.id,
        "name": p.name,
        "provider": p.protocol,
        "api_key": p.api_key,
        "base_url": p.base_url,
        "model": p.model,
        "system_model": p.model,
        "writing_model": p.model,
    }


# ── endpoints ──────────────────────────────────────────

@router.get("/")
def list_configs():
    config = _service.get_config()
    return [_profile_to_dict(p) for p in config.profiles]


@router.post("/")
def create_config(body: ConfigCreate):
    config = _service.get_config()
    new_profile = LLMProfile(
        id=f"profile-{len(config.profiles) + 1}",
        name=body.name,
        preset_key="custom-openai-compatible",
        protocol=body.provider,  # type: ignore[arg-type]
        base_url=body.base_url,
        api_key=body.api_key,
        model=body.model or body.system_model or body.writing_model,
    )
    config.profiles.append(new_profile)
    saved = _service.save_config(config)
    return _profile_to_dict(saved.profiles[-1])


@router.put("/{config_id}")
def update_config(config_id: str, body: ConfigUpdate):
    config = _service.get_config()
    for i, p in enumerate(config.profiles):
        if p.id == config_id:
            update_data = body.model_dump(exclude_none=True)
            # 映射旧字段名到新字段名
            if "provider" in update_data:
                update_data["protocol"] = update_data.pop("provider")
            updated = p.model_copy(update={k: v for k, v in update_data.items() if hasattr(p, k)})
            config.profiles[i] = updated
            _service.save_config(config)
            return _profile_to_dict(updated)
    raise HTTPException(404, "Config not found")


@router.delete("/{config_id}")
def delete_config(config_id: str):
    config = _service.get_config()
    original_len = len(config.profiles)
    config.profiles = [p for p in config.profiles if p.id != config_id]
    if len(config.profiles) == original_len:
        raise HTTPException(404, "Config not found")
    _service.save_config(config)
    return {"ok": True}


@router.post("/{config_id}/activate")
def activate_config(config_id: str):
    config = _service.get_config()
    ids = {p.id for p in config.profiles}
    if config_id not in ids:
        raise HTTPException(404, "Config not found")
    config.active_profile_id = config_id
    _service.save_config(config)
    return {"ok": True}


@router.post("/fetch-models")
async def fetch_models(body: FetchModelsRequest):
    """复用 llm-control/models 端点的逻辑。"""
    from interfaces.api.v1.workbench.llm_control import list_models
    from interfaces.api.v1.workbench.llm_control import ModelListRequest

    payload = ModelListRequest(
        protocol=body.provider,
        base_url=body.base_url,
        api_key=body.api_key,
    )
    result = await list_models(payload)
    return [m.id for m in result.items]


# ── embedding endpoints ────────────────────────────────

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
    # 返回默认配置（embedding 配置暂未迁移到新体系）
    return {
        "mode": "local",
        "api_key": "",
        "base_url": "",
        "model": "text-embedding-3-small",
        "use_gpu": True,
        "model_path": "BAAI/bge-small-zh-v1.5",
    }


@embedding_router.put("/")
def update_embedding_config(body: EmbeddingConfigUpdate):
    # 暂时返回写入的值（后续可持久化）
    return body.model_dump()


@embedding_router.post("/fetch-models")
async def fetch_embedding_models(body: FetchModelsRequest):
    if not body.base_url:
        return []
    from interfaces.api.v1.workbench.llm_control import list_models
    from interfaces.api.v1.workbench.llm_control import ModelListRequest

    payload = ModelListRequest(
        protocol=body.provider,
        base_url=body.base_url,
        api_key=body.api_key,
    )
    result = await list_models(payload)
    return [m.id for m in result.items]
