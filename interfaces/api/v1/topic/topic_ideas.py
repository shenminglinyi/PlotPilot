"""选题立项池 API 路由。"""
import inspect
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from application.core.dtos.novel_dto import NovelDTO
from application.topic.dtos import (
    CompareTopicIdeasRequestDTO,
    TopicGenerateRequestDTO,
    TopicIdeaCompareResultDTO,
    TopicIdeaDTO,
    TopicMarketSignalCollectRequestDTO,
    TopicMarketSignalAutomationSettingsDTO,
    TopicMarketSignalDTO,
    TopicMarketSignalImportRequestDTO,
    TopicMarketSignalSummaryDTO,
    TopicMarketSignalSourceConnectionDTO,
    TopicMarketSignalSourceCredentialStatusDTO,
    TopicMarketSignalSourceHealthDTO,
    TopicMarketSignalSourceDTO,
)
from application.topic.services.topic_idea_service import (
    TopicIdeaGenerationError,
    TopicIdeaService,
)
from interfaces.api.dependencies import get_topic_idea_service


router = APIRouter(prefix="/topics", tags=["topics"])


class UpdateTopicIdeaStatusRequest(BaseModel):
    """更新选题状态请求。"""

    status: Optional[str] = Field(None, description="选题状态")
    title: Optional[str] = None
    genre: Optional[str] = None
    world_preset: Optional[str] = None
    length_tier: Optional[str] = None
    logline: Optional[str] = None
    premise: Optional[str] = None
    protagonist_hook: Optional[str] = None
    core_conflict: Optional[str] = None
    opening_hook: Optional[str] = None
    selling_points: Optional[List[str]] = None
    long_term_potential: Optional[str] = None
    risk_notes: Optional[List[str]] = None
    market_tags: Optional[List[str]] = None
    score: Optional[int] = None
    development_notes: Optional[dict[str, Any]] = None
    evaluation: Optional[dict[str, Any]] = None

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class UpdateMarketSignalAutomationSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    interval_minutes: Optional[int] = Field(None, ge=15, le=1440)
    limit_per_source: Optional[int] = Field(None, ge=1, le=30)
    lookback_days: Optional[int] = Field(None, ge=1, le=90)
    source_weights: Optional[dict[str, float]] = None
    selected_source_keys: Optional[List[str]] = None

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class UpdateMarketSignalSourceCredentialsRequest(BaseModel):
    api_key: Optional[str] = None
    cookie: Optional[str] = None
    endpoint_url: Optional[str] = None
    headers: Optional[dict[str, str]] = None

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _value_error_response(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "not found" in detail.lower():
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=400, detail=detail)


@router.post("/generate", response_model=List[TopicIdeaDTO])
async def generate_topic_ideas(
    request: TopicGenerateRequestDTO,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """生成选题候选。"""
    try:
        return await _maybe_await(service.generate(request))
    except TopicIdeaGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/compare", response_model=TopicIdeaCompareResultDTO)
async def compare_topic_ideas(
    request: CompareTopicIdeasRequestDTO,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """对比多个选题候选。"""
    topic_ids = [topic_id for topic_id in request.topic_ids if str(topic_id).strip()]
    if len(topic_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two topic_ids are required")
    if len(topic_ids) > 5:
        raise HTTPException(status_code=400, detail="At most five topic_ids are supported")
    try:
        return await _maybe_await(service.compare(topic_ids))
    except ValueError as exc:
        raise _value_error_response(exc)


@router.post("/signals/import", response_model=List[TopicMarketSignalDTO])
async def import_market_signals(
    request: TopicMarketSignalImportRequestDTO,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """导入手动市场观察信号。"""
    try:
        return await _maybe_await(service.import_market_signals(request))
    except ValueError as exc:
        raise _value_error_response(exc)


@router.post("/signals/collect", response_model=List[TopicMarketSignalDTO])
async def collect_market_signals(
    request: TopicMarketSignalCollectRequestDTO,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """从公开来源手动触发采集市场信号。"""
    try:
        return await _maybe_await(service.collect_market_signals(request))
    except ValueError as exc:
        raise _value_error_response(exc)


@router.post("/signals/sources/test", response_model=List[TopicMarketSignalSourceConnectionDTO])
async def test_market_signal_sources(
    request: TopicMarketSignalCollectRequestDTO,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """测试市场信号来源连接，不保存采集结果。"""
    return await _maybe_await(service.test_market_signal_sources(request))


@router.get("/signals/sources", response_model=List[TopicMarketSignalSourceDTO])
async def list_market_signal_sources(
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """列出可手动触发采集的公开来源。"""
    return await _maybe_await(service.list_market_signal_sources())


@router.get("/signals/source-health", response_model=List[TopicMarketSignalSourceHealthDTO])
async def list_market_signal_source_health(
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """列出市场信号来源采集健康状态。"""
    return await _maybe_await(service.list_market_signal_source_health())


@router.get("/signals", response_model=List[TopicMarketSignalDTO])
async def list_market_signals(
    limit: int = 20,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """列出市场观察信号。"""
    return await _maybe_await(service.list_market_signals(limit=limit))


@router.get("/signals/summary", response_model=TopicMarketSignalSummaryDTO)
async def summarize_market_signals(
    limit: int = 100,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """汇总市场观察信号。"""
    return await _maybe_await(service.summarize_market_signals(limit=limit))


@router.get("/signals/automation", response_model=TopicMarketSignalAutomationSettingsDTO)
async def get_market_signal_automation_settings(
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """获取市场信号自动采集设置。"""
    return await _maybe_await(service.get_market_signal_settings())


@router.patch("/signals/automation", response_model=TopicMarketSignalAutomationSettingsDTO)
async def update_market_signal_automation_settings(
    request: UpdateMarketSignalAutomationSettingsRequest,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """更新市场信号自动采集设置。"""
    changes = request.changes()
    if not changes:
        raise HTTPException(status_code=400, detail="No automation setting fields provided")
    try:
        return await _maybe_await(service.update_market_signal_settings(changes))
    except ValueError as exc:
        raise _value_error_response(exc)


@router.get(
    "/signals/source-credentials",
    response_model=List[TopicMarketSignalSourceCredentialStatusDTO],
)
async def list_market_signal_source_credentials(
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """列出市场信号来源凭据配置状态，不返回明文凭据。"""
    return await _maybe_await(service.list_market_signal_source_credentials())


@router.patch(
    "/signals/sources/{source_key}/credentials",
    response_model=TopicMarketSignalSourceCredentialStatusDTO,
)
async def update_market_signal_source_credentials(
    source_key: str,
    request: UpdateMarketSignalSourceCredentialsRequest,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """保存单个市场信号来源凭据，返回脱敏状态。"""
    changes = request.changes()
    if not changes:
        raise HTTPException(status_code=400, detail="No credential fields provided")
    try:
        return await _maybe_await(
            service.update_market_signal_source_credentials(source_key, changes)
        )
    except ValueError as exc:
        raise _value_error_response(exc)


@router.get("/", response_model=List[TopicIdeaDTO])
async def list_topic_ideas(
    status: Optional[str] = None,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """列出选题候选。"""
    return await _maybe_await(service.list(status=status))


@router.get("/{topic_id}", response_model=TopicIdeaDTO)
async def get_topic_idea(
    topic_id: str,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """获取选题详情。"""
    try:
        topic = await _maybe_await(service.get(topic_id))
    except ValueError as exc:
        raise _value_error_response(exc)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"Topic idea not found: {topic_id}")
    return topic


@router.post("/{topic_id}/deepen", response_model=TopicIdeaDTO)
async def deepen_topic_idea(
    topic_id: str,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """深化单条选题候选。"""
    try:
        return await _maybe_await(service.deepen(topic_id))
    except TopicIdeaGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise _value_error_response(exc)


@router.post("/{topic_id}/evaluate", response_model=TopicIdeaDTO)
async def evaluate_topic_idea(
    topic_id: str,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """评估单条选题候选。"""
    try:
        return await _maybe_await(service.evaluate(topic_id))
    except TopicIdeaGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise _value_error_response(exc)


@router.patch("/{topic_id}", response_model=TopicIdeaDTO)
async def update_topic_idea_status(
    topic_id: str,
    request: UpdateTopicIdeaStatusRequest,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """更新选题状态。"""
    changes = request.changes()
    if not changes:
        raise HTTPException(status_code=400, detail="No topic idea fields provided")
    try:
        update = getattr(service, "update", None)
        if update is not None:
            topic = await _maybe_await(update(topic_id, changes))
        else:
            topic = await _maybe_await(service.update_status(topic_id, changes["status"]))
    except ValueError as exc:
        raise _value_error_response(exc)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"Topic idea not found: {topic_id}")
    return topic


@router.post("/{topic_id}/adopt", response_model=NovelDTO)
async def adopt_topic_idea(
    topic_id: str,
    service: TopicIdeaService = Depends(get_topic_idea_service),
):
    """采纳选题并创建小说。"""
    try:
        return await _maybe_await(service.adopt(topic_id))
    except ValueError as exc:
        raise _value_error_response(exc)
