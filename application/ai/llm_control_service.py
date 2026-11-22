from __future__ import annotations

import json
import logging
import threading
from time import perf_counter
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from application.ai.local_gateway_probe import validate_loopback_gateway_url
from domain.ai.errors import LLMNotConfiguredError
from domain.ai.services.llm_service import DEFAULT_MAX_OUTPUT_TOKENS
from infrastructure.ai.llm_environment import LLMEnvironmentSettings
from infrastructure.ai.oauth_credential_store import (
    OAuthCredentialStore,
    VALID_OAUTH_PROVIDERS,
    get_oauth_credential_store,
)
from infrastructure.ai.url_utils import (
    normalize_anthropic_base_url,
    normalize_gemini_base_url,
    normalize_openai_base_url,
)
from infrastructure.persistence.database.connection import get_database
from infrastructure.persistence.database.write_dispatch import (
    sqlite_writes_bypass_queue,
)

if TYPE_CHECKING:
    from application.ai.llm_oauth_service import LLMOAuthService
    from domain.ai.services.llm_service import LLMService

logger = logging.getLogger(__name__)

LLMProtocol = Literal['openai', 'anthropic', 'gemini']
LLMEndpointMode = Literal['unified', 'independent']
LLMAuthMode = Literal['api_key', 'oauth', 'local_gateway']
LLMRoleName = Literal['main', 'cheap', 'kg']

VALID_LLM_ROLES: tuple[str, ...] = ('main', 'cheap', 'kg')
MASKED_SECRET_SENTINEL = '__plotpilot_stored_secret__'
_LLM_CONFIG_WRITE_LOCK = threading.RLock()

_FORBIDDEN_CREDENTIAL_HEADERS: frozenset[str] = frozenset(
    {
        'authorization',
        'proxy-authorization',
        'x-api-key',
        'api-key',
        'apikey',
        'x-goog-api-key',
        'anthropic-api-key',
        'openai-api-key',
        'cookie',
        'set-cookie',
        'x-auth-token',
        'x-access-token',
        'x-csrf-token',
        'x-session-token',
    }
)
_FORBIDDEN_CREDENTIAL_HEADER_TOKENS: tuple[str, ...] = (
    'api-key',
    'apikey',
    'api_key',
    'secret',
    'password',
    'passwd',
    'access-token',
    'access_token',
    'refresh-token',
    'refresh_token',
    'auth-token',
    'auth_token',
    'bearer',
    'private-key',
)
_FORBIDDEN_CREDENTIAL_QUERY_KEYS: frozenset[str] = frozenset(
    {
        'key',
        'api_key',
        'apikey',
        'api-key',
        'access_token',
        'access-token',
        'refresh_token',
        'refresh-token',
        'client_secret',
        'client-secret',
        'token',
        'secret',
        'password',
        'auth',
        'authorization',
    }
)


def _is_credential_header_name(name: str) -> bool:
    low = str(name or '').strip().lower()
    if not low:
        return False
    if low in _FORBIDDEN_CREDENTIAL_HEADERS:
        return True
    return any(tok in low for tok in _FORBIDDEN_CREDENTIAL_HEADER_TOKENS)


def _is_credential_query_key(name: str) -> bool:
    low = str(name or '').strip().lower()
    if not low:
        return False
    if low in _FORBIDDEN_CREDENTIAL_QUERY_KEYS:
        return True
    return any(
        tok in low
        for tok in ('api_key', 'apikey', 'secret', 'password', 'access_token', 'refresh_token')
    )


def _validate_safe_extra_headers(value: Dict[str, Any] | None) -> Dict[str, str]:
    cleaned: Dict[str, str] = {}
    for raw_k, raw_v in (value or {}).items():
        k = str(raw_k).strip()
        v = str(raw_v).strip()
        if not k or not v:
            continue
        if _is_credential_header_name(k):
            raise ValueError(
                f'extra_headers 不允许包含认证或密钥请求头 ({k})，请使用专属 API Key 或 OAuth 授权通道'
            )
        cleaned[k] = v
    return cleaned


def _scrub_extra_headers(value: Dict[str, Any] | None) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(k).strip(): str(v).strip()
        for k, v in value.items()
        if str(k).strip() and str(v).strip() and not _is_credential_header_name(str(k))
    }


def _validate_safe_extra_query(value: Dict[str, Any] | None) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for raw_k, raw_v in (value or {}).items():
        k = str(raw_k).strip()
        if not k:
            continue
        if _is_credential_query_key(k):
            raise ValueError(
                f'extra_query 不允许包含认证或密钥查询参数 ({k})，请使用专属 API Key 或 OAuth 授权通道'
            )
        cleaned[k] = raw_v
    return cleaned


def _scrub_extra_query(value: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        str(k).strip(): v
        for k, v in value.items()
        if str(k).strip() and not _is_credential_query_key(str(k))
    }


def _validate_and_split_origin_url(
    url_text: str,
    *,
    allow_schemeless: bool = True,
) -> Optional[tuple[str, str, int, str]]:
    s = (url_text or '').strip()
    if not s or any(ch.isspace() or ord(ch) < 32 for ch in s):
        return None
    if '?' in s or '#' in s:
        return None
    if '://' in s:
        scheme_prefix = s.split('://', 1)[0].lower()
        if scheme_prefix not in ('http', 'https'):
            return None
        candidate = s
    else:
        if not allow_schemeless:
            return None
        candidate = f'https://{s}'

    try:
        parsed = urlsplit(candidate)
        scheme = (parsed.scheme or '').lower()
        if scheme not in ('http', 'https'):
            return None
        netloc = parsed.netloc or ''
        if parsed.username is not None or parsed.password is not None or '@' in netloc:
            return None
        if parsed.query or parsed.fragment:
            return None

        if netloc.startswith('['):
            if ']' not in netloc:
                return None
            after_bracket = netloc.split(']', 1)[1]
            if after_bracket:
                if not after_bracket.startswith(':'):
                    return None
                port_token = after_bracket[1:]
                if not port_token or not port_token.isascii() or not port_token.isdigit():
                    return None
        elif ':' in netloc:
            host_part, port_token = netloc.rsplit(':', 1)
            if ':' in host_part or not port_token or not port_token.isascii() or not port_token.isdigit():
                return None

        port = parsed.port
        if port is not None and not (1 <= port <= 65535):
            return None

        host = (parsed.hostname or '').strip().lower().rstrip('.')
    except ValueError:
        return None

    if not host:
        return None

    effective_port = port if port is not None else (443 if scheme == 'https' else 80)
    clean_path = (parsed.path or '').rstrip('/')
    return (scheme, host, effective_port, clean_path)


def _sanitize_public_base_url(
    url_text: Optional[str],
    *,
    auth_mode: str = 'api_key',
) -> str:
    raw = (url_text or '').strip()
    if not raw:
        return ''
    if auth_mode == 'local_gateway':
        try:
            return validate_loopback_gateway_url(raw)
        except ValueError:
            return ''
    if _validate_and_split_origin_url(raw, allow_schemeless=True) is None:
        return ''
    return raw


class LLMPreset(BaseModel):
    key: str
    label: str
    protocol: LLMProtocol
    default_base_url: str = ''
    default_model: str = ''
    description: str = ''
    tags: List[str] = Field(default_factory=list)


class LLMProfile(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: str
    name: str
    preset_key: str = 'custom-openai-compatible'
    protocol: LLMProtocol = 'openai'
    base_url: str = ''
    api_key: str = ''
    model: str = ''
    temperature: float = 0.7
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    timeout_seconds: int = 300
    extra_headers: Dict[str, str] = Field(default_factory=dict)
    extra_query: Dict[str, Any] = Field(default_factory=dict)
    extra_body: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ''
    use_legacy_chat_completions: bool = False
    auth_mode: LLMAuthMode = 'api_key'
    oauth_provider: str = ''
    oauth_session_id: str = ''
    has_secret: bool = False

    @field_validator('temperature')
    @classmethod
    def _validate_temperature(cls, value: float) -> float:
        if not 0 <= value <= 2:
            raise ValueError('temperature must be between 0 and 2')
        return value

    @field_validator('max_tokens')
    @classmethod
    def _validate_max_tokens(cls, value: int) -> int:
        if value <= 0:
            raise ValueError('value must be positive')
        return max(value, DEFAULT_MAX_OUTPUT_TOKENS)

    @field_validator('timeout_seconds')
    @classmethod
    def _validate_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError('value must be positive')
        return value

    @field_validator('extra_headers')
    @classmethod
    def _normalize_headers(cls, value: Dict[str, str]) -> Dict[str, str]:
        return _validate_safe_extra_headers(value)

    @field_validator('extra_query')
    @classmethod
    def _normalize_query(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        return _validate_safe_extra_query(value)

    @model_validator(mode='after')
    def _sync_secret_indicator(self) -> 'LLMProfile':
        if self.auth_mode == 'api_key':
            self.has_secret = bool(self.api_key and self.api_key.strip())
        elif self.auth_mode == 'oauth':
            self.has_secret = bool(self.oauth_session_id and self.oauth_session_id.strip())
        else:
            self.has_secret = False
        return self


class LLMControlConfig(BaseModel):
    version: int = 1
    active_profile_id: Optional[str] = None
    #: 统一 = 单档案主力端点；独立 = 主力 / 经济 / 知识图谱 等分档案（持久化在 llm_config_meta）
    endpoint_mode: LLMEndpointMode = 'unified'
    role_bindings: Dict[str, str] = Field(default_factory=dict)
    profiles: List[LLMProfile] = Field(default_factory=list)

    @model_validator(mode='after')
    def _validate_active_profile(self) -> 'LLMControlConfig':
        if not self.profiles:
            self.role_bindings = {}
            return self
        ids = [profile.id for profile in self.profiles]
        id_set = set(ids)
        if not self.active_profile_id or self.active_profile_id not in id_set:
            self.active_profile_id = ids[0]
        if self.endpoint_mode not in ('unified', 'independent'):
            self.endpoint_mode = 'unified'
        cleaned_bindings: Dict[str, str] = {}
        for role_key, bound_id in (self.role_bindings or {}).items():
            rk = str(role_key or '').strip()
            bid = str(bound_id or '').strip()
            if rk in VALID_LLM_ROLES and bid in id_set:
                cleaned_bindings[rk] = bid
        self.role_bindings = cleaned_bindings
        return self


class LLMRuntimeSummary(BaseModel):
    source: Literal['profile', 'mock']
    active_profile_id: Optional[str] = None
    active_profile_name: Optional[str] = None
    protocol: Optional[LLMProtocol] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    using_mock: bool = False
    reason: Optional[str] = None


class LLMControlPanelData(BaseModel):
    config: LLMControlConfig
    presets: List[LLMPreset]
    runtime: LLMRuntimeSummary


class LLMTestResult(BaseModel):
    ok: bool
    provider_label: str
    model: str
    latency_ms: int
    preview: str = ''
    error: Optional[str] = None


class LLMControlService:
    """LLM 控制面板服务 —— 配置持久化到 SQLite（OAuth 令牌独立存于 0600 文件）。"""

    def __init__(
        self,
        *,
        db_provider: Optional[Callable[[], Any]] = None,
        oauth_credential_store: Optional[OAuthCredentialStore] = None,
        oauth_service: Optional['LLMOAuthService'] = None,
    ) -> None:
        self._db_provider = db_provider or get_database
        self._oauth_store = oauth_credential_store
        self._oauth_service = oauth_service
        self._schema_checked = False

    # ---- 内部 DB 与 OAuth 辅助 ---------------------------------------

    def _db(self):
        db = self._db_provider()
        if not self._schema_checked:
            with _LLM_CONFIG_WRITE_LOCK:
                if not self._schema_checked:
                    if self._ensure_schema(db):
                        self._schema_checked = True
        return db

    def _get_oauth_store(self) -> OAuthCredentialStore:
        if self._oauth_store is None:
            self._oauth_store = get_oauth_credential_store()
        return self._oauth_store

    def _get_oauth_service(self) -> 'LLMOAuthService':
        if self._oauth_service is None:
            from application.ai.llm_oauth_service import LLMOAuthService

            self._oauth_service = LLMOAuthService(
                credential_store=self._get_oauth_store(),
                control_service=self,
            )
        return self._oauth_service

    @staticmethod
    def _ensure_schema(db: Any) -> bool:
        """幂等补齐旧 SQLite 库中 llm_profiles 的 OAuth / auth_mode 列。

        仅在 llm_profiles 已存在且列已补齐时返回 True。若连接上已存在调用方未提交事务且
        表结构需要执行 DDL 迁移，则显式抛出 RuntimeError 拒绝迁移，绝不隐式提交调用方事务。
        """
        alters = {
            'auth_mode': "ALTER TABLE llm_profiles ADD COLUMN auth_mode TEXT NOT NULL DEFAULT 'api_key'",
            'oauth_provider': "ALTER TABLE llm_profiles ADD COLUMN oauth_provider TEXT NOT NULL DEFAULT ''",
            'oauth_session_id': "ALTER TABLE llm_profiles ADD COLUMN oauth_session_id TEXT NOT NULL DEFAULT ''",
        }
        if hasattr(db, 'get_connection'):
            conn = db.get_connection()
            raw_rows = conn.execute("PRAGMA table_info(llm_profiles)").fetchall()
            if not raw_rows:
                return False
            cols = {
                str(dict(r).get('name') if hasattr(r, 'keys') else r[1])
                for r in raw_rows
            }
            if all(col in cols for col in alters):
                return True
            if conn.in_transaction:
                raise RuntimeError(
                    'SQLite 连接在执行 LLM 配置表结构迁移前已处于未提交事务状态'
                )
            with sqlite_writes_bypass_queue():
                conn.execute("BEGIN IMMEDIATE")
                try:
                    recheck_rows = conn.execute(
                        "PRAGMA table_info(llm_profiles)"
                    ).fetchall()
                    recheck_cols = {
                        str(dict(r).get('name') if hasattr(r, 'keys') else r[1])
                        for r in recheck_rows
                    }
                    for col, sql in alters.items():
                        if col not in recheck_cols:
                            conn.execute(sql)
                    conn.commit()
                    if hasattr(db, '_maybe_checkpoint'):
                        db._maybe_checkpoint()
                except Exception:
                    if conn.in_transaction:
                        conn.rollback()
                    raise
            return True

        rows = db.fetch_all("PRAGMA table_info(llm_profiles)")
        if not rows:
            return False
        cols = {str(r.get('name') or '') for r in rows if isinstance(r, dict)}
        if not cols:
            return False
        if all(col in cols for col in alters):
            return True
        if getattr(db, 'in_transaction', False):
            raise RuntimeError(
                '数据库适配器在执行 LLM 配置表结构迁移前已处于未提交事务状态'
            )
        with sqlite_writes_bypass_queue():
            for col, sql in alters.items():
                if col not in cols:
                    db.execute(sql)
            db.commit()
        return True

    def _get_meta(self, key: str, default: str = '') -> str:
        row = self._db().fetch_one(
            "SELECT value FROM llm_config_meta WHERE key = ?", (key,)
        )
        return row['value'] if row else default

    def _set_meta(self, key: str, value: str) -> None:
        self._db().execute(
            "INSERT OR REPLACE INTO llm_config_meta (key, value) VALUES (?, ?)",
            (key, value),
        )

    def _row_to_profile(self, row: dict) -> LLMProfile:
        raw_auth_mode = str(row.get('auth_mode') or 'api_key').strip()
        auth_mode: LLMAuthMode = (
            raw_auth_mode  # type: ignore[assignment]
            if raw_auth_mode in ('api_key', 'oauth', 'local_gateway')
            else 'api_key'
        )
        try:
            parsed_headers = json.loads(row.get('extra_headers') or '{}')
        except ValueError:
            parsed_headers = {}
        try:
            parsed_query = json.loads(row.get('extra_query') or '{}')
        except ValueError:
            parsed_query = {}
        try:
            parsed_body = json.loads(row.get('extra_body') or '{}')
        except ValueError:
            parsed_body = {}
        return LLMProfile(
            id=row['id'],
            name=row['name'],
            preset_key=row['preset_key'],
            protocol=row['protocol'],
            base_url=row['base_url'] or '',
            api_key=row['api_key'] or '',
            model=row['model'] or '',
            temperature=row['temperature'],
            max_tokens=int(row.get('max_tokens') or DEFAULT_MAX_OUTPUT_TOKENS),
            timeout_seconds=row['timeout_seconds'],
            extra_headers=_scrub_extra_headers(parsed_headers),
            extra_query=_scrub_extra_query(parsed_query),
            extra_body=parsed_body if isinstance(parsed_body, dict) else {},
            notes=row['notes'] or '',
            use_legacy_chat_completions=bool(row.get('use_legacy_chat_completions', 0)),
            auth_mode=auth_mode,
            oauth_provider=str(row.get('oauth_provider') or ''),
            oauth_session_id=str(row.get('oauth_session_id') or ''),
        )

    def _profile_to_row(self, p: LLMProfile) -> dict:
        return dict(
            id=p.id,
            name=p.name,
            preset_key=p.preset_key,
            protocol=p.protocol,
            base_url=p.base_url,
            api_key='' if p.auth_mode in ('oauth', 'local_gateway') else p.api_key,
            model=p.model,
            temperature=p.temperature,
            max_tokens=p.max_tokens,
            timeout_seconds=p.timeout_seconds,
            extra_headers=json.dumps(_scrub_extra_headers(p.extra_headers), ensure_ascii=False),
            extra_query=json.dumps(_scrub_extra_query(p.extra_query), ensure_ascii=False),
            extra_body=json.dumps(p.extra_body, ensure_ascii=False),
            notes=p.notes,
            use_legacy_chat_completions=int(p.use_legacy_chat_completions),
            auth_mode=p.auth_mode,
            oauth_provider=p.oauth_provider,
            oauth_session_id=p.oauth_session_id,
        )

    def _fetch_stored_profiles_map(self) -> Dict[str, LLMProfile]:
        try:
            rows = self._db().fetch_all(
                "SELECT * FROM llm_profiles ORDER BY sort_order, created_at"
            )
            return {r['id']: self._row_to_profile(r) for r in rows if r.get('id')}
        except Exception:
            return {}

    # ---- 密钥脱敏与同源保护 -------------------------------------------

    def _credential_origin(
        self, profile: LLMProfile
    ) -> Optional[tuple[str, str, str, int, str]]:
        preset = self.get_preset_map().get(profile.preset_key)
        protocol: LLMProtocol = profile.protocol or (
            preset.protocol if preset else 'openai'
        )
        explicit_base = (profile.base_url or '').strip()
        if explicit_base:
            if _validate_and_split_origin_url(explicit_base, allow_schemeless=True) is None:
                return None

        raw_base = explicit_base or (preset.default_base_url if preset else '')
        if not raw_base:
            if protocol == 'anthropic':
                raw_base = 'https://api.anthropic.com'
            elif protocol == 'gemini':
                raw_base = 'https://generativelanguage.googleapis.com/v1beta'
            else:
                raw_base = 'https://api.openai.com/v1'

        if _validate_and_split_origin_url(raw_base, allow_schemeless=True) is None:
            return None

        normalized = self._normalize_base_url(protocol, raw_base)
        parsed_origin = _validate_and_split_origin_url(normalized, allow_schemeless=True)
        if parsed_origin is None:
            return None
        scheme, host, effective_port, clean_path = parsed_origin
        return (protocol, scheme, host, effective_port, clean_path)

    def _same_credential_target(
        self, existing: LLMProfile, candidate: LLMProfile
    ) -> bool:
        existing_origin = self._credential_origin(existing)
        candidate_origin = self._credential_origin(candidate)
        if existing_origin is None or candidate_origin is None:
            return False
        return existing_origin == candidate_origin

    def assert_masked_secret_target_matches(
        self, existing: Optional[LLMProfile], candidate: LLMProfile
    ) -> str:
        """Strictly authorize MASKED_SECRET_SENTINEL reuse only on an identical valid target."""
        if (
            existing is None
            or existing.auth_mode != 'api_key'
            or not (existing.api_key and existing.api_key.strip())
        ):
            raise ValueError('未找到已保存的 API Key，请重新输入对应的密钥')
        if not self._same_credential_target(existing, candidate):
            raise ValueError('修改网关地址或协议后，请重新输入对应的 API Key')
        return existing.api_key.strip()

    def redact_profile(self, profile: LLMProfile) -> LLMProfile:
        safe_headers = _scrub_extra_headers(profile.extra_headers)
        safe_query = _scrub_extra_query(profile.extra_query)
        safe_base_url = _sanitize_public_base_url(
            profile.base_url, auth_mode=profile.auth_mode
        )
        if profile.auth_mode == 'oauth':
            from application.ai.llm_oauth_service import get_canonical_oauth_spec

            prov = profile.oauth_provider.strip()
            sid = profile.oauth_session_id.strip()
            effective_prov = prov or sid
            try:
                oauth_base_url = (
                    get_canonical_oauth_spec(effective_prov).base_url
                    if effective_prov
                    else ''
                )
            except ValueError:
                oauth_base_url = ''
            has_oauth = bool(
                sid
                and (not prov or sid == prov)
                and self._get_oauth_store().get_session(sid) is not None
            )
            return profile.model_copy(
                update={
                    'base_url': oauth_base_url,
                    'api_key': '',
                    'has_secret': has_oauth,
                    'extra_headers': safe_headers,
                    'extra_query': safe_query,
                }
            )
        if profile.auth_mode == 'local_gateway':
            return profile.model_copy(
                update={
                    'base_url': safe_base_url,
                    'api_key': '',
                    'has_secret': False,
                    'extra_headers': safe_headers,
                    'extra_query': safe_query,
                }
            )
        has_key = bool(profile.api_key and profile.api_key.strip())
        return profile.model_copy(
            update={
                'base_url': safe_base_url,
                'api_key': MASKED_SECRET_SENTINEL if has_key else '',
                'has_secret': has_key,
                'extra_headers': safe_headers,
                'extra_query': safe_query,
            }
        )

    def redact_config(self, config: LLMControlConfig) -> LLMControlConfig:
        return config.model_copy(
            update={'profiles': [self.redact_profile(p) for p in config.profiles]}
        )

    def redact_runtime_summary(
        self, runtime: LLMRuntimeSummary
    ) -> LLMRuntimeSummary:
        safe_base = _sanitize_public_base_url(runtime.base_url) or None
        return runtime.model_copy(update={'base_url': safe_base})

    def redact_panel_data(self, panel: LLMControlPanelData) -> LLMControlPanelData:
        return panel.model_copy(
            update={
                'config': self.redact_config(panel.config),
                'runtime': self.redact_runtime_summary(panel.runtime),
            }
        )

    # ---- 公共接口 -----------------------------------------------------

    def get_presets(self) -> List[LLMPreset]:
        return [
            LLMPreset(
                key='custom-openai-compatible',
                label='OpenAI 兼容 / 国产通用',
                protocol='openai',
                default_base_url='',
                default_model='',
                description='适用于所有 OpenAI-compatible 网关：OpenAI、DeepSeek、Qwen、GLM、豆包、SiliconFlow、OpenRouter 等。',
                tags=['custom', 'openai-compatible', 'domestic'],
            ),
            LLMPreset(
                key='openrouter',
                label='OpenRouter（聚合 / OAuth）',
                protocol='openai',
                default_base_url='https://openrouter.ai/api/v1',
                default_model='anthropic/claude-3.7-sonnet',
                description='OpenRouter 官方网关，支持公开 OAuth PKCE 一键免密连接或 API Key 接入。',
                tags=['official', 'oauth'],
            ),
            LLMPreset(
                key='openai-official',
                label='OpenAI 官方',
                protocol='openai',
                default_base_url='https://api.openai.com/v1',
                default_model='',
                description='OpenAI 官方接口（自动兼容底层 Responses API 与 Chat Completions）。导入后请在「模型名」填写所用模型 ID。',
                tags=['official'],
            ),
            LLMPreset(
                key='claude-official',
                label='Claude / Anthropic 官方',
                protocol='anthropic',
                default_base_url='https://api.anthropic.com',
                default_model='',
                description='Anthropic Messages 接口；也可接入 Claude-compatible 网关。请填写网关文档中的模型 ID。',
                tags=['official'],
            ),
            LLMPreset(
                key='gemini-official',
                label='Gemini / Google 官方',
                protocol='gemini',
                default_base_url='https://generativelanguage.googleapis.com/v1beta',
                default_model='',
                description='Gemini generateContent / streamGenerateContent 接口。请填写 Google 文档中的模型 ID。',
                tags=['official'],
            ),
            LLMPreset(
                key='deepseek',
                label='DeepSeek',
                protocol='openai',
                default_base_url='https://api.deepseek.com/v1',
                default_model='',
                description='DeepSeek 官方 OpenAI-compatible 接口。模型名以官方文档为准。',
                tags=['domestic', 'preset'],
            ),
            LLMPreset(
                key='qwen-dashscope',
                label='Qwen / DashScope',
                protocol='openai',
                default_base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
                default_model='',
                description='阿里云百炼 / DashScope OpenAI-compatible 接口。模型名以控制台为准。',
                tags=['domestic', 'preset'],
            ),
            LLMPreset(
                key='glm-openai',
                label='智谱 GLM（OpenAI 兼容）',
                protocol='openai',
                default_base_url='https://open.bigmodel.cn/api/paas/v4',
                default_model='',
                description='智谱 OpenAI-compatible 接口。模型名以智谱文档为准。',
                tags=['domestic', 'preset'],
            ),
            LLMPreset(
                key='glm-anthropic',
                label='智谱 GLM（Claude 兼容）',
                protocol='anthropic',
                default_base_url='https://open.bigmodel.cn/api/anthropic',
                default_model='',
                description='智谱 Anthropic-compatible 接口。模型名以智谱文档为准。',
                tags=['domestic', 'preset'],
            ),
            LLMPreset(
                key='doubao-ark',
                label='豆包 / 火山方舟 Ark',
                protocol='openai',
                default_base_url='https://ark.cn-beijing.volces.com/api/v3',
                default_model='',
                description='方舟 OpenAI-compatible 接口；模型名以方舟控制台 Endpoint 为准。',
                tags=['domestic', 'preset'],
            ),
        ]

    def get_preset_map(self) -> Dict[str, LLMPreset]:
        return {preset.key: preset for preset in self.get_presets()}

    def get_control_panel_data(self, *, redact_secrets: bool = False) -> LLMControlPanelData:
        config = self.get_config()
        panel = LLMControlPanelData(
            config=config,
            presets=self.get_presets(),
            runtime=self.get_runtime_summary(config),
        )
        return self.redact_panel_data(panel) if redact_secrets else panel

    _INSERT_PROFILE_SQL = """INSERT INTO llm_profiles (
            id, name, preset_key, protocol, base_url, api_key, model,
            temperature, max_tokens, timeout_seconds,
            extra_headers, extra_query, extra_body, notes,
            use_legacy_chat_completions,
            auth_mode, oauth_provider, oauth_session_id,
            sort_order
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""

    def _read_snapshot_from_conn(
        self, conn: Any
    ) -> tuple[List[LLMProfile], Dict[str, LLMProfile], Dict[str, str]]:
        raw_rows = conn.execute(
            "SELECT * FROM llm_profiles ORDER BY sort_order, created_at"
        ).fetchall()
        profiles: List[LLMProfile] = []
        existing_by_id: Dict[str, LLMProfile] = {}
        for raw_row in raw_rows:
            row_dict = dict(raw_row)
            prof = self._row_to_profile(row_dict)
            profiles.append(prof)
            row_id = row_dict.get('id')
            if row_id:
                existing_by_id[str(row_id)] = prof

        meta_rows = conn.execute(
            "SELECT key, value FROM llm_config_meta"
        ).fetchall()
        meta_map: Dict[str, str] = {}
        for raw_meta in meta_rows:
            md = dict(raw_meta)
            mk = md.get('key')
            if mk is not None:
                meta_map[str(mk)] = str(md.get('value') or '')
        return profiles, existing_by_id, meta_map

    def _read_snapshot_from_adapter(
        self, db: Any
    ) -> tuple[List[LLMProfile], Dict[str, LLMProfile], Dict[str, str]]:
        rows = db.fetch_all(
            "SELECT * FROM llm_profiles ORDER BY sort_order, created_at"
        )
        profiles: List[LLMProfile] = []
        existing_by_id: Dict[str, LLMProfile] = {}
        for row in rows:
            prof = self._row_to_profile(row)
            profiles.append(prof)
            row_id = row.get('id')
            if row_id:
                existing_by_id[str(row_id)] = prof

        meta_rows = db.fetch_all("SELECT key, value FROM llm_config_meta")
        meta_map: Dict[str, str] = {}
        for mr in meta_rows:
            mk = mr.get('key')
            if mk is not None:
                meta_map[str(mk)] = str(mr.get('value') or '')
        return profiles, existing_by_id, meta_map

    def _assemble_config_from_snapshot(
        self,
        profiles: List[LLMProfile],
        meta_map: Dict[str, str],
    ) -> LLMControlConfig:
        active_id = meta_map.get('active_profile_id', '')
        valid_ids = {p.id for p in profiles}
        if not active_id or active_id not in valid_ids:
            active_id = profiles[0].id

        endpoint_mode = meta_map.get('endpoint_mode', '')
        if endpoint_mode not in ('unified', 'independent'):
            endpoint_mode = self._infer_endpoint_mode_from_profiles(profiles)

        raw_bindings = meta_map.get('role_bindings', '{}')
        try:
            parsed_bindings = json.loads(raw_bindings) if raw_bindings else {}
        except ValueError:
            parsed_bindings = {}
        if not isinstance(parsed_bindings, dict):
            parsed_bindings = {}

        return LLMControlConfig(
            version=1,
            active_profile_id=active_id,
            endpoint_mode=endpoint_mode,  # type: ignore[arg-type]
            role_bindings=parsed_bindings,
            profiles=profiles,
        )

    def _build_profile_insert_params(
        self, profiles: List[LLMProfile]
    ) -> List[tuple[Any, ...]]:
        params_list: List[tuple[Any, ...]] = []
        for idx, profile in enumerate(profiles):
            row = self._profile_to_row(profile)
            row['sort_order'] = idx
            params_list.append((
                row['id'], row['name'], row['preset_key'], row['protocol'],
                row['base_url'], row['api_key'], row['model'],
                row['temperature'], row['max_tokens'], row['timeout_seconds'],
                row['extra_headers'], row['extra_query'], row['extra_body'],
                row['notes'], row['use_legacy_chat_completions'],
                row['auth_mode'], row['oauth_provider'], row['oauth_session_id'],
                row['sort_order'],
            ))
        return params_list

    def _write_config_to_conn(self, conn: Any, sanitized: LLMControlConfig) -> None:
        conn.execute("DELETE FROM llm_profiles")
        conn.execute("DELETE FROM llm_config_meta")
        conn.executemany(
            "INSERT OR REPLACE INTO llm_config_meta (key, value) VALUES (?, ?)",
            [
                ('active_profile_id', sanitized.active_profile_id or ''),
                ('endpoint_mode', sanitized.endpoint_mode),
                (
                    'role_bindings',
                    json.dumps(sanitized.role_bindings, ensure_ascii=False),
                ),
            ],
        )
        params_list = self._build_profile_insert_params(sanitized.profiles)
        if params_list:
            conn.executemany(self._INSERT_PROFILE_SQL, params_list)

    def _write_config_to_adapter(self, db: Any, sanitized: LLMControlConfig) -> None:
        db.execute("DELETE FROM llm_profiles")
        db.execute("DELETE FROM llm_config_meta")
        db.execute(
            "INSERT OR REPLACE INTO llm_config_meta (key, value) VALUES (?, ?)",
            ('active_profile_id', sanitized.active_profile_id or ''),
        )
        db.execute(
            "INSERT OR REPLACE INTO llm_config_meta (key, value) VALUES (?, ?)",
            ('endpoint_mode', sanitized.endpoint_mode),
        )
        db.execute(
            "INSERT OR REPLACE INTO llm_config_meta (key, value) VALUES (?, ?)",
            ('role_bindings', json.dumps(sanitized.role_bindings, ensure_ascii=False)),
        )
        params_list = self._build_profile_insert_params(sanitized.profiles)
        if params_list:
            db.execute_many(self._INSERT_PROFILE_SQL, params_list)

    def _run_in_write_transaction(
        self,
        conn_work: Callable[[Any], LLMControlConfig],
        adapter_work: Callable[[Any], LLMControlConfig],
    ) -> LLMControlConfig:
        with _LLM_CONFIG_WRITE_LOCK, sqlite_writes_bypass_queue():
            db = self._db()
            if hasattr(db, 'get_connection'):
                conn = db.get_connection()
                if conn.in_transaction:
                    raise RuntimeError(
                        'SQLite 连接在进入 LLM 配置原子事务前已处于未提交事务状态'
                    )
                conn.execute("BEGIN IMMEDIATE")
                try:
                    result = conn_work(conn)
                    conn.commit()
                    if hasattr(db, '_maybe_checkpoint'):
                        db._maybe_checkpoint()
                    return result
                except Exception:
                    if conn.in_transaction:
                        conn.rollback()
                    raise
            return adapter_work(db)

    def get_config(self) -> LLMControlConfig:
        """从数据库读取完整配置；仅在 IMMEDIATE 写事务重检仍为空库时写入初始默认值。"""
        db = self._db()
        if hasattr(db, 'get_connection'):
            conn = db.get_connection()
            started_read_tx = False
            if not conn.in_transaction:
                conn.execute("BEGIN")
                started_read_tx = True
            try:
                profiles, _, meta_map = self._read_snapshot_from_conn(conn)
            except Exception:
                if started_read_tx and conn.in_transaction:
                    conn.rollback()
                raise
            else:
                if started_read_tx and conn.in_transaction:
                    conn.commit()
        else:
            profiles, _, meta_map = self._read_snapshot_from_adapter(db)

        if profiles:
            return self._assemble_config_from_snapshot(profiles, meta_map)

        def _init_conn(conn: Any) -> LLMControlConfig:
            rechecked_profiles, _, rechecked_meta = self._read_snapshot_from_conn(conn)
            if rechecked_profiles:
                return self._assemble_config_from_snapshot(
                    rechecked_profiles, rechecked_meta
                )
            sanitized = self._sanitize_config(
                self._build_initial_config(), existing_by_id={}
            )
            self._write_config_to_conn(conn, sanitized)
            logger.info(
                "LLM 初始默认配置已写入数据库 (%d 个 profiles)",
                len(sanitized.profiles),
            )
            return sanitized

        def _init_adapter(adapter: Any) -> LLMControlConfig:
            rechecked_profiles, _, rechecked_meta = self._read_snapshot_from_adapter(
                adapter
            )
            if rechecked_profiles:
                return self._assemble_config_from_snapshot(
                    rechecked_profiles, rechecked_meta
                )
            sanitized = self._sanitize_config(
                self._build_initial_config(), existing_by_id={}
            )
            self._write_config_to_adapter(adapter, sanitized)
            return sanitized

        return self._run_in_write_transaction(_init_conn, _init_adapter)

    @staticmethod
    def _infer_endpoint_mode_from_profiles(profiles: List[LLMProfile]) -> LLMEndpointMode:
        """无 meta 时的向后兼容：存在「经济模型」「知识图谱模型」档案则视为独立端点 UI。"""
        for p in profiles:
            n = p.name or ''
            if '经济模型' in n or '知识图谱' in n or '知识图谱模型' in n:
                return 'independent'
        return 'unified'

    def save_config(self, config: LLMControlConfig) -> LLMControlConfig:
        """将配置全量原子写入数据库（在单次 IMMEDIATE 事务与写锁内完成读取、掩码同源校验与替换写入）。"""

        def _save_conn(conn: Any) -> LLMControlConfig:
            _, existing_by_id, _ = self._read_snapshot_from_conn(conn)
            sanitized = self._sanitize_config(config, existing_by_id=existing_by_id)
            self._write_config_to_conn(conn, sanitized)
            return sanitized

        def _save_adapter(adapter: Any) -> LLMControlConfig:
            _, existing_by_id, _ = self._read_snapshot_from_adapter(adapter)
            sanitized = self._sanitize_config(config, existing_by_id=existing_by_id)
            self._write_config_to_adapter(adapter, sanitized)
            return sanitized

        sanitized = self._run_in_write_transaction(_save_conn, _save_adapter)
        logger.info("LLM 配置已保存到数据库 (%d 个 profiles)", len(sanitized.profiles))
        return sanitized

    def mutate_config(
        self, mutator: Callable[[LLMControlConfig], LLMControlConfig]
    ) -> LLMControlConfig:
        """在同一个 IMMEDIATE 事务内原子完成最新配置快照读取、变更派生、掩码校验与持久化。"""

        def _mutate_conn(conn: Any) -> LLMControlConfig:
            profiles, existing_by_id, meta_map = self._read_snapshot_from_conn(conn)
            current_cfg = (
                self._assemble_config_from_snapshot(profiles, meta_map)
                if profiles
                else self._sanitize_config(
                    self._build_initial_config(), existing_by_id={}
                )
            )
            updated_cfg = mutator(current_cfg)
            sanitized = self._sanitize_config(
                updated_cfg, existing_by_id=existing_by_id
            )
            self._write_config_to_conn(conn, sanitized)
            return sanitized

        def _mutate_adapter(adapter: Any) -> LLMControlConfig:
            profiles, existing_by_id, meta_map = self._read_snapshot_from_adapter(
                adapter
            )
            current_cfg = (
                self._assemble_config_from_snapshot(profiles, meta_map)
                if profiles
                else self._sanitize_config(
                    self._build_initial_config(), existing_by_id={}
                )
            )
            updated_cfg = mutator(current_cfg)
            sanitized = self._sanitize_config(
                updated_cfg, existing_by_id=existing_by_id
            )
            self._write_config_to_adapter(adapter, sanitized)
            return sanitized

        sanitized = self._run_in_write_transaction(_mutate_conn, _mutate_adapter)
        logger.info("LLM 配置已原子变更并保存 (%d 个 profiles)", len(sanitized.profiles))
        return sanitized

    def get_active_profile(self, config: Optional[LLMControlConfig] = None) -> Optional[LLMProfile]:
        cfg = config or self.get_config()
        if not cfg.profiles:
            return None
        target_id = cfg.active_profile_id
        for profile in cfg.profiles:
            if profile.id == target_id:
                return profile
        return cfg.profiles[0]

    def resolve_profile(self, profile: LLMProfile) -> LLMProfile:
        _validate_safe_extra_headers(profile.extra_headers)
        _validate_safe_extra_query(profile.extra_query)
        if profile.auth_mode == 'oauth':
            from application.ai.llm_oauth_service import get_canonical_oauth_spec

            raw_provider = profile.oauth_provider.strip()
            raw_session = profile.oauth_session_id.strip()
            if raw_provider and raw_session and raw_provider != raw_session:
                raise LLMNotConfiguredError(
                    'OAuth 档案提供商与会话标识不匹配，已阻断跨服务令牌混用'
                )
            provider_key = raw_provider or raw_session
            try:
                spec = get_canonical_oauth_spec(provider_key)
            except ValueError as exc:
                raise LLMNotConfiguredError(str(exc)) from exc

            canonical_base = self._normalize_base_url(spec.protocol, spec.base_url)
            model = profile.model.strip() or spec.default_model
            session_id = provider_key if raw_session == provider_key else ''
            token = (
                self._get_oauth_service().resolve_access_token_sync(session_id)
                if session_id
                else ''
            )
            use_legacy = (
                spec.use_legacy_chat_completions
                if provider_key in ('openrouter', 'github_models')
                else profile.use_legacy_chat_completions
            )
            return LLMProfile(
                **{
                    **profile.model_dump(),
                    'preset_key': spec.preset_key,
                    'protocol': spec.protocol,
                    'base_url': canonical_base,
                    'model': model,
                    'api_key': token,
                    'use_legacy_chat_completions': use_legacy,
                }
            )

        if profile.auth_mode == 'local_gateway':
            try:
                validated_loopback = validate_loopback_gateway_url(profile.base_url)
            except ValueError as exc:
                raise LLMNotConfiguredError(
                    f"本地订阅网关地址未通过回环安全校验：{exc}"
                ) from exc
            protocol = profile.protocol or 'openai'
            normalized_loopback = self._normalize_base_url(protocol, validated_loopback)
            return LLMProfile(
                **{
                    **profile.model_dump(),
                    'protocol': protocol,
                    'base_url': normalized_loopback,
                    'model': profile.model.strip(),
                    'api_key': 'local-gateway',
                }
            )

        explicit_base = (profile.base_url or '').strip()
        if explicit_base and _validate_and_split_origin_url(explicit_base, allow_schemeless=True) is None:
            raise ValueError('Base URL 格式不合法（禁止包含账号口令、非法端口或查询参数）')

        effective_api_key = profile.api_key
        if effective_api_key.strip() == MASKED_SECRET_SENTINEL:
            stored = self._fetch_stored_profiles_map().get(profile.id.strip())
            effective_api_key = self.assert_masked_secret_target_matches(stored, profile)

        preset = self.get_preset_map().get(profile.preset_key)
        protocol = profile.protocol or (preset.protocol if preset else 'openai')
        base_url = self._normalize_base_url(
            protocol,
            explicit_base or (preset.default_base_url if preset else ''),
        )
        model = profile.model.strip() or (preset.default_model if preset else '')
        return LLMProfile(
            **{
                **profile.model_dump(),
                'protocol': protocol,
                'base_url': base_url,
                'model': model,
                'api_key': effective_api_key,
            }
        )

    async def resolve_profile_async(self, profile: LLMProfile) -> LLMProfile:
        """异步解析档案：OAuth 模式走异步无阻塞令牌刷新，避免阻塞事件循环。"""
        _validate_safe_extra_headers(profile.extra_headers)
        _validate_safe_extra_query(profile.extra_query)
        if profile.auth_mode != 'oauth':
            return self.resolve_profile(profile)

        from application.ai.llm_oauth_service import get_canonical_oauth_spec

        raw_provider = profile.oauth_provider.strip()
        raw_session = profile.oauth_session_id.strip()
        if raw_provider and raw_session and raw_provider != raw_session:
            raise LLMNotConfiguredError(
                'OAuth 档案提供商与会话标识不匹配，已阻断跨服务令牌混用'
            )
        provider_key = raw_provider or raw_session
        try:
            spec = get_canonical_oauth_spec(provider_key)
        except ValueError as exc:
            raise LLMNotConfiguredError(str(exc)) from exc

        canonical_base = self._normalize_base_url(spec.protocol, spec.base_url)
        model = profile.model.strip() or spec.default_model
        session_id = provider_key if raw_session == provider_key else ''
        token = (
            await self._get_oauth_service().resolve_access_token_async(session_id)
            if session_id
            else ''
        )
        use_legacy = (
            spec.use_legacy_chat_completions
            if provider_key in ('openrouter', 'github_models')
            else profile.use_legacy_chat_completions
        )
        return LLMProfile(
            **{
                **profile.model_dump(),
                'preset_key': spec.preset_key,
                'protocol': spec.protocol,
                'base_url': canonical_base,
                'model': model,
                'api_key': token,
                'use_legacy_chat_completions': use_legacy,
            }
        )

    def resolve_active_profile(self, config: Optional[LLMControlConfig] = None) -> Optional[LLMProfile]:
        active = self.get_active_profile(config)
        if active is None:
            return None
        return self.resolve_profile(active)

    async def resolve_active_profile_async(
        self, config: Optional[LLMControlConfig] = None
    ) -> Optional[LLMProfile]:
        active = self.get_active_profile(config)
        if active is None:
            return None
        return await self.resolve_profile_async(active)

    def _select_role_candidate(
        self, role: LLMRoleName, cfg: LLMControlConfig
    ) -> Optional[LLMProfile]:
        raw_bindings = cfg.role_bindings or {}
        if role in raw_bindings and str(raw_bindings.get(role) or '').strip():
            bound_id = str(raw_bindings[role]).strip()
            return next((p for p in cfg.profiles if p.id == bound_id), None)

        if role == 'cheap':
            return (
                next((p for p in cfg.profiles if (p.name or '').strip() == '经济模型'), None)
                or next((p for p in cfg.profiles if '经济' in (p.name or '')), None)
            )
        if role == 'kg':
            return (
                next((p for p in cfg.profiles if (p.name or '').strip() == '知识图谱模型'), None)
                or next((p for p in cfg.profiles if '知识图谱' in (p.name or '')), None)
            )
        return None

    def _resolve_effective_main_sync(self, cfg: LLMControlConfig) -> Optional[LLMProfile]:
        if not cfg.profiles:
            return None
        fallback_main: Optional[LLMProfile] = None
        if cfg.endpoint_mode == 'independent':
            cand_main = self._select_role_candidate('main', cfg)
            if cand_main is not None:
                try:
                    resolved_main = self.resolve_profile(cand_main)
                    if resolved_main.model.strip() and resolved_main.api_key.strip():
                        return resolved_main
                    fallback_main = resolved_main
                except Exception as exc:
                    logger.warning("解析独立主力绑定档案失败，回退激活档案: %s", exc)
        try:
            return self.resolve_active_profile(cfg)
        except Exception:
            if fallback_main is not None:
                return fallback_main
            raise

    async def _resolve_effective_main_async(
        self, cfg: LLMControlConfig
    ) -> Optional[LLMProfile]:
        if not cfg.profiles:
            return None
        fallback_main: Optional[LLMProfile] = None
        if cfg.endpoint_mode == 'independent':
            cand_main = self._select_role_candidate('main', cfg)
            if cand_main is not None:
                try:
                    resolved_main = await self.resolve_profile_async(cand_main)
                    if resolved_main.model.strip() and resolved_main.api_key.strip():
                        return resolved_main
                    fallback_main = resolved_main
                except Exception as exc:
                    logger.warning("异步解析独立主力绑定档案失败，回退激活档案: %s", exc)
        try:
            return await self.resolve_active_profile_async(cfg)
        except Exception:
            if fallback_main is not None:
                return fallback_main
            raise

    def resolve_role_profile(
        self,
        role: LLMRoleName = 'main',
        config: Optional[LLMControlConfig] = None,
    ) -> Optional[LLMProfile]:
        """按 L3 角色（main / cheap / kg）解析目标档案，未配置或异常时自动回退有效主力档案。"""
        cfg = config or self.get_config()
        if not cfg.profiles:
            return None

        if cfg.endpoint_mode != 'independent':
            return self.resolve_active_profile(cfg)

        if role == 'main':
            return self._resolve_effective_main_sync(cfg)

        candidate = self._select_role_candidate(role, cfg)
        if candidate is not None:
            try:
                resolved = self.resolve_profile(candidate)
                if resolved.model.strip() and resolved.api_key.strip():
                    return resolved
            except Exception as exc:
                logger.warning("解析角色 %s 档案失败，已自动回退主力模型: %s", role, exc)

        return self._resolve_effective_main_sync(cfg)

    async def resolve_role_profile_async(
        self,
        role: LLMRoleName = 'main',
        config: Optional[LLMControlConfig] = None,
    ) -> Optional[LLMProfile]:
        """异步按 L3 角色（main / cheap / kg）解析目标档案，避免同步 OAuth 刷新阻塞事件循环。"""
        cfg = config or self.get_config()
        if not cfg.profiles:
            return None

        if cfg.endpoint_mode != 'independent':
            return await self.resolve_active_profile_async(cfg)

        if role == 'main':
            return await self._resolve_effective_main_async(cfg)

        candidate = self._select_role_candidate(role, cfg)
        if candidate is not None:
            try:
                resolved = await self.resolve_profile_async(candidate)
                if resolved.model.strip() and resolved.api_key.strip():
                    return resolved
            except Exception as exc:
                logger.warning("异步解析角色 %s 档案失败，已自动回退主力模型: %s", role, exc)

        return await self._resolve_effective_main_async(cfg)

    def apply_golden_role_routing(
        self,
        *,
        source_profile_id: str,
        main_model: str,
        cheap_model: str = '',
        kg_model: str = '',
    ) -> LLMControlConfig:
        """在单次 IMMEDIATE 事务内原子读取源档案最新凭证、克隆三角色档案并启用独立端点路由。"""
        src_id = (source_profile_id or '').strip()

        def _mutate(cfg: LLMControlConfig) -> LLMControlConfig:
            source: Optional[LLMProfile] = None
            if src_id:
                source = next((p for p in cfg.profiles if p.id == src_id), None)
            if source is None and not src_id:
                source = self.get_active_profile(cfg)
            if source is None:
                raise ValueError(f"未找到源配置档案: {source_profile_id}")

            clean_main = (main_model or '').strip() or source.model.strip()
            if not clean_main:
                raise ValueError('必须指定主力模型（main_model）')
            clean_cheap = (cheap_model or '').strip() or clean_main
            clean_kg = (kg_model or '').strip() or clean_cheap

            base_dump = source.model_dump()

            def _make_role_profile(
                pid: str, name: str, model_id: str, note: str
            ) -> LLMProfile:
                return LLMProfile(
                    **{
                        **base_dump,
                        'id': pid,
                        'name': name,
                        'model': model_id,
                        'notes': note,
                    }
                )

            role_profiles = [
                _make_role_profile(
                    'golden-role-main',
                    '主力模型',
                    clean_main,
                    '黄金省额分工：主力正文与核心大纲',
                ),
                _make_role_profile(
                    'golden-role-cheap',
                    '经济模型',
                    clean_cheap,
                    '黄金省额分工：章后摘要与高频巡检',
                ),
                _make_role_profile(
                    'golden-role-kg',
                    '知识图谱模型',
                    clean_kg,
                    '黄金省额分工：三元组与状态结构化抽取',
                ),
            ]

            for rp in role_profiles:
                replaced = False
                for idx, existing in enumerate(cfg.profiles):
                    if existing.id == rp.id:
                        cfg.profiles[idx] = rp
                        replaced = True
                        break
                if not replaced:
                    cfg.profiles.append(rp)

            cfg.endpoint_mode = 'independent'
            cfg.active_profile_id = 'golden-role-main'
            cfg.role_bindings = {
                'main': 'golden-role-main',
                'cheap': 'golden-role-cheap',
                'kg': 'golden-role-kg',
            }
            return cfg

        return self.mutate_config(_mutate)

    def get_runtime_summary(self, config: Optional[LLMControlConfig] = None) -> LLMRuntimeSummary:
        cfg = config or self.get_config()
        active_raw = (
            (self._select_role_candidate('main', cfg) or self.get_active_profile(cfg))
            if cfg.endpoint_mode == 'independent'
            else self.get_active_profile(cfg)
        )
        try:
            profile = self.resolve_role_profile('main', cfg)
        except Exception as exc:
            safe_raw_base = (
                _sanitize_public_base_url(
                    active_raw.base_url, auth_mode=active_raw.auth_mode
                )
                if active_raw
                else ''
            )
            return LLMRuntimeSummary(
                source='mock',
                active_profile_id=active_raw.id if active_raw else None,
                active_profile_name=active_raw.name if active_raw else None,
                protocol=active_raw.protocol if active_raw else None,
                model=(active_raw.model or None) if active_raw else None,
                base_url=safe_raw_base or None,
                using_mock=True,
                reason=str(exc),
            )

        if profile is None:
            return LLMRuntimeSummary(
                source='mock',
                using_mock=True,
                reason='未找到任何 LLM 配置：AI 生成请求将直接报错，请先在「LLM 控制」中添加并激活模型档案',
            )

        safe_profile_base = _sanitize_public_base_url(
            profile.base_url, auth_mode=profile.auth_mode
        )
        if not profile.api_key.strip() or not profile.model.strip():
            reason = (
                '当前激活的 OAuth 档案尚未完成授权或会话已过期，请重新连接授权'
                if profile.auth_mode == 'oauth' and not profile.api_key.strip()
                else '当前激活配置缺少 API Key 或模型名：AI 生成请求将直接报错，请先补全配置'
            )
            return LLMRuntimeSummary(
                source='mock',
                active_profile_id=profile.id,
                active_profile_name=profile.name,
                protocol=profile.protocol,
                model=profile.model or None,
                base_url=safe_profile_base or None,
                using_mock=True,
                reason=reason,
            )

        return LLMRuntimeSummary(
            source='profile',
            active_profile_id=profile.id,
            active_profile_name=profile.name,
            protocol=profile.protocol,
            model=profile.model,
            base_url=safe_profile_base or None,
            using_mock=False,
        )

    async def test_profile_model(
        self,
        profile: LLMProfile,
        llm_service_factory: Callable[[LLMProfile], 'LLMService'],
    ) -> LLMTestResult:
        resolved = await self.resolve_profile_async(profile)
        if not resolved.api_key.strip() or not resolved.model.strip():
            return LLMTestResult(
                ok=False,
                provider_label=resolved.name,
                model=resolved.model or '',
                latency_ms=0,
                error='请先填写 API Key 与模型名后再测试',
            )
        started = perf_counter()
        llm_service: Optional['LLMService'] = None
        try:
            llm_service = llm_service_factory(resolved)
            from domain.ai.services.llm_service import GenerationConfig
            from domain.ai.value_objects.prompt import Prompt

            prompt = Prompt(
                system='你是连通性测试助手。',
                user='请只回复"连接成功"。',
            )
            config = GenerationConfig(
                model=resolved.model,
                max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
                temperature=0,
            )
            result = await llm_service.generate(prompt, config)
            latency_ms = int((perf_counter() - started) * 1000)
            body = (result.content or '').strip()
            if not body:
                return LLMTestResult(
                    ok=False,
                    provider_label=resolved.name,
                    model=resolved.model or '',
                    latency_ms=latency_ms,
                    error=(
                        "模型返回了空内容。请核对：API Key 是否有效、模型名与协议是否匹配、"
                        "base_url 是否正确；若使用代理或网关，也可能是超时截断或限流。"
                    ),
                )
            preview = body.replace('\r', ' ').replace('\n', ' ')
            return LLMTestResult(
                ok=True,
                provider_label=resolved.name,
                model=resolved.model,
                latency_ms=latency_ms,
                preview=preview[:120],
            )
        except Exception as exc:
            latency_ms = int((perf_counter() - started) * 1000)
            err_text = str(exc).strip()
            if not err_text:
                err_text = "未知错误（异常无消息），请查看服务端日志。"
            return LLMTestResult(
                ok=False,
                provider_label=resolved.name,
                model=resolved.model or '',
                latency_ms=latency_ms,
                error=err_text,
            )
        finally:
            if llm_service is not None and hasattr(llm_service, 'aclose'):
                try:
                    await llm_service.aclose()
                except Exception:
                    pass

    def _sanitize_config(
        self,
        config: LLMControlConfig,
        *,
        existing_by_id: Optional[Dict[str, LLMProfile]] = None,
    ) -> LLMControlConfig:
        stored_map = existing_by_id if existing_by_id is not None else {}
        profiles: List[LLMProfile] = []
        seen_ids: set[str] = set()
        for index, profile in enumerate(config.profiles):
            raw_id = profile.id.strip()
            candidate_id = raw_id or f'profile-{index + 1}'
            if candidate_id in seen_ids:
                candidate_id = f'{candidate_id}-{index + 1}'
            seen_ids.add(candidate_id)

            clean_headers = _validate_safe_extra_headers(profile.extra_headers)
            clean_query = _validate_safe_extra_query(profile.extra_query)
            auth_mode: LLMAuthMode = (
                profile.auth_mode
                if profile.auth_mode in ('api_key', 'oauth', 'local_gateway')
                else 'api_key'
            )
            raw_base_url = profile.base_url.strip()
            raw_api_key = profile.api_key.strip()

            if auth_mode == 'oauth':
                from application.ai.llm_oauth_service import get_canonical_oauth_spec

                clean_provider = (
                    profile.oauth_provider.strip() or profile.oauth_session_id.strip()
                )
                if clean_provider not in VALID_OAUTH_PROVIDERS:
                    raise ValueError(f'不支持的 OAuth 提供商: {clean_provider}')
                raw_sid = profile.oauth_session_id.strip()
                if raw_sid and raw_sid != clean_provider:
                    raise ValueError('OAuth 档案提供商与会话标识不匹配')
                spec = get_canonical_oauth_spec(clean_provider)
                clean_api_key = ''
                clean_base_url = spec.base_url
                clean_oauth_provider = clean_provider
                clean_oauth_session = clean_provider if raw_sid else ''
                clean_protocol: LLMProtocol = spec.protocol
            elif auth_mode == 'local_gateway':
                clean_base_url = validate_loopback_gateway_url(raw_base_url)
                clean_api_key = ''
                clean_oauth_provider = ''
                clean_oauth_session = ''
                clean_protocol = profile.protocol
            else:
                if (
                    raw_base_url
                    and _validate_and_split_origin_url(raw_base_url, allow_schemeless=True) is None
                ):
                    raise ValueError(
                        'Base URL 格式不合法（禁止包含账号口令、非法端口或查询参数）'
                    )
                clean_base_url = raw_base_url
                clean_oauth_provider = ''
                clean_oauth_session = ''
                clean_protocol = profile.protocol
                if raw_api_key == MASKED_SECRET_SENTINEL:
                    existing = stored_map.get(candidate_id) or stored_map.get(raw_id)
                    clean_api_key = self.assert_masked_secret_target_matches(
                        existing, profile
                    )
                else:
                    clean_api_key = raw_api_key

            profiles.append(
                LLMProfile(
                    **{
                        **profile.model_dump(),
                        'id': candidate_id,
                        'name': profile.name.strip() or f'配置 {index + 1}',
                        'protocol': clean_protocol,
                        'base_url': clean_base_url,
                        'api_key': clean_api_key,
                        'model': profile.model.strip(),
                        'max_tokens': DEFAULT_MAX_OUTPUT_TOKENS,
                        'extra_headers': clean_headers,
                        'extra_query': clean_query,
                        'auth_mode': auth_mode,
                        'oauth_provider': clean_oauth_provider,
                        'oauth_session_id': clean_oauth_session,
                    }
                )
            )

        if not profiles:
            profiles = self._build_initial_config().profiles

        valid_ids = {p.id for p in profiles}
        active_profile_id = (
            config.active_profile_id
            if config.active_profile_id in valid_ids
            else profiles[0].id
        )
        mode = (
            config.endpoint_mode
            if config.endpoint_mode in ('unified', 'independent')
            else 'unified'
        )
        role_bindings = {
            str(k).strip(): str(v).strip()
            for k, v in (config.role_bindings or {}).items()
            if str(k).strip() in VALID_LLM_ROLES and str(v).strip() in valid_ids
        }
        return LLMControlConfig(
            version=1,
            active_profile_id=active_profile_id,
            endpoint_mode=mode,  # type: ignore[arg-type]
            role_bindings=role_bindings,
            profiles=profiles,
        )

    @staticmethod
    def _normalize_base_url(protocol: LLMProtocol, base_url: str) -> str:
        if protocol == 'anthropic':
            return normalize_anthropic_base_url(base_url) or ''
        if protocol == 'gemini':
            return normalize_gemini_base_url(base_url) or ''
        return normalize_openai_base_url(base_url) or ''

    def _build_initial_config(self) -> LLMControlConfig:
        profiles = [
            LLMProfile(
                id='openai-compatible-default',
                name='OpenAI 兼容 / 国产通用',
                preset_key='custom-openai-compatible',
                protocol='openai',
                base_url='',
                model='',
            ),
            LLMProfile(
                id='claude-official-default',
                name='Claude / Anthropic',
                preset_key='claude-official',
                protocol='anthropic',
                base_url='https://api.anthropic.com',
                model='',
            ),
            LLMProfile(
                id='gemini-official-default',
                name='Gemini / Google',
                preset_key='gemini-official',
                protocol='gemini',
                base_url='https://generativelanguage.googleapis.com/v1beta',
                model='',
            ),
        ]
        active_profile_id = profiles[0].id

        env = LLMEnvironmentSettings.from_env()

        anthropic_key = env.anthropic_api_key_with_token_fallback
        openai_key = env.openai_api_key
        gemini_key = env.gemini_api_key
        ark_key = env.ark_api_key

        if anthropic_key and (env.provider == 'anthropic' or not env.provider):
            profiles[1] = profiles[1].model_copy(update={
                'api_key': anthropic_key,
                'base_url': env.anthropic_base_url or profiles[1].base_url,
                'model': env.anthropic_model or profiles[1].model,
            })
            active_profile_id = profiles[1].id
        elif openai_key and (env.provider == 'openai' or not env.provider):
            profiles[0] = profiles[0].model_copy(update={
                'name': 'OpenAI / 兼容网关',
                'preset_key': env.openai_preset_key,
                'api_key': openai_key,
                'base_url': env.openai_base_url,
                'model': env.openai_model,
            })
            active_profile_id = profiles[0].id
        elif gemini_key:
            profiles[2] = profiles[2].model_copy(update={
                'api_key': gemini_key,
                'base_url': env.gemini_base_url or profiles[2].base_url,
                'model': env.gemini_model or profiles[2].model,
            })
            active_profile_id = profiles[2].id
        elif ark_key:
            profiles[0] = profiles[0].model_copy(update={
                'name': '豆包 / Ark',
                'preset_key': 'doubao-ark',
                'api_key': ark_key,
                'base_url': env.ark_base_url_or_default,
                'model': env.ark_model,
            })
            active_profile_id = profiles[0].id

        return LLMControlConfig(
            version=1,
            active_profile_id=active_profile_id,
            endpoint_mode='unified',
            profiles=profiles,
        )
