"""Vertex AI LLM 提供商实现 (使用最新版 google-genai SDK)"""
from __future__ import annotations
import logging
import os
from typing import Any, AsyncIterator, Optional

try:
    from google import genai
    from google.genai import types
    from google.genai.types import HttpOptions
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.config.settings import Settings
from .base import BaseProvider
from .model_resolution import require_resolved_model_id

logger = logging.getLogger(__name__)

DEFAULT_MODEL = 'gemini-1.5-flash'
DEFAULT_REGION = 'us-central1'

class VertexAIProvider(BaseProvider):
    """使用最新版 Google GenAI SDK 的 Vertex AI 提供商实现
    
    优势：
    1. 统一的 Client 接口，原生支持 Vertex AI 模式。
    2. 支持 Gemini 2.0+ 的高级特性（如 Thinking Config）。
    3. 支持集成 Google Search 等工具。
    """
    
    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.client = None
        if not HAS_GENAI:
            logger.error("google-genai SDK not installed. Please run 'pip install google-genai'")
            return

        # 安全获取 region 和 project_id (CodeRabbit: 防止 NoneType 报错)
        raw_region = (
            settings.extra_body.get('region') 
            or os.getenv("GOOGLE_CLOUD_LOCATION") 
            or os.getenv("GCP_REGION") 
            or DEFAULT_REGION
        )
        self.region = raw_region.strip() if raw_region else DEFAULT_REGION

        raw_project_id = (
            settings.extra_body.get('project_id') 
            or os.getenv("GOOGLE_CLOUD_PROJECT") 
            or os.getenv("GCP_PROJECT_ID")
            or ""
        )
        self.project_id = raw_project_id.strip()
        
        # 2. 初始化客户端 (回归 Vertex AI 企业专线 + 注入关键计费请求头)
        try:
            # 使用动态读取的 project_id，确保以后改 .env 也能生效
            self.client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.region if self.region != "us-central1" else "global", # 默认改用 global 避坑
                # 关键：手动注入计费项目头，解决 ADC 环境下的 404/403 问题
                http_options={
                    'headers': {'x-goog-user-project': self.project_id}
                }
            )
            logger.info(f"Vertex AI (GenAI SDK) initialized: project={self.project_id}")
        except Exception as e:
            logger.error(f"Failed to initialize GenAI Client: {e}")

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        """执行单次文本生成任务。

        Args:
            prompt: 包含系统指令和用户输入的 Prompt 对象。
            config: 包含模型 ID、温度等参数的生成配置。

        Returns:
            GenerationResult: 包含生成文本及 Token 使用量元数据的结果。
        """
        self._ensure_sdk()
        model_id = self._get_resolved_model(config)
        
        gen_config = self._build_genai_config(config, prompt.system, model_id)
        
        # 使用 aio 异步客户端
        response = await self.client.aio.models.generate_content(
            model=model_id,
            contents=prompt.user,
            config=gen_config
        )
        
        # 提取内容 (CodeRabbit: 增加严格的空值与安全拦截防护)
        content = self._get_response_text(response)
        
        # 提取 Token 使用量
        usage = getattr(response, 'usage_metadata', None)
        if usage:
            token_usage = TokenUsage(
                input_tokens=usage.prompt_token_count or 0,
                output_tokens=usage.candidates_token_count or 0
            )
        else:
            token_usage = TokenUsage(input_tokens=0, output_tokens=0)
        
        return GenerationResult(content=content, token_usage=token_usage)

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig) -> AsyncIterator[str]:
        """执行流式文本生成任务。

        Args:
            prompt: 包含系统指令和用户输入的 Prompt 对象。
            config: 包含模型 ID、温度等参数的生成配置。

        Yields:
            str: 生成的文本片段。
        """
        self._ensure_sdk()
        model_id = self._get_resolved_model(config)
        gen_config = self._build_genai_config(config, prompt.system, model_id)
        
        # 异步流式生成
        # 修正异步流式调用语法：先 await 获取流，再 async for 遍历
        stream = await self.client.aio.models.generate_content_stream(
            model=model_id,
            contents=prompt.user,
            config=gen_config
        )
        async for chunk in stream:
            # CodeRabbit: 捕获流式末尾的 Token 统计 (如果 SDK 提供了)
            if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                usage = chunk.usage_metadata
                logger.debug(f"Vertex AI Stream Usage: input={usage.prompt_token_count}, output={usage.candidates_token_count}")
            
            if chunk.text:
                yield chunk.text

    def _get_response_text(self, response: Any) -> str:
        """安全地从响应对象中提取文本，处理被拦截或空响应的情况"""
        if not response.candidates:
            raise ValueError("Vertex AI 未返回任何候选结果。请检查输入是否包含违规内容。")
            
        candidate = response.candidates[0]
        if candidate.finish_reason == "SAFETY":
            raise ValueError("内容生成被 Vertex AI 安全过滤器拦截。请尝试修改输入或降低敏感度。")
        elif candidate.finish_reason == "RECITATION":
            raise ValueError("内容生成因涉及版权/引用限制被拦截。")
        elif candidate.finish_reason != "STOP" and candidate.finish_reason != "MAX_TOKENS":
            # 记录其他异常结束原因，但尝试返回已有文本
            logger.warning(f"Vertex AI generation finished with unexpected reason: {candidate.finish_reason}")

        try:
            return response.text or ""
        except (ValueError, AttributeError):
            # 如果访问 .text 依然报错，说明该 candidate 确实不可读
            return ""

    def _ensure_sdk(self):
        if not HAS_GENAI:
            raise ImportError("请运行 'pip install google-genai' 以安装 Vertex AI 所需的 SDK。")
        if not self.client:
            raise RuntimeError("Vertex AI 客户端未就绪。请检查 .env 中的 GCP_PROJECT_ID 和 GCP_REGION 配置。")

    def _get_resolved_model(self, config: GenerationConfig) -> str:
        model_id = require_resolved_model_id(
            config.model,
            self.settings.default_model,
            provider_label="Vertex AI",
        ).strip()
        
        # 遵循“真经”：直接返回模型名，SDK 会在底层自动补全 publishers/google/models/ 路径
        return model_id

    def _build_genai_config(self, config: GenerationConfig, system_instruction: Optional[str], model_id: str) -> types.GenerateContentConfig:
        """构建最新版 GenAI SDK 的配置对象"""
        eb = self.settings.extra_body or {}
        is_gemini_3 = 'gemini-3' in model_id.lower()
        
        # 映射基础参数
        params: dict[str, Any] = {
            "max_output_tokens": config.max_tokens,
            "safety_settings": self._build_safety_settings(),
            "system_instruction": system_instruction.strip() if system_instruction and system_instruction.strip() else None
        }

        # 如果不是 Gemini 3.x 模型，或者显式配置，则包含采样参数
        if not is_gemini_3:
            params["temperature"] = config.temperature
            params["top_p"] = eb.get("top_p", 0.95)
            if eb.get("top_k"):
                params["top_k"] = eb.get("top_k")
        
        # 针对 Gemini 的思维配置 (Thinking)
        if is_gemini_3:
            # 针对 Gemini 3.x，仅保留 thinking_level，不支持 thinking_budget_tokens
            thinking_level = eb.get("thinking_level") or eb.get("thinkingLevel")
            if "thinking_budget" in eb or "thinking_budget_tokens" in eb:
                logger.warning("thinking_budget or thinking_budget_tokens is no longer recommended for Gemini 3.x models. Use thinking_level instead.")
                if not thinking_level:
                    thinking_level = "medium"
            if thinking_level:
                params["thinking_config"] = types.ThinkingConfig(
                    thinking_level=str(thinking_level).lower()
                )
        else:
            # 针对旧模型，保留原有逻辑
            if "thinking_level" in eb or "thinking_budget_tokens" in eb:
                budget = eb.get("thinking_budget_tokens")
                level = str(eb.get("thinking_level", "medium")).lower()
                params["thinking_config"] = types.ThinkingConfig(
                    include_thoughts=True,
                    include_thoughts_in_response=True,
                    thinking_level=level if not budget else None,
                    thinking_budget_tokens=int(budget) if budget else None
                )
            
        # 针对搜索工具的支持
        if eb.get("use_google_search"):
            params["tools"] = [types.Tool(google_search=types.GoogleSearch())]
            
        return types.GenerateContentConfig(**params)

    def _build_safety_settings(self) -> list[types.SafetySetting]:
        """构建安全设置"""
        return [
            types.SafetySetting(
                category=cat,
                threshold="OFF", # 对应代码片段中的 OFF (即 BLOCK_NONE)
            ) for cat in [
                "HARM_CATEGORY_HATE_SPEECH",
                "HARM_CATEGORY_HARASSMENT",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "HARM_CATEGORY_DANGEROUS_CONTENT",
            ]
        ]
