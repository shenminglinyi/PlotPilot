"""Comprehensive security & protocol unit tests for Phase A:
- OAuthCredentialStore atomic 0600 persistence & single-use PKCE / RFC 8628 Device Flow states
- Loopback-only HTTP client guard (403 on LAN/external IPs, 200 on 127.0.0.1)
- OpenRouter PKCE, GitHub Device Flow (pending -> slow_down -> completed), Google Gemini PKCE + refresh rotation
- GeminiProvider OAuth Bearer header vs API key query param isolation
- Origin-bound MASKED_SECRET_SENTINEL protection against SSRF credential exfiltration
- Local Gateway (Magpie) loopback SSRF guard, model pool discovery, CLI non-secret status, & golden role connect
- Server-side golden role credential cloning (/role-routing/apply-golden) with zero plaintext leakage
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.ai.llm_control_service import (
    LLMControlConfig,
    LLMControlService,
    LLMProfile,
    MASKED_SECRET_SENTINEL,
)
from application.ai.llm_oauth_service import LLMOAuthService
from application.ai.local_gateway_probe import (
    LocalGatewayProbeService,
    recommend_role_models,
    validate_loopback_gateway_url,
)
from domain.ai.errors import LLMNotConfiguredError
from infrastructure.ai.llm_environment import LLMEnvironmentSettings
from infrastructure.ai.oauth_credential_store import (
    OAuthCredentialStore,
    OAuthSessionRecord,
    OAuthStateError,
    compute_pkce_s256_challenge,
)
from infrastructure.ai.provider_factory import LLMProviderFactory
from infrastructure.ai.providers.gemini_provider import GeminiProvider
from infrastructure.persistence.database.connection import DatabaseConnection
from interfaces.api.settings import API_V1_PREFIX
from interfaces.api.v1.workbench import llm_control, llm_oauth_routes


class _FakeClock:
    def __init__(self, initial: float = 1_750_000_000.0) -> None:
        self.current = initial

    def now(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


@pytest.fixture()
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    clock = _FakeClock()
    db_path = tmp_path / "test_llm_phase_a.db"
    db = DatabaseConnection(str(db_path))
    oauth_path = tmp_path / "llm-oauth-sessions.json"
    store = OAuthCredentialStore(oauth_path, time_fn=clock.now)

    env_holder: dict[str, LLMEnvironmentSettings] = {
        "settings": LLMEnvironmentSettings()
    }
    handler_holder: dict[str, Callable[[httpx.Request], httpx.Response]] = {
        "async": lambda req: httpx.Response(404, json={"error": f"unhandled {req.url}"}),
        "sync": lambda req: httpx.Response(404, json={"error": f"unhandled {req.url}"}),
    }

    def make_async_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: handler_holder["async"](req)),
            timeout=5.0,
            trust_env=False,
            follow_redirects=False,
        )

    def make_sync_client() -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(lambda req: handler_holder["sync"](req)),
            timeout=5.0,
            trust_env=False,
            follow_redirects=False,
        )

    control_service = LLMControlService(
        db_provider=lambda: db,
        oauth_credential_store=store,
    )
    oauth_service = LLMOAuthService(
        credential_store=store,
        control_service=control_service,
        env_settings_provider=lambda: env_holder["settings"],
        client_factory=make_async_client,
        sync_client_factory=make_sync_client,
    )
    control_service._oauth_service = oauth_service

    fake_home = tmp_path / "fake_home"
    fake_home.mkdir(parents=True, exist_ok=True)
    probe_service = LocalGatewayProbeService(
        control_service=control_service,
        env_settings_provider=lambda: env_holder["settings"],
        client_factory=make_async_client,
        cli_which=lambda name: f"/usr/bin/{name}" if name in ("magpie", "claude") else None,
        home_dir_provider=lambda: fake_home,
    )

    factory = LLMProviderFactory(control_service)
    monkeypatch.setattr(llm_control, "_service", control_service)
    monkeypatch.setattr(llm_control, "_factory", factory)
    llm_control._invalidate_llm_panel_cache()

    app = FastAPI()
    app.include_router(llm_oauth_routes.router, prefix=API_V1_PREFIX)
    app.include_router(llm_control.router, prefix=API_V1_PREFIX)
    app.dependency_overrides[llm_oauth_routes.get_llm_oauth_service] = lambda: oauth_service
    app.dependency_overrides[
        llm_oauth_routes.get_local_gateway_probe_service
    ] = lambda: probe_service
    app.dependency_overrides[
        llm_control.get_llm_control_service_dep
    ] = lambda: control_service

    def make_http_client(client_host: str = "127.0.0.1") -> TestClient:
        return TestClient(app, client=(client_host, 55555))

    try:
        yield {
            "clock": clock,
            "db": db,
            "store": store,
            "oauth_path": oauth_path,
            "fake_home": fake_home,
            "env_holder": env_holder,
            "handler_holder": handler_holder,
            "control_service": control_service,
            "oauth_service": oauth_service,
            "probe_service": probe_service,
            "factory": factory,
            "make_http_client": make_http_client,
        }
    finally:
        llm_control._invalidate_llm_panel_cache()
        db.close_all(skip_checkpoint=True)


# ── 1. OAuthCredentialStore Atomic 0600 & PKCE S256 / Replay Tests ──────


def test_oauth_credential_store_atomic_0600_roundtrip_and_no_tmp_leftovers(tmp_path: Path):
    store_file = tmp_path / "nested" / "llm-oauth-sessions.json"
    store = OAuthCredentialStore(store_file)

    record = OAuthSessionRecord(
        session_id="openrouter",
        provider="openrouter",
        access_token="sk-or-v1-ultra-secret-token",
        refresh_token="rt-secret-token",
        account_label="OpenRouter PKCE",
        connected_at=100.0,
        updated_at=100.0,
    )
    store.save_session(record)

    assert store_file.is_file()
    leftover_tmps = list(store_file.parent.glob(".llm-oauth-*.tmp"))
    assert leftover_tmps == []

    st_mode = stat.S_IMODE(os.stat(store_file).st_mode)
    if os.name != "nt":
        assert st_mode == 0o600
    else:
        assert bool(st_mode & stat.S_IREAD)
        assert bool(st_mode & stat.S_IWRITE)

    reloaded_store = OAuthCredentialStore(store_file)
    loaded = reloaded_store.get_session("openrouter")
    assert loaded is not None
    assert loaded.access_token == "sk-or-v1-ultra-secret-token"
    assert loaded.refresh_token == "rt-secret-token"

    assert reloaded_store.delete_session("openrouter") is True
    assert OAuthCredentialStore(store_file).get_session("openrouter") is None


def test_pkce_s256_rfc7636_vector_and_single_use_state_consumption(tmp_path: Path):
    # RFC 7636 Appendix B official test vector
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    expected_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert compute_pkce_s256_challenge(verifier) == expected_challenge

    clock = _FakeClock()
    store = OAuthCredentialStore(tmp_path / "oauth.json", time_fn=clock.now)
    flow = store.create_pkce_flow(
        "openrouter",
        redirect_uri="http://127.0.0.1:8005/api/v1/llm-control/oauth/openrouter/callback",
        ttl_seconds=600,
    )
    assert len(flow.code_verifier) >= 43

    # Wrong provider rejected (does not consume valid openrouter state if provider mismatches)
    with pytest.raises(OAuthStateError):
        store.consume_pkce_state("google_gemini", flow.state)

    # Wrong state rejected
    with pytest.raises(OAuthStateError):
        store.consume_pkce_state("openrouter", "forged-state-value")

    # Valid state consumed once
    consumed = store.consume_pkce_state("openrouter", flow.state)
    assert consumed.code_verifier == flow.code_verifier

    # Replay of exact same state MUST fail immediately
    with pytest.raises(OAuthStateError):
        store.consume_pkce_state("openrouter", flow.state)

    # Expired state rejected
    expiring_flow = store.create_pkce_flow(
        "openrouter",
        redirect_uri="http://127.0.0.1:8005/api/v1/llm-control/oauth/openrouter/callback",
        ttl_seconds=60,
    )
    clock.advance(61)
    with pytest.raises(OAuthStateError):
        store.consume_pkce_state("openrouter", expiring_flow.state)


# ── 2. Loopback-Only Guard Tests ────────────────────────────────────────


@pytest.mark.parametrize(
    "remote_host",
    ["192.168.1.50", "10.0.0.5", "203.0.113.9", "evil.example"],
)
def test_non_loopback_clients_receive_403_across_credential_and_gateway_routes(
    isolated_env: dict[str, Any],
    remote_host: str,
):
    outside = isolated_env["make_http_client"](remote_host)

    assert outside.get("/api/v1/llm-control").status_code == 403
    assert outside.put("/api/v1/llm-control", json={"profiles": []}).status_code == 403
    assert outside.get("/api/v1/llm-control/runtime").status_code == 403
    assert outside.post("/api/v1/llm-control/models", json={}).status_code == 403
    assert (
        outside.post(
            "/api/v1/llm-control/test",
            json={"id": "p1", "name": "P1", "model": "gpt-4o", "api_key": "k"},
        ).status_code
        == 403
    )
    assert outside.get("/api/v1/llm-control/oauth/status").status_code == 403
    assert outside.post("/api/v1/llm-control/oauth/openrouter/start").status_code == 403
    assert outside.post("/api/v1/llm-control/local-gateways/probe").status_code == 403
    assert (
        outside.post(
            "/api/v1/llm-control/local-gateways/connect",
            json={"base_url": "http://127.0.0.1:3425/v1", "main_model": "gpt-4o"},
        ).status_code
        == 403
    )

    local = isolated_env["make_http_client"]("127.0.0.1")
    assert local.get("/api/v1/llm-control").status_code == 200
    assert local.get("/api/v1/llm-control/oauth/status").status_code == 200


# ── 3. OpenRouter PKCE Full Flow & Canonical Base URL Pinning ───────────


def test_openrouter_pkce_full_flow_zero_sqlite_secret_and_canonical_pinning(
    isolated_env: dict[str, Any],
):
    http = isolated_env["make_http_client"]("127.0.0.1")
    db: DatabaseConnection = isolated_env["db"]
    control: LLMControlService = isolated_env["control_service"]

    exchanged_payloads: list[dict[str, Any]] = []

    def handle_async(req: httpx.Request) -> httpx.Response:
        if str(req.url) == "https://openrouter.ai/api/v1/auth/keys":
            body = json.loads(req.content.decode("utf-8"))
            exchanged_payloads.append(body)
            return httpx.Response(200, json={"key": "sk-or-v1-live-secret-999"})
        return httpx.Response(404)

    isolated_env["handler_holder"]["async"] = handle_async

    # Even if an attacker passes a malicious callback_origin, backend MUST ignore it!
    start_resp = http.post(
        "/api/v1/llm-control/oauth/openrouter/start",
        json={"callback_origin": "https://evil.example"},
    )
    assert start_resp.status_code == 200
    auth_url = start_resp.json()["authorize_url"]
    parsed_auth = urlsplit(auth_url)
    assert parsed_auth.scheme == "https"
    assert parsed_auth.netloc == "openrouter.ai"
    qs = parse_qs(parsed_auth.query)
    assert "evil.example" not in qs["callback_url"][0]
    assert qs["callback_url"][0].startswith("http://127.0.0.1")
    assert qs["code_challenge_method"] == ["S256"]
    state = qs["state"][0]

    # Complete callback
    cb_resp = http.get(
        "/api/v1/llm-control/oauth/openrouter/callback",
        params={"code": "auth-code-xyz", "state": state},
    )
    assert cb_resp.status_code == 200
    assert "default-src 'none'" in cb_resp.headers["Content-Security-Policy"]
    assert "window.location.origin" in cb_resp.text
    assert "sk-or-v1-live-secret-999" not in cb_resp.text
    assert len(exchanged_payloads) == 1
    assert exchanged_payloads[0]["code"] == "auth-code-xyz"
    assert exchanged_payloads[0]["code_challenge_method"] == "S256"

    # Replaying callback with same state fails with 400
    replay_resp = http.get(
        "/api/v1/llm-control/oauth/openrouter/callback",
        params={"code": "auth-code-xyz", "state": state},
    )
    assert replay_resp.status_code == 400

    # Verify SQLite llm_profiles has ZERO secret stored
    row = db.fetch_one("SELECT * FROM llm_profiles WHERE id = ?", ("oauth-openrouter",))
    assert row is not None
    assert row["api_key"] == ""
    assert row["auth_mode"] == "oauth"
    assert row["oauth_provider"] == "openrouter"

    # Verify HTTP panel & oauth/status NEVER leak the secret
    panel_resp = http.get("/api/v1/llm-control")
    assert panel_resp.status_code == 200
    panel_text = panel_resp.text
    assert "sk-or-v1-live-secret-999" not in panel_text
    or_profile_json = next(
        p for p in panel_resp.json()["config"]["profiles"] if p["id"] == "oauth-openrouter"
    )
    assert or_profile_json["api_key"] == ""
    assert or_profile_json["has_secret"] is True

    status_resp = http.get("/api/v1/llm-control/oauth/status")
    assert "sk-or-v1-live-secret-999" not in status_resp.text
    or_status = next(
        p for p in status_resp.json()["providers"] if p["provider"] == "openrouter"
    )
    assert or_status["connected"] is True

    # Even if base_url in profile is tampered to an attacker domain, resolve_profile pins canonical OpenRouter URL!
    stored_profile = next(
        p for p in control.get_config().profiles if p.id == "oauth-openrouter"
    )
    tampered = stored_profile.model_copy(
        update={"base_url": "https://attacker.example/v1", "protocol": "anthropic"}
    )
    resolved = control.resolve_profile(tampered)
    assert resolved.api_key == "sk-or-v1-live-secret-999"
    assert resolved.base_url == "https://openrouter.ai/api/v1"
    assert resolved.protocol == "openai"

    # Disconnect cleans up session & profile state
    disc_resp = http.delete("/api/v1/llm-control/oauth/openrouter")
    assert disc_resp.status_code == 200
    or_after = next(
        p for p in disc_resp.json()["providers"] if p["provider"] == "openrouter"
    )
    assert or_after["connected"] is False


# ── 4. GitHub Device Flow & Google Gemini OAuth Refresh Rotation ────────


def test_github_device_flow_pending_slowdown_and_completion(
    isolated_env: dict[str, Any],
):
    http = isolated_env["make_http_client"]("127.0.0.1")
    clock: _FakeClock = isolated_env["clock"]
    control: LLMControlService = isolated_env["control_service"]

    # Without client_id configured, start returns clear HTTP 400
    missing_resp = http.post("/api/v1/llm-control/oauth/github/device/start", json={})
    assert missing_resp.status_code == 400

    poll_responses = [
        {"error": "authorization_pending"},
        {"error": "slow_down"},
        {"access_token": "ghu_secret_models_token_777", "token_type": "bearer"},
    ]
    upstream_poll_calls = 0

    def handle_async(req: httpx.Request) -> httpx.Response:
        nonlocal upstream_poll_calls
        if str(req.url) == "https://github.com/login/device/code":
            return httpx.Response(
                200,
                json={
                    "device_code": "dev-code-123",
                    "user_code": "WDJB-MJHT",
                    "verification_uri": "https://github.com/login/device",
                    "expires_in": 900,
                    "interval": 5,
                },
            )
        if str(req.url) == "https://github.com/login/oauth/access_token":
            idx = min(upstream_poll_calls, len(poll_responses) - 1)
            upstream_poll_calls += 1
            return httpx.Response(200, json=poll_responses[idx])
        return httpx.Response(404)

    isolated_env["handler_holder"]["async"] = handle_async

    start = http.post(
        "/api/v1/llm-control/oauth/github/device/start",
        json={"client_id": "Iv1.publicclient123"},
    )
    assert start.status_code == 200
    start_data = start.json()
    flow_id = start_data["flow_id"]
    assert start_data["user_code"] == "WDJB-MJHT"
    assert start_data["interval"] == 5

    # Immediate poll at t=0 (before initial 5s interval) is rate-limited locally per RFC 8628
    p0 = http.post("/api/v1/llm-control/oauth/github/device/poll", json={"flow_id": flow_id})
    assert p0.status_code == 200
    assert p0.json()["status"] == "pending"
    assert p0.json()["interval"] == 5
    assert upstream_poll_calls == 0

    # Advance past initial 5s interval -> Poll #1 -> authorization_pending
    clock.advance(5.0)
    p1 = http.post("/api/v1/llm-control/oauth/github/device/poll", json={"flow_id": flow_id})
    assert p1.status_code == 200
    assert p1.json()["status"] == "pending"
    assert p1.json()["interval"] == 5
    assert upstream_poll_calls == 1

    # Immediate poll 1s later is rate-limited locally without hitting GitHub
    clock.advance(1.0)
    p_fast = http.post(
        "/api/v1/llm-control/oauth/github/device/poll", json={"flow_id": flow_id}
    )
    assert p_fast.json()["status"] == "pending"
    assert upstream_poll_calls == 1

    # Advance past remaining interval -> Poll #2 -> slow_down bumps interval from 5 to 10
    clock.advance(4.5)
    p2 = http.post("/api/v1/llm-control/oauth/github/device/poll", json={"flow_id": flow_id})
    assert p2.status_code == 200
    assert p2.json()["status"] == "slow_down"
    assert p2.json()["interval"] == 10
    assert upstream_poll_calls == 2

    # Advance past 10s bumped interval -> Poll #3 -> completed!
    clock.advance(10.5)
    p3 = http.post("/api/v1/llm-control/oauth/github/device/poll", json={"flow_id": flow_id})
    assert p3.status_code == 200
    assert p3.json()["status"] == "completed"
    assert p3.json()["profile_id"] == "oauth-github_models"
    assert upstream_poll_calls == 3

    gh_profile = next(
        p for p in control.get_config().profiles if p.id == "oauth-github_models"
    )
    assert gh_profile.api_key == ""
    resolved = control.resolve_profile(gh_profile)
    assert resolved.api_key == "ghu_secret_models_token_777"
    assert resolved.base_url == "https://models.inference.ai.azure.com"


def test_google_gemini_pkce_refresh_rotation_and_bearer_header_isolation(
    isolated_env: dict[str, Any],
):
    http = isolated_env["make_http_client"]("127.0.0.1")
    clock: _FakeClock = isolated_env["clock"]
    control: LLMControlService = isolated_env["control_service"]
    factory: LLMProviderFactory = isolated_env["factory"]
    store: OAuthCredentialStore = isolated_env["store"]

    def handle_async(req: httpx.Request) -> httpx.Response:
        if str(req.url) == "https://oauth2.googleapis.com/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "ya29.initial-google-access",
                    "refresh_token": "1//initial-google-refresh",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        return httpx.Response(404)

    refresh_calls = 0

    def handle_sync(req: httpx.Request) -> httpx.Response:
        nonlocal refresh_calls
        if str(req.url) == "https://oauth2.googleapis.com/token":
            refresh_calls += 1
            form = parse_qs(req.content.decode("utf-8"))
            assert form["grant_type"] == ["refresh_token"]
            assert form["refresh_token"] == ["1//initial-google-refresh"]
            assert form["client_id"] == ["google-desktop-client.apps.googleusercontent.com"]
            return httpx.Response(
                200,
                json={
                    "access_token": "ya29.rotated-google-access-v2",
                    "refresh_token": "1//rotated-google-refresh-v2",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        return httpx.Response(404)

    isolated_env["handler_holder"]["async"] = handle_async
    isolated_env["handler_holder"]["sync"] = handle_sync

    start = http.post(
        "/api/v1/llm-control/oauth/google/start",
        json={"client_id": "google-desktop-client.apps.googleusercontent.com"},
    )
    assert start.status_code == 200
    qs = parse_qs(urlsplit(start.json()["authorize_url"]).query)
    state = qs["state"][0]

    cb = http.get(
        "/api/v1/llm-control/oauth/google/callback",
        params={"code": "4/google-code", "state": state},
    )
    assert cb.status_code == 200
    assert "ya29." not in cb.text

    # Before expiry: uses initial token without refresh call
    gemini_profile = next(
        p for p in control.get_config().profiles if p.id == "oauth-google_gemini"
    )
    resolved_initial = control.resolve_profile(gemini_profile)
    assert resolved_initial.api_key == "ya29.initial-google-access"
    assert refresh_calls == 0

    # Advance within 60s of expiry -> triggers sync refresh + atomic rotation in 0600 store!
    clock.advance(3555.0)
    provider = factory.create_from_profile(gemini_profile)
    assert isinstance(provider, GeminiProvider)
    assert refresh_calls == 1
    assert provider.settings.use_oauth_bearer is True
    assert provider.settings.api_key == "ya29.rotated-google-access-v2"

    # GeminiProvider MUST use Authorization: Bearer and MUST omit ?key= in URL query
    assert "key" not in provider._build_query()
    assert provider._build_query({"alt": "sse"}) == {"alt": "sse"}
    headers = provider._build_headers(stream=False)
    assert headers["Authorization"] == "Bearer ya29.rotated-google-access-v2"

    persisted_record = store.get_session("google_gemini")
    assert persisted_record is not None
    assert persisted_record.access_token == "ya29.rotated-google-access-v2"
    assert persisted_record.refresh_token == "1//rotated-google-refresh-v2"


# ── 5. Origin-Bound MASKED_SECRET_SENTINEL Protection ───────────────────


def test_masked_secret_sentinel_preserves_same_origin_and_blocks_ssrf_exfiltration(
    isolated_env: dict[str, Any],
):
    http = isolated_env["make_http_client"]("127.0.0.1")
    control: LLMControlService = isolated_env["control_service"]

    assert len(MASKED_SECRET_SENTINEL) == 27
    assert MASKED_SECRET_SENTINEL.startswith("__plotpilot_")

    # Save initial real API key
    put_resp = http.put(
        "/api/v1/llm-control",
        json={
            "active_profile_id": "p-openai",
            "endpoint_mode": "unified",
            "profiles": [
                {
                    "id": "p-openai",
                    "name": "OpenAI Prod",
                    "preset_key": "openai-official",
                    "protocol": "openai",
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-real-prod-secret-key",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    assert put_resp.status_code == 200
    assert "sk-real-prod-secret-key" not in put_resp.text
    returned_profile = put_resp.json()["config"]["profiles"][0]
    assert returned_profile["api_key"] == MASKED_SECRET_SENTINEL
    assert returned_profile["has_secret"] is True

    # Saving back with MASKED_SECRET_SENTINEL and SAME base_url preserves real key in SQLite
    returned_profile["model"] = "gpt-4.1"
    same_origin_resp = http.put(
        "/api/v1/llm-control",
        json={
            "active_profile_id": "p-openai",
            "endpoint_mode": "unified",
            "profiles": [returned_profile],
        },
    )
    assert same_origin_resp.status_code == 200
    assert control.resolve_active_profile().api_key == "sk-real-prod-secret-key"
    assert control.resolve_active_profile().model == "gpt-4.1"

    # Changing base_url to evil.example while keeping MASKED_SECRET_SENTINEL MUST fail with 400!
    evil_profile = dict(returned_profile)
    evil_profile["base_url"] = "https://evil.example/v1"
    ssrf_put = http.put(
        "/api/v1/llm-control",
        json={
            "active_profile_id": "p-openai",
            "endpoint_mode": "unified",
            "profiles": [evil_profile],
        },
    )
    assert ssrf_put.status_code == 400
    assert "重新输入" in ssrf_put.json()["detail"]

    # Also blocked on POST /test and POST /models!
    ssrf_test = http.post("/api/v1/llm-control/test", json=evil_profile)
    assert ssrf_test.status_code == 400

    ssrf_models = http.post(
        "/api/v1/llm-control/models",
        json={
            "profile_id": "p-openai",
            "protocol": "openai",
            "base_url": "https://evil.example/v1",
            "api_key": MASKED_SECRET_SENTINEL,
        },
    )
    assert ssrf_models.status_code == 400

    # Stored key in SQLite remains intact and uncorrupted
    assert control.resolve_active_profile().api_key == "sk-real-prod-secret-key"


# ── 6. Local Gateway SSRF Guard & Magpie Discovery / Connect ────────────


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://192.168.1.1:3425/v1",
        "http://10.0.0.8:11434/v1",
        "http://172.16.0.1:4000/v1",
        "http://169.254.169.254/latest",
        "http://169.254.169.254:8080/latest",
        "http://example.com:3425/v1",
        "http://0.0.0.0:3425/v1",
        "http://127.0.0.1:8005/v1",
        "http://127.0.0.1:80/v1",
        "http://127.0.0.1/v1",
        "http://user:pass@127.0.0.1:3425/v1",
        "file:///etc/passwd",
    ],
)
def test_local_gateway_ssrf_guard_rejects_non_loopback_and_unsafe_urls(
    isolated_env: dict[str, Any],
    blocked_url: str,
):
    with pytest.raises(ValueError):
        validate_loopback_gateway_url(blocked_url)

    http = isolated_env["make_http_client"]("127.0.0.1")
    probe_resp = http.post(
        "/api/v1/llm-control/local-gateways/probe",
        json={"custom_url": blocked_url},
    )
    assert probe_resp.status_code == 400

    conn_resp = http.post(
        "/api/v1/llm-control/local-gateways/connect",
        json={"base_url": blocked_url, "main_model": "gpt-4o"},
    )
    assert conn_resp.status_code == 400


def test_local_gateway_magpie_probe_golden_recommendation_and_connect(
    isolated_env: dict[str, Any],
):
    http = isolated_env["make_http_client"]("127.0.0.1")
    control: LLMControlService = isolated_env["control_service"]
    db: DatabaseConnection = isolated_env["db"]

    magpie_models = [
        "group/auto-task",
        "claude/claude-opus-5-5",
        "claude/claude-haiku-5-5",
        "workbuddy/deepseek-v4.1-flash",
        "antigravity/gemini-4-hydrogen",
    ]

    def handle_async(req: httpx.Request) -> httpx.Response:
        if str(req.url) == "http://127.0.0.1:3425/v1/models":
            return httpx.Response(
                200,
                json={"data": [{"id": m, "owned_by": "magpie"} for m in magpie_models]},
            )
        return httpx.Response(404)

    isolated_env["handler_holder"]["async"] = handle_async

    probe_resp = http.post("/api/v1/llm-control/local-gateways/probe", json={})
    assert probe_resp.status_code == 200
    body = probe_resp.json()
    gw = body["gateways"][0]
    assert gw["id"] == "magpie-local"
    assert gw["kind"] == "magpie"
    assert gw["reachable"] is True
    assert gw["recommended_roles"] == {
        "main": "claude/claude-opus-5-5",
        "cheap": "workbuddy/deepseek-v4.1-flash",
        "kg": "workbuddy/deepseek-v4.1-flash",
    }
    cli_ids = {item["id"] for item in body["cli_tools"]}
    assert {"magpie", "claude", "codex", "gemini", "gh"} <= cli_ids

    # Connect local gateway with golden roles enabled
    conn_resp = http.post(
        "/api/v1/llm-control/local-gateways/connect",
        json={
            "base_url": "http://127.0.0.1:3425/v1",
            "name": "Magpie 订阅网关",
            "main_model": gw["recommended_roles"]["main"],
            "cheap_model": gw["recommended_roles"]["cheap"],
            "kg_model": "antigravity/gemini-4-hydrogen",
            "enable_golden_roles": True,
        },
    )
    assert conn_resp.status_code == 200
    cfg_json = conn_resp.json()["config"]
    assert cfg_json["endpoint_mode"] == "independent"
    assert cfg_json["active_profile_id"] == "local-gateway-main"
    assert cfg_json["role_bindings"] == {
        "main": "local-gateway-main",
        "cheap": "local-gateway-cheap",
        "kg": "local-gateway-kg",
    }

    assert control.resolve_role_profile("main").model == "claude/claude-opus-5-5"
    assert control.resolve_role_profile("cheap").model == "workbuddy/deepseek-v4.1-flash"
    assert control.resolve_role_profile("kg").model == "antigravity/gemini-4-hydrogen"

    # If SQLite row for local_gateway is tampered to non-loopback, resolve_profile raises LLMNotConfiguredError!
    db.execute(
        "UPDATE llm_profiles SET base_url = ? WHERE id = ?",
        ("http://192.168.1.99:3425/v1", "local-gateway-main"),
    )
    db.commit()
    tampered = next(
        p for p in control.get_config().profiles if p.id == "local-gateway-main"
    )
    with pytest.raises(LLMNotConfiguredError):
        control.resolve_profile(tampered)


# ── 7. Golden Role Routing Server-Side Credential Cloning ───────────────


def test_apply_golden_role_routing_clones_credentials_without_exposing_secrets(
    isolated_env: dict[str, Any],
):
    http = isolated_env["make_http_client"]("127.0.0.1")
    control: LLMControlService = isolated_env["control_service"]

    control.save_config(
        LLMControlConfig(
            active_profile_id="openrouter-key-profile",
            endpoint_mode="unified",
            profiles=[
                LLMProfile(
                    id="openrouter-key-profile",
                    name="OpenRouter Key",
                    preset_key="openrouter",
                    protocol="openai",
                    base_url="https://openrouter.ai/api/v1",
                    api_key="sk-or-super-private-7890",
                    model="anthropic/claude-sonnet-4",
                )
            ],
        )
    )

    rec = recommend_role_models(
        [
            "anthropic/claude-sonnet-4",
            "openai/gpt-4o-mini",
            "gemini-2.5-flash",
        ]
    )
    assert rec["main"] == "anthropic/claude-sonnet-4"
    assert rec["cheap"] == "openai/gpt-4o-mini"

    apply_resp = http.post(
        "/api/v1/llm-control/role-routing/apply-golden",
        json={
            "source_profile_id": "openrouter-key-profile",
            "main_model": "anthropic/claude-sonnet-4",
            "cheap_model": "openai/gpt-4o-mini",
            "kg_model": "gemini-2.5-flash",
        },
    )
    assert apply_resp.status_code == 200
    assert "sk-or-super-private-7890" not in apply_resp.text

    resp_cfg = apply_resp.json()["config"]
    assert resp_cfg["endpoint_mode"] == "independent"
    assert resp_cfg["role_bindings"] == {
        "main": "golden-role-main",
        "cheap": "golden-role-cheap",
        "kg": "golden-role-kg",
    }
    for p in resp_cfg["profiles"]:
        assert p["api_key"] == MASKED_SECRET_SENTINEL
        assert p["has_secret"] is True

    # Server-side resolution injects the real cloned credential for all 3 roles!
    main_res = control.resolve_role_profile("main")
    cheap_res = control.resolve_role_profile("cheap")
    kg_res = control.resolve_role_profile("kg")
    assert main_res.api_key == "sk-or-super-private-7890"
    assert main_res.model == "anthropic/claude-sonnet-4"
    assert cheap_res.api_key == "sk-or-super-private-7890"
    assert cheap_res.model == "openai/gpt-4o-mini"
    assert kg_res.api_key == "sk-or-super-private-7890"
    assert kg_res.model == "gemini-2.5-flash"


def test_cross_provider_oauth_session_confusion_is_blocked(
    isolated_env: dict[str, Any],
):
    http = isolated_env["make_http_client"]("127.0.0.1")
    store = isolated_env["store"]
    control: LLMControlService = isolated_env["control_service"]

    from infrastructure.ai.oauth_credential_store import OAuthSessionRecord

    store.save_session(
        OAuthSessionRecord(
            session_id="google_gemini",
            provider="google_gemini",
            access_token="ya29.secret-google-token",
            connected_at=1000.0,
            updated_at=1000.0,
        )
    )

    # Attempt to bind google_gemini session_id onto an openrouter oauth_provider profile -> HTTP 400
    confused_resp = http.put(
        "/api/v1/llm-control",
        json={
            "active_profile_id": "confused-oauth",
            "endpoint_mode": "unified",
            "profiles": [
                {
                    "id": "confused-oauth",
                    "name": "Confused OAuth",
                    "preset_key": "openrouter",
                    "protocol": "openai",
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key": "",
                    "model": "gpt-4o",
                    "auth_mode": "oauth",
                    "oauth_provider": "openrouter",
                    "oauth_session_id": "google_gemini",
                }
            ],
        },
    )
    assert confused_resp.status_code == 400

    # Even if constructed directly in memory/DB, resolve_profile refuses cross-provider session mismatch
    confused_profile = LLMProfile(
        id="confused-oauth",
        name="Confused OAuth",
        preset_key="openrouter",
        protocol="openai",
        base_url="https://openrouter.ai/api/v1",
        api_key="",
        model="gpt-4o",
        auth_mode="oauth",
        oauth_provider="openrouter",
        oauth_session_id="google_gemini",
    )
    with pytest.raises(LLMNotConfiguredError):
        control.resolve_profile(confused_profile)


def test_localhost_dns_rebinding_to_non_loopback_ip_is_blocked(monkeypatch: pytest.MonkeyPatch):
    import socket
    from application.ai.local_gateway_probe import validate_loopback_gateway_url

    def _fake_getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.99", port))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    with pytest.raises(ValueError, match="非回环"):
        validate_loopback_gateway_url("http://localhost:3425/v1")


@pytest.mark.asyncio
async def test_f1_loopback_transport_pins_validated_ip_and_blocks_connection_time_rebinding(
    monkeypatch: pytest.MonkeyPatch,
):
    import socket
    import httpcore
    from application.ai.local_gateway_probe import validate_loopback_gateway_target
    from infrastructure.ai.loopback_transport import (
        LoopbackOnlyAsyncBackend,
        LoopbackOnlyAsyncTransport,
        LoopbackOnlySyncTransport,
    )
    from infrastructure.ai.config.settings import Settings
    from infrastructure.ai.providers.openai_provider import OpenAIProvider

    connected_targets: list[tuple[str, int]] = []

    class _RecordingInnerBackend(httpcore.AsyncNetworkBackend):
        async def connect_tcp(
            self,
            host: str,
            port: int,
            timeout: Any = None,
            local_address: Any = None,
            socket_options: Any = None,
        ) -> Any:
            connected_targets.append((host, port))
            raise httpcore.ConnectError("stub-connected")

    # 1) Validation returns 127.0.0.1, then DNS flips to 192.168.1.99 at connection time:
    #    pinned_ips ensures zero second DNS lookup and connects ONLY to 127.0.0.1.
    target = validate_loopback_gateway_target(
        "http://localhost:3425/v1",
        resolver=lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))],
    )
    assert target.pinned_ips == ("127.0.0.1",)

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.99", port))],
    )
    pinned_backend = LoopbackOnlyAsyncBackend(
        pinned_ips=target.pinned_ips,
        allowed_port=target.port,
        inner=_RecordingInnerBackend(),
    )
    with pytest.raises(httpcore.ConnectError, match="stub-connected"):
        await pinned_backend.connect_tcp("localhost", 3425)
    assert connected_targets == [("127.0.0.1", 3425)]

    # 2) Unpinned saved local_gateway backend resolves at connection time and blocks 192.168.1.99 BEFORE inner.connect_tcp!
    connected_targets.clear()
    dynamic_backend = LoopbackOnlyAsyncBackend(
        inner=_RecordingInnerBackend(),
        resolver=lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.99", port))],
    )
    with pytest.raises(httpcore.ConnectError, match="非回环"):
        await dynamic_backend.connect_tcp("localhost", 3425)
    assert connected_targets == []

    from infrastructure.ai.providers.anthropic_provider import AnthropicProvider

    # 3) Provider client created with loopback_only=True attaches LoopbackOnly transports
    provider = OpenAIProvider(
        Settings(
            api_key="local-gateway",
            base_url="http://localhost:3425/v1",
            default_model="gpt-4o",
            loopback_only=True,
        )
    )
    gemini_local = GeminiProvider(
        Settings(
            api_key="local-gateway",
            base_url="http://localhost:3425/v1beta",
            default_model="gemini-2.5-flash",
            loopback_only=True,
        )
    )
    anthropic_local = AnthropicProvider(
        Settings(
            api_key="local-gateway",
            base_url="http://localhost:3425",
            default_model="claude-sonnet-4-20250514",
            loopback_only=True,
        )
    )
    try:
        assert isinstance(provider._http_client._transport, LoopbackOnlyAsyncTransport)
        assert provider._http_client.follow_redirects is False
        assert isinstance(gemini_local._http_client._transport, LoopbackOnlyAsyncTransport)
        assert gemini_local._http_client.follow_redirects is False
        assert isinstance(anthropic_local._http_client_async._transport, LoopbackOnlyAsyncTransport)
        assert isinstance(anthropic_local._http_client_sync._transport, LoopbackOnlySyncTransport)
        assert anthropic_local._http_client_async.follow_redirects is False
        assert anthropic_local._http_client_sync.follow_redirects is False
    finally:
        await provider._http_client.aclose()
        await gemini_local._http_client.aclose()
        await anthropic_local._http_client_async.aclose()
        anthropic_local._http_client_sync.close()


@pytest.mark.asyncio
async def test_f2_device_flow_concurrent_single_flight_and_timeout_slowdown(
    tmp_path: Path,
):
    import asyncio

    clock = _FakeClock()
    db = DatabaseConnection(str(tmp_path / "f2.db"))
    store = OAuthCredentialStore(tmp_path / "f2-oauth.json", time_fn=clock.now)
    control = LLMControlService(db_provider=lambda: db, oauth_credential_store=store)

    upstream_poll_calls = 0
    mode = "slow_pending"

    class _AsyncGateTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal upstream_poll_calls
            if str(request.url) == "https://github.com/login/device/code":
                return httpx.Response(
                    200,
                    json={
                        "device_code": "dev-f2",
                        "user_code": "F222-CODE",
                        "verification_uri": "https://github.com/login/device",
                        "expires_in": 900,
                        "interval": 5,
                    },
                )
            if str(request.url) == "https://github.com/login/oauth/access_token":
                upstream_poll_calls += 1
                if mode == "slow_pending":
                    await asyncio.sleep(0.05)
                    return httpx.Response(200, json={"error": "authorization_pending"})
                if mode == "timeout":
                    raise httpx.ReadTimeout("upstream timed out", request=request)
            return httpx.Response(404)

    oauth_service = LLMOAuthService(
        credential_store=store,
        control_service=control,
        env_settings_provider=lambda: LLMEnvironmentSettings(),
        client_factory=lambda: httpx.AsyncClient(
            transport=_AsyncGateTransport(), timeout=5.0, trust_env=False
        ),
    )
    control._oauth_service = oauth_service

    try:
        started = await oauth_service.start_github_device_flow(client_id="Iv1.f2test")
        flow_id = started.flow_id

        # Advance past initial 5s interval, then launch 3 concurrent polls
        clock.advance(5.0)
        results = await asyncio.gather(
            oauth_service.poll_github_device_flow(flow_id=flow_id),
            oauth_service.poll_github_device_flow(flow_id=flow_id),
            oauth_service.poll_github_device_flow(flow_id=flow_id),
        )
        assert upstream_poll_calls == 1
        assert all(r.status == "pending" for r in results)

        # Advance past 5s interval, simulate connection timeout -> RFC 8628 slow_down backoff (+5s -> 10s)
        clock.advance(5.0)
        mode = "timeout"
        timeout_res = await oauth_service.poll_github_device_flow(flow_id=flow_id)
        assert upstream_poll_calls == 2
        assert timeout_res.status == "slow_down"
        assert timeout_res.interval == 10
    finally:
        db.close_all(skip_checkpoint=True)


@pytest.mark.asyncio
async def test_f3_refresh_single_flight_and_disconnect_or_relogin_invalidation(
    tmp_path: Path,
):
    import asyncio

    clock = _FakeClock()
    db = DatabaseConnection(str(tmp_path / "f3.db"))
    store = OAuthCredentialStore(tmp_path / "f3-oauth.json", time_fn=clock.now)
    control = LLMControlService(db_provider=lambda: db, oauth_credential_store=store)

    refresh_posts = 0
    refresh_entered = asyncio.Event()
    allow_refresh_finish = asyncio.Event()
    next_access_token = "ya29.refreshed-v1"

    class _RefreshTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal refresh_posts
            if str(request.url) == "https://oauth2.googleapis.com/token":
                refresh_posts += 1
                refresh_entered.set()
                await allow_refresh_finish.wait()
                return httpx.Response(
                    200,
                    json={
                        "access_token": next_access_token,
                        "refresh_token": "1//refreshed-rt",
                        "expires_in": 3600,
                    },
                )
            return httpx.Response(404)

    oauth_service = LLMOAuthService(
        credential_store=store,
        control_service=control,
        env_settings_provider=lambda: LLMEnvironmentSettings(
            google_oauth_client_id="f3-client.apps.googleusercontent.com"
        ),
        client_factory=lambda: httpx.AsyncClient(
            transport=_RefreshTransport(), timeout=5.0, trust_env=False
        ),
    )
    control._oauth_service = oauth_service

    try:
        # Case A: 3 concurrent async callers share 1 single-flight refresh
        store.save_session(
            OAuthSessionRecord(
                session_id="google_gemini",
                provider="google_gemini",
                access_token="ya29.expired",
                refresh_token="1//seed-rt",
                expires_at=clock.now() + 10.0,
                client_id="f3-client.apps.googleusercontent.com",
                connected_at=clock.now(),
                updated_at=clock.now(),
            )
        )
        allow_refresh_finish.set()
        tokens = await asyncio.gather(
            oauth_service.resolve_access_token_async("google_gemini"),
            oauth_service.resolve_access_token_async("google_gemini"),
            oauth_service.resolve_access_token_async("google_gemini"),
        )
        assert refresh_posts == 1
        assert tokens == ["ya29.refreshed-v1", "ya29.refreshed-v1", "ya29.refreshed-v1"]

        # Case B: disconnect() while async refresh is in flight MUST NOT resurrect deleted session
        clock.advance(3580.0)
        refresh_entered.clear()
        allow_refresh_finish.clear()
        next_access_token = "ya29.zombie-token"

        inflight_task = asyncio.create_task(
            oauth_service.resolve_access_token_async("google_gemini")
        )
        await refresh_entered.wait()
        oauth_service.disconnect("google_gemini")
        assert store.get_session("google_gemini") is None

        allow_refresh_finish.set()
        zombie_result = await inflight_task
        assert zombie_result == ""
        assert store.get_session("google_gemini") is None

        # Case C: newer login saved while stale refresh is in flight MUST win
        store.save_session(
            OAuthSessionRecord(
                session_id="google_gemini",
                provider="google_gemini",
                access_token="ya29.old-expiring",
                refresh_token="1//old-rt",
                expires_at=clock.now() + 5.0,
                client_id="f3-client.apps.googleusercontent.com",
                connected_at=clock.now(),
                updated_at=clock.now(),
            )
        )
        refresh_entered.clear()
        allow_refresh_finish.clear()
        next_access_token = "ya29.stale-refresh-output"

        stale_task = asyncio.create_task(
            oauth_service.resolve_access_token_async("google_gemini")
        )
        await refresh_entered.wait()
        store.save_session(
            OAuthSessionRecord(
                session_id="google_gemini",
                provider="google_gemini",
                access_token="ya29.fresh-relogin-account",
                refresh_token="1//fresh-relogin-rt",
                expires_at=clock.now() + 3600.0,
                client_id="f3-client.apps.googleusercontent.com",
                connected_at=clock.now(),
                updated_at=clock.now(),
            )
        )
        allow_refresh_finish.set()
        resolved_after_race = await stale_task
        assert resolved_after_race == "ya29.fresh-relogin-account"
        final_session = store.get_session("google_gemini")
        assert final_session is not None
        assert final_session.access_token == "ya29.fresh-relogin-account"
        assert final_session.refresh_token == "1//fresh-relogin-rt"
    finally:
        db.close_all(skip_checkpoint=True)


def test_f4_google_reauth_without_refresh_token_never_inherits_previous_account_token(
    isolated_env: dict[str, Any],
):
    http = isolated_env["make_http_client"]("127.0.0.1")
    store: OAuthCredentialStore = isolated_env["store"]

    store.save_session(
        OAuthSessionRecord(
            session_id="google_gemini",
            provider="google_gemini",
            access_token="ya29.account-a-access",
            refresh_token="1//account-a-secret-refresh",
            expires_at=1_750_003_600.0,
            client_id="google-desktop-client.apps.googleusercontent.com",
            connected_at=1_750_000_000.0,
            updated_at=1_750_000_000.0,
        )
    )

    isolated_env["handler_holder"]["async"] = lambda req: (
        httpx.Response(
            200,
            json={
                "access_token": "ya29.account-b-access",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )
        if str(req.url) == "https://oauth2.googleapis.com/token"
        else httpx.Response(404)
    )

    start = http.post(
        "/api/v1/llm-control/oauth/google/start",
        json={"client_id": "google-desktop-client.apps.googleusercontent.com"},
    )
    state = parse_qs(urlsplit(start.json()["authorize_url"]).query)["state"][0]
    cb = http.get(
        "/api/v1/llm-control/oauth/google/callback",
        params={"code": "4/account-b-code", "state": state},
    )
    assert cb.status_code == 200

    updated = store.get_session("google_gemini")
    assert updated is not None
    assert updated.access_token == "ya29.account-b-access"
    assert updated.refresh_token == ""


def test_masked_secret_path_and_userinfo_origin_binding(
    isolated_env: dict[str, Any],
):
    http = isolated_env["make_http_client"]("127.0.0.1")

    seed = http.put(
        "/api/v1/llm-control",
        json={
            "active_profile_id": "p-tenant",
            "endpoint_mode": "unified",
            "profiles": [
                {
                    "id": "p-tenant",
                    "name": "Tenant A",
                    "preset_key": "custom-openai-compatible",
                    "protocol": "openai",
                    "base_url": "https://gateway.example.com/tenant-a/v1",
                    "api_key": "sk-tenant-a-secret",
                    "model": "gpt-4o",
                }
            ],
        },
    )
    assert seed.status_code == 200
    masked_profile = seed.json()["config"]["profiles"][0]
    assert masked_profile["api_key"] == MASKED_SECRET_SENTINEL

    # Changing path on same host (/tenant-a/v1 -> /tenant-b/v1) with masked secret MUST fail with 400
    cross_path = dict(masked_profile, base_url="https://gateway.example.com/tenant-b/v1")
    assert (
        http.put(
            "/api/v1/llm-control",
            json={"active_profile_id": "p-tenant", "profiles": [cross_path]},
        ).status_code
        == 400
    )

    # Injecting userinfo on same host/path MUST fail with 400
    with_userinfo = dict(
        masked_profile, base_url="https://attacker@gateway.example.com/tenant-a/v1"
    )
    assert (
        http.put(
            "/api/v1/llm-control",
            json={"active_profile_id": "p-tenant", "profiles": [with_userinfo]},
        ).status_code
        == 400
    )


def test_round3_oauth_refresh_slot_generation_validation_prevents_stale_clobber(
    isolated_env: dict[str, Any],
):
    """OAUTH-F3-01: Stale generation callers cannot displace a newer generation's refresh slot."""
    from infrastructure.ai.oauth_credential_store import OAuthSessionRecord

    store = isolated_env["store"]
    oauth_service = isolated_env["oauth_service"]

    g1 = store.save_session(
        OAuthSessionRecord(
            session_id="google_gemini",
            provider="google_gemini",
            access_token="ya29.g1-expired",
            refresh_token="1//g1-refresh",
            expires_at=10.0,
            connected_at=1.0,
            updated_at=1.0,
        )
    )

    # Rotate to g2 (also expired so g2 can legitimately acquire a leader slot)
    g2 = store.save_session(
        OAuthSessionRecord(
            session_id="google_gemini",
            provider="google_gemini",
            access_token="ya29.g2-expired",
            refresh_token="1//g2-refresh",
            expires_at=10.0,
            connected_at=2.0,
            updated_at=2.0,
        )
    )
    assert g2.generation > g1.generation

    state_g2_leader, slot_g2 = store.acquire_refresh_slot_sync(
        "google_gemini", generation=g2.generation
    )
    assert state_g2_leader == "leader"
    assert slot_g2 is not None

    # A delayed caller still holding g1 snapshot MUST return ("stale", None) without touching slot_g2!
    state_stale, slot_stale = store.acquire_refresh_slot_sync(
        "google_gemini", generation=g1.generation
    )
    assert state_stale == "stale"
    assert slot_stale is None

    # Concurrent g2 caller joins as follower on the intact slot_g2!
    state_g2_follower, slot_g2_follow = store.acquire_refresh_slot_sync(
        "google_gemini", generation=g2.generation
    )
    assert state_g2_follower == "follower"
    assert slot_g2_follow is slot_g2

    store.release_refresh_slot("google_gemini", slot_g2)

    # Also verify resolve_access_token_sync handles a stale snapshot cleanly by re-reading g3!
    isolated_env["handler_holder"]["sync"] = lambda req: httpx.Response(
        200,
        json={
            "access_token": "ya29.g3-refreshed",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
    )
    store.save_session(
        OAuthSessionRecord(
            session_id="google_gemini",
            provider="google_gemini",
            access_token="ya29.g3-expired",
            refresh_token="1//g3-refresh",
            client_id="gid.apps.googleusercontent.com",
            expires_at=10.0,
            connected_at=3.0,
            updated_at=3.0,
        )
    )
    resolved_tok = oauth_service.resolve_access_token_sync("google_gemini")
    assert resolved_tok == "ya29.g3-refreshed"


def test_round3_gemini_oauth_bearer_rejects_reserved_auth_query_and_headers():
    """GATEWAY-01: Gemini OAuth Bearer mode rejects extra_query/extra_headers auth overrides."""
    from infrastructure.ai.config.settings import Settings
    from infrastructure.ai.providers.gemini_provider import GeminiProvider

    with pytest.raises(ValueError, match="extra_query"):
        Settings(
            protocol="gemini",
            api_key="ya29.oauth-token",
            default_model="gemini-2.5-pro",
            use_oauth_bearer=True,
            extra_query={"key": "AIza-injected"},
        )

    with pytest.raises(ValueError, match="extra_headers"):
        Settings(
            protocol="gemini",
            api_key="ya29.oauth-token",
            default_model="gemini-2.5-pro",
            use_oauth_bearer=True,
            extra_headers={"Authorization": "Bearer attacker"},
        )

    # Defense in depth: even if mutated after Settings construction, GeminiProvider rejects at build time
    valid_settings = Settings(
        protocol="gemini",
        api_key="ya29.oauth-token",
        default_model="gemini-2.5-pro",
        use_oauth_bearer=True,
    )
    provider = GeminiProvider(valid_settings)
    assert provider._build_query() == {}
    assert provider._build_headers(stream=False)["Authorization"] == "Bearer ya29.oauth-token"

    valid_settings.extra_query["API_KEY"] = "AIza-post-mutation"
    with pytest.raises(ValueError, match="forbids query credential"):
        provider._build_query()
    valid_settings.extra_query.clear()

    valid_settings.extra_headers["x-goog-api-key"] = "AIza-header-mutation"
    with pytest.raises(ValueError, match="forbids authentication header override"):
        provider._build_headers(stream=False)


def test_round3_control_service_credential_header_redaction_and_invalid_origins(
    isolated_env: dict[str, Any],
):
    """CS-01, CS-02, CS-03, CS-04: Credential header rejection/scrubbing, port 0/userinfo origin rejection, and independent main fallback."""
    control: LLMControlService = isolated_env["control_service"]
    db: DatabaseConnection = isolated_env["db"]

    # CS-01: Credential-bearing headers & query params rejected on construction
    with pytest.raises(ValueError, match="extra_headers"):
        LLMProfile(
            id="bad-hdr",
            name="Bad Header",
            protocol="openai",
            api_key="sk-1",
            model="gpt-4o",
            extra_headers={"Authorization": "Bearer leaked-secret"},
        )

    with pytest.raises(ValueError, match="extra_query"):
        LLMProfile(
            id="bad-qry",
            name="Bad Query",
            protocol="gemini",
            api_key="AIza-1",
            model="gemini-2.5-pro",
            extra_query={"api_key": "leaked-query-secret"},
        )

    # CS-01 defense-in-depth: even if legacy DB row or model_copy bypasses validator, redact_profile & _row_to_profile scrub it!
    bypassed = LLMProfile(
        id="p-clean",
        name="Clean",
        protocol="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-dedicated",
        model="gpt-4o",
        extra_headers={"X-Custom-Trace": "ok"},
    )
    bypassed.extra_headers["Authorization"] = "Bearer sneaky"
    bypassed.extra_query["access_token"] = "sneaky-q"
    redacted = control.redact_profile(bypassed)
    assert "Authorization" not in redacted.extra_headers
    assert redacted.extra_headers == {"X-Custom-Trace": "ok"}
    assert "access_token" not in redacted.extra_query

    # CS-02: Equal userinfo URLs, port 0, and malformed ports NEVER compare equal or authorize masked secret reuse!
    p_existing_bad = LLMProfile(
        id="p-bad-url",
        name="Bad URL",
        protocol="openai",
        base_url="https://user:pass@api.example.com/v1",
        api_key="sk-stored",
        model="gpt-4o",
    )
    p_cand_bad = p_existing_bad.model_copy(update={"api_key": MASKED_SECRET_SENTINEL})
    assert control._credential_origin(p_existing_bad) is None
    assert control._same_credential_target(p_existing_bad, p_cand_bad) is False
    with pytest.raises(ValueError):
        control.assert_masked_secret_target_matches(p_existing_bad, p_cand_bad)

    p_default_port = LLMProfile(
        id="p-port",
        name="Default Port",
        protocol="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-port",
        model="gpt-4o",
    )
    p_zero_port = p_default_port.model_copy(
        update={"base_url": "https://api.example.com:0/v1", "api_key": MASKED_SECRET_SENTINEL}
    )
    assert control._credential_origin(p_zero_port) is None
    with pytest.raises(ValueError):
        control.assert_masked_secret_target_matches(p_default_port, p_zero_port)

    # CS-03: Independent secondary fallback uses role_bindings['main'] even when active_profile_id differs or fails!
    broken_active = LLMProfile(
        id="broken-active",
        name="Broken Active",
        protocol="openai",
        base_url="http://127.0.0.1:3425/v1",
        model="gpt-4o",
        auth_mode="oauth",
        oauth_provider="openrouter",
        oauth_session_id="google_gemini",  # Intentionally mismatched so resolving active raises!
    )
    bound_main = LLMProfile(
        id="bound-main",
        name="Bound Main",
        protocol="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-bound-main",
        model="gpt-4.1",
        auth_mode="api_key",
    )
    ind_cfg = LLMControlConfig(
        active_profile_id="broken-active",
        endpoint_mode="independent",
        role_bindings={"main": "bound-main"},
        profiles=[broken_active, bound_main],
    )
    assert control.resolve_role_profile("main", ind_cfg).id == "bound-main"
    assert control.resolve_role_profile("cheap", ind_cfg).id == "bound-main"
    assert control.resolve_role_profile("kg", ind_cfg).id == "bound-main"

    # CS-04: Masked save rejects if concurrent save rotated auth_mode or deleted profile before lock acquisition
    control.save_config(
        LLMControlConfig(
            active_profile_id="p-port",
            endpoint_mode="unified",
            profiles=[p_default_port],
        )
    )
    # Rotate p-port to local_gateway in DB, then attempt stale masked api_key save -> rejected!
    control.save_config(
        LLMControlConfig(
            active_profile_id="p-port",
            endpoint_mode="unified",
            profiles=[
                LLMProfile(
                    id="p-port",
                    name="Rotated Gateway",
                    protocol="openai",
                    base_url="http://127.0.0.1:3425/v1",
                    model="claude/claude-opus-5-5",
                    auth_mode="local_gateway",
                )
            ],
        )
    )
    stale_masked_candidate = p_default_port.model_copy(
        update={"api_key": MASKED_SECRET_SENTINEL}
    )
    with pytest.raises(ValueError, match="API Key"):
        control.save_config(
            LLMControlConfig(
                active_profile_id="p-port",
                endpoint_mode="unified",
                profiles=[stale_masked_candidate],
            )
        )
    assert db is not None


@pytest.mark.asyncio
async def test_round4_openai_responses_kwargs_never_promote_nested_extra_body_auth():
    """GATEWAY-R3-01: OpenAIProvider._build_responses_request_kwargs keeps extra_body nested and never promotes nested extra_headers / extra_query into top-level SDK kwargs."""
    from domain.ai.services.llm_service import GenerationConfig
    from domain.ai.value_objects.prompt import Prompt
    from infrastructure.ai.providers.openai_provider import OpenAIProvider, Settings

    settings = Settings(
        api_key="oauth-bearer-token-safe",
        base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-4.1",
        use_oauth_bearer=True,
        extra_headers={"X-Safe-Trace": "1"},
        extra_body={
            "extra_headers": {"Authorization": "Bearer evil-override"},
            "extra_query": {"key": "evil-query-key"},
            "reasoning": {"effort": "medium"},
        },
    )
    provider = OpenAIProvider(settings=settings)
    try:
        kwargs = provider._build_responses_request_kwargs(
            Prompt(system="sys", user="hello"),
            GenerationConfig(model="openai/gpt-4.1", max_tokens=256),
            stream=False,
        )
        assert kwargs.get("extra_headers") == {"X-Safe-Trace": "1"}
        assert kwargs.get("extra_query") is None
        assert "reasoning" not in kwargs
        assert kwargs["extra_body"] == {
            "extra_headers": {"Authorization": "Bearer evil-override"},
            "extra_query": {"key": "evil-query-key"},
            "reasoning": {"effort": "medium"},
        }
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_round5_openai_generate_via_stream_closes_stream_on_mid_iteration_error_and_gemini_splits_crlf():
    """GATEWAY-R4-01 & GATEWAY-R4-02: OpenAI _generate_via_stream guarantees stream.close() on iteration error, and Gemini stream_generate parses CRLF split across chunk boundaries."""
    from domain.ai.services.llm_service import GenerationConfig
    from domain.ai.value_objects.prompt import Prompt
    from infrastructure.ai.providers.gemini_provider import GeminiProvider
    from infrastructure.ai.providers.openai_provider import OpenAIProvider, Settings as OpenAISettings
    from infrastructure.ai.config.settings import Settings as GeminiSettings

    # 1. GATEWAY-R4-01: _generate_via_stream closes stream when iteration raises
    oa_settings = OpenAISettings(
        api_key="sk-test-key",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4.1",
    )
    oa_provider = OpenAIProvider(settings=oa_settings)
    closed_flag = False

    class _FailingStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise RuntimeError("mid-stream boom")

        async def close(self):
            nonlocal closed_flag
            closed_flag = True

    async def _fake_create(**kwargs):
        return _FailingStream()

    oa_provider.async_client.chat.completions.create = _fake_create  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="mid-stream boom"):
            await oa_provider._generate_via_stream({"model": "gpt-4.1", "messages": []})
        assert closed_flag is True
    finally:
        await oa_provider.aclose()

    # 2. GATEWAY-R4-02: Gemini stream_generate preserves SSE events when CRLF is split across chunks
    chunks_to_send = [
        'data: {"candidates":[{"content":{"parts":[{"text":"潮水"}]}}]}\r',
        '\n\r',
        '\ndata: {"candidates":[{"content":{"parts":[{"text":"退去"}]}}]}\r',
        '\n\r',
        '\n',
    ]

    class _MockByteStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for piece in chunks_to_send:
                yield piece.encode("utf-8")

        async def aclose(self) -> None:
            pass

    def _gemini_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=_MockByteStream(),
        )

    gem_client = httpx.AsyncClient(transport=httpx.MockTransport(_gemini_handler))
    gem_provider = GeminiProvider(
        settings=GeminiSettings(
            api_key="ya29.test-oauth",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            default_model="gemini-2.5-pro",
            use_oauth_bearer=True,
        ),
    )
    old_gem_client = gem_provider._http_client
    gem_provider._http_client = gem_client
    try:
        emitted: list[str] = []
        async for piece in gem_provider.stream_generate(
            Prompt(system="sys", user="hi"),
            GenerationConfig(model="gemini-2.5-pro"),
        ):
            emitted.append(piece)
        assert "".join(emitted) == "潮水退去"
    finally:
        await old_gem_client.aclose()
        await gem_provider.aclose()


@pytest.mark.asyncio
async def test_round6_gemini_sse_error_scalars_and_control_service_concurrency_and_redaction(
    tmp_path: Path,
):
    """Verify GATEWAY-R5-01, CC-R5-01, CC-R5-02, R5-CT-01, and R5-CT-02."""
    import sqlite3
    from application.ai.llm_control_service import (
        LLMControlConfig,
        LLMControlService,
        LLMProfile,
        _validate_and_split_origin_url,
    )
    from application.ai.local_gateway_probe import validate_loopback_gateway_url
    from domain.ai.services.llm_service import GenerationConfig
    from domain.ai.value_objects.prompt import Prompt
    from infrastructure.ai.config.settings import Settings as GeminiSettings
    from infrastructure.ai.providers.gemini_provider import GeminiProvider

    # 1. GATEWAY-R5-01: Gemini SSE error events raise across all JSON types, empty data, and [DONE]
    gem_provider = GeminiProvider(
        settings=GeminiSettings(
            api_key="ya29.r6-oauth",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            default_model="gemini-2.5-pro",
            use_oauth_bearer=True,
        )
    )
    try:
        for raw_err_evt in [
            'event: error\ndata: "quota exhausted"',
            "event: error\ndata: []",
            "event: error\ndata: null",
            "event: error\ndata: [DONE]",
            "event: error\ndata:",
            "event: error\ndata: not-json",
        ]:
            with pytest.raises(RuntimeError, match="Gemini SSE error"):
                gem_provider._parse_sse_event(raw_err_evt)

        class _ErrTailStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"candidates":[{"content":{"parts":[{"text":"first"}]}}]}\n\n'
                yield b'event: error\ndata: "quota exhausted"'

            async def aclose(self) -> None:
                pass

        err_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    headers={"Content-Type": "text/event-stream"},
                    stream=_ErrTailStream(),
                )
            )
        )
        old_c = gem_provider._http_client
        gem_provider._http_client = err_client
        try:
            seen: list[str] = []
            with pytest.raises(RuntimeError, match="Gemini SSE error: quota exhausted"):
                async for part in gem_provider.stream_generate(
                    Prompt(system="s", user="u"),
                    GenerationConfig(model="gemini-2.5-pro"),
                ):
                    seen.append(part)
            assert seen == ["first"]
        finally:
            await old_c.aclose()
    finally:
        await gem_provider.aclose()

    # 2. CC-R5-01 & urlsplit secret non-echoing
    assert _validate_and_split_origin_url("https://[::1/v1") is None
    assert _validate_and_split_origin_url("https://example.com\uff1a443/v1") is None
    with pytest.raises(ValueError) as gw_exc:
        validate_loopback_gateway_url("http://alice:ultra-secret-pw@localhost\uff1a3425/v1")
    assert "ultra-secret-pw" not in str(gw_exc.value)

    # 3. CC-R5-02: Legacy stored row with credential-bearing URL is scrubbed in redacted panel + runtime
    db_path = tmp_path / "r6.db"
    db = DatabaseConnection(str(db_path))
    control = LLMControlService(db_provider=lambda: db)
    try:
        # First initialize schema/tables
        _ = control.get_config()
        conn = db.get_connection()
        conn.execute("DELETE FROM llm_profiles")
        conn.execute("DELETE FROM llm_config_meta")
        conn.execute(
            """INSERT INTO llm_profiles (
                id, name, preset_key, protocol, base_url, api_key, model,
                temperature, max_tokens, timeout_seconds,
                extra_headers, extra_query, extra_body, notes,
                use_legacy_chat_completions, auth_mode, oauth_provider, oauth_session_id, sort_order
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "legacy-cred-url",
                "Legacy Row",
                "custom-openai-compatible",
                "openai",
                "https://alice:example-password@api.example/v1?api_key=example-secret",
                "sk-legacy-secret",
                "gpt-4.1",
                0.7,
                8192,
                120,
                "{}",
                "{}",
                "{}",
                "",
                0,
                "api_key",
                "",
                "",
                0,
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO llm_config_meta (key, value) VALUES (?, ?)",
            ("active_profile_id", "legacy-cred-url"),
        )
        conn.commit()

        redacted_panel = control.get_control_panel_data(redact_secrets=True)
        dumped = redacted_panel.model_dump_json()
        assert "example-password" not in dumped
        assert "example-secret" not in dumped
        assert "sk-legacy-secret" not in dumped
        assert redacted_panel.config.profiles[0].base_url == ""
        assert redacted_panel.runtime.base_url is None

        # 4. R5-CT-01: Empty initial observation does NOT overwrite a concurrently saved profile
        conn.execute("DELETE FROM llm_profiles")
        conn.execute("DELETE FROM llm_config_meta")
        conn.commit()

        orig_read = control._read_snapshot_from_conn
        call_idx = 0

        def _interleaved_read(c):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                # Simulate initial read seeing empty table, right before writer B commits
                ext_conn = sqlite3.connect(str(db_path))
                try:
                    ext_conn.execute(
                        """INSERT INTO llm_profiles (
                            id, name, preset_key, protocol, base_url, api_key, model,
                            temperature, max_tokens, timeout_seconds,
                            extra_headers, extra_query, extra_body, notes,
                            use_legacy_chat_completions, auth_mode, oauth_provider, oauth_session_id, sort_order
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            "writer-b-profile",
                            "Writer B",
                            "custom-openai-compatible",
                            "openai",
                            "https://api.openai.com/v1",
                            "sk-writer-b-key",
                            "gpt-4.1",
                            0.7,
                            8192,
                            120,
                            "{}",
                            "{}",
                            "{}",
                            "",
                            0,
                            "api_key",
                            "",
                            "",
                            0,
                        ),
                    )
                    ext_conn.execute(
                        "INSERT OR REPLACE INTO llm_config_meta (key, value) VALUES (?, ?)",
                        ("active_profile_id", "writer-b-profile"),
                    )
                    ext_conn.commit()
                finally:
                    ext_conn.close()
                return ([], {}, {})
            return orig_read(c)

        control._read_snapshot_from_conn = _interleaved_read  # type: ignore[method-assign]
        try:
            loaded_cfg = control.get_config()
            assert [p.id for p in loaded_cfg.profiles] == ["writer-b-profile"]
            assert loaded_cfg.profiles[0].api_key == "sk-writer-b-key"
        finally:
            control._read_snapshot_from_conn = orig_read  # type: ignore[method-assign]

        # 5. R5-CT-02: apply_golden_role_routing reads latest committed key inside BEGIN IMMEDIATE
        ext_conn2 = sqlite3.connect(str(db_path))
        try:
            ext_conn2.execute(
                "UPDATE llm_profiles SET api_key = ? WHERE id = ?",
                ("sk-rotated-fresh", "writer-b-profile"),
            )
            ext_conn2.commit()
        finally:
            ext_conn2.close()

        golden_cfg = control.apply_golden_role_routing(
            source_profile_id="writer-b-profile",
            main_model="gpt-4.1",
            cheap_model="gpt-4.1-mini",
            kg_model="gpt-4.1-nano",
        )
        by_id = {p.id: p for p in golden_cfg.profiles}
        assert by_id["writer-b-profile"].api_key == "sk-rotated-fresh"
        assert by_id["golden-role-main"].api_key == "sk-rotated-fresh"
        assert by_id["golden-role-cheap"].api_key == "sk-rotated-fresh"
        assert by_id["golden-role-kg"].api_key == "sk-rotated-fresh"
    finally:
        db.close_all(skip_checkpoint=True)


@pytest.mark.asyncio
async def test_round7_openai_responses_terminal_failures_and_post_output_fallback_guard():
    """GATEWAY-R6-01 & GATEWAY-R6-02:
    1) Responses terminal failure/incomplete/error events raise RuntimeError (both after partial output and without text),
       without triggering Chat Completions fallback or poisoning _fallback_to_chat_cache.
    2) Pre-output protocol-unsupported 400/404 still falls back to Chat Completions cleanly.
    3) Post-output exception (even containing '400'/'404' or BadRequestError) closes the stream and propagates failure
       without starting a second Chat Completions generation or poisoning _fallback_to_chat_cache.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from domain.ai.services.llm_service import GenerationConfig
    from domain.ai.value_objects.prompt import Prompt
    from infrastructure.ai.config.settings import Settings
    from infrastructure.ai.providers.openai_provider import OpenAIProvider

    class _ClosableAsyncStream:
        def __init__(self, items, *, tail_error: Exception | None = None):
            self._items = iter(items)
            self._tail_error = tail_error
            self.closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._items)
            except StopIteration as exc:
                if self._tail_error is not None:
                    err = self._tail_error
                    self._tail_error = None
                    raise err
                raise StopAsyncIteration from exc

        async def close(self):
            self.closed = True

    prompt = Prompt(system="sys", user="hello")
    cfg = GenerationConfig(model="gpt-4.1", temperature=0.2, max_tokens=128)

    # 1. Partial text followed by response.failed -> raises RuntimeError, closes stream, zero chat fallback
    url_failed = "https://r7-failed.example/v1"
    OpenAIProvider._fallback_to_chat_cache.discard(url_failed)
    provider_failed = OpenAIProvider(Settings(api_key="sk-test", base_url=url_failed))
    failed_stream = _ClosableAsyncStream(
        [
            SimpleNamespace(type="response.output_text.delta", delta="partial"),
            SimpleNamespace(
                type="response.failed",
                response=SimpleNamespace(
                    status="failed",
                    error=SimpleNamespace(code="400_upstream", message="upstream exploded"),
                ),
            ),
        ]
    )
    with (
        patch.object(provider_failed.async_client.responses, "create", new_callable=AsyncMock) as mock_resp,
        patch.object(provider_failed.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_chat,
    ):
        mock_resp.return_value = failed_stream
        emitted: list[str] = []
        with pytest.raises(RuntimeError, match="response.failed"):
            async for chunk in provider_failed.stream_generate(prompt, cfg):
                emitted.append(chunk)
        assert emitted == ["partial"]
        assert failed_stream.closed is True
        assert mock_chat.await_count == 0
        assert url_failed not in OpenAIProvider._fallback_to_chat_cache

    # 2. Failure-only stream & response.incomplete stream -> raises RuntimeError without chat fallback
    for term_chunk, expected_match in [
        (
            SimpleNamespace(
                type="response.failed",
                response=SimpleNamespace(status="failed", error={"message": "404 backend"}),
            ),
            "response.failed",
        ),
        (
            SimpleNamespace(
                type="response.incomplete",
                response=SimpleNamespace(
                    status="incomplete",
                    incomplete_details=SimpleNamespace(reason="max_output_tokens"),
                ),
            ),
            "incomplete",
        ),
        (
            {"type": "error", "message": "400 stream error"},
            "event=error",
        ),
    ]:
        s = _ClosableAsyncStream([term_chunk])
        with (
            patch.object(provider_failed.async_client.responses, "create", new_callable=AsyncMock) as mock_resp,
            patch.object(provider_failed.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_chat,
        ):
            mock_resp.return_value = s
            with pytest.raises(RuntimeError, match=expected_match):
                _ = [c async for c in provider_failed.stream_generate(prompt, cfg)]
            assert s.closed is True
            assert mock_chat.await_count == 0
            assert url_failed not in OpenAIProvider._fallback_to_chat_cache

    # 3. Post-output exception containing '400' MUST NOT trigger second generation via Chat Completions
    url_mid_err = "https://r7-midstream-err.example/v1"
    OpenAIProvider._fallback_to_chat_cache.discard(url_mid_err)
    provider_mid = OpenAIProvider(Settings(api_key="sk-test", base_url=url_mid_err))
    mid_stream = _ClosableAsyncStream(
        [SimpleNamespace(type="response.output_text.delta", delta="first answer")],
        tail_error=RuntimeError("400 gateway failure"),
    )
    with (
        patch.object(provider_mid.async_client.responses, "create", new_callable=AsyncMock) as mock_resp,
        patch.object(provider_mid.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_chat,
    ):
        mock_resp.return_value = mid_stream
        emitted_mid: list[str] = []
        with pytest.raises(RuntimeError, match="interrupted after partial output"):
            async for chunk in provider_mid.stream_generate(prompt, cfg):
                emitted_mid.append(chunk)
        assert emitted_mid == ["first answer"]
        assert mid_stream.closed is True
        assert mock_chat.await_count == 0
        assert url_mid_err not in OpenAIProvider._fallback_to_chat_cache

    # 4. Pre-output 404/400 error STILL falls back to Chat Completions cleanly
    url_pre_fallback = "https://r7-preoutput-fallback.example/v1"
    OpenAIProvider._fallback_to_chat_cache.discard(url_pre_fallback)
    provider_pre = OpenAIProvider(Settings(api_key="sk-test", base_url=url_pre_fallback))
    chat_stream = _ClosableAsyncStream(
        [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="chat fallback ok"))])]
    )
    with (
        patch.object(
            provider_pre.async_client.responses,
            "create",
            new_callable=AsyncMock,
            side_effect=RuntimeError("404 Not Found"),
        ),
        patch.object(
            provider_pre.async_client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=chat_stream,
        ) as mock_chat,
    ):
        out = [c async for c in provider_pre.stream_generate(prompt, cfg)]
        assert out == ["chat fallback ok"]
        assert mock_chat.await_count == 1
        assert url_pre_fallback in OpenAIProvider._fallback_to_chat_cache
    OpenAIProvider._fallback_to_chat_cache.discard(url_pre_fallback)


def test_round7_legacy_schema_migration_rejects_caller_transaction_without_committing(
    tmp_path: Path,
):
    """R6-CT-01:
    When llm_profiles lacks OAuth columns (legacy schema) and the caller already holds an uncommitted
    transaction on conn, get_config / save_config / apply_golden_role_routing on a fresh LLMControlService
    must raise RuntimeError BEFORE executing DDL or committing the caller's pending work.
    Caller rollback must remove the pending marker row, and subsequent migration without an active
    caller transaction must succeed cleanly.
    """
    from infrastructure.persistence.database.connection import DatabaseConnection

    db_path = tmp_path / "r7_legacy_schema.db"
    db = DatabaseConnection(str(db_path))
    try:
        conn = db.get_connection()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS caller_marker (id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS llm_config_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            DROP TABLE IF EXISTS llm_profiles;
            CREATE TABLE llm_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                preset_key TEXT NOT NULL,
                protocol TEXT NOT NULL,
                base_url TEXT NOT NULL DEFAULT '',
                api_key TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                temperature REAL NOT NULL DEFAULT 0.7,
                max_tokens INTEGER NOT NULL DEFAULT 8192,
                timeout_seconds INTEGER NOT NULL DEFAULT 120,
                extra_headers TEXT NOT NULL DEFAULT '{}',
                extra_query TEXT NOT NULL DEFAULT '{}',
                extra_body TEXT NOT NULL DEFAULT '{}',
                notes TEXT NOT NULL DEFAULT '',
                use_legacy_chat_completions INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()

        fresh_service = LLMControlService(db_provider=lambda: db)
        assert fresh_service._schema_checked is False

        # Start a caller-owned uncommitted transaction with a pending marker row
        conn.execute("BEGIN")
        conn.execute("INSERT INTO caller_marker (id) VALUES ('must-not-commit')")
        assert conn.in_transaction is True

        # Entry via get_config(), save_config(), and apply_golden_role_routing() must all reject
        with pytest.raises(RuntimeError, match="未提交事务"):
            fresh_service.get_config()
        assert fresh_service._schema_checked is False
        assert conn.in_transaction is True

        with pytest.raises(RuntimeError, match="未提交事务"):
            fresh_service.save_config(
                LLMControlConfig(
                    active_profile_id="p1",
                    endpoint_mode="unified",
                    profiles=[
                        LLMProfile(
                            id="p1",
                            name="P1",
                            preset_key="openai-official",
                            protocol="openai",
                            api_key="sk-1",
                            model="gpt-4o",
                        )
                    ],
                )
            )
        assert fresh_service._schema_checked is False
        assert conn.in_transaction is True

        with pytest.raises(RuntimeError, match="未提交事务"):
            fresh_service.apply_golden_role_routing(
                source_profile_id="p1",
                main_model="gpt-4o",
            )
        assert fresh_service._schema_checked is False
        assert conn.in_transaction is True

        # Roll back caller transaction -> marker row MUST be gone (proving zero premature commit!)
        conn.rollback()
        marker_rows = conn.execute("SELECT id FROM caller_marker").fetchall()
        assert marker_rows == []

        # Now without an active caller transaction, the same fresh_service migrates cleanly and initializes!
        initialized = fresh_service.get_config()
        assert fresh_service._schema_checked is True
        assert len(initialized.profiles) >= 1
        migrated_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(llm_profiles)").fetchall()
        }
        assert {"auth_mode", "oauth_provider", "oauth_session_id"}.issubset(migrated_cols)
    finally:
        db.close_all(skip_checkpoint=True)


@pytest.mark.asyncio
async def test_round8_responses_cleanup_preserves_terminal_error_and_gemini_array_sse_errors():
    """GATEWAY-R7-01 & GATEWAY-R7-02:
    1) When a Responses stream raises a terminal error (both before and after outward text) AND close()
       raises an exception containing '404'/'400', the primary terminal exception is preserved and neither
       Chat Completions fallback nor _fallback_to_chat_cache poisoning occurs; cleanup-only errors after
       normal exhaustion also raise without triggering protocol fallback.
    2) GeminiProvider._parse_sse_event / stream_generate raises RuntimeError on array-form SSE error payloads
       (error-only array, mixed candidate+error array, and array error following earlier candidate text).
    """
    import httpx
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from domain.ai.services.llm_service import GenerationConfig
    from domain.ai.value_objects.prompt import Prompt
    from infrastructure.ai.config.settings import Settings
    from infrastructure.ai.providers.openai_provider import OpenAIProvider

    class _CleanupFailingStream:
        def __init__(self, chunks, *, close_exc: Exception):
            self._chunks = iter(chunks)
            self._close_exc = close_exc
            self.close_called = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def close(self):
            self.close_called = True
            raise self._close_exc

    prompt = Prompt(system="sys", user="hi")
    cfg = GenerationConfig(model="gpt-4.1", temperature=0.2, max_tokens=64)

    # 1a. Pre-output response.failed + close() raising RuntimeError('404 during stream cleanup')
    url_r8 = "https://r8-cleanup-guard.example/v1"
    OpenAIProvider._fallback_to_chat_cache.discard(url_r8)
    provider = OpenAIProvider(Settings(api_key="sk-test", base_url=url_r8))
    s_pre = _CleanupFailingStream(
        [
            {
                "type": "response.failed",
                "response": {"status": "failed", "error": {"message": "generation failed"}},
            }
        ],
        close_exc=RuntimeError("404 during stream cleanup"),
    )
    with (
        patch.object(provider.async_client.responses, "create", new_callable=AsyncMock, return_value=s_pre),
        patch.object(provider.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_chat,
    ):
        with pytest.raises(RuntimeError, match="generation failed"):
            _ = [c async for c in provider.stream_generate(prompt, cfg)]
        assert s_pre.close_called is True
        assert mock_chat.await_count == 0
        assert url_r8 not in OpenAIProvider._fallback_to_chat_cache

    # 1b. Post-output response.failed + close() raising RuntimeError('404 during stream cleanup')
    s_post = _CleanupFailingStream(
        [
            SimpleNamespace(type="response.output_text.delta", delta="partial"),
            {
                "type": "response.failed",
                "response": {"status": "failed", "error": {"message": "post-output terminal fail"}},
            },
        ],
        close_exc=RuntimeError("404 during stream cleanup"),
    )
    with (
        patch.object(provider.async_client.responses, "create", new_callable=AsyncMock, return_value=s_post),
        patch.object(provider.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_chat,
    ):
        collected: list[str] = []
        with pytest.raises(RuntimeError, match="post-output terminal fail"):
            async for c in provider.stream_generate(prompt, cfg):
                collected.append(c)
        assert collected == ["partial"]
        assert s_post.close_called is True
        assert mock_chat.await_count == 0
        assert url_r8 not in OpenAIProvider._fallback_to_chat_cache

    # 1c. Normal completion + close() raising RuntimeError('404 during stream cleanup') -> no fallback!
    s_clean_err = _CleanupFailingStream(
        [SimpleNamespace(type="response.completed")],
        close_exc=RuntimeError("404 during stream cleanup"),
    )
    with (
        patch.object(provider.async_client.responses, "create", new_callable=AsyncMock, return_value=s_clean_err),
        patch.object(provider.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_chat,
    ):
        with pytest.raises(RuntimeError, match="stream cleanup failed"):
            _ = [c async for c in provider.stream_generate(prompt, cfg)]
        assert s_clean_err.close_called is True
        assert mock_chat.await_count == 0
        assert url_r8 not in OpenAIProvider._fallback_to_chat_cache

    # 2. Gemini array-form SSE error payloads
    gemini = GeminiProvider(Settings(api_key="gem-key", default_model="gemini-2.5-flash"))
    # Error-only array
    with pytest.raises(RuntimeError, match="upstream failed"):
        gemini._parse_sse_event('data: [{"error":{"code":503,"message":"upstream failed","status":"UNAVAILABLE"}}]')
    # Mixed candidate + error array
    with pytest.raises(RuntimeError, match="mixed failure"):
        gemini._parse_sse_event(
            'data: [{"candidates":[{"content":{"parts":[{"text":"partial"}]}}]},{"error":{"code":500,"message":"mixed failure"}}]'
        )
    # Full stream_generate: candidate SSE event followed by array error SSE event -> raises RuntimeError & closes response
    sse_wire = (
        'data: {"candidates":[{"content":{"parts":[{"text":"partial"}]}}]}\n\n'
        'data: [{"error":{"code":503,"message":"array tail failure","status":"UNAVAILABLE"}}]\n\n'
    )
    gemini._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                text=sse_wire,
            )
        )
    )
    try:
        got_chunks: list[str] = []
        with pytest.raises(RuntimeError, match="array tail failure"):
            async for piece in gemini.stream_generate(prompt, cfg):
                got_chunks.append(piece)
        assert got_chunks == ["partial"]
    finally:
        await gemini._http_client.aclose()







