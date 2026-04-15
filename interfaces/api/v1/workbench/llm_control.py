from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

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
