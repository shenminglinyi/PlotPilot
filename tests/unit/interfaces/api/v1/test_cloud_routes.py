"""云连接器路由层测试：回环守卫、会话端点传输、代理错误映射。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.cloud.connection_service import (
    CloudConnectionError,
    CloudResponse,
    CloudSessionError,
)
from interfaces.api.v1.cloud import get_cloud_connection_service, router as cloud_router


class _StubService:
    def __init__(self) -> None:
        self.login_calls: list[tuple[str, str]] = []
        self.proxy_calls: list[dict] = []
        self.login_error: Exception | None = None
        self.proxy_error: Exception | None = None

    def login(self, username: str, password: str):
        if self.login_error:
            raise self.login_error
        self.login_calls.append((username, password))
        return {"logged_in": True, "username": username, "display_name": "", "user_id": ""}

    def logout(self):
        return {"logged_in": False}

    def status(self):
        return {"logged_in": False}

    def request(self, method: str, path: str, *, json_body=None, params=None):
        if self.proxy_error:
            raise self.proxy_error
        self.proxy_calls.append({"method": method, "path": path})
        return CloudResponse(status_code=200, body={"data": {"ok": True}})


def _build(service: _StubService, *, client_host: str) -> TestClient:
    app = FastAPI()
    app.include_router(cloud_router, prefix="/api/v1")
    app.dependency_overrides[get_cloud_connection_service] = lambda: service
    return TestClient(app, client=(client_host, 55555))


@pytest.fixture()
def client():
    service = _StubService()
    return _build(service, client_host="127.0.0.1"), service


def test_session_login_and_logout_roundtrip(client):
    http, service = client

    login = http.post("/api/v1/cloud/session", json={"username": "a", "password": "b"})
    assert login.status_code == 200
    assert login.json()["data"]["logged_in"] is True
    assert service.login_calls == [("a", "b")]

    status = http.get("/api/v1/cloud/session")
    assert status.status_code == 200

    logout = http.delete("/api/v1/cloud/session")
    assert logout.status_code == 200
    assert logout.json()["data"] == {"logged_in": False}


def test_non_loopback_client_rejected():
    service = _StubService()
    outside = _build(service, client_host="192.168.1.50")

    response = outside.get("/api/v1/cloud/session")

    assert response.status_code == 403
    assert service.login_calls == []
    assert service.proxy_calls == []


def test_proxy_passes_whitelisted_path(client):
    http, service = client
    response = http.post(
        "/api/v1/cloud/proxy",
        json={"method": "GET", "path": "/api/v1/social/notifications"},
    )
    assert response.status_code == 200
    assert service.proxy_calls[-1]["path"] == "/api/v1/social/notifications"


def test_proxy_error_mapping(client):
    http, service = client
    service.proxy_error = CloudSessionError("cloud session expired; sign in again")
    session_expired = http.post(
        "/api/v1/cloud/proxy",
        json={"method": "GET", "path": "/api/v1/social/notifications"},
    )
    assert session_expired.status_code == 401

    service.proxy_error = CloudConnectionError("cloud unreachable")
    unreachable = http.post(
        "/api/v1/cloud/proxy",
        json={"method": "GET", "path": "/api/v1/social/notifications"},
    )
    assert unreachable.status_code == 502

    service.proxy_error = ValueError("path not allowed")
    forbidden = http.post(
        "/api/v1/cloud/proxy",
        json={"method": "GET", "path": "/api/v1/novels/n1"},
    )
    assert forbidden.status_code == 400
