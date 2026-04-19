from __future__ import annotations

import json
import logging
import os
from time import perf_counter
from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from infrastructure.persistence.database.connection import get_database
from infrastructure.ai.url_utils import (
    normalize_anthropic_base_url,
    normalize_gemini_base_url,
    normalize_openai_base_url,
)

logger = logging.getLogger(__name__)

LLMProtocol = Literal['openai', 'anthropic', 'gemini']


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
    max_tokens: int = 4096
    timeout_seconds: int = 300
    extra_headers: Dict[str, str] = Field(default_factory=dict)
    extra_query: Dict[str, Any] = Field(default_factory=dict)
    extra_body: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ''
    use_legacy_chat_completions: bool = False

    @field_validator('temperature')
    @classmethod
    def _validate_temperature(cls, value: float) -> float:
        if not 0 <= value <= 2:
            raise ValueError('temperature must be between 0 and 2')
        return value

    @field_validator('max_tokens', 'timeout_seconds')
    @classmethod
    def _validate_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError('value must be positive')
        return value

    @field_validator('extra_headers')
    @classmethod
    def _normalize_headers(cls, value: Dict[str, str]) -> Dict[str, str]:
        return {
            str(k).strip(): str(v).strip()
            for k, v in (value or {}).items()
            if str(k).strip() and str(v).strip()
        }


class LLMControlConfig(BaseModel):
    version: int = 1
    active_profile_id: Optional[str] = None
    profiles: List[LLMProfile] = Field(default_factory=list)

    @model_validator(mode='after')
    def _validate_active_profile(self) -> 'LLMControlConfig':
        if not self.profiles:
            return self
        ids = [profile.id for profile in self.profiles]
        if not self.active_profile_id or self.active_profile_id not in ids:
            self.active_profile_id = ids[0]
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
    """LLM 控制面板服务 —— 配置全部持久化到 SQLite（llm_profiles + llm_config_meta 表）。"""

    # ---- 内部 DB 辅助 ------------------------------------------------

    def _db(self):
        return get_database()

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
        return LLMProfile(
            id=row['id'],
            name=row['name'],
            preset_key=row['preset_key'],
            protocol=row['protocol'],
            base_url=row['base_url'] or '',
            api_key=row['api_key'] or '',
            model=row['model'] or '',
            temperature=row['temperature'],
            max_tokens=row['max_tokens'],
            timeout_seconds=row['timeout_seconds'],
            extra_headers=json.loads(row.get('extra_headers') or '{}'),
            extra_query=json.loads(row.get('extra_query') or '{}'),
            extra_body=json.loads(row.get('extra_body') or '{}'),
            notes=row['notes'] or '',
            use_legacy_chat_completions=bool(row.get('use_legacy_chat_completions', 0)),
        )

    def _profile_to_row(self, p: LLMProfile) -> dict:
        return dict(
            id=p.id,
            name=p.name,
            preset_key=p.preset_key,
            protocol=p.protocol,
            base_url=p.base_url,
            api_key=p.api_key,
            model=p.model,
            temperature=p.temperature,
            max_tokens=p.max_tokens,
            timeout_seconds=p.timeout_seconds,
            extra_headers=json.dumps(p.extra_headers, ensure_ascii=False),
            extra_query=json.dumps(p.extra_query, ensure_ascii=False),
            extra_body=json.dumps(p.extra_body, ensure_ascii=False),
            notes=p.notes,
            use_legacy_chat_completions=int(p.use_legacy_chat_completions),
        )

    # ---- 公共接口（保持与原文件版一致）----------------------------------

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

    def get_control_panel_data(self) -> LLMControlPanelData:
        config = self.get_config()
        return LLMControlPanelData(
            config=config,
            presets=self.get_presets(),
            runtime=self.get_runtime_summary(config),
        )

    def get_config(self) -> LLMControlConfig:
        """从数据库读取完整配置；空库时自动写入初始默认值。"""
        try:
            rows = self._db().fetch_all(
                "SELECT * FROM llm_profiles ORDER BY sort_order, created_at"
            )
        except Exception as exc:
            logger.warning('读取 LLM profiles 失败，回退默认配置: %s', exc)
            rows = []

        profiles = [self._row_to_profile(r) for r in rows]

        if not profiles:
            config = self._build_initial_config()
            self.save_config(config)
            return config

        active_id = self._get_meta('active_profile_id')
        # 校验 active_id 是否在当前 profiles 中
        valid_ids = {p.id for p in profiles}
        if not active_id or active_id not in valid_ids:
            active_id = profiles[0].id

        return LLMControlConfig(version=1, active_profile_id=active_id, profiles=profiles)

    def save_config(self, config: LLMControlConfig) -> LLMControlConfig:
        """将配置全量写入数据库（先清后写）。"""
        sanitized = self._sanitize_config(config)
        db = self._db()

        # 清空旧数据
        db.execute("DELETE FROM llm_profiles")
        db.execute("DELETE FROM llm_config_meta")

        # 写入 meta
        db.execute(
            "INSERT OR REPLACE INTO llm_config_meta (key, value) VALUES (?, ?)",
            ('active_profile_id', sanitized.active_profile_id or ''),
        )

        # 批量写入 profiles
        params_list = []
        for idx, profile in enumerate(sanitized.profiles):
            row = self._profile_to_row(profile)
            row['sort_order'] = idx
            params_list.append((
                row['id'], row['name'], row['preset_key'], row['protocol'],
                row['base_url'], row['api_key'], row['model'],
                row['temperature'], row['max_tokens'], row['timeout_seconds'],
                row['extra_headers'], row['extra_query'], row['extra_body'],
                row['notes'], row['use_legacy_chat_completions'], row['sort_order'],
            ))

        db.execute_many(
            """INSERT INTO llm_profiles (
                id, name, preset_key, protocol, base_url, api_key, model,
                temperature, max_tokens, timeout_seconds,
                extra_headers, extra_query, extra_body, notes,
                use_legacy_chat_completions, sort_order
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            params_list,
        )

        logger.info("LLM 配置已保存到数据库 (%d 个 profiles)", len(sanitized.profiles))
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
        preset = self.get_preset_map().get(profile.preset_key)
        protocol = profile.protocol or (preset.protocol if preset else 'openai')
        base_url = self._normalize_base_url(
            protocol,
            profile.base_url.strip() or (preset.default_base_url if preset else ''),
        )
        model = profile.model.strip() or (preset.default_model if preset else '')
        return LLMProfile(
            **{
                **profile.model_dump(),
                'protocol': protocol,
                'base_url': base_url,
                'model': model,
            }
        )

    def resolve_active_profile(self, config: Optional[LLMControlConfig] = None) -> Optional[LLMProfile]:
        active = self.get_active_profile(config)
        if active is None:
            return None
        return self.resolve_profile(active)

    def get_runtime_summary(self, config: Optional[LLMControlConfig] = None) -> LLMRuntimeSummary:
        profile = self.resolve_active_profile(config)
        if profile is None:
            return LLMRuntimeSummary(
                source='mock',
                using_mock=True,
                reason='未找到任何 LLM 配置',
            )

        if not profile.api_key.strip() or not profile.model.strip():
            return LLMRuntimeSummary(
                source='mock',
                active_profile_id=profile.id,
                active_profile_name=profile.name,
                protocol=profile.protocol,
                model=profile.model or None,
                base_url=profile.base_url or None,
                using_mock=True,
                reason='当前激活配置缺少 API Key 或模型名，运行时将退回 MockProvider',
            )

        return LLMRuntimeSummary(
            source='profile',
            active_profile_id=profile.id,
            active_profile_name=profile.name,
            protocol=profile.protocol,
            model=profile.model,
            base_url=profile.base_url,
            using_mock=False,
        )

    async def test_profile_model(
        self,
        profile: LLMProfile,
        llm_service_factory: Callable[[LLMProfile], LLMService],
    ) -> LLMTestResult:
        resolved = self.resolve_profile(profile)
        if not resolved.api_key.strip() or not resolved.model.strip():
            return LLMTestResult(
                ok=False,
                provider_label=resolved.name,
                model=resolved.model or '',
                latency_ms=0,
                error='请先填写 API Key 与模型名后再测试',
            )
        started = perf_counter()
        try:
            llm_service = llm_service_factory(resolved)
            from domain.ai.value_objects.prompt import Prompt
            from domain.ai.services.llm_service import GenerationConfig
            prompt = Prompt(
                system='你是连通性测试助手。',
                user='请只回复"连接成功"。',
            )
            config = GenerationConfig(
                model=resolved.model,
                max_tokens=min(resolved.max_tokens, 64),
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

    def _sanitize_config(self, config: LLMControlConfig) -> LLMControlConfig:
        profiles: List[LLMProfile] = []
        seen_ids: set = set()
        for index, profile in enumerate(config.profiles):
            candidate_id = profile.id.strip() or f'profile-{index + 1}'
            if candidate_id in seen_ids:
                candidate_id = f'{candidate_id}-{index + 1}'
            seen_ids.add(candidate_id)
            profiles.append(
                LLMProfile(
                    **{
                        **profile.model_dump(),
                        'id': candidate_id,
                        'name': profile.name.strip() or f'配置 {index + 1}',
                        'base_url': profile.base_url.strip(),
                        'api_key': profile.api_key.strip(),
                        'model': profile.model.strip(),
                    }
                )
            )

        if not profiles:
            profiles = self._build_initial_config().profiles

        active_profile_id = config.active_profile_id if config.active_profile_id in {p.id for p in profiles} else profiles[0].id
        return LLMControlConfig(version=1, active_profile_id=active_profile_id, profiles=profiles)

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

        llm_provider = os.getenv('LLM_PROVIDER', '').strip().lower()

        anthropic_key = (os.getenv('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_AUTH_TOKEN') or '').strip()
        openai_key = (os.getenv('OPENAI_API_KEY') or '').strip()
        gemini_key = (os.getenv('GEMINI_API_KEY') or '').strip()
        ark_key = (os.getenv('ARK_API_KEY') or '').strip()

        if anthropic_key and (llm_provider == 'anthropic' or not llm_provider):
            profiles[1] = profiles[1].model_copy(update={
                'api_key': anthropic_key,
                'base_url': (os.getenv('ANTHROPIC_BASE_URL') or '').strip() or profiles[1].base_url,
                'model': (os.getenv('ANTHROPIC_MODEL') or '').strip() or profiles[1].model,
            })
            active_profile_id = profiles[1].id
        elif openai_key and (llm_provider == 'openai' or not llm_provider):
            profiles[0] = profiles[0].model_copy(update={
                'name': 'OpenAI / 兼容网关',
                'preset_key': 'openai-official' if not os.getenv('OPENAI_BASE_URL') else 'custom-openai-compatible',
                'api_key': openai_key,
                'base_url': (os.getenv('OPENAI_BASE_URL') or '').strip(),
                'model': (os.getenv('OPENAI_MODEL') or '').strip(),
            })
            active_profile_id = profiles[0].id
        elif gemini_key:
            profiles[2] = profiles[2].model_copy(update={
                'api_key': gemini_key,
                'base_url': (os.getenv('GEMINI_BASE_URL') or '').strip() or profiles[2].base_url,
                'model': (os.getenv('GEMINI_MODEL') or '').strip() or profiles[2].model,
            })
            active_profile_id = profiles[2].id
        elif ark_key:
            profiles[0] = profiles[0].model_copy(update={
                'name': '豆包 / Ark',
                'preset_key': 'doubao-ark',
                'api_key': ark_key,
                'base_url': (os.getenv('ARK_BASE_URL') or '').strip() or 'https://ark.cn-beijing.volces.com/api/v3',
                'model': (os.getenv('ARK_MODEL') or '').strip(),
            })
            active_profile_id = profiles[0].id

        return LLMControlConfig(version=1, active_profile_id=active_profile_id, profiles=profiles)
