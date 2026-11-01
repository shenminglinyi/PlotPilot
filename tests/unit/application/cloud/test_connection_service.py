"""云连接器服务测试：服务端 cookie 会话、旋转原子性、白名单、401 单刷。

用 httpx.MockTransport 模拟 plotpilot.xyz（不联网）：
- 登录下发 access_token + pp_refresh cookie
- 业务 401 → 自动用 cookie 刷新 → 重发成功
- 刷新响应旋转 cookie → 新凭证落盘后才算成功
- 路径白名单：非广场/社交路径拒绝
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from application.cloud.connection_service import (
    CloudConnectionService,
    CloudSessionError,
)
from infrastructure.cloud.session_store import CloudSession, CloudSessionStore
from interfaces.api.settings import CloudSettings

BASE = "https://plotpilot.test"


class FakeCloud:
    """极简 pw 桩：登录/刷新/带 Bearer 的社交读接口。"""

    def __init__(self) -> None:
        self.refresh_counter = 0
        self.refresh_cookie = "cookie-v1"
        self.access_counter = 0
        self.requests: list[dict] = []

    @property
    def refresh_calls(self) -> int:
        return self.refresh_counter

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(
            {
                "method": request.method,
                "path": request.url.path,
                "auth": request.headers.get("authorization", ""),
                "client": request.headers.get("x-plotpilot-client", ""),
                "cookie": request.headers.get("cookie", ""),
            }
        )
        path = request.url.path
        if path == "/api/v1/auth/login":
            self.access_counter += 1
            return httpx.Response(
                200,
                json={"access_token": f"access-{self.access_counter}", "expires_in": 1800},
                headers={
                    "set-cookie": (
                        f"pp_refresh={self.refresh_cookie}; Path=/api/v1/auth; "
                        "HttpOnly; Secure; SameSite=Strict"
                    )
                },
            )
        if path == "/api/v1/auth/refresh":
            self.refresh_counter += 1
            self.access_counter += 1
            self.refresh_cookie = f"cookie-v{self.refresh_counter + 1}"
            return httpx.Response(
                200,
                json={"access_token": f"access-{self.access_counter}", "expires_in": 1800},
                headers={
                    "set-cookie": (
                        f"pp_refresh={self.refresh_cookie}; Path=/api/v1/auth; "
                        "HttpOnly; Secure; SameSite=Strict"
                    )
                },
            )
        if path == "/api/v1/auth/logout":
            return httpx.Response(200, json={"ok": True})
        if path == "/api/v1/social/notifications":
            auth = request.headers.get("authorization", "")
            if auth == "Bearer stale-token":
                return httpx.Response(401, json={"detail": "token expired"})
            return httpx.Response(200, json={"data": {"unread_count": 3}})
        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture()
def fake_cloud() -> FakeCloud:
    return FakeCloud()


@pytest.fixture()
def session_file(tmp_path: Path) -> Path:
    return tmp_path / "session.json"


@pytest.fixture()
def service(
    fake_cloud: FakeCloud, session_file: Path
) -> tuple[CloudConnectionService, FakeCloud]:
    settings = CloudSettings(base_url=BASE, session_path=str(session_file))
    store = CloudSessionStore(path=session_file)

    def client_factory():
        # 动态分发：测试可替换 fake_cloud.handler 改写单次行为
        return httpx.Client(
            transport=httpx.MockTransport(lambda request: fake_cloud.handler(request)),
            base_url=BASE,
        )

    return CloudConnectionService(settings, store, client_factory=client_factory), fake_cloud


def test_login_stores_credentials_server_side_only(
    service: tuple[CloudConnectionService, FakeCloud], session_file: Path
):
    connector, cloud = service

    data = connector.login("alice", "pw123")

    # 对外身份概要不含 token/cookie（浏览器零凭证契约）
    assert data == {
        "logged_in": True,
        "username": "alice",
        "display_name": "",
        "user_id": "",
    }
    # 请求头带 client 标识（存在性校验非白名单）
    assert cloud.requests[0]["client"] == "plotpilot-kernel"
    # 会话文件已写
    payload = json.loads(session_file.read_text())
    assert payload["access_token"] == "access-1"
    assert payload["refresh_cookie"] == "cookie-v1"


def test_proxy_requires_login_for_writes(
    service: tuple[CloudConnectionService, FakeCloud],
):
    """非 GET 无会话直接报错（写操作必须登录）。"""
    connector, _ = service
    with pytest.raises(CloudSessionError):
        connector.request("POST", "/api/v1/prompt-square/community/assets/c1/events")


def test_proxy_anonymous_get_catalog(
    service: tuple[CloudConnectionService, FakeCloud],
):
    """公开目录 GET 匿名可读（桌面端拉下来自渲染广场的入口）。"""
    connector, cloud = service

    # 未登录直接 GET 公开目录：裸发不带 Authorization
    response = connector.request(
        "GET", "/api/v1/prompt-square/genres", params={"limit": 24}
    )

    assert response.status_code == 404  # 桶未注册该路径但已放行转发
    sent = cloud.requests[0]
    assert sent["method"] == "GET"
    assert sent["path"] == "/api/v1/prompt-square/genres"
    assert sent["auth"] == ""
    assert sent["client"] == "plotpilot-kernel"


def test_proxy_anonymous_get_hot_novels_passes_401_through(
    service: tuple[CloudConnectionService, FakeCloud],
):
    """匿名 GET 受保护路径（hot-novels）：401 原样透传，不拖拽会话/不报错。"""
    connector, _ = service

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/prompt-square/hot-novels":
            return httpx.Response(401, json={"detail": "authentication required"})
        raise AssertionError(f"unexpected path: {request.url.path}")

    service[1].handler = handler

    response = connector.request("GET", "/api/v1/prompt-square/hot-novels")

    assert response.status_code == 401
    assert response.body["detail"] == "authentication required"
    # 匿名路径不产生本地会话副作用
    assert connector.status() == {"logged_in": False}


def test_proxy_get_uses_bearer_when_logged_in(
    service: tuple[CloudConnectionService, FakeCloud],
):
    """登录后 GET 目录走 Bearer（个性化/受保护面可访问）。"""
    connector, cloud = service
    connector.login("alice", "pw123")

    connector.request("GET", "/api/v1/prompt-square/hot-novels")

    sent = [r for r in cloud.requests if r["path"] == "/api/v1/prompt-square/hot-novels"][0]
    assert sent["auth"].startswith("Bearer access-")


def test_proxy_success_after_auto_refresh(
    service: tuple[CloudConnectionService, FakeCloud], session_file: Path
):
    connector, cloud = service
    connector.login("alice", "pw123")
    # 人工把凭证改成失效态，触发 401 → refresh → 重发
    connector._store.save(
        CloudSession(
            access_token="stale-token",
            refresh_cookie="cookie-v1",
            expires_at=0.0,
            username="alice",
        )
    )

    response = connector.request("GET", "/api/v1/social/notifications")

    assert response.ok
    assert response.body["data"]["unread_count"] == 3
    # 刷新恰一次（旋转后重发成功，不循环重试）
    assert cloud.refresh_calls == 1
    # 新凭证已落盘（旋转先落盘契约）
    payload = json.loads(session_file.read_text())
    assert payload["access_token"] == "access-2"
    assert payload["refresh_cookie"] == "cookie-v2"


def test_proxy_path_whitelist(service: tuple[CloudConnectionService, FakeCloud]):
    connector, _ = service
    connector.login("alice", "pw123")

    # 非广场/社交路径：拒绝（数据边界契约——小说/引擎路径永不上云）
    with pytest.raises(ValueError):
        connector.request("GET", "/api/v1/novels/n1")
    with pytest.raises(ValueError):
        connector.request("GET", "/api/v1/engine/generation")
    with pytest.raises(ValueError):
        connector.request("GET", "../etc/passwd")
    with pytest.raises(ValueError):
        connector.request("GET", "http://evil.example.com/api/v1/social/feed")

    # 广场与社交路径放行（桩未注册该路径但已放行转发）
    response = connector.request("GET", "/api/v1/prompt-square/community/assets")
    assert response.status_code == 404


def test_double_401_clears_session_and_reports_expired(
    service: tuple[CloudConnectionService, FakeCloud], session_file: Path
):
    connector, cloud = service
    connector.login("alice", "pw123")
    # 刷新端点返回 401（cookie 链已死）：refresh 拒绝 → 显式失效
    original = cloud.handler

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/refresh":
            return httpx.Response(401, json={"detail": "revoked"})
        return original(request)

    cloud.handler = handler
    connector._store.save(
        CloudSession(
            access_token="stale-token",
            refresh_cookie="cookie-v1",
            expires_at=0.0,
            username="alice",
        )
    )

    with pytest.raises(CloudSessionError):
        connector.request("GET", "/api/v1/social/notifications")
    # 会话清理（本地凭证不残留）
    assert connector.status() == {"logged_in": False}


def test_logout_clears_local_session(
    service: tuple[CloudConnectionService, FakeCloud], session_file: Path
):
    connector, _ = service
    connector.login("alice", "pw123")
    assert session_file.exists()

    result = connector.logout()

    assert result == {"logged_in": False}
    assert not session_file.exists()
    assert connector.status() == {"logged_in": False}
