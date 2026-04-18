"""TokenWatcher API 路由"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional, Any, Dict

from infrastructure.monitoring import get_token_watcher, TokenWatcherConfig

router = APIRouter(prefix="/api/v1/token-watcher", tags=["token-watcher"])


class TokenLogItem(BaseModel):
    id: int
    timestamp: str
    model: str
    provider: str
    operation_type: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    success: int
    error_message: Optional[str] = None
    request_preview: Optional[str] = None
    response_preview: Optional[str] = None


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
    success_count: int
    error_count: int
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
):
    """获取 Token 使用日志（分页）"""
    watcher = get_token_watcher()
    result = watcher.get_logs(page=page, page_size=page_size)
    
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


@router.delete("/logs/{log_id}")
def delete_log(log_id: int):
    """删除单条日志"""
    watcher = get_token_watcher()
    success = watcher.delete_log(log_id)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="日志记录不存在")
    return {"success": True, "deleted_id": log_id}


@router.delete("/logs")
def clear_logs():
    """清空所有日志"""
    watcher = get_token_watcher()
    count = watcher.clear_logs()
    return {"success": True, "deleted_count": count}
