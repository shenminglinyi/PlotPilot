"""Loopback local subscription gateway (Magpie / LiteLLM / Ollama / vLLM) probe & SSRF guard.

Strict security invariants:
1. Only loopback hosts (127.0.0.1, ::1, localhost) with explicit ports 1024..65535
   (excluding PlotPilot's own backend port 8005) are permitted.
2. HTTP probing disables environment proxies (trust_env=False), disables redirects
   (follow_redirects=False), enforces a 1.5s timeout, and caps bodies at 512 KB.
3. Official CLI status checks inspect ONLY binary presence and path existence
   metadata — NEVER reading or returning raw credential files or tokens.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import shutil
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Callable, Dict, List, Literal, Optional, Tuple
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field

from infrastructure.ai.llm_environment import (
    LLMEnvironmentSettings,
    MAGPIE_DEFAULT_GATEWAY_URL,
)
from infrastructure.ai.loopback_transport import (
    ALLOWED_LOOPBACK_HOSTNAMES,
    DEFAULT_BLOCKED_PORTS,
    LoopbackDnsResolver,
    LoopbackOnlyAsyncTransport,
    resolve_loopback_host_ips,
)

if TYPE_CHECKING:
    from application.ai.llm_control_service import LLMControlConfig, LLMControlService

logger = logging.getLogger(__name__)

MAX_MODELS_RESPONSE_BYTES = 512 * 1024
MAX_DISCOVERED_MODELS = 200

MAIN_MODEL_PRIORITY: tuple[str, ...] = (
    "claude/claude-opus-5-5",
    "claude/claude-sonnet-5-5",
    "antigravity/gemini-4-argon",
    "auto/claude-opus-5-5",
    "auto/claude-sonnet-5-5",
    "codex/gpt-6.1-sol",
    "anthropic/claude-sonnet-4",
    "anthropic/claude-3.7-sonnet",
    "openai/gpt-4.1",
    "gpt-4o",
    "gemini-2.5-pro",
)

CHEAP_MODEL_PRIORITY: tuple[str, ...] = (
    "workbuddy/deepseek-v4.1-flash",
    "claude/claude-haiku-5-5",
    "antigravity/gemini-3.8-flash",
    "auto/gemini-3.8-flash",
    "grok/grok-4.7-build-fast",
    "workbuddy/glm-5.3-flash",
    "openai/gpt-4o-mini",
    "gpt-4o-mini",
    "gemini-2.5-flash",
    "anthropic/claude-3.5-haiku",
)

KG_MODEL_PRIORITY: tuple[str, ...] = (
    "workbuddy/deepseek-v4.1-flash",
    "antigravity/gemini-4-hydrogen",
    "antigravity/gemini-3.8-flash",
    "claude/claude-haiku-5-5",
    "openai/gpt-4o-mini",
    "gemini-2.5-flash",
)


class RoleModelRecommendation(BaseModel):
    main: str = ""
    cheap: str = ""
    kg: str = ""


class LocalGatewayProbeItem(BaseModel):
    id: str
    name: str
    kind: Literal["magpie", "openai_local_gateway"] = "openai_local_gateway"
    base_url: str
    reachable: bool = False
    latency_ms: int = 0
    models: List[str] = Field(default_factory=list)
    recommended_roles: RoleModelRecommendation = Field(
        default_factory=RoleModelRecommendation
    )
    error: str = ""


class CLIStatusItem(BaseModel):
    id: str
    name: str
    installed: bool = False
    authenticated_hint: bool = False
    note: str = ""


class LocalGatewayProbeResult(BaseModel):
    gateways: List[LocalGatewayProbeItem] = Field(default_factory=list)
    cli_tools: List[CLIStatusItem] = Field(default_factory=list)


@dataclass(frozen=True)
class ValidatedLoopbackGateway:
    """Validated loopback gateway URL paired with its resolved numeric loopback IPs."""

    url: str
    scheme: str
    hostname: str
    port: int
    pinned_ips: Tuple[str, ...]


def validate_loopback_gateway_target(
    url: str,
    *,
    blocked_ports: set[int] | frozenset[int] = DEFAULT_BLOCKED_PORTS,
    resolver: Optional[LoopbackDnsResolver] = None,
) -> ValidatedLoopbackGateway:
    """Strictly validate a loopback gateway URL and capture its verified loopback IPs.

    Raises ValueError on any non-loopback host, missing/invalid/blocked port,
    non-HTTP(S) scheme, credentials, query/fragment, or path traversal.
    """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("本地网关地址不能为空")

    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise ValueError("本地网关地址格式无效") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError("本地网关地址仅允许 http 或 https 协议")

    if parsed.username is not None or parsed.password is not None:
        raise ValueError("本地网关地址不允许携带用户名或密码")

    if parsed.query or parsed.fragment:
        raise ValueError("本地网关地址不允许包含查询参数或锚点")

    hostname = (parsed.hostname or "").strip().lower()
    if hostname not in ALLOWED_LOOPBACK_HOSTNAMES:
        raise ValueError(
            "本地订阅网关仅允许回环地址（127.0.0.1、::1 或 localhost），拒绝访问局域网或公网地址"
        )

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("本地网关端口无效") from exc

    if port is None or not (1024 <= port <= 65535):
        raise ValueError("本地网关必须显式指定 1024..65535 范围内的端口")

    if port in blocked_ports:
        raise ValueError(f"端口 {port} 为系统保留端口，不可作为本地模型网关")

    pinned_ips = resolve_loopback_host_ips(hostname, port, resolver=resolver)

    raw_path = parsed.path or ""
    if ".." in raw_path.split("/"):
        raise ValueError("本地网关路径包含非法段")

    clean_path = raw_path.rstrip("/")
    if not clean_path:
        clean_path = "/v1"
    elif not clean_path.startswith("/"):
        clean_path = "/" + clean_path

    host_repr = f"[{hostname}]" if ":" in hostname else hostname
    return ValidatedLoopbackGateway(
        url=f"{scheme}://{host_repr}:{port}{clean_path}",
        scheme=scheme,
        hostname=hostname,
        port=port,
        pinned_ips=pinned_ips,
    )


def validate_loopback_gateway_url(
    url: str,
    *,
    blocked_ports: set[int] | frozenset[int] = DEFAULT_BLOCKED_PORTS,
    resolver: Optional[LoopbackDnsResolver] = None,
) -> str:
    """Strictly validate and normalize a local loopback gateway URL."""
    return validate_loopback_gateway_target(
        url,
        blocked_ports=blocked_ports,
        resolver=resolver,
    ).url


def recommend_role_models(models: List[str]) -> Dict[str, str]:
    """Compute golden quota-saving (main, cheap, kg) model recommendations."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in models or []:
        m = str(item or "").strip()
        if m and m not in seen:
            seen.add(m)
            cleaned.append(m)

    if not cleaned:
        return {"main": "", "cheap": "", "kg": ""}

    non_group = [m for m in cleaned if not m.startswith("group/")]
    pool = non_group or cleaned

    main_model = next((cand for cand in MAIN_MODEL_PRIORITY if cand in seen), "")
    if not main_model:
        main_model = pool[0]

    cheap_model = next((cand for cand in CHEAP_MODEL_PRIORITY if cand in seen), "")
    if not cheap_model:
        cheap_model = next(
            (
                m
                for m in pool
                if any(tok in m.lower() for tok in ("flash", "haiku", "mini"))
            ),
            main_model,
        )

    kg_model = next((cand for cand in KG_MODEL_PRIORITY if cand in seen), "")
    if not kg_model:
        kg_model = next(
            (
                m
                for m in pool
                if any(
                    tok in m.lower()
                    for tok in ("deepseek", "hydrogen", "flash", "haiku", "mini")
                )
            ),
            cheap_model,
        )

    return {
        "main": main_model,
        "cheap": cheap_model or main_model,
        "kg": kg_model or cheap_model or main_model,
    }


def _classify_gateway_kind(
    base_url: str, models: List[str]
) -> Literal["magpie", "openai_local_gateway"]:
    if ":3425/" in f"{base_url}/":
        return "magpie"
    for m in models:
        if m == "group/auto-task" or m.startswith(
            ("antigravity/", "codex/", "claude/", "workbuddy/")
        ):
            return "magpie"
    return "openai_local_gateway"


class LocalGatewayProbeService:
    """Probes loopback subscription gateways & official CLI presence safely."""

    def __init__(
        self,
        *,
        control_service: Optional["LLMControlService"] = None,
        env_settings_provider: Callable[
            [], LLMEnvironmentSettings
        ] = LLMEnvironmentSettings.from_env,
        client_factory: Optional[Callable[[], httpx.AsyncClient]] = None,
        dns_resolver: Optional[LoopbackDnsResolver] = None,
        cli_which: Callable[[str], Optional[str]] = shutil.which,
        home_dir_provider: Callable[[], Path] = Path.home,
    ) -> None:
        self._control_service = control_service
        self._env_provider = env_settings_provider
        self._custom_client_factory = client_factory
        self._dns_resolver = dns_resolver
        self._cli_which = cli_which
        self._home_dir_provider = home_dir_provider

    def _build_probe_client(self, target: ValidatedLoopbackGateway) -> httpx.AsyncClient:
        if self._custom_client_factory is not None:
            return self._custom_client_factory()
        return httpx.AsyncClient(
            transport=LoopbackOnlyAsyncTransport(
                pinned_ips=target.pinned_ips,
                allowed_port=target.port,
                blocked_ports=DEFAULT_BLOCKED_PORTS,
                resolver=self._dns_resolver,
                limits=httpx.Limits(max_connections=2, max_keepalive_connections=0),
            ),
            timeout=1.5,
            trust_env=False,
            follow_redirects=False,
        )

    def _get_control_service(self) -> "LLMControlService":
        if self._control_service is None:
            from application.ai.llm_control_service import LLMControlService

            self._control_service = LLMControlService()
        return self._control_service

    async def _probe_single_gateway(
        self,
        *,
        gateway_id: str,
        name: str,
        target: ValidatedLoopbackGateway,
    ) -> LocalGatewayProbeItem:
        validated_base_url = target.url
        models_url = f"{validated_base_url.rstrip('/')}/models"
        started = perf_counter()
        try:
            async with self._build_probe_client(target) as client:
                async with client.stream(
                    "GET",
                    models_url,
                    headers={"Accept": "application/json"},
                ) as response:
                    status_code = response.status_code
                    chunks: list[bytes] = []
                    total_bytes = 0
                    async for chunk in response.aiter_bytes():
                        total_bytes += len(chunk)
                        if total_bytes > MAX_MODELS_RESPONSE_BYTES:
                            raise ValueError("本地网关响应体积超过 512 KB 安全上限")
                        chunks.append(chunk)

            latency_ms = int((perf_counter() - started) * 1000)
            if status_code >= 400:
                return LocalGatewayProbeItem(
                    id=gateway_id,
                    name=name,
                    kind=_classify_gateway_kind(validated_base_url, []),
                    base_url=validated_base_url,
                    reachable=False,
                    latency_ms=latency_ms,
                    error=f"HTTP {status_code}",
                )

            raw_body = b"".join(chunks).decode("utf-8", errors="replace")
            payload = json.loads(raw_body)
            raw_list = payload.get("data") if isinstance(payload, dict) else None
            models: list[str] = []
            if isinstance(raw_list, list):
                for entry in raw_list[:MAX_DISCOVERED_MODELS]:
                    if isinstance(entry, dict):
                        mid = str(entry.get("id") or "").strip()
                        if mid and len(mid) <= 200:
                            models.append(mid)

            kind = _classify_gateway_kind(validated_base_url, models)
            rec = recommend_role_models(models)
            return LocalGatewayProbeItem(
                id=gateway_id,
                name=name,
                kind=kind,
                base_url=validated_base_url,
                reachable=True,
                latency_ms=latency_ms,
                models=models,
                recommended_roles=RoleModelRecommendation(**rec),
                error="",
            )
        except Exception as exc:
            latency_ms = int((perf_counter() - started) * 1000)
            return LocalGatewayProbeItem(
                id=gateway_id,
                name=name,
                kind=_classify_gateway_kind(validated_base_url, []),
                base_url=validated_base_url,
                reachable=False,
                latency_ms=latency_ms,
                error=str(exc) or type(exc).__name__,
            )

    def inspect_cli_tools(self, *, magpie_reachable: bool = False) -> List[CLIStatusItem]:
        """Non-destructive, secret-free inspection of official local CLI tools."""
        try:
            home = self._home_dir_provider()
        except Exception:
            home = Path(".")

        magpie_bin = bool(
            self._cli_which("magpie")
            or (home / "Downloads" / "magpie-windows-amd64.exe").is_file()
            or (home / ".magpie" / "bin" / "magpie.exe").is_file()
            or (home / ".magpie" / "bin" / "magpie").is_file()
        )
        magpie_installed = magpie_bin or magpie_reachable
        magpie_auth = magpie_reachable or (home / ".magpie").is_dir() or (
            home / ".config" / "magpie"
        ).is_dir()

        claude_installed = bool(self._cli_which("claude"))
        claude_auth = (home / ".claude").is_dir()

        codex_installed = bool(self._cli_which("codex"))
        codex_auth = (home / ".codex" / "auth.json").is_file()

        gemini_installed = bool(self._cli_which("gemini"))
        gemini_auth = (home / ".gemini").is_dir()

        gh_installed = bool(self._cli_which("gh"))
        gh_auth = (home / ".config" / "gh" / "hosts.yml").is_file() or (
            home / "AppData" / "Roaming" / "GitHub CLI" / "hosts.yml"
        ).is_file()

        return [
            CLIStatusItem(
                id="magpie",
                name="Magpie CLI",
                installed=magpie_installed,
                authenticated_hint=magpie_auth,
                note=(
                    "已检测到本机 Magpie 订阅桥接网关正在运行"
                    if magpie_reachable
                    else (
                        "已检测到本机 Magpie 工具（启动网关后可一键接入多订阅模型池）"
                        if magpie_installed
                        else "未检测到 Magpie；若使用本地多订阅聚合网关可启动于 127.0.0.1:3425"
                    )
                ),
            ),
            CLIStatusItem(
                id="claude",
                name="Claude Code CLI",
                installed=claude_installed,
                authenticated_hint=claude_auth,
                note=(
                    "已检测到本机 Claude CLI（可通过本机订阅网关桥接，墨枢不直接读取私有凭证）"
                    if claude_installed
                    else "未安装 Claude CLI"
                ),
            ),
            CLIStatusItem(
                id="codex",
                name="OpenAI Codex CLI",
                installed=codex_installed,
                authenticated_hint=codex_auth,
                note=(
                    "已检测到本机 Codex CLI（可通过本机订阅网关桥接，墨枢不直接读取私有凭证）"
                    if codex_installed
                    else "未安装 Codex CLI"
                ),
            ),
            CLIStatusItem(
                id="gemini",
                name="Gemini CLI",
                installed=gemini_installed,
                authenticated_hint=gemini_auth,
                note=(
                    "已检测到本机 Gemini CLI（支持 Google OAuth PKCE 或本机网关接入）"
                    if gemini_installed
                    else "未安装 Gemini CLI"
                ),
            ),
            CLIStatusItem(
                id="gh",
                name="GitHub CLI",
                installed=gh_installed,
                authenticated_hint=gh_auth,
                note=(
                    "已检测到 GitHub CLI（亦可使用上方 GitHub Models 设备码直接授权）"
                    if gh_installed
                    else "未安装 GitHub CLI"
                ),
            ),
        ]

    async def probe(self, custom_url: str = "") -> LocalGatewayProbeResult:
        env = self._env_provider()
        raw_magpie = env.magpie_gateway_url_or_default
        try:
            magpie_target = validate_loopback_gateway_target(
                raw_magpie,
                resolver=self._dns_resolver,
            )
        except ValueError:
            magpie_target = validate_loopback_gateway_target(
                MAGPIE_DEFAULT_GATEWAY_URL,
                resolver=self._dns_resolver,
            )

        custom_target: Optional[ValidatedLoopbackGateway] = None
        if (custom_url or "").strip():
            custom_target = validate_loopback_gateway_target(
                custom_url,
                resolver=self._dns_resolver,
            )

        gateways: list[LocalGatewayProbeItem] = []
        magpie_item = await self._probe_single_gateway(
            gateway_id="magpie-local",
            name="Magpie 本机订阅网关",
            target=magpie_target,
        )
        gateways.append(magpie_item)

        if custom_target is not None and custom_target.url != magpie_target.url:
            custom_item = await self._probe_single_gateway(
                gateway_id="custom-local",
                name="自定义本机网关",
                target=custom_target,
            )
            gateways.append(custom_item)

        cli_tools = self.inspect_cli_tools(magpie_reachable=magpie_item.reachable)
        return LocalGatewayProbeResult(gateways=gateways, cli_tools=cli_tools)

    def connect_local_gateway(
        self,
        *,
        base_url: str,
        main_model: str,
        name: str = "Magpie 订阅网关",
        cheap_model: str = "",
        kg_model: str = "",
        enable_golden_roles: bool = True,
        use_legacy_chat_completions: bool = True,
    ) -> "LLMControlConfig":
        from application.ai.llm_control_service import LLMProfile

        validated_url = validate_loopback_gateway_url(
            base_url,
            resolver=self._dns_resolver,
        )
        clean_main = (main_model or "").strip()
        if not clean_main:
            raise ValueError("必须指定主力模型（main_model）")

        clean_cheap = (cheap_model or "").strip() or clean_main
        clean_kg = (kg_model or "").strip() or clean_cheap
        label_suffix = f"（{name.strip()}）" if (name or "").strip() else ""

        control = self._get_control_service()

        def _mutate(cfg: "LLMControlConfig") -> "LLMControlConfig":
            def _upsert(profile_id: str, new_profile: LLMProfile) -> None:
                for idx, existing in enumerate(cfg.profiles):
                    if existing.id == profile_id:
                        cfg.profiles[idx] = new_profile
                        return
                cfg.profiles.append(new_profile)

            main_profile = LLMProfile(
                id="local-gateway-main",
                name=f"主力模型{label_suffix}",
                preset_key="custom-openai-compatible",
                protocol="openai",
                base_url=validated_url,
                api_key="",
                model=clean_main,
                auth_mode="local_gateway",
                use_legacy_chat_completions=use_legacy_chat_completions,
                notes="本机回环订阅网关（主力创作与核心大纲）",
            )
            _upsert("local-gateway-main", main_profile)

            if enable_golden_roles:
                cheap_profile = LLMProfile(
                    id="local-gateway-cheap",
                    name="经济模型",
                    preset_key="custom-openai-compatible",
                    protocol="openai",
                    base_url=validated_url,
                    api_key="",
                    model=clean_cheap,
                    auth_mode="local_gateway",
                    use_legacy_chat_completions=use_legacy_chat_completions,
                    notes="本机回环订阅网关（章后摘要与常规巡检）",
                )
                kg_profile = LLMProfile(
                    id="local-gateway-kg",
                    name="知识图谱模型",
                    preset_key="custom-openai-compatible",
                    protocol="openai",
                    base_url=validated_url,
                    api_key="",
                    model=clean_kg,
                    auth_mode="local_gateway",
                    use_legacy_chat_completions=use_legacy_chat_completions,
                    notes="本机回环订阅网关（三元组与状态结构化抽取）",
                )
                _upsert("local-gateway-cheap", cheap_profile)
                _upsert("local-gateway-kg", kg_profile)
                cfg.endpoint_mode = "independent"
                cfg.role_bindings = {
                    "main": "local-gateway-main",
                    "cheap": "local-gateway-cheap",
                    "kg": "local-gateway-kg",
                }
            else:
                cfg.endpoint_mode = "unified"
                cfg.role_bindings = {"main": "local-gateway-main"}

            cfg.active_profile_id = "local-gateway-main"
            return cfg

        return control.mutate_config(_mutate)
