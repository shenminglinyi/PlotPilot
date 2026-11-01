"""云连接器应用服务：登录/服务端会话/自动刷新/受控代理请求.

会话模型（与 pw 硬切契约对齐）：
- 登录拿 {access_token, expires_in} + Set-Cookie pp_refresh（HttpOnly;
  Secure; SameSite=Strict; Path=/api/v1/auth）——服务端 cookie jar 自管，
  不受浏览器约束；浏览器全程零凭证。
- 业务请求带 Bearer access_token；401 时用存储的 cookie 刷新一次，
  旋转后**先落盘新凭证再返回业务结果**；刷新失败显式报「会话失效」，
  绝不循环重试。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from infrastructure.cloud.session_store import CloudSession, CloudSessionStore
from interfaces.api.settings import CloudSettings

logger = logging.getLogger(__name__)

CLIENT_HEADER = "x-plotpilot-client"
REFRESH_COOKIE_NAME = "pp_refresh"
# 刷新提前量：到期前 60s 内即刷新，避免边界竞态
_EXPIRY_SKEW_SECONDS = 60.0


class CloudSessionError(RuntimeError):
    """云端会话不可用（未登录/已失效）。"""


class CloudConnectionError(RuntimeError):
    """云端网络不可达/传输失败。"""


@dataclass(frozen=True)
class CloudResponse:
    status_code: int
    body: dict[str, Any]

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class CloudConnectionService:
    def __init__(
        self,
        settings: CloudSettings,
        store: CloudSessionStore,
        *,
        client_factory=None,
        clock=time.time,
    ) -> None:
        self._settings = settings
        self._store = store
        # client_factory 注入点：测试传 MockTransport 的 httpx.Client
        self._client_factory = client_factory or self._default_client
        self._clock = clock

    # ── 会话面（/cloud/session 代理） ──

    def login(self, username: str, password: str) -> dict[str, Any]:
        """登录并持久化服务端会话。登录体永不落日志。"""
        try:
            with self._new_client() as client:
                response = client.post(
                    "/api/v1/auth/login",
                    json={"username": username, "password": password},
                    headers={CLIENT_HEADER: self._settings.client_name},
                )
        except httpx.HTTPError as exc:
            raise CloudConnectionError(f"cloud unreachable: {exc}") from exc
        if response.status_code != 200:
            raise CloudSessionError(f"cloud login failed: {response.status_code}")
        payload = _safe_json(response)
        token_pair = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        access_token = str(token_pair.get("access_token") or "")
        expires_in = float(token_pair.get("expires_in") or 0)
        if not access_token:
            raise CloudSessionError("cloud login response missing access_token")
        session = CloudSession(
            access_token=access_token,
            refresh_cookie=_extract_refresh_cookie(response),
            expires_at=self._clock() + expires_in,
            username=username,
            display_name=str(token_pair.get("display_name") or ""),
            user_id=str(token_pair.get("user_id") or ""),
        )
        self._store.save(session)
        # 凭证只存服务端；对外只回身份概要（无 token 无 cookie）
        return {
            "logged_in": True,
            "username": session.username,
            "display_name": session.display_name,
            "user_id": session.user_id,
        }

    def logout(self) -> dict[str, Any]:
        session = self._store.load()
        if session is None:
            return {"logged_in": False}
        try:
            with self._new_client() as client:
                client.post(
                    "/api/v1/auth/logout",
                    cookies={REFRESH_COOKIE_NAME: session.refresh_cookie}
                    if session.refresh_cookie
                    else None,
                    headers={CLIENT_HEADER: self._settings.client_name},
                )
        except httpx.HTTPError:
            logger.warning("[CloudConnector] logout upstream unreachable; clearing local session")
        self._store.clear()
        return {"logged_in": False}

    def status(self) -> dict[str, Any]:
        session = self._store.load()
        if session is None:
            return {"logged_in": False}
        return {
            "logged_in": True,
            "username": session.username,
            "display_name": session.display_name,
            "user_id": session.user_id,
            "expires_at": session.expires_at,
        }

    # ── 代理面（/cloud/** 透传） ──

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> CloudResponse:
        """受控代理请求：白名单路径校验 + Bearer + 单次自动刷新。

        GET 允许匿名（公开目录面：genres/facets/assets/community），
        未登录时直接裸发，401 原样透传给前端决定是否引导登录；
        非 GET 无会话直接报错。
        """
        normalized = _normalize_proxy_path(path)
        if not normalized:
            raise ValueError(f"path not allowed: {path}")
        session = self._store.load()
        if session is None or not session.access_token:
            if str(method).upper() != "GET":
                raise CloudSessionError("cloud session missing; sign in first")
            try:
                anonymous = self._send(None, method, normalized, json_body, params)
            except httpx.HTTPError as exc:
                raise CloudConnectionError(f"cloud unreachable: {exc}") from exc
            return _to_cloud_response(anonymous)
        try:
            first = self._send(session, method, normalized, json_body, params)
        except httpx.HTTPError as exc:
            raise CloudConnectionError(f"cloud unreachable: {exc}") from exc
        if first.status_code != 401:
            return _to_cloud_response(first)
        refreshed = self._refresh(session)
        if refreshed is None:
            raise CloudSessionError("cloud session expired; sign in again")
        try:
            second = self._send(refreshed, method, normalized, json_body, params)
        except httpx.HTTPError as exc:
            raise CloudConnectionError(f"cloud unreachable: {exc}") from exc
        if second.status_code == 401:
            # 二次 401：凭证链已死，清理并显式报失效（不循环）
            self._store.clear()
            raise CloudSessionError("cloud session expired; sign in again")
        return _to_cloud_response(second)

    # ── 内部 ──

    def _refresh(self, session: CloudSession) -> CloudSession | None:
        """旋转：成功则先落盘再返回；失败返回 None（调用方报失效）。"""
        if not session.refresh_cookie:
            return None
        try:
            with self._new_client() as client:
                response = client.post(
                    "/api/v1/auth/refresh",
                    cookies={REFRESH_COOKIE_NAME: session.refresh_cookie},
                    headers={CLIENT_HEADER: self._settings.client_name},
                )
        except httpx.HTTPError:
            logger.warning("[CloudConnector] refresh upstream unreachable")
            return None
        if response.status_code != 200:
            logger.warning("[CloudConnector] refresh rejected: %d", response.status_code)
            # 刷新被拒：凭证链已死（family 被吊销/轮换丢失），本地清除
            self._store.clear()
            return None
        payload = _safe_json(response)
        token_pair = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        access_token = str(token_pair.get("access_token") or "")
        if not access_token:
            return None
        rotated = CloudSession(
            access_token=access_token,
            # Set-Cookie 旋转则替换；未随响应下发则沿用旧值（同族宽限）
            refresh_cookie=_extract_refresh_cookie(response) or session.refresh_cookie,
            expires_at=self._clock() + float(token_pair.get("expires_in") or 0),
            username=session.username,
            display_name=session.display_name,
            user_id=session.user_id,
        )
        # 原子性：新凭证先落盘，旧 cookie 在服务端已被作废——此时起会话
        # 只认新凭证；崩溃丢失=下次 401 显式失效，用户重登（可接受下界）
        self._store.save(rotated)
        return rotated

    def _send(
        self,
        session: CloudSession | None,
        method: str,
        path: str,
        json_body: dict[str, Any] | None,
        params: dict[str, Any] | None,
    ):
        # session=None 即匿名 GET（公开目录面）：不带 Authorization，
        # 服务端对受保护路径自然回 401，由前端引导登录
        headers = {CLIENT_HEADER: self._settings.client_name}
        if session is not None:
            headers["Authorization"] = f"Bearer {session.access_token}"
        with self._new_client() as client:
            return client.request(
                method,
                path,
                json=json_body,
                params=params,
                headers=headers,
            )

    def _default_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._settings.base_url,
            timeout=self._settings.request_timeout_seconds,
            follow_redirects=False,
        )

    def _new_client(self):
        return self._client_factory()


# ── 模块级纯函数 ──

# 代理白名单：只允许广场与社交面（数据边界契约，见 docs/social-plaza-design 13.3）。
# 目录 GET（genres/facets/assets/hot-novels）供桌面端「拉下来」自渲染广场：
# 公开目录可匿名读；hot-novels 服务端需登录，匿名时 401 透传由前端引导。
_ALLOWED_PROXY_PREFIXES = (
    "/api/v1/prompt-square/genres",
    "/api/v1/prompt-square/facets",
    "/api/v1/prompt-square/opening-workflow",
    "/api/v1/prompt-square/assets",
    "/api/v1/prompt-square/hot-novels",
    "/api/v1/prompt-square/community",
    "/api/v1/prompt-square/book-seeds",
    "/api/v1/social",
)


def _normalize_proxy_path(path: str) -> str:
    normalized = str(path or "").strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if ".." in normalized or "//" in normalized:
        return ""
    if normalized.startswith(_ALLOWED_PROXY_PREFIXES):
        return normalized
    return ""


def _extract_refresh_cookie(response: httpx.Response) -> str:
    for header_value in response.headers.get_list("set-cookie"):
        for part in header_value.split(";"):
            name, _, value = part.strip().partition("=")
            if name == REFRESH_COOKIE_NAME and value:
                return value
    return ""


def _to_cloud_response(response: httpx.Response) -> CloudResponse:
    return CloudResponse(status_code=response.status_code, body=_safe_json(response))


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}
