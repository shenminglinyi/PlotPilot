"""模型适配器 — Layer 6: 不同 LLM 的 Anti-AI 参数适配。

核心功能：
- 为不同模型（OpenAI/Claude/本地模型）适配 Anti-AI 参数
- Logit Bias 的 token_id 映射
- 不同模型的 system prompt 格式适配
- 流式生成参数优化
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ModelAdapter:
    """模型适配器 — 为不同 LLM 适配 Anti-AI 参数。"""

    def __init__(self, model_name: str = "gpt-4"):
        self._model_name = model_name.lower()

    @property
    def is_openai(self) -> bool:
        return any(k in self._model_name for k in ["gpt", "o1", "o3", "o4"])

    @property
    def is_claude(self) -> bool:
        return "claude" in self._model_name

    @property
    def is_local(self) -> bool:
        return any(k in self._model_name for k in ["llama", "qwen", "deepseek", "glm", "local"])

    def adapt_system_prompt(self, system_prompt: str) -> str:
        """适配 system prompt 格式。

        OpenAI: 原样使用
        Claude: 添加 XML 标签增强结构
        本地: 简化格式
        """
        if self.is_claude:
            # Claude 对结构化标签更敏感
            return f"<anti_ai_protocol>\n{system_prompt}\n</anti_ai_protocol>"
        elif self.is_local:
            # 本地模型可能对长 system prompt 效果不佳，提取核心
            if len(system_prompt) > 2000:
                logger.info("ModelAdapter: 本地模型 — 精简 system prompt")
                lines = system_prompt.split("\n")
                core_lines = [l for l in lines if l.strip() and not l.startswith("  ")]
                return "\n".join(core_lines[:30])
        return system_prompt

    def adapt_generation_params(self, base_params: Dict[str, Any]) -> Dict[str, Any]:
        """适配生成参数。

        Args:
            base_params: 基础参数

        Returns:
            适配后的参数
        """
        params = dict(base_params)

        if self.is_openai:
            # OpenAI: 可以使用 logit_bias
            params.setdefault("logit_bias", {})
            # 降低 temperature 减少随机性带来的 AI 味
            params.setdefault("temperature", 0.85)

        elif self.is_claude:
            # Claude: 不支持 logit_bias，但 system prompt 效果更好
            params.setdefault("temperature", 0.85)
            if "logit_bias" in params:
                del params["logit_bias"]

        elif self.is_local:
            # 本地模型: 更低的 temperature
            params.setdefault("temperature", 0.8)
            if "logit_bias" in params:
                del params["logit_bias"]

        return params

    def adapt_logit_bias(
        self,
        bias_config: Dict[str, float],
        tokenizer: Any = None,
    ) -> Dict[int, float]:
        """将 token 文本 bias 转为 token_id bias。

        Args:
            bias_config: {token_text: bias_value}
            tokenizer: 模型的 tokenizer（可选）

        Returns:
            {token_id: bias_value} 用于 API 调用
        """
        if not self.is_openai:
            # 非 OpenAI 模型不支持 logit_bias
            return {}

        if tokenizer is None:
            # 没有 tokenizer 时无法转换
            logger.warning("ModelAdapter: 没有 tokenizer，无法构建 logit_bias")
            return {}

        result: Dict[int, float] = {}
        for token_text, bias in bias_config.items():
            try:
                token_ids = tokenizer.encode(token_text)
                for tid in token_ids:
                    result[tid] = bias
            except Exception as e:
                logger.debug("ModelAdapter: token 编码失败 %s: %s", token_text, e)

        return result

    def get_recommended_chunk_size(self) -> int:
        """获取推荐的 chunk 大小（用于 ChunkedBufferScanner）。"""
        if self.is_local:
            return 150  # 本地模型生成速度慢，chunk 小一点
        return 200  # 云端模型 chunk 可以大一些

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息。"""
        return {
            "model_name": self._model_name,
            "is_openai": self.is_openai,
            "is_claude": self.is_claude,
            "is_local": self.is_local,
            "supports_logit_bias": self.is_openai,
            "recommended_chunk_size": self.get_recommended_chunk_size(),
        }


# 全局缓存
_adapters: Dict[str, ModelAdapter] = {}

def get_model_adapter(model_name: str = "gpt-4") -> ModelAdapter:
    """获取模型适配器。"""
    if model_name not in _adapters:
        _adapters[model_name] = ModelAdapter(model_name)
    return _adapters[model_name]
