"""Cloud connector routes: 广场+社交代理（内核唯一上云通道）.

数据边界（显式契约）：云=广场+社交，仅此而已——作品手稿/知识图谱/
引擎状态永不上云。代理路径白名单在 application.cloud.connection_service。
安全边界：连接器路由仅接受本机回环客户端（内核默认本地工具；
绑定 0.0.0.0 的部署由运维侧防火墙兜底）。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from application.cloud.connection_service import (
    CloudConnectionError,
    CloudConnectionService,
    CloudResponse,
    CloudSessionError,
)
from interfaces.api.dependencies import get_cloud_connection_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cloud", tags=["cloud"])


def _assert_loopback_client(request: Request) -> None:
    """连接器路由只接受本机回环客户端（推演修正 8：局域网代打洞）。"""
    client = request.client
    host = (client.host if client else "") or ""
    if host not in ("127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost"):
        logger.warning("[CloudRoutes] non-loopback client rejected: %s", host)
        raise HTTPException(status_code=403, detail="cloud connector is loopback-only")


class CloudLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class CloudProxyResponse(BaseModel):
    status_code: int
    body: dict[str, Any] = Field(default_factory=dict)


# ── 会话面 ──


@router.get("/session")
async def cloud_session_status(
    _guard: None = Depends(_assert_loopback_client),
    service: CloudConnectionService = Depends(get_cloud_connection_service),
):
    return {"data": service.status()}


@router.post("/session")
async def cloud_session_login(
    body: CloudLoginRequest,
    _guard: None = Depends(_assert_loopback_client),
    service: CloudConnectionService = Depends(get_cloud_connection_service),
):
    try:
        data = service.login(body.username, body.password)
    except CloudSessionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"data": data}


@router.delete("/session")
async def cloud_session_logout(
    _guard: None = Depends(_assert_loopback_client),
    service: CloudConnectionService = Depends(get_cloud_connection_service),
):
    return {"data": service.logout()}


# ── 代理面：/cloud/proxy → 白名单内的 pw 广场+社交接口 ──


class CloudProxyRequest(BaseModel):
    method: str = Field(pattern="^(GET|POST|PATCH|DELETE)$")
    path: str = Field(min_length=1, max_length=400)
    body: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/proxy")
async def cloud_proxy(
    payload: CloudProxyRequest,
    _guard: None = Depends(_assert_loopback_client),
    service: CloudConnectionService = Depends(get_cloud_connection_service),
):
    """受控代理：路径白名单（广场+社交）+ Bearer + 401 单次自动刷新。"""
    try:
        response: CloudResponse = service.request(
            payload.method,
            payload.path,
            json_body=payload.body or None,
            params=payload.params or None,
        )
    except CloudSessionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except CloudConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if response.status_code >= 500:
        raise HTTPException(
            status_code=502, detail=f"cloud upstream {response.status_code}"
        )
    return CloudProxyResponse(status_code=response.status_code, body=response.body)
