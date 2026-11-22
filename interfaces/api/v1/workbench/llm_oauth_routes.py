"""OAuth 2.0 PKCE / Device Flow, loopback local subscription gateway, & L3 role routing API."""
from __future__ import annotations

import html
import ipaddress
import json
import logging
from typing import List
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from application.ai.llm_control_service import LLMControlPanelData, LLMControlService
from application.ai.llm_oauth_service import (
    LLMOAuthService,
    OAuthConfigurationError,
    OAuthDevicePollResult,
    OAuthDeviceStartResult,
    OAuthFlowError,
    OAuthPKCEStartResult,
    OAuthStatusResponse,
    OAuthUpstreamError,
)
from application.ai.local_gateway_probe import (
    ALLOWED_LOOPBACK_HOSTNAMES,
    LocalGatewayProbeResult,
    LocalGatewayProbeService,
    RoleModelRecommendation,
    recommend_role_models,
)
from interfaces.api.settings import API_V1_PREFIX
from interfaces.api.v1.workbench.llm_control import (
    _invalidate_llm_panel_cache,
    _service as _default_control_service,
    assert_loopback_request,
    get_llm_control_service_dep,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/llm-control",
    tags=["llm-control"],
    dependencies=[Depends(assert_loopback_request)],
)

_default_oauth_service = LLMOAuthService(control_service=_default_control_service)
_default_gateway_probe_service = LocalGatewayProbeService(
    control_service=_default_control_service
)

OAUTH_CALLBACK_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"
)


def get_llm_oauth_service() -> LLMOAuthService:
    return _default_oauth_service


def get_local_gateway_probe_service() -> LocalGatewayProbeService:
    return _default_gateway_probe_service


# ── Request Models ──────────────────────────────────────────────────────


class OAuthOpenRouterStartRequest(BaseModel):
    callback_origin: str = ""


class OAuthGitHubDeviceStartRequest(BaseModel):
    client_id: str = ""


class OAuthGitHubDevicePollRequest(BaseModel):
    flow_id: str


class OAuthGoogleStartRequest(BaseModel):
    client_id: str = ""
    client_secret: str = ""
    callback_origin: str = ""


class LocalGatewayProbeRequest(BaseModel):
    custom_url: str = ""


class LocalGatewayConnectRequest(BaseModel):
    base_url: str = "http://127.0.0.1:3425/v1"
    name: str = "Magpie 订阅网关"
    main_model: str
    cheap_model: str = ""
    kg_model: str = ""
    enable_golden_roles: bool = True
    use_legacy_chat_completions: bool = True


class RoleRoutingRecommendRequest(BaseModel):
    models: List[str] = Field(default_factory=list)
    source_profile_id: str = ""


class ApplyGoldenRoleRoutingRequest(BaseModel):
    source_profile_id: str = ""
    main_model: str
    cheap_model: str = ""
    kg_model: str = ""


# ── Loopback Callback Builder & Xuan-Paper Callback HTML ────────────────


def _extract_safe_loopback_origin(raw_origin: str) -> str:
    candidate = (raw_origin or "").strip()
    if not candidate:
        return ""
    parsed = urlsplit(candidate)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return ""
    if parsed.username is not None or parsed.password is not None:
        return ""
    if parsed.query or parsed.fragment or (parsed.path and parsed.path != "/"):
        return ""
    hostname = (parsed.hostname or "").strip().lower()
    if hostname not in ALLOWED_LOOPBACK_HOSTNAMES:
        return ""
    if hostname != "localhost":
        try:
            ip_obj = ipaddress.ip_address(hostname)
            if not ip_obj.is_loopback or ip_obj.is_unspecified:
                return ""
        except ValueError:
            return ""
    try:
        port = parsed.port
    except ValueError:
        return ""
    if port is None or not (1024 <= port <= 65535):
        return ""
    host_fmt = f"[{hostname}]" if ":" in hostname else hostname
    return f"{scheme}://{host_fmt}:{port}"


def _build_loopback_callback_url(
    request: Request,
    callback_subpath: str,
    callback_origin: str = "",
) -> str:
    safe_origin = _extract_safe_loopback_origin(callback_origin)
    if not safe_origin:
        req_host = (request.url.hostname or "127.0.0.1").strip().lower()
        host = req_host if req_host in ALLOWED_LOOPBACK_HOSTNAMES else "127.0.0.1"
        host_fmt = f"[{host}]" if ":" in host else host
        scheme = "https" if (request.url.scheme or "").lower() == "https" else "http"
        port = request.url.port
        safe_origin = f"{scheme}://{host_fmt}:{port}" if port else f"{scheme}://{host_fmt}"

    return f"{safe_origin}{API_V1_PREFIX}/llm-control{callback_subpath}"


def _render_oauth_callback_html(
    *,
    provider: str,
    title: str,
    ok: bool,
    detail_message: str,
    status_code: int = 200,
) -> HTMLResponse:
    safe_title = html.escape(title)
    safe_message = html.escape(detail_message)
    badge_text = "授权已就绪" if ok else "授权未完成"
    accent = "#1f5e5b" if ok else "#a33b2e"
    js_payload = json.dumps(
        {
            "type": "plotpilot-oauth-complete",
            "provider": provider,
            "ok": bool(ok),
        },
        ensure_ascii=False,
    )

    document = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>墨枢 · {safe_title}</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f4f4f2;
      color: #161615;
      font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    }}
    .card {{
      max-width: 440px;
      width: calc(100% - 32px);
      background: #ffffff;
      border-top: 2px solid {accent};
      border-radius: 6px;
      padding: 28px 26px;
    }}
    .badge {{
      display: inline-block;
      font-size: 12px;
      padding: 2px 8px;
      border-radius: 4px;
      color: #ffffff;
      background: {accent};
      margin-bottom: 12px;
    }}
    h1 {{
      font-size: 20px;
      margin: 0 0 10px;
      font-weight: 600;
    }}
    p {{
      font-size: 14px;
      line-height: 1.65;
      color: #52524e;
      margin: 0 0 16px;
      max-width: 52ch;
    }}
    .hint {{
      font-size: 13px;
      color: #6e6e6a;
      border-top: 1px solid #e6e5e0;
      padding-top: 12px;
    }}
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">{badge_text}</span>
    <h1>{safe_title}</h1>
    <p>{safe_message}</p>
    <div class="hint">令牌已安全封存于本机内核（0600），可关闭此窗口返回墨枢。</div>
  </div>
  <script>
    (function () {{
      var msg = {js_payload};
      if (window.opener && !window.opener.closed) {{
        try {{
          window.opener.postMessage(msg, window.location.origin);
        }} catch (_) {{}}
      }}
    }})();
  </script>
</body>
</html>"""

    return HTMLResponse(
        content=document,
        status_code=status_code,
        headers={
            "Content-Security-Policy": OAUTH_CALLBACK_CSP,
            "Cache-Control": "no-store",
            "X-Frame-Options": "DENY",
        },
    )


# ── OAuth Status & Disconnect ───────────────────────────────────────────


@router.get("/oauth/status", response_model=OAuthStatusResponse)
async def get_oauth_status(
    oauth_service: LLMOAuthService = Depends(get_llm_oauth_service),
) -> OAuthStatusResponse:
    return oauth_service.get_status()


@router.delete("/oauth/{provider}", response_model=OAuthStatusResponse)
async def disconnect_oauth_provider(
    provider: str,
    oauth_service: LLMOAuthService = Depends(get_llm_oauth_service),
) -> OAuthStatusResponse:
    try:
        result = oauth_service.disconnect(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _invalidate_llm_panel_cache()
    return result


# ── OpenRouter PKCE ─────────────────────────────────────────────────────


@router.post("/oauth/openrouter/start", response_model=OAuthPKCEStartResult)
async def start_openrouter_oauth(
    request: Request,
    payload: OAuthOpenRouterStartRequest = Body(
        default_factory=OAuthOpenRouterStartRequest
    ),
    oauth_service: LLMOAuthService = Depends(get_llm_oauth_service),
) -> OAuthPKCEStartResult:
    redirect_uri = _build_loopback_callback_url(
        request,
        "/oauth/openrouter/callback",
        payload.callback_origin,
    )
    return oauth_service.start_openrouter_pkce(redirect_uri)


@router.get("/oauth/openrouter/callback", response_class=HTMLResponse)
async def callback_openrouter_oauth(
    code: str = "",
    state: str = "",
    error: str = "",
    oauth_service: LLMOAuthService = Depends(get_llm_oauth_service),
) -> HTMLResponse:
    if error:
        if state:
            try:
                oauth_service.credential_store.consume_pkce_state("openrouter", state)
            except OAuthFlowError:
                pass
        return _render_oauth_callback_html(
            provider="openrouter",
            title="OpenRouter 授权已取消",
            ok=False,
            detail_message=f"上游返回错误：{error}",
            status_code=400,
        )

    try:
        await oauth_service.complete_openrouter_pkce(code=code, state=state)
    except (OAuthFlowError, OAuthUpstreamError) as exc:
        return _render_oauth_callback_html(
            provider="openrouter",
            title="OpenRouter 授权失败",
            ok=False,
            detail_message=str(exc),
            status_code=400,
        )
    except Exception as exc:
        logger.error("OpenRouter OAuth callback error: %s", exc, exc_info=True)
        return _render_oauth_callback_html(
            provider="openrouter",
            title="OpenRouter 授权异常",
            ok=False,
            detail_message="完成授权交换时发生内部异常，请返回墨枢重试。",
            status_code=500,
        )

    _invalidate_llm_panel_cache()
    return _render_oauth_callback_html(
        provider="openrouter",
        title="OpenRouter 已连接",
        ok=True,
        detail_message="PKCE 授权已完成并自动建立 OpenRouter 档案，可关闭此窗口返回墨枢。",
        status_code=200,
    )


# ── GitHub Models Device Flow ───────────────────────────────────────────


@router.post("/oauth/github/device/start", response_model=OAuthDeviceStartResult)
async def start_github_device_oauth(
    payload: OAuthGitHubDeviceStartRequest = Body(
        default_factory=OAuthGitHubDeviceStartRequest
    ),
    oauth_service: LLMOAuthService = Depends(get_llm_oauth_service),
) -> OAuthDeviceStartResult:
    try:
        return await oauth_service.start_github_device_flow(client_id=payload.client_id)
    except OAuthConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OAuthUpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/oauth/github/device/poll", response_model=OAuthDevicePollResult)
async def poll_github_device_oauth(
    payload: OAuthGitHubDevicePollRequest,
    oauth_service: LLMOAuthService = Depends(get_llm_oauth_service),
) -> OAuthDevicePollResult:
    result = await oauth_service.poll_github_device_flow(flow_id=payload.flow_id)
    if result.status == "completed":
        _invalidate_llm_panel_cache()
    return result


# ── Google Gemini PKCE ──────────────────────────────────────────────────


@router.post("/oauth/google/start", response_model=OAuthPKCEStartResult)
async def start_google_oauth(
    request: Request,
    payload: OAuthGoogleStartRequest = Body(default_factory=OAuthGoogleStartRequest),
    oauth_service: LLMOAuthService = Depends(get_llm_oauth_service),
) -> OAuthPKCEStartResult:
    redirect_uri = _build_loopback_callback_url(
        request,
        "/oauth/google/callback",
        payload.callback_origin,
    )
    try:
        return oauth_service.start_google_pkce(
            redirect_uri,
            client_id=payload.client_id,
            client_secret=payload.client_secret,
        )
    except OAuthConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/oauth/google/callback", response_class=HTMLResponse)
async def callback_google_oauth(
    code: str = "",
    state: str = "",
    error: str = "",
    oauth_service: LLMOAuthService = Depends(get_llm_oauth_service),
) -> HTMLResponse:
    if error:
        if state:
            try:
                oauth_service.credential_store.consume_pkce_state("google_gemini", state)
            except OAuthFlowError:
                pass
        return _render_oauth_callback_html(
            provider="google_gemini",
            title="Google Gemini 授权已取消",
            ok=False,
            detail_message=f"上游返回错误：{error}",
            status_code=400,
        )

    try:
        await oauth_service.complete_google_pkce(code=code, state=state)
    except (OAuthFlowError, OAuthUpstreamError) as exc:
        return _render_oauth_callback_html(
            provider="google_gemini",
            title="Google Gemini 授权失败",
            ok=False,
            detail_message=str(exc),
            status_code=400,
        )
    except Exception as exc:
        logger.error("Google Gemini OAuth callback error: %s", exc, exc_info=True)
        return _render_oauth_callback_html(
            provider="google_gemini",
            title="Google Gemini 授权异常",
            ok=False,
            detail_message="完成授权交换时发生内部异常，请返回墨枢重试。",
            status_code=500,
        )

    _invalidate_llm_panel_cache()
    return _render_oauth_callback_html(
        provider="google_gemini",
        title="Google Gemini 已连接",
        ok=True,
        detail_message="Google OAuth 2.0 PKCE 授权已完成并自动启用刷新轮换，可关闭此窗口返回墨枢。",
        status_code=200,
    )


# ── Local Subscription Gateways (Magpie / Loopback) ─────────────────────


@router.post("/local-gateways/probe", response_model=LocalGatewayProbeResult)
async def probe_local_gateways(
    payload: LocalGatewayProbeRequest = Body(default_factory=LocalGatewayProbeRequest),
    probe_service: LocalGatewayProbeService = Depends(get_local_gateway_probe_service),
) -> LocalGatewayProbeResult:
    try:
        return await probe_service.probe(custom_url=payload.custom_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/local-gateways/connect", response_model=LLMControlPanelData)
async def connect_local_gateway_route(
    payload: LocalGatewayConnectRequest,
    probe_service: LocalGatewayProbeService = Depends(get_local_gateway_probe_service),
    control_service: LLMControlService = Depends(get_llm_control_service_dep),
) -> LLMControlPanelData:
    try:
        saved = probe_service.connect_local_gateway(
            base_url=payload.base_url,
            main_model=payload.main_model,
            name=payload.name,
            cheap_model=payload.cheap_model,
            kg_model=payload.kg_model,
            enable_golden_roles=payload.enable_golden_roles,
            use_legacy_chat_completions=payload.use_legacy_chat_completions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_llm_panel_cache()
    panel = LLMControlPanelData(
        config=saved,
        presets=control_service.get_presets(),
        runtime=control_service.get_runtime_summary(saved),
    )
    return control_service.redact_panel_data(panel)


# ── L3 Golden Role Routing ──────────────────────────────────────────────


@router.post("/role-routing/recommend", response_model=RoleModelRecommendation)
async def recommend_role_routing(
    payload: RoleRoutingRecommendRequest,
) -> RoleModelRecommendation:
    rec = recommend_role_models(payload.models)
    return RoleModelRecommendation(**rec)


@router.post("/role-routing/apply-golden", response_model=LLMControlPanelData)
async def apply_golden_role_routing_route(
    payload: ApplyGoldenRoleRoutingRequest,
    control_service: LLMControlService = Depends(get_llm_control_service_dep),
) -> LLMControlPanelData:
    try:
        saved = control_service.apply_golden_role_routing(
            source_profile_id=payload.source_profile_id,
            main_model=payload.main_model,
            cheap_model=payload.cheap_model,
            kg_model=payload.kg_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_llm_panel_cache()
    panel = LLMControlPanelData(
        config=saved,
        presets=control_service.get_presets(),
        runtime=control_service.get_runtime_summary(saved),
    )
    return control_service.redact_panel_data(panel)
