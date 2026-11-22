"""Standard public OAuth 2.0 PKCE & RFC 8628 Device Flow orchestration for LLM providers.

Supported public OAuth providers (strictly pinned to canonical upstream origins):
1. OpenRouter  — OAuth 2.0 PKCE (S256), zero client_id required
2. GitHub Models — RFC 8628 Device Authorization Flow
3. Google Gemini — OAuth 2.0 Desktop PKCE (S256) + automatic refresh_token rotation

Tokens are stored exclusively in OAuthCredentialStore (0600 file) and NEVER written
into SQLite llm_profiles or returned in HTTP responses.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from infrastructure.ai.llm_environment import LLMEnvironmentSettings
from infrastructure.ai.oauth_credential_store import (
    DEFAULT_PKCE_TTL_SECONDS,
    OAuthCredentialStore,
    OAuthFlowError,
    OAuthProviderKey,
    OAuthSessionRecord,
    OAuthStateError,
    VALID_OAUTH_PROVIDERS,
    compute_pkce_s256_challenge,
    get_oauth_credential_store,
)

if TYPE_CHECKING:
    from application.ai.llm_control_service import LLMControlService, LLMProfile

logger = logging.getLogger(__name__)


class OAuthConfigurationError(ValueError):
    """Raised when required public OAuth client configuration (e.g. client_id) is missing."""


class OAuthUpstreamError(RuntimeError):
    """Raised when an upstream OAuth authorization/token endpoint returns an error."""


@dataclass(frozen=True)
class CanonicalOAuthProviderSpec:
    provider: OAuthProviderKey
    title: str
    flow_type: Literal["pkce", "device_code"]
    protocol: Literal["openai", "anthropic", "gemini"]
    base_url: str
    preset_key: str
    default_model: str
    use_legacy_chat_completions: bool
    setup_hint: str
    authorize_url: str = ""
    device_code_url: str = ""
    token_url: str = ""
    scope: str = ""


CANONICAL_OAUTH_PROVIDERS: Dict[OAuthProviderKey, CanonicalOAuthProviderSpec] = {
    "openrouter": CanonicalOAuthProviderSpec(
        provider="openrouter",
        title="OpenRouter",
        flow_type="pkce",
        protocol="openai",
        base_url="https://openrouter.ai/api/v1",
        preset_key="openrouter",
        default_model="anthropic/claude-3.7-sonnet",
        use_legacy_chat_completions=True,
        setup_hint="公开 PKCE 零密钥直连，无需预置 Client ID",
        authorize_url="https://openrouter.ai/auth",
        token_url="https://openrouter.ai/api/v1/auth/keys",
        scope="",
    ),
    "github_models": CanonicalOAuthProviderSpec(
        provider="github_models",
        title="GitHub Models",
        flow_type="device_code",
        protocol="openai",
        base_url="https://models.inference.ai.azure.com",
        preset_key="custom-openai-compatible",
        default_model="gpt-4o",
        use_legacy_chat_completions=True,
        setup_hint="标准 RFC 8628 设备码授权（可填入公共 Client ID 或设置 PLOTPILOT_GITHUB_OAUTH_CLIENT_ID）",
        device_code_url="https://github.com/login/device/code",
        token_url="https://github.com/login/oauth/access_token",
        scope="read:user models:read",
    ),
    "google_gemini": CanonicalOAuthProviderSpec(
        provider="google_gemini",
        title="Google Gemini",
        flow_type="pkce",
        protocol="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        preset_key="gemini-official",
        default_model="gemini-2.5-pro",
        use_legacy_chat_completions=False,
        setup_hint="标准 Google OAuth 2.0 PKCE 桌面授权（可填入公共 Client ID 或设置 PLOTPILOT_GOOGLE_OAUTH_CLIENT_ID）",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scope=(
            "https://www.googleapis.com/auth/generative-language.retriever "
            "https://www.googleapis.com/auth/cloud-platform"
        ),
    ),
}


class OAuthProviderStatusItem(BaseModel):
    provider: OAuthProviderKey
    title: str
    flow_type: Literal["pkce", "device_code"]
    configured: bool
    connected: bool
    account_label: str = ""
    expires_at: Optional[float] = None
    profile_id: str
    setup_hint: str


class OAuthStatusResponse(BaseModel):
    providers: List[OAuthProviderStatusItem]


class OAuthPKCEStartResult(BaseModel):
    authorize_url: str
    state_expires_in: int = DEFAULT_PKCE_TTL_SECONDS


class OAuthDeviceStartResult(BaseModel):
    flow_id: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class OAuthDevicePollResult(BaseModel):
    status: Literal["pending", "slow_down", "completed", "expired", "error"]
    interval: int = 5
    profile_id: str = "oauth-github_models"
    message: str = ""


def get_canonical_oauth_spec(provider: str) -> CanonicalOAuthProviderSpec:
    key = (provider or "").strip()
    if key not in CANONICAL_OAUTH_PROVIDERS:
        raise ValueError(f"不支持的 OAuth 提供商: {provider}")
    return CANONICAL_OAUTH_PROVIDERS[key]  # type: ignore[index]


class LLMOAuthService:
    """Orchestrates public OAuth PKCE & Device Code flows and token refresh."""

    def __init__(
        self,
        *,
        credential_store: Optional[OAuthCredentialStore] = None,
        control_service: Optional["LLMControlService"] = None,
        env_settings_provider: Callable[
            [], LLMEnvironmentSettings
        ] = LLMEnvironmentSettings.from_env,
        client_factory: Optional[Callable[[], httpx.AsyncClient]] = None,
        sync_client_factory: Optional[Callable[[], httpx.Client]] = None,
    ) -> None:
        self.credential_store = credential_store or get_oauth_credential_store()
        self._control_service = control_service
        self._env_provider = env_settings_provider
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(
                timeout=15.0,
                trust_env=False,
                follow_redirects=False,
            )
        )
        self._sync_client_factory = sync_client_factory or (
            lambda: httpx.Client(
                timeout=10.0,
                trust_env=False,
                follow_redirects=False,
            )
        )

    def _get_control_service(self) -> "LLMControlService":
        if self._control_service is None:
            from application.ai.llm_control_service import LLMControlService

            self._control_service = LLMControlService(
                oauth_credential_store=self.credential_store
            )
        return self._control_service

    def get_status(self) -> OAuthStatusResponse:
        env = self._env_provider()
        sessions = self.credential_store.list_sessions()
        now = self.credential_store.now()
        items: list[OAuthProviderStatusItem] = []

        for provider_key in VALID_OAUTH_PROVIDERS:
            spec = CANONICAL_OAUTH_PROVIDERS[provider_key]
            record = sessions.get(provider_key)
            if provider_key == "openrouter":
                configured = True
            elif provider_key == "github_models":
                configured = bool(
                    env.github_oauth_client_id.strip()
                    or (record and record.client_id.strip())
                )
            else:
                configured = bool(
                    env.google_oauth_client_id.strip()
                    or (record and record.client_id.strip())
                )

            connected = False
            account_label = ""
            expires_at: float | None = None
            if record and record.access_token.strip():
                is_hard_expired = (
                    record.expires_at is not None
                    and now >= record.expires_at
                    and not record.refresh_token.strip()
                )
                if not is_hard_expired:
                    connected = True
                    account_label = record.account_label
                    expires_at = record.expires_at

            items.append(
                OAuthProviderStatusItem(
                    provider=provider_key,
                    title=spec.title,
                    flow_type=spec.flow_type,
                    configured=configured,
                    connected=connected,
                    account_label=account_label,
                    expires_at=expires_at,
                    profile_id=f"oauth-{provider_key}",
                    setup_hint=spec.setup_hint,
                )
            )
        return OAuthStatusResponse(providers=items)

    # ── OpenRouter PKCE ──────────────────────────────────────────────────

    def start_openrouter_pkce(self, redirect_uri: str) -> OAuthPKCEStartResult:
        spec = CANONICAL_OAUTH_PROVIDERS["openrouter"]
        flow = self.credential_store.create_pkce_flow(
            "openrouter",
            redirect_uri=redirect_uri,
            ttl_seconds=DEFAULT_PKCE_TTL_SECONDS,
        )
        challenge = compute_pkce_s256_challenge(flow.code_verifier)
        callback_with_state = f"{redirect_uri}?{urlencode({'state': flow.state})}"
        query = urlencode(
            {
                "callback_url": callback_with_state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": flow.state,
            }
        )
        return OAuthPKCEStartResult(
            authorize_url=f"{spec.authorize_url}?{query}",
            state_expires_in=DEFAULT_PKCE_TTL_SECONDS,
        )

    async def complete_openrouter_pkce(self, *, code: str, state: str) -> "LLMProfile":
        spec = CANONICAL_OAUTH_PROVIDERS["openrouter"]
        flow = self.credential_store.consume_pkce_state("openrouter", state)
        clean_code = (code or "").strip()
        if not clean_code:
            raise OAuthFlowError("OpenRouter 回调缺少授权码 code")

        async with self._client_factory() as client:
            response = await client.post(
                spec.token_url,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json={
                    "code": clean_code,
                    "code_verifier": flow.code_verifier,
                    "code_challenge_method": "S256",
                },
            )
        if response.status_code >= 400:
            raise OAuthUpstreamError(
                f"OpenRouter PKCE 换取密钥失败（HTTP {response.status_code}）"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise OAuthUpstreamError("OpenRouter 返回了非 JSON 响应") from exc

        access_token = str(
            (payload.get("key") or payload.get("access_token") or "")
            if isinstance(payload, dict)
            else ""
        ).strip()
        if not access_token:
            raise OAuthUpstreamError("OpenRouter 未返回有效授权密钥")

        now = self.credential_store.now()
        record = OAuthSessionRecord(
            session_id="openrouter",
            provider="openrouter",
            access_token=access_token,
            token_type="Bearer",
            expires_at=None,
            account_label="OpenRouter PKCE",
            connected_at=now,
            updated_at=now,
        )
        self.credential_store.save_session(record)
        return self._upsert_oauth_profile("openrouter")

    # ── GitHub Models Device Flow (RFC 8628) ─────────────────────────────

    async def start_github_device_flow(
        self, *, client_id: str = ""
    ) -> OAuthDeviceStartResult:
        spec = CANONICAL_OAUTH_PROVIDERS["github_models"]
        env = self._env_provider()
        effective_client_id = (
            (client_id or "").strip() or env.github_oauth_client_id.strip()
        )
        if not effective_client_id:
            raise OAuthConfigurationError(
                "尚未配置 GitHub OAuth Client ID：请在面板填入公共 Client ID，"
                "或设置环境变量 PLOTPILOT_GITHUB_OAUTH_CLIENT_ID（也可直接使用本机 Magpie 订阅网关免配置连接）"
            )

        async with self._client_factory() as client:
            response = await client.post(
                spec.device_code_url,
                headers={"Accept": "application/json"},
                data={
                    "client_id": effective_client_id,
                    "scope": spec.scope,
                },
            )
        if response.status_code >= 400:
            raise OAuthUpstreamError(
                f"GitHub 设备码请求失败（HTTP {response.status_code}）"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise OAuthUpstreamError("GitHub 设备码端点返回非 JSON 响应") from exc

        if not isinstance(payload, dict) or payload.get("error"):
            err_desc = (
                payload.get("error_description") or payload.get("error")
                if isinstance(payload, dict)
                else "unknown"
            )
            raise OAuthUpstreamError(f"GitHub 设备码请求被拒绝: {err_desc}")

        device_code = str(payload.get("device_code") or "").strip()
        user_code = str(payload.get("user_code") or "").strip()
        verification_uri = str(
            payload.get("verification_uri") or "https://github.com/login/device"
        ).strip()
        expires_in = int(payload.get("expires_in") or 900)
        interval = max(1, int(payload.get("interval") or 5))

        if not device_code or not user_code:
            raise OAuthUpstreamError("GitHub 设备码响应缺少 device_code 或 user_code")

        flow = self.credential_store.create_device_flow(
            provider="github_models",
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            expires_in=expires_in,
            interval=interval,
            client_id=effective_client_id,
        )
        return OAuthDeviceStartResult(
            flow_id=flow.flow_id,
            user_code=flow.user_code,
            verification_uri=flow.verification_uri,
            expires_in=expires_in,
            interval=flow.interval,
        )

    async def poll_github_device_flow(self, *, flow_id: str) -> OAuthDevicePollResult:
        spec = CANONICAL_OAUTH_PROVIDERS["github_models"]
        initial_flow = self.credential_store.get_device_flow(flow_id)
        if initial_flow is None or initial_flow.provider != "github_models":
            return OAuthDevicePollResult(
                status="expired",
                interval=5,
                profile_id="oauth-github_models",
                message="设备码授权会话不存在或已过期，请重新获取设备码",
            )

        poll_state, flow = self.credential_store.begin_device_flow_poll(flow_id)
        if poll_state == "expired" or flow is None or flow.provider != "github_models":
            return OAuthDevicePollResult(
                status="expired",
                interval=flow.interval if flow else initial_flow.interval,
                profile_id="oauth-github_models",
                message="设备码已过期，请重新发起授权",
            )

        if poll_state in ("rate_limited", "in_flight"):
            return OAuthDevicePollResult(
                status="pending",
                interval=flow.interval,
                profile_id="oauth-github_models",
                message="正在等待用户在 GitHub 页面输入设备码确认授权",
            )

        poll_settled = False
        try:
            try:
                async with self._client_factory() as client:
                    response = await client.post(
                        spec.token_url,
                        headers={"Accept": "application/json"},
                        data={
                            "client_id": flow.client_id,
                            "device_code": flow.device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        },
                    )
            except httpx.TimeoutException:
                updated = self.credential_store.complete_device_flow_poll(
                    flow.flow_id,
                    outcome="timeout",
                )
                poll_settled = True
                return OAuthDevicePollResult(
                    status="slow_down",
                    interval=updated.interval if updated else flow.interval + 5,
                    profile_id="oauth-github_models",
                    message="连接 GitHub 令牌服务超时，已按 RFC 8628 自动降低轮询频率",
                )
            except httpx.RequestError as exc:
                updated = self.credential_store.complete_device_flow_poll(
                    flow.flow_id,
                    outcome="transient_error",
                )
                poll_settled = True
                return OAuthDevicePollResult(
                    status="error",
                    interval=updated.interval if updated else flow.interval,
                    profile_id="oauth-github_models",
                    message=f"GitHub 令牌服务网络异常: {type(exc).__name__}",
                )

            if response.status_code >= 500:
                updated = self.credential_store.complete_device_flow_poll(
                    flow.flow_id,
                    outcome="transient_error",
                )
                poll_settled = True
                return OAuthDevicePollResult(
                    status="error",
                    interval=updated.interval if updated else flow.interval,
                    profile_id="oauth-github_models",
                    message=f"GitHub 令牌服务暂时不可用（HTTP {response.status_code}）",
                )

            try:
                payload = response.json()
            except ValueError:
                updated = self.credential_store.complete_device_flow_poll(
                    flow.flow_id,
                    outcome="transient_error",
                )
                poll_settled = True
                return OAuthDevicePollResult(
                    status="error",
                    interval=updated.interval if updated else flow.interval,
                    profile_id="oauth-github_models",
                    message="GitHub 令牌端点返回了非 JSON 响应",
                )

            if not isinstance(payload, dict):
                self.credential_store.complete_device_flow_poll(
                    flow.flow_id,
                    outcome="terminal",
                )
                poll_settled = True
                return OAuthDevicePollResult(
                    status="error",
                    interval=flow.interval,
                    profile_id="oauth-github_models",
                    message="GitHub 令牌响应格式异常",
                )

            access_token = str(payload.get("access_token") or "").strip()
            if access_token:
                self.credential_store.complete_device_flow_poll(
                    flow.flow_id,
                    outcome="terminal",
                )
                poll_settled = True
                now = self.credential_store.now()
                expires_in = payload.get("expires_in")
                expires_at = (now + float(expires_in)) if expires_in else None
                refresh_token = str(payload.get("refresh_token") or "").strip()
                record = OAuthSessionRecord(
                    session_id="github_models",
                    provider="github_models",
                    access_token=access_token,
                    refresh_token=refresh_token,
                    token_type=str(payload.get("token_type") or "Bearer"),
                    expires_at=expires_at,
                    scope=str(payload.get("scope") or spec.scope),
                    account_label="GitHub Models",
                    client_id=flow.client_id,
                    connected_at=now,
                    updated_at=now,
                )
                self.credential_store.save_session(record)
                profile = self._upsert_oauth_profile("github_models")
                return OAuthDevicePollResult(
                    status="completed",
                    interval=flow.interval,
                    profile_id=profile.id,
                    message="GitHub Models 授权已完成",
                )

            err_code = str(payload.get("error") or "").strip()
            raw_upstream_interval = payload.get("interval")
            parsed_interval: int | None = None
            if raw_upstream_interval is not None:
                try:
                    parsed_interval = int(raw_upstream_interval)
                except (TypeError, ValueError):
                    parsed_interval = None

            if err_code == "authorization_pending":
                updated = self.credential_store.complete_device_flow_poll(
                    flow.flow_id,
                    outcome="pending",
                    upstream_interval=parsed_interval,
                )
                poll_settled = True
                return OAuthDevicePollResult(
                    status="pending",
                    interval=updated.interval if updated else flow.interval,
                    profile_id="oauth-github_models",
                    message="等待用户在浏览器输入设备码并确认授权",
                )
            if err_code == "slow_down":
                updated = self.credential_store.complete_device_flow_poll(
                    flow.flow_id,
                    outcome="slow_down",
                    upstream_interval=parsed_interval,
                )
                poll_settled = True
                return OAuthDevicePollResult(
                    status="slow_down",
                    interval=updated.interval if updated else flow.interval + 5,
                    profile_id="oauth-github_models",
                    message="轮询过快，已按 RFC 8628 自动调大轮询间隔",
                )
            if err_code == "expired_token":
                self.credential_store.complete_device_flow_poll(
                    flow.flow_id,
                    outcome="terminal",
                )
                poll_settled = True
                return OAuthDevicePollResult(
                    status="expired",
                    interval=flow.interval,
                    profile_id="oauth-github_models",
                    message="设备码已过期，请重新发起授权",
                )

            self.credential_store.complete_device_flow_poll(
                flow.flow_id,
                outcome="terminal",
            )
            poll_settled = True
            err_msg = str(payload.get("error_description") or err_code or "设备码授权被拒绝")
            return OAuthDevicePollResult(
                status="error",
                interval=flow.interval,
                profile_id="oauth-github_models",
                message=err_msg,
            )
        finally:
            if not poll_settled:
                self.credential_store.complete_device_flow_poll(
                    flow.flow_id,
                    outcome="transient_error",
                )

    # ── Google Gemini PKCE + Refresh Rotation ────────────────────────────

    def start_google_pkce(
        self,
        redirect_uri: str,
        *,
        client_id: str = "",
        client_secret: str = "",
    ) -> OAuthPKCEStartResult:
        spec = CANONICAL_OAUTH_PROVIDERS["google_gemini"]
        env = self._env_provider()
        effective_client_id = (
            (client_id or "").strip() or env.google_oauth_client_id.strip()
        )
        effective_client_secret = (
            (client_secret or "").strip() or env.google_oauth_client_secret.strip()
        )
        if not effective_client_id:
            raise OAuthConfigurationError(
                "尚未配置 Google OAuth Client ID：请在面板填入桌面应用 Client ID，"
                "或设置环境变量 PLOTPILOT_GOOGLE_OAUTH_CLIENT_ID"
            )

        flow = self.credential_store.create_pkce_flow(
            "google_gemini",
            redirect_uri=redirect_uri,
            ttl_seconds=DEFAULT_PKCE_TTL_SECONDS,
            client_id=effective_client_id,
            client_secret=effective_client_secret,
        )
        challenge = compute_pkce_s256_challenge(flow.code_verifier)
        query = urlencode(
            {
                "client_id": effective_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": spec.scope,
                "state": flow.state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",
            }
        )
        return OAuthPKCEStartResult(
            authorize_url=f"{spec.authorize_url}?{query}",
            state_expires_in=DEFAULT_PKCE_TTL_SECONDS,
        )

    async def complete_google_pkce(self, *, code: str, state: str) -> "LLMProfile":
        spec = CANONICAL_OAUTH_PROVIDERS["google_gemini"]
        flow = self.credential_store.consume_pkce_state("google_gemini", state)
        clean_code = (code or "").strip()
        if not clean_code:
            raise OAuthFlowError("Google OAuth 回调缺少授权码 code")

        form_data: dict[str, str] = {
            "client_id": flow.client_id,
            "code": clean_code,
            "code_verifier": flow.code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": flow.redirect_uri,
        }
        if flow.client_secret:
            form_data["client_secret"] = flow.client_secret

        async with self._client_factory() as client:
            response = await client.post(
                spec.token_url,
                headers={"Accept": "application/json"},
                data=form_data,
            )
        if response.status_code >= 400:
            raise OAuthUpstreamError(
                f"Google OAuth 换取令牌失败（HTTP {response.status_code}）"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise OAuthUpstreamError("Google OAuth 令牌端点返回非 JSON 响应") from exc

        if not isinstance(payload, dict):
            raise OAuthUpstreamError("Google OAuth 令牌响应格式无效")

        access_token = str(payload.get("access_token") or "").strip()
        if not access_token:
            raise OAuthUpstreamError("Google OAuth 未返回有效 access_token")

        refresh_token = str(payload.get("refresh_token") or "").strip()
        now = self.credential_store.now()
        expires_in = payload.get("expires_in")
        expires_at = (now + float(expires_in)) if expires_in else (now + 3600.0)

        record = OAuthSessionRecord(
            session_id="google_gemini",
            provider="google_gemini",
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=str(payload.get("token_type") or "Bearer"),
            expires_at=expires_at,
            scope=str(payload.get("scope") or spec.scope),
            account_label="Google Gemini OAuth",
            client_id=flow.client_id,
            client_secret=flow.client_secret,
            connected_at=now,
            updated_at=now,
        )
        self.credential_store.save_session(record)
        return self._upsert_oauth_profile("google_gemini")

    # ── Token Resolution & Refresh Rotation ──────────────────────────────

    def _build_refresh_form(self, record: OAuthSessionRecord) -> tuple[str, dict[str, str]]:
        spec = CANONICAL_OAUTH_PROVIDERS[record.provider]
        env = self._env_provider()
        if record.provider == "google_gemini":
            client_id = record.client_id or env.google_oauth_client_id
            client_secret = record.client_secret or env.google_oauth_client_secret
        elif record.provider == "github_models":
            client_id = record.client_id or env.github_oauth_client_id
            client_secret = ""
        else:
            client_id = record.client_id
            client_secret = record.client_secret

        form: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": record.refresh_token,
        }
        if client_id:
            form["client_id"] = client_id
        if client_secret:
            form["client_secret"] = client_secret
        return spec.token_url, form

    def _commit_refreshed_payload(
        self, record: OAuthSessionRecord, payload: dict[str, Any]
    ) -> OAuthSessionRecord | None:
        new_access = str(payload.get("access_token") or "").strip()
        if not new_access:
            raise OAuthUpstreamError("OAuth 刷新令牌响应缺少 access_token")
        new_refresh = str(payload.get("refresh_token") or "").strip() or record.refresh_token
        now = self.credential_store.now()
        expires_in = payload.get("expires_in")
        expires_at = (now + float(expires_in)) if expires_in else (now + 3600.0)
        updated = OAuthSessionRecord(
            session_id=record.session_id,
            provider=record.provider,
            access_token=new_access,
            refresh_token=new_refresh,
            token_type=str(payload.get("token_type") or record.token_type or "Bearer"),
            expires_at=expires_at,
            scope=str(payload.get("scope") or record.scope),
            account_label=record.account_label,
            client_id=record.client_id,
            client_secret=record.client_secret,
            connected_at=record.connected_at,
            updated_at=now,
            generation=record.generation,
        )
        return self.credential_store.compare_and_swap_session(
            session_id=record.session_id,
            expected_generation=record.generation,
            expected_refresh_token=record.refresh_token,
            updated_record=updated,
        )

    def _resolve_current_valid_token(self, session_id: str) -> str:
        """Re-read store after refresh/invalidation so deleted or replaced sessions are respected."""
        latest = self.credential_store.get_session(session_id)
        if latest is None or not latest.access_token.strip():
            return ""
        now = self.credential_store.now()
        if not latest.is_expired(skew_seconds=60.0, now=now):
            return latest.access_token
        if latest.expires_at is not None and now < latest.expires_at:
            return latest.access_token
        return ""

    def resolve_access_token_sync(self, session_id: str) -> str:
        key = (session_id or "").strip()
        if not key:
            return ""

        for _attempt in range(3):
            record = self.credential_store.get_session(key)
            if record is None or not record.access_token.strip():
                return ""

            now = self.credential_store.now()
            if not record.is_expired(skew_seconds=60.0, now=now):
                return record.access_token

            if not (
                record.refresh_token.strip()
                and CANONICAL_OAUTH_PROVIDERS[record.provider].token_url
            ):
                return self._resolve_current_valid_token(key)

            acquire_state, slot = self.credential_store.acquire_refresh_slot_sync(
                key, record.generation
            )
            if acquire_state == "stale" or slot is None:
                continue

            if acquire_state == "follower":
                slot.done_event.wait(timeout=15.0)
                after_wait = self.credential_store.get_session(key)
                if (
                    after_wait is not None
                    and after_wait.generation != record.generation
                    and after_wait.is_expired(
                        skew_seconds=60.0, now=self.credential_store.now()
                    )
                    and after_wait.refresh_token.strip()
                ):
                    continue
                return self._resolve_current_valid_token(key)

            try:
                current = self.credential_store.get_session(key)
                if current is None or not current.access_token.strip():
                    return ""
                if current.generation != record.generation:
                    continue
                if not current.is_expired(
                    skew_seconds=60.0, now=self.credential_store.now()
                ):
                    return current.access_token

                token_url, form = self._build_refresh_form(current)
                try:
                    with self._sync_client_factory() as client:
                        response = client.post(
                            token_url,
                            headers={"Accept": "application/json"},
                            data=form,
                        )
                    if response.status_code < 400:
                        payload = response.json()
                        if isinstance(payload, dict) and payload.get("access_token"):
                            committed = self._commit_refreshed_payload(current, payload)
                            if committed is not None:
                                return committed.access_token
                            return self._resolve_current_valid_token(key)
                    logger.warning(
                        "OAuth token sync refresh failed for %s: HTTP %s",
                        current.provider,
                        response.status_code,
                    )
                except Exception as exc:
                    logger.warning(
                        "OAuth token sync refresh error for %s: %s",
                        current.provider,
                        exc,
                    )
            finally:
                self.credential_store.release_refresh_slot(key, slot)
            break

        return self._resolve_current_valid_token(key)

    async def resolve_access_token_async(self, session_id: str) -> str:
        key = (session_id or "").strip()
        if not key:
            return ""

        loop = asyncio.get_running_loop()
        for _attempt in range(3):
            record = self.credential_store.get_session(key)
            if record is None or not record.access_token.strip():
                return ""

            now = self.credential_store.now()
            if not record.is_expired(skew_seconds=60.0, now=now):
                return record.access_token

            if not (
                record.refresh_token.strip()
                and CANONICAL_OAUTH_PROVIDERS[record.provider].token_url
            ):
                return self._resolve_current_valid_token(key)

            acquire_state, slot, waiter_fut = (
                self.credential_store.acquire_refresh_slot_async(
                    key, record.generation, loop
                )
            )
            if acquire_state == "stale" or slot is None:
                continue

            if acquire_state == "follower":
                if waiter_fut is not None and not slot.done_event.is_set():
                    try:
                        await asyncio.wait_for(asyncio.shield(waiter_fut), timeout=15.0)
                    except asyncio.TimeoutError:
                        pass
                after_wait = self.credential_store.get_session(key)
                if (
                    after_wait is not None
                    and after_wait.generation != record.generation
                    and after_wait.is_expired(
                        skew_seconds=60.0, now=self.credential_store.now()
                    )
                    and after_wait.refresh_token.strip()
                ):
                    continue
                return self._resolve_current_valid_token(key)

            try:
                current = self.credential_store.get_session(key)
                if current is None or not current.access_token.strip():
                    return ""
                if current.generation != record.generation:
                    continue
                if not current.is_expired(
                    skew_seconds=60.0, now=self.credential_store.now()
                ):
                    return current.access_token

                token_url, form = self._build_refresh_form(current)
                try:
                    async with self._client_factory() as client:
                        response = await client.post(
                            token_url,
                            headers={"Accept": "application/json"},
                            data=form,
                        )
                    if response.status_code < 400:
                        payload = response.json()
                        if isinstance(payload, dict) and payload.get("access_token"):
                            committed = self._commit_refreshed_payload(current, payload)
                            if committed is not None:
                                return committed.access_token
                            return self._resolve_current_valid_token(key)
                    logger.warning(
                        "OAuth token async refresh failed for %s: HTTP %s",
                        current.provider,
                        response.status_code,
                    )
                except Exception as exc:
                    logger.warning(
                        "OAuth token async refresh error for %s: %s",
                        current.provider,
                        exc,
                    )
            finally:
                self.credential_store.release_refresh_slot(key, slot)
            break

        return self._resolve_current_valid_token(key)

    # ── Profile Upsert & Disconnect ──────────────────────────────────────

    def _upsert_oauth_profile(self, provider: OAuthProviderKey) -> "LLMProfile":
        from application.ai.llm_control_service import LLMProfile

        spec = CANONICAL_OAUTH_PROVIDERS[provider]
        control = self._get_control_service()
        cfg = control.get_config()
        profile_id = f"oauth-{provider}"

        active = control.get_active_profile(cfg)
        active_was_unconfigured = True
        if active is not None:
            try:
                resolved_active = control.resolve_profile(active)
                active_was_unconfigured = not (
                    resolved_active.api_key.strip() and resolved_active.model.strip()
                )
            except Exception:
                active_was_unconfigured = True

        existing_idx: int | None = None
        existing_profile: LLMProfile | None = None
        for idx, item in enumerate(cfg.profiles):
            if item.id == profile_id:
                existing_idx = idx
                existing_profile = item
                break

        chosen_model = (
            existing_profile.model.strip()
            if existing_profile and existing_profile.model.strip()
            else spec.default_model
        )
        new_profile = LLMProfile(
            id=profile_id,
            name=f"{spec.title} (OAuth)",
            preset_key=spec.preset_key,
            protocol=spec.protocol,
            base_url=spec.base_url,
            api_key="",
            model=chosen_model,
            temperature=existing_profile.temperature if existing_profile else 0.7,
            timeout_seconds=existing_profile.timeout_seconds if existing_profile else 300,
            notes=existing_profile.notes if existing_profile else f"{spec.title} 官方 OAuth 授权连接",
            use_legacy_chat_completions=spec.use_legacy_chat_completions,
            auth_mode="oauth",
            oauth_provider=provider,
            oauth_session_id=provider,
        )

        if existing_idx is not None:
            cfg.profiles[existing_idx] = new_profile
        else:
            cfg.profiles.append(new_profile)

        if active_was_unconfigured or cfg.active_profile_id == profile_id:
            cfg.active_profile_id = profile_id

        saved = control.save_config(cfg)
        return next((p for p in saved.profiles if p.id == profile_id), new_profile)

    def disconnect(self, provider: str) -> OAuthStatusResponse:
        key = (provider or "").strip()
        if key not in VALID_OAUTH_PROVIDERS:
            raise ValueError(f"不支持的 OAuth 提供商: {provider}")

        self.credential_store.delete_session(key)
        control = self._get_control_service()
        cfg = control.get_config()
        bound_ids = set((cfg.role_bindings or {}).values())
        target_profile_id = f"oauth-{key}"

        updated_profiles = []
        changed = False
        for p in cfg.profiles:
            if p.oauth_provider == key or p.oauth_session_id == key:
                changed = True
                if p.id == target_profile_id and p.id not in bound_ids and len(cfg.profiles) > 1:
                    continue
                updated_profiles.append(
                    p.model_copy(update={"oauth_session_id": "", "api_key": "", "has_secret": False})
                )
            else:
                updated_profiles.append(p)

        if changed:
            cfg.profiles = updated_profiles
            control.save_config(cfg)

        return self.get_status()


__all__ = [
    "CANONICAL_OAUTH_PROVIDERS",
    "CanonicalOAuthProviderSpec",
    "LLMOAuthService",
    "OAuthConfigurationError",
    "OAuthDevicePollResult",
    "OAuthDeviceStartResult",
    "OAuthFlowError",
    "OAuthPKCEStartResult",
    "OAuthProviderStatusItem",
    "OAuthStateError",
    "OAuthStatusResponse",
    "OAuthUpstreamError",
    "get_canonical_oauth_spec",
]
