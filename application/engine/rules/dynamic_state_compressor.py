"""动态状态压缩器 — Layer 5: 上下文配额管理。

核心机制：
- 洋葱模型配额分配：T0(核心约束) > T1(角色状态) > T2(上下文) > T3(大纲)
- 动态压缩：当总上下文超出预算时，从外层开始压缩
- T0 级约束（Anti-AI 行为协议）永远不被压缩
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ContextLayer:
    """上下文层。"""
    name: str
    tier: int  # 0=最高优先级, 3=最低
    content: str = ""
    max_chars: int = 0
    compressible: bool = True
    compressed: bool = False

    @property
    def current_chars(self) -> int:
        return len(self.content)

    @property
    def utilization(self) -> float:
        if self.max_chars <= 0:
            return 0.0
        return self.current_chars / self.max_chars


# ─── 默认配额分配 ───

DEFAULT_QUOTA = {
    0: {"name": "Anti-AI 行为协议 + 核心约束", "max_chars": 2000, "compressible": False},
    1: {"name": "角色状态锁 + 声线指纹", "max_chars": 1500, "compressible": True},
    2: {"name": "Bible 摘要 + 前情提要", "max_chars": 3000, "compressible": True},
    3: {"name": "大纲 + 节拍表", "max_chars": 2000, "compressible": True},
}

# 总预算
TOTAL_BUDGET = 8500  # 字符数


class DynamicStateCompressor:
    """动态状态压缩器。"""

    def __init__(self, total_budget: int = TOTAL_BUDGET):
        self._total_budget = total_budget
        self._layers: Dict[int, ContextLayer] = {}
        for tier, config in DEFAULT_QUOTA.items():
            self._layers[tier] = ContextLayer(
                name=config["name"],
                tier=tier,
                max_chars=config["max_chars"],
                compressible=config["compressible"],
            )

    def set_content(self, tier: int, content: str) -> None:
        """设置指定层的内容。"""
        if tier in self._layers:
            self._layers[tier].content = content
            self._layers[tier].compressed = False

    def get_total_chars(self) -> int:
        """获取当前总字符数。"""
        return sum(layer.current_chars for layer in self._layers.values())

    def get_utilization(self) -> float:
        """获取当前利用率。"""
        if self._total_budget <= 0:
            return 0.0
        return self.get_total_chars() / self._total_budget

    def compress_if_needed(self) -> bool:
        """如果超出预算，从最低优先级层开始压缩。

        Returns:
            是否执行了压缩
        """
        total = self.get_total_chars()
        if total <= self._total_budget:
            return False

        # 从最低优先级（tier 3）开始压缩
        for tier in sorted(self._layers.keys(), reverse=True):
            layer = self._layers[tier]
            if not layer.compressible:
                continue

            if layer.current_chars == 0:
                continue

            # 压缩策略：截断到 max_chars 的 70%
            target_chars = int(layer.max_chars * 0.7)
            if layer.current_chars > target_chars:
                layer.content = layer.content[:target_chars] + "\n...(已压缩)"
                layer.compressed = True
                logger.info(
                    "DynamicStateCompressor: 压缩 T%d 层 %s %d → %d 字符",
                    tier, layer.name, layer.current_chars, target_chars,
                )

            # 检查是否已经够用
            if self.get_total_chars() <= self._total_budget:
                return True

        return self.get_total_chars() <= self._total_budget

    def build_final_context(self) -> str:
        """构建最终上下文文本。"""
        self.compress_if_needed()

        parts = []
        for tier in sorted(self._layers.keys()):
            layer = self._layers[tier]
            if layer.content:
                if layer.tier == 0:
                    parts.append(f"━━━ {layer.name}（不可压缩）━━━\n{layer.content}")
                else:
                    suffix = "（已压缩）" if layer.compressed else ""
                    parts.append(f"━━━ {layer.name}{suffix} ━━━\n{layer.content}")

        return "\n\n".join(parts)

    def get_stats(self) -> Dict[str, Any]:
        """获取压缩统计。"""
        return {
            "total_budget": self._total_budget,
            "total_chars": self.get_total_chars(),
            "utilization": round(self.get_utilization(), 2),
            "layers": {
                f"T{tier}": {
                    "name": layer.name,
                    "chars": layer.current_chars,
                    "max": layer.max_chars,
                    "utilization": round(layer.utilization, 2),
                    "compressed": layer.compressed,
                    "compressible": layer.compressible,
                }
                for tier, layer in self._layers.items()
            },
        }


# 全局单例
_compressor: Optional[DynamicStateCompressor] = None

def get_dynamic_state_compressor() -> DynamicStateCompressor:
    global _compressor
    if _compressor is None:
        _compressor = DynamicStateCompressor()
    return _compressor
