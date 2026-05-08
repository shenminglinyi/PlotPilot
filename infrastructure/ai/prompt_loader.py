"""PromptLoader — 轻量级提示词直接读取器（多 JSON 文件驱动）。

v3.0 重构：
- 从单个 prompts_defaults.json 拆分为多个分类 JSON 文件
- 支持多文件加载：prompts_*.json 均自动扫描
- 保留对旧版 prompts_defaults.json 的向后兼容
- 提供类型安全的访问接口（dict / list / str）
- 零依赖：不需要数据库连接，启动即用
- 单例缓存：只读一次 JSON，后续全内存

文件结构：
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
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 提示词目录
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# 分类 JSON 文件的 glob 模式
_CATEGORY_GLOB = "prompts_*.json"

# 旧版单文件路径（向后兼容）
_LEGACY_DEFAULTS_PATH = _PROMPTS_DIR / "prompts_defaults.json"

# 加载优先级：分类文件 > 旧版单文件
# 分类文件中的提示词会覆盖旧版中同 ID 的提示词


class PromptLoader:
    """轻量级提示词加载器 — 多 JSON 文件读取，无 DB 依赖。"""

    _instance: Optional["PromptLoader"] = None
    _data: Dict[str, Any] = {"_meta": {}, "categories": [], "prompts": []}
    _index: Dict[str, Dict[str, Any]] = {}  # id -> prompt entry
    _categories: Dict[str, Dict[str, Any]] = {}  # key -> category definition

    def __new__(cls) -> "PromptLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """加载所有提示词 JSON 文件（分类文件 + 旧版兼容）。"""
        self._data = {"_meta": {"version": "3.0.0"}, "categories": [], "prompts": []}
        self._index = {}
        self._categories = {}

        prompts_dir = _PROMPTS_DIR
        if not prompts_dir.exists():
            logger.warning("PromptLoader: 提示词目录不存在 %s", prompts_dir)
            return

        # Phase 1: 加载旧版 prompts_defaults.json（低优先级）
        legacy_prompts = self._load_single_file(_LEGACY_DEFAULTS_PATH)

        # Phase 2: 加载所有分类 JSON 文件（高优先级，覆盖旧版）
        category_files = sorted(prompts_dir.glob(_CATEGORY_GLOB))
        category_prompts: Dict[str, Dict[str, Any]] = {}  # id -> prompt

        for cat_file in category_files:
            file_data = self._load_single_file(cat_file)
            if not file_data:
                continue

            # 提取分类定义
            cat_def = file_data.get("category", {})
            if cat_def and "key" in cat_def:
                self._categories[cat_def["key"]] = cat_def

            # 提取提示词
            for p in file_data.get("prompts", []):
                if "id" in p:
                    category_prompts[p["id"]] = p

        # Phase 3: 合并：旧版 + 分类覆盖
        all_prompts: Dict[str, Dict[str, Any]] = {}

        # 先放入旧版
        for p in legacy_prompts:
            if "id" in p:
                all_prompts[p["id"]] = p

        # 分类文件覆盖旧版
        for pid, p in category_prompts.items():
            all_prompts[pid] = p

        # 构建索引和数据
        self._index = all_prompts
        self._data["prompts"] = list(all_prompts.values())

        # 构建分类列表
        # 如果分类文件有定义则用分类文件的，否则从提示词中推断
        if self._categories:
            self._data["categories"] = sorted(
                list(self._categories.values()),
                key=lambda c: c.get("sort_order", 99)
            )
        elif legacy_prompts:
            # 旧版兼容：从旧版 _meta/categories 提取
            legacy_data = self._load_raw_json(_LEGACY_DEFAULTS_PATH)
            if legacy_data:
                self._data["categories"] = legacy_data.get("categories", [])
                self._data["_meta"] = legacy_data.get("_meta", {})

        # 补充：收集提示词中出现的分类但不在 categories 列表中的
        existing_cat_keys = {c.get("key") for c in self._data["categories"]}
        for p in all_prompts.values():
            cat_key = p.get("category", "")
            if cat_key and cat_key not in existing_cat_keys:
                self._data["categories"].append({
                    "key": cat_key,
                    "name": cat_key,
                    "icon": "📝",
                    "description": "",
                    "color": "#6b7280",
                })
                existing_cat_keys.add(cat_key)

        logger.info(
            "PromptLoader: 已加载 %d 个提示词模板（%d 个分类文件），%d 个分类",
            len(self._index),
            len(category_files),
            len(self._data["categories"]),
        )

    @staticmethod
    def _load_raw_json(path: Path) -> Optional[Dict[str, Any]]:
        """加载 JSON 文件的原始数据。"""
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("PromptLoader: 读取 JSON 失败 %s — %s", path, exc)
            return None

    def _load_single_file(self, path: Path) -> List[Dict[str, Any]]:
        """从单个 JSON 文件加载提示词列表。"""
        data = self._load_raw_json(path)
        if not data:
            return []
        return data.get("prompts", [])

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
    # 分类信息
    # ------------------------------------------------------------------

    def get_categories(self) -> List[Dict[str, Any]]:
        """获取所有分类定义（含 sort_order 排序）。"""
        return self._data.get("categories", [])

    def get_category(self, key: str) -> Optional[Dict[str, Any]]:
        """获取单个分类定义。"""
        return self._categories.get(key)

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

    @property
    def total_count(self) -> int:
        """已加载的提示词总数。"""
        return len(self._index)


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
