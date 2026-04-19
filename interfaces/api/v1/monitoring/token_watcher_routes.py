"""TokenWatcher API 路由"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional

from infrastructure.monitoring import get_token_watcher

router = APIRouter(prefix="/api/v1/token-watcher", tags=["token-watcher"])


class TokenLogItem(BaseModel):
    id: int
    timestamp: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    success: int
    error_message: Optional[str] = None


class TokenLogsResponse(BaseModel):
    logs: List[TokenLogItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class TokenSummaryResponse(BaseModel):
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    avg_latency_ms: float


class TokenStatsItem(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    avg_latency_ms: float


class ConfigResponse(BaseModel):
    enabled: bool
    paginate: int
    usage_only: bool


class UpdateConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    paginate: Optional[int] = None
    usage_only: Optional[bool] = None


class StatusResponse(BaseModel):
    config: ConfigResponse
    summary: TokenSummaryResponse


@router.get("/status", response_model=StatusResponse)
def get_status():
    """获取 TokenWatcher 状态和配置"""
    watcher = get_token_watcher()
    config = watcher.config
    summary = watcher.get_summary()

    return StatusResponse(
        config=ConfigResponse(
            enabled=config.enabled,
            paginate=config.paginate,
            usage_only=config.usage_only,
        ),
        summary=TokenSummaryResponse(**summary),
    )


@router.get("/config", response_model=ConfigResponse)
def get_config():
    """获取 TokenWatcher 配置"""
    watcher = get_token_watcher()
    config = watcher.config

    return ConfigResponse(
        enabled=config.enabled,
        paginate=config.paginate,
        usage_only=config.usage_only,
    )


@router.put("/config", response_model=ConfigResponse)
def update_config(request: UpdateConfigRequest):
    """更新 TokenWatcher 配置"""
    watcher = get_token_watcher()
    watcher.update_config(
        enabled=request.enabled,
        paginate=request.paginate,
        usage_only=request.usage_only
    )

    config = watcher.config
    return ConfigResponse(
        enabled=config.enabled,
        paginate=config.paginate,
        usage_only=config.usage_only,
    )


@router.get("/logs", response_model=TokenLogsResponse)
def get_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="每页数量"),
    provider: Optional[str] = Query(None, description="筛选提供商"),
    model: Optional[str] = Query(None, description="筛选模型"),
    time_range: Optional[str] = Query(None, description="时间范围: today, week, month"),
):
    """获取 Token 使用日志（分页）"""
    watcher = get_token_watcher()
    result = watcher.get_logs(
        page=page,
        page_size=page_size,
        provider=provider,
        model=model,
        time_range=time_range,
    )

    logs = [TokenLogItem(**log) for log in result['logs']]

    return TokenLogsResponse(
        logs=logs,
        total=result['total'],
        page=result['page'],
        page_size=result['page_size'],
        total_pages=result['total_pages'],
    )


@router.get("/summary", response_model=TokenSummaryResponse)
def get_summary():
    """获取 Token 使用汇总"""
    watcher = get_token_watcher()
    summary = watcher.get_summary()
    return TokenSummaryResponse(**summary)


@router.get("/stats", response_model=List[TokenStatsItem])
def get_stats(
    group_by: str = Query('provider', description="分组维度: provider, model, provider_model"),
    provider: Optional[str] = Query(None, description="筛选提供商"),
    model: Optional[str] = Query(None, description="筛选模型"),
    time_range: Optional[str] = Query(None, description="时间范围: today, week, month"),
):
    """按维度查询统计数据"""
    watcher = get_token_watcher()
    stats = watcher.get_stats_by_dimension(
        group_by=group_by,
        provider=provider,
        model=model,
        time_range=time_range,
    )
    return [TokenStatsItem(**item) for item in stats]


class FiltersResponse(BaseModel):
    providers: List[str]
    models: List[str]


@router.get("/filters", response_model=FiltersResponse)
def get_filters():
    """获取可用的筛选选项"""
    watcher = get_token_watcher()
    return FiltersResponse(**watcher.get_filters())


@router.get("/logs/export")
def export_logs(
    provider: Optional[str] = Query(None, description="筛选提供商"),
    model: Optional[str] = Query(None, description="筛选模型"),
    time_range: Optional[str] = Query(None, description="时间范围: today, week, month"),
):
    """导出日志数据"""
    watcher = get_token_watcher()
    logs = watcher.export_logs(
        provider=provider,
        model=model,
        time_range=time_range,
    )

    export_data = []
    for log in logs:
        export_data.append({
            '时间': log['timestamp'],
            '提供商': log['provider'],
            '模型': log['model'],
            '输入Token': log['input_tokens'],
            '输出Token': log['output_tokens'],
            '总Token': log['total_tokens'],
            '延迟ms': log['latency_ms'],
            '状态': '成功' if log['success'] else '失败',
            '错误信息': log['error_message'] or '',
        })

    return export_data


@router.delete("/stats")
def reset_stats():
    """重置统计数据（同时清空日志）"""
    watcher = get_token_watcher()
    count = watcher.reset_stats()
    return {"success": True, "deleted_count": count}
