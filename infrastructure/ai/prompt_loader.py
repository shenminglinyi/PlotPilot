"""PromptLoader — 轻量级提示词直接读取器（JSON 文件驱动）。

与 PromptManager（数据库驱动、面向 UI 编辑）不同，本模块专注于：
- 从 prompts_defaults.json 直接读取提示词内容
- 提供类型安全的访问接口（dict / list / str）
- 零依赖：不需要数据库连接，启动即用
- 单例缓存：只读一次 JSON，后续全内存

适用场景：
  代码中的硬编码提示词 → 统一从此模块获取
  运行时需要提示词文本/模板/指令字典的任何地方
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# JSON 种子文件路径
_DEFAULTS_PATH = (
    Path(__file__).resolve().parent / "prompts" / "prompts_defaults.json"
)


class PromptLoader:
    """轻量级提示词加载器 — 直接从 JSON 读取，无 DB 依赖。"""

    _instance: Optional["PromptLoader"] = None
    _data: Dict[str, Any] = {}
    _index: Dict[str, Dict[str, Any]] = {}  # id -> prompt entry

    def __new__(cls) -> "PromptLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """加载并索引 prompts_defaults.json。"""
        path = _DEFAULTS_PATH
        if not path.exists():
            logger.warning("PromptLoader: 种子文件不存在 %s", path)
            self._data = {}
            self._index = {}
            return

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("PromptLoader: 读取种子文件失败 %s", exc)
            self._data = {}
            self._index = {}
            return

        self._data = raw
        # 按 id 建立快速索引
        self._index = {
            p["id"]: p for p in raw.get("prompts", []) if "id" in p
        }
        logger.info(
            "PromptLoader: 已加载 %d 个提示词模板",
            len(self._index),
        )

    def reload(self) -> None:
        """重新加载（编辑 JSON 后调用）。"""
        self._load()

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------

    def get(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """按 id 获取完整提示词条目。

        Returns:
          None 或包含 id/name/system/user_template/_directives 等字段的 dict。
        """
        return self._index.get(prompt_id)

    def get_system(self, prompt_id: str) -> str:
        """获取 system 提示词文本。"""
        entry = self._index.get(prompt_id)
        return (entry or {}).get("system", "")

    def get_user_template(self, prompt_id: str) -> str:
        """获取 user_template 模板文本。"""
        entry = self._index.get(prompt_id)
        return (entry or {}).get("user_template", "")

    def get_field(self, prompt_id: str, field: str, default: Any = None) -> Any:
        """获取指定字段值（支持下划线前缀的私有字段如 _directives）。"""
        entry = self._index.get(prompt_id)
        if not entry:
            return default
        return entry.get(field, default)

    # ------------------------------------------------------------------
    # 特殊结构访问（为沙漏 / 节拍等场景优化）
    # ------------------------------------------------------------------

    def get_directives_dict(
        self, prompt_id: str, directives_key: str = "_directives"
    ) -> Dict[str, str]:
        """获取指令字典（如 PHASE_DIRECTIVES: {OPENING: "...", ...}）。

        Returns:
          空字典（找不到时安全降级）。
        """
        entry = self._index.get(prompt_id)
        if not entry:
            return {}
        raw = entry.get(directives_key, {})
        if isinstance(raw, dict):
            # 确保所有 value 都是 str
            return {k: str(v) for k, v in raw.items()}
        return {}

    def get_list_field(
        self, prompt_id: str, field: str
    ) -> List[str]:
        """获取列表字段（如 _sensory_rotation）。

        Returns:
          空列表（找不到时安全降级）。
        """
        entry = self._index.get(prompt_id)
        if not entry:
            return []
        raw = entry.get(field, [])
        if isinstance(raw, list):
            return [str(x) for x in raw]
        return []

    def render(
        self,
        prompt_id: str,
        template_field: str = "user_template",
        variables: Optional[Dict[str, Any]] = None,
    ) -> str:
        """简单渲染模板（{variable} 替换）。

        Args:
            prompt_id: 提示词 ID
            template_field: 要渲染的字段名（默认 user_template，
                           也可传 system_template 等）
            variables: 变量字典

        Returns:
          渲染后的字符串。
        """
        raw = self.get_field(prompt_id, template_field, "")
        if not raw or not variables:
            return raw

        class SafeDict(dict):
            def __missing__(self, key: str) -> str:
                return "{" + key + "}"

        try:
            return raw.format_map(SafeDict(variables))
        except (KeyError, ValueError, IndexError):
            return raw

    # ------------------------------------------------------------------
    # 元信息
    # ------------------------------------------------------------------

    @property
    def all_ids(self) -> List[str]:
        """所有已注册的提示词 ID 列表。"""
        return list(self._index.keys())

    def list_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按分类列出提示词条目。"""
        return [
            p for p in self._index.values() if p.get("category") == category
        ]

    @property
    def meta(self) -> Dict[str, Any]:
        """返回 _meta 信息。"""
        return self._data.get("_meta", {})

    def exists(self, prompt_id: str) -> bool:
        """检查提示词是否存在。"""
        return prompt_id in self._index


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
