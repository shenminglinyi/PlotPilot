from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from application.paths import DATA_DIR
from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt
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
    _DEFAULT_OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')
    _DEFAULT_ANTHROPIC_MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6')
    _DEFAULT_GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')
    _DEFAULT_ARK_MODEL = os.getenv('ARK_MODEL', 'doubao-seed-2-0-mini-260215')

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or (DATA_DIR / 'llm_profiles.json')
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

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
                default_model=self._DEFAULT_OPENAI_MODEL,
                description='OpenAI 官方接口（自动兼容底层 Responses API 与 Chat Completions）。',
                tags=['official'],
            ),
            LLMPreset(
                key='claude-official',
                label='Claude / Anthropic 官方',
                protocol='anthropic',
                default_base_url='https://api.anthropic.com',
                default_model=self._DEFAULT_ANTHROPIC_MODEL,
                description='Anthropic Messages 接口；也可接入 Claude-compatible 网关。',
                tags=['official'],
            ),
            LLMPreset(
                key='gemini-official',
                label='Gemini / Google 官方',
                protocol='gemini',
                default_base_url='https://generativelanguage.googleapis.com/v1beta',
                default_model=self._DEFAULT_GEMINI_MODEL,
                description='Gemini generateContent / streamGenerateContent 接口。',
                tags=['official'],
            ),
            LLMPreset(
                key='deepseek',
                label='DeepSeek',
                protocol='openai',
                default_base_url='https://api.deepseek.com/v1',
                default_model='deepseek-chat',
                description='DeepSeek 官方 OpenAI-compatible 接口。',
                tags=['domestic', 'preset'],
            ),
            LLMPreset(
                key='qwen-dashscope',
                label='Qwen / DashScope',
                protocol='openai',
                default_base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
                default_model='qwen-plus',
                description='阿里云百炼 / DashScope OpenAI-compatible 接口。',
                tags=['domestic', 'preset'],
            ),
            LLMPreset(
                key='glm-openai',
                label='智谱 GLM（OpenAI 兼容）',
                protocol='openai',
                default_base_url='https://open.bigmodel.cn/api/paas/v4',
                default_model='glm-4.5',
                description='智谱 OpenAI-compatible 接口。',
                tags=['domestic', 'preset'],
            ),
            LLMPreset(
                key='glm-anthropic',
                label='智谱 GLM（Claude 兼容）',
                protocol='anthropic',
                default_base_url='https://open.bigmodel.cn/api/anthropic',
                default_model='glm-4.5',
                description='智谱 Anthropic-compatible 接口。',
                tags=['domestic', 'preset'],
            ),
            LLMPreset(
                key='doubao-ark',
                label='豆包 / 火山方舟 Ark',
                protocol='openai',
                default_base_url='https://ark.cn-beijing.volces.com/api/v3',
                default_model=self._DEFAULT_ARK_MODEL,
                description='方舟 OpenAI-compatible 接口；也兼容仓库现有 ARK_BASE_URL 配置。',
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
        if not self.config_path.exists():
            config = self._build_initial_config()
            self._write_config(config)
            return config

        try:
            raw = json.loads(self.config_path.read_text(encoding='utf-8'))
            config = LLMControlConfig.model_validate(raw)
        except Exception as exc:
            logger.warning('加载 LLM 配置失败，回退默认配置: %s', exc)
            config = self._build_initial_config()
            self._write_config(config)
            return config

        if not config.profiles:
            config = self._build_initial_config()
            self._write_config(config)
            return config

        return config

    def save_config(self, config: LLMControlConfig) -> LLMControlConfig:
        sanitized = self._sanitize_config(config)
        self._write_config(sanitized)
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
            base_url=profile.base_url or None,
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
            prompt = Prompt(
                system='你是连通性测试助手。',
                user='请只回复“连接成功”。',
            )
            config = GenerationConfig(
                model=resolved.model or None,
                max_tokens=min(resolved.max_tokens, 64),
                temperature=0,
            )
            result = await llm_service.generate(prompt, config)
            latency_ms = int((perf_counter() - started) * 1000)
            preview = (result.content or '').strip().replace('\r', ' ').replace('\n', ' ')
            return LLMTestResult(
                ok=True,
                provider_label=resolved.name,
                model=resolved.model,
                latency_ms=latency_ms,
                preview=preview[:120],
            )
        except Exception as exc:
            latency_ms = int((perf_counter() - started) * 1000)
            return LLMTestResult(
                ok=False,
                provider_label=resolved.name,
                model=resolved.model or '',
                latency_ms=latency_ms,
                error=str(exc),
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

    def _write_config(self, config: LLMControlConfig) -> None:
        tmp_path = self.config_path.with_suffix('.json.tmp')
        tmp_path.write_text(
            json.dumps(config.model_dump(mode='json'), ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        tmp_path.replace(self.config_path)

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
                model=self._DEFAULT_ANTHROPIC_MODEL,
            ),
            LLMProfile(
                id='gemini-official-default',
                name='Gemini / Google',
                preset_key='gemini-official',
                protocol='gemini',
                base_url='https://generativelanguage.googleapis.com/v1beta',
                model=self._DEFAULT_GEMINI_MODEL,
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
                'model': (os.getenv('OPENAI_MODEL') or '').strip() or self._DEFAULT_OPENAI_MODEL,
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
                'model': (os.getenv('ARK_MODEL') or '').strip() or self._DEFAULT_ARK_MODEL,
            })
            active_profile_id = profiles[0].id

        return LLMControlConfig(version=1, active_profile_id=active_profile_id, profiles=profiles)
