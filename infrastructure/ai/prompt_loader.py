"""PromptLoader — CPMS 向后兼容代理层。

v4.0 重构（CPMS 统一入口）：
- PromptLoader 现在是 PromptRegistry 的代理
- 所有实际读取操作委托给 PromptRegistry（DB 驱动）
- 保持与 v3.0 完全相同的 API 接口（平滑迁移）
- 现有调用者无需修改，但推荐直接使用 PromptRegistry

迁移路径：
  Phase 1: PromptLoader 委托给 PromptRegistry（当前阶段）
  Phase 2: 所有调用者迁移到 PromptRegistry
  Phase 3: PromptLoader 标记为 deprecated

文件结构（仅作种子源，运行时不再直接读取）：
  infrastructure/ai/prompts/
    prompts_generation.json   — 内容生成类
    prompts_extraction.json   — 信息提取类
    prompts_review.json       — 审稿质检类
    prompts_planning.json     — 规划设计类
    prompts_world.json        — 世界设定类
    prompts_creative.json     — 创意辅助类
    prompts_anti_ai.json      — Anti-AI 防御类
    prompts_defaults.json     — (旧版兼容，不再主动加载)
"""
from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 提示词目录（仅作种子源参考）
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class PromptLoader:
    """CPMS 向后兼容代理 — 所有操作委托给 PromptRegistry。

    v4.0: PromptLoader 不再直接读取 JSON 文件，
    而是委托给 PromptRegistry（DB 驱动，SSOT）。
    保持与 v3.0 完全相同的 API 接口。
    """

    _instance: Optional["PromptLoader"] = None

    def __new__(cls) -> "PromptLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_registry(self):
        """获取 PromptRegistry 实例（延迟导入避免循环依赖）。"""
        from infrastructure.ai.prompt_registry import get_prompt_registry
        return get_prompt_registry()

    def reload(self) -> None:
        """热重载（委托给 PromptRegistry）。"""
        self._get_registry().hot_reload()

    # ------------------------------------------------------------------
    # 基础查询（委托给 PromptRegistry）
    # ------------------------------------------------------------------

    def get(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """按 id 获取完整提示词条目。

        Returns:
          None 或包含 id/name/system/user_template 等字段的 dict。
        """
        registry = self._get_registry()
        node = registry.get_node(prompt_id)
        if not node:
            return None
        return node.to_detail_dict()

    def get_system(self, prompt_id: str) -> str:
        """获取 system 提示词文本。"""
        return self._get_registry().get_system(prompt_id)

    def get_user_template(self, prompt_id: str) -> str:
        """获取 user_template 模板文本。"""
        return self._get_registry().get_user_template(prompt_id)

    def get_field(self, prompt_id: str, field: str, default: Any = None) -> Any:
        """获取指定字段值。"""
        return self._get_registry().get_field(prompt_id, field, default)

    # ------------------------------------------------------------------
    # 特殊结构访问（委托给 PromptRegistry）
    # ------------------------------------------------------------------

    def get_directives_dict(
        self, prompt_id: str, directives_key: str = "_directives"
    ) -> Dict[str, str]:
        """获取指令字典。"""
        return self._get_registry().get_directives_dict(prompt_id, directives_key)

    def get_list_field(
        self, prompt_id: str, field: str
    ) -> List[str]:
        """获取列表字段。"""
        return self._get_registry().get_list_field(prompt_id, field)

    def render(
        self,
        prompt_id: str,
        template_field: str = "user_template",
        variables: Optional[Dict[str, Any]] = None,
    ) -> str:
        """渲染模板（委托给 PromptRegistry 的模板引擎）。"""
        registry = self._get_registry()

        if template_field == "user_template":
            result = registry.render(prompt_id, variables)
            return result.user if result else ""
        elif template_field in ("system", "system_template"):
            result = registry.render(prompt_id, variables)
            return result.system if result else ""
        else:
            # 回退：获取原始字段文本
            raw = registry.get_field(prompt_id, template_field, "")
            return raw or ""

    # ------------------------------------------------------------------
    # 分类信息（委托给 PromptRegistry）
    # ------------------------------------------------------------------

    def get_categories(self) -> List[Dict[str, Any]]:
        """获取所有分类定义。"""
        return self._get_registry().get_categories()

    def get_category(self, key: str) -> Optional[Dict[str, Any]]:
        """获取单个分类定义。"""
        categories = self.get_categories()
        for cat in categories:
            if cat.get("key") == key:
                return cat
        return None

    # ------------------------------------------------------------------
    # 元信息
    # ------------------------------------------------------------------

    @property
    def all_ids(self) -> List[str]:
        """所有已注册的提示词 ID 列表。"""
        return self._get_registry().all_ids

    def list_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按分类列出提示词条目。"""
        return self._get_registry().list_by_category(category)

    @property
    def meta(self) -> Dict[str, Any]:
        """返回 _meta 信息（兼容旧版）。"""
        return {"version": "4.0.0", "engine": "cpms"}

    def exists(self, prompt_id: str) -> bool:
        """检查提示词是否存在。"""
        return self._get_registry().exists(prompt_id)

    @property
    def total_count(self) -> int:
        """已加载的提示词总数。"""
        return self._get_registry().total_count


# ------------------------------------------------------------------
# 便捷函数（推荐使用方式）
# ------------------------------------------------------------------


def get_prompt_loader() -> PromptLoader:
    """获取全局 PromptLoader 单例。"""
    return PromptLoader()


def get_directives(prompt_id: str) -> Dict[str, str]:
    """快捷方式：获取指令字典。"""
    return get_prompt_loader().get_directives_dict(prompt_id)


def get_prompt_text(
    prompt_id: str, field: str = "user_template"
) -> str:
    """快捷方式：获取某个字段的原始文本。"""
    return get_prompt_loader().get_field(prompt_id, field, "")
