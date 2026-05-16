"""TokenGuard + SafeLogitBiasBuilder — Layer 6 辅助: Token 级硬拦截。

核心机制：
- TokenGuard: 管理 AI 味 Token 黑名单
- SafeLogitBiasBuilder: 安全地构建 Logit Bias 参数

重要设计决策：
- 中文 Token 碎片化导致 Logit Bias 误伤率高
- 因此：AC 自动机为主扫描器（文本层面），Logit Bias 为辅助（Token 层面）
- Logit Bias 仅用于高确信度的英文 Token（如 "however", "furthermore" 等）
- 中文 AI 味检测完全依赖 AC 自动机
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TokenBiasEntry:
    """Token 偏置条目。"""
    token: str
    token_id: Optional[int] = None
    bias: float = -100.0  # -100 = 完全禁止, -10 = 强力抑制, -1 = 轻微抑制
    reason: str = ""
    language: str = "en"  # en / zh


# ─── 高确信度英文 AI 味 Token 黑名单 ───

ENGLISH_AI_TOKENS: List[TokenBiasEntry] = [
    # 转折/连接词（AI写作中过度使用）
    TokenBiasEntry(token="However", bias=-5.0, reason="AI转折词偏好", language="en"),
    TokenBiasEntry(token="Furthermore", bias=-10.0, reason="AI递进词偏好", language="en"),
    TokenBiasEntry(token="Moreover", bias=-10.0, reason="AI递进词偏好", language="en"),
    TokenBiasEntry(token="Nevertheless", bias=-8.0, reason="AI转折词偏好", language="en"),
    TokenBiasEntry(token="Additionally", bias=-8.0, reason="AI补充词偏好", language="en"),
    TokenBiasEntry(token="Consequently", bias=-8.0, reason="AI因果词偏好", language="en"),
    TokenBiasEntry(token="Subsequently", bias=-8.0, reason="AI时间词偏好", language="en"),
    TokenBiasEntry(token="Notably", bias=-5.0, reason="AI强调词偏好", language="en"),
    TokenBiasEntry(token="Essentially", bias=-5.0, reason="AI总结词偏好", language="en"),
    TokenBiasEntry(token="Undoubtedly", bias=-8.0, reason="AI断言词偏好", language="en"),
    TokenBiasEntry(token="Intriguingly", bias=-10.0, reason="AI形容词偏好", language="en"),
    TokenBiasEntry(token="Remarkably", bias=-10.0, reason="AI形容词偏好", language="en"),
]


class TokenGuard:
    """Token 级硬拦截守卫。"""

    def __init__(self):
        self._blacklist: Dict[str, TokenBiasEntry] = {}
        for entry in ENGLISH_AI_TOKENS:
            self._blacklist[entry.token.lower()] = entry

    def add_token(self, entry: TokenBiasEntry) -> None:
        """添加 Token 到黑名单。"""
        self._blacklist[entry.token.lower()] = entry

    def is_blocked(self, token: str) -> bool:
        """检查 Token 是否被完全禁止。"""
        entry = self._blacklist.get(token.lower())
        return entry is not None and entry.bias <= -100.0

    def get_bias(self, token: str) -> float:
        """获取 Token 的偏置值。"""
        entry = self._blacklist.get(token.lower())
        return entry.bias if entry else 0.0

    def get_all_entries(self) -> List[TokenBiasEntry]:
        """获取所有黑名单条目。"""
        return list(self._blacklist.values())


class SafeLogitBiasBuilder:
    """安全 Logit Bias 构建器。

    核心安全策略：
    1. 中文 Token 不加入 Logit Bias（碎片化误伤）
    2. 仅对高确信度英文 Token 生效
    3. bias 值不能过激（最低 -10，不用 -100）
    4. 每个 request 的 bias 条目数有上限
    """

    MAX_BIAS_ENTRIES = 50
    MIN_BIAS = -10.0  # 不使用 -100（完全禁止），避免误伤

    def __init__(self, token_guard: Optional[TokenGuard] = None):
        self._guard = token_guard or TokenGuard()

    def build_logit_bias(
        self,
        model_name: str = "",
        extra_suppressions: Optional[Dict[str, float]] = None,
    ) -> Dict[int, float]:
        """构建 Logit Bias 字典。

        Args:
            model_name: 模型名称（用于适配不同 tokenizer）
            extra_suppressions: 额外的抑制项 {token: bias}

        Returns:
            OpenAI API 的 logit_bias 参数 {token_id: bias}
        """
        # 注意：实际使用时需要将 token 文本转为 token_id
        # 这里返回的是概念性的 bias 配置
        # 在运行时，由 model_adapter 负责将 token 文本转为 ID

        bias_config: Dict[str, float] = {}

        # 从 TokenGuard 获取基础 bias
        for entry in self._guard.get_all_entries():
            if entry.language == "en":  # 仅英文
                bias_config[entry.token] = max(entry.bias, self.MIN_BIAS)

        # 合并额外抑制
        if extra_suppressions:
            for token, bias in extra_suppressions.items():
                bias_config[token] = max(bias, self.MIN_BIAS)

        # 限制条目数
        if len(bias_config) > self.MAX_BIAS_ENTRIES:
            # 保留 bias 值最低（抑制最强）的条目
            sorted_items = sorted(bias_config.items(), key=lambda x: x[1])
            bias_config = dict(sorted_items[:self.MAX_BIAS_ENTRIES])

        logger.info(
            "SafeLogitBiasBuilder: 已构建 %d 条 Logit Bias 配置",
            len(bias_config),
        )

        # 返回配置（token_id 需要运行时转换）
        return bias_config

    def get_bias_config_for_api(self, model_name: str = "") -> Dict[str, Any]:
        """获取 API 调用所需的 bias 配置。

        Returns:
            可直接用于 API 调用的配置字典。
        """
        bias_config = self.build_logit_bias(model_name)
        return {
            "logit_bias_config": bias_config,
            "note": "token_id mapping needs to be done at runtime by model_adapter",
        }


# 全局单例
_guard: Optional[TokenGuard] = None
_builder: Optional[SafeLogitBiasBuilder] = None

def get_token_guard() -> TokenGuard:
    global _guard
    if _guard is None:
        _guard = TokenGuard()
    return _guard

def get_logit_bias_builder() -> SafeLogitBiasBuilder:
    global _builder
    if _builder is None:
        _builder = SafeLogitBiasBuilder()
    return _builder
