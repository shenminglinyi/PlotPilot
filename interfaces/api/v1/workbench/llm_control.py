from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from application.ai.llm_control_service import (
    LLMControlConfig,
    LLMControlPanelData,
    LLMProfile,
    LLMTestResult,
    LLMControlService,
)
from infrastructure.ai.provider_factory import LLMProviderFactory

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/llm-control', tags=['llm-control'])

_service = LLMControlService()
_factory = LLMProviderFactory(_service)


# ---------- 模型列表拉取 ----------

class ModelListRequest(BaseModel):
    """请求体：根据 API Key 和 Base URL 拉取可用模型列表。"""
    protocol: str = 'openai'
    base_url: str = ''
    api_key: str = ''
    timeout_ms: int = 30000


class ModelItem(BaseModel):
    id: str = ''
    name: str = ''
    owned_by: str = ''


class ModelListResponse(BaseModel):
    success: bool = True
    items: List[ModelItem] = Field(default_factory=list)
    count: int = 0


def _normalize_model_items(data: Dict[str, Any]) -> List[ModelItem]:
    """将不同网关的 /models 响应统一为 ModelItem 列表。"""
    items: List[ModelItem] = []
    raw_list = data.get('data', [])
    if not isinstance(raw_list, list):
        return items
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        items.append(ModelItem(
            id=str(entry.get('id', '')),
            name=str(entry.get('id', '')),  # 多数网关不返回 name，回退到 id
            owned_by=str(entry.get('owned_by', '')),
        ))
    return items


@router.post('/models', response_model=ModelListResponse)
async def list_models(payload: ModelListRequest) -> ModelListResponse:
    """根据当前配置的 endpoint 拉取模型列表（OpenAI / Anthropic 兼容）。"""
    candidate = payload.model_dump()
    if not candidate.get('api_key'):
        # 尝试从当前激活配置中获取 key 作为 fallback
        active = _service.get_active_profile()
        if active:
            candidate['api_key'] = active.api_key

    api_format = (candidate.get('protocol') or '').strip().lower()
    api_key = (candidate.get('api_key') or '').strip()
    if not api_key:
        raise HTTPException(status_code=400, detail='API key is required to fetch model list')

    base_url = (candidate.get('base_url') or '').strip()
    timeout = max(1.0, (candidate.get('timeout_ms') or 30000) / 1000)

    if api_format == 'anthropic':
        url = f"{(base_url or 'https://api.anthropic.com').rstrip('/')}/v1/models"
        headers = {
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
        }
    else:
        url = f"{(base_url or 'https://api.openai.com/v1').rstrip('/')}/models"
        headers = {
            'Authorization': f'Bearer {api_key}',
        }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
        normalized = _normalize_model_items(data)
        return ModelListResponse(
            success=True,
            items=normalized,
            count=len(normalized),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f'Failed to fetch model list: {exc}') from exc


# ---------- 核心 CRUD + 测试 ----------

@router.get('', response_model=LLMControlPanelData)
async def get_llm_control_panel() -> LLMControlPanelData:
    return _service.get_control_panel_data()


@router.put('', response_model=LLMControlPanelData)
async def save_llm_control_panel(config: LLMControlConfig) -> LLMControlPanelData:
    saved = _service.save_config(config)
    return LLMControlPanelData(
        config=saved,
        presets=_service.get_presets(),
        runtime=_service.get_runtime_summary(saved),
    )


@router.post('/test', response_model=LLMTestResult)
async def test_llm_profile(profile: LLMProfile) -> LLMTestResult:
    try:
        return await _service.test_profile_model(profile, _factory.create_from_profile)
    except Exception as exc:
        logger.error('测试 LLM 配置失败: %s', exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
