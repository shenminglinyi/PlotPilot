"""PromptRegistry — CPMS 统一提示词注册中心。

核心设计（SSOT 原则）：
- 所有业务代码通过 PromptRegistry 读取提示词（替代 PromptLoader + PromptManager 双轨制）
- PromptRegistry 底层从 PromptManager（DB）读取，不再直接读 JSON 文件
- 提供缓存层（内存缓存，避免频繁 DB 查询）
- 提供热重载能力（修改后立即生效）
- 完整兼容 PromptLoader 的所有查询接口（平滑迁移）

Architecture:
  PromptRegistry (facade)
    ├─ PromptManager     (DB 读写)
    ├─ PromptTemplateEngine (渲染)
    ├─ VariableRegistry   (变量 Schema)
    └─ PromptBindingStore (工作流绑定)

迁移路径：
  1. PromptLoader 的所有调用者改为调用 PromptRegistry
  2. PromptLoader 本身改为 PromptRegistry 的代理（过渡期）
  3. 最终移除 PromptLoader
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.prompt_manager import (
    NodeInfo,
    PromptManager,
    get_prompt_manager,
)
from infrastructure.ai.prompt_template_engine import (
    PromptTemplateEngine,
    RenderResult,
    ValidationResult,
    VariableSchema,
    get_template_engine,
)

logger = logging.getLogger(__name__)


class PromptRegistry:
    """CPMS 统一提示词注册中心。

    职责：
    1. 统一读取入口：所有业务代码从这里获取提示词
    2. 缓存管理：内存缓存避免频繁 DB 查询，支持 TTL 和手动失效
    3. 渲染服务：集成 PromptTemplateEngine（Jinja2）
    4. 兼容层：提供与 PromptLoader 兼容的接口（平滑迁移）
    5. 热重载：修改后缓存立即失效
    """

    def __init__(
        self,
        prompt_manager: Optional[PromptManager] = None,
        template_engine: Optional[PromptTemplateEngine] = None,
        cache_ttl_seconds: int = 300,  # 默认 5 分钟缓存
    ):
        self._mgr = prompt_manager
        self._engine = template_engine
        self._cache_ttl = cache_ttl_seconds

        # 内存缓存
        self._node_cache: Dict[str, NodeInfo] = {}    # node_key -> NodeInfo
        self._cache_timestamps: Dict[str, float] = {}  # node_key -> timestamp
        self._categories_cache: Optional[List[Dict]] = None
        self._categories_cache_ts: float = 0

    # ─── 依赖注入（延迟初始化） ───

    def _get_manager(self) -> PromptManager:
        if self._mgr is None:
            self._mgr = get_prompt_manager()
        return self._mgr

    def _get_engine(self) -> PromptTemplateEngine:
        if self._engine is None:
            self._engine = get_template_engine()
        return self._engine

    # ─── 核心读取（统一入口） ───

    def get_node(self, node_key: str, use_cache: bool = True) -> Optional[NodeInfo]:
        """按 node_key 获取提示词节点（含激活版本内容）。

        这是所有业务代码应使用的**唯一**读取入口。
        """
        # 检查缓存
        if use_cache and node_key in self._node_cache:
            ts = self._cache_timestamps.get(node_key, 0)
            if time.time() - ts < self._cache_ttl:
                return self._node_cache[node_key]

        mgr = self._get_manager()
        mgr.ensure_seeded()
        node = mgr.get_node(node_key, by_key=True)

        if node:
            self._node_cache[node_key] = node
            self._cache_timestamps[node_key] = time.time()

        return node

    def get_system(self, node_key: str) -> str:
        """获取节点的 system prompt 文本。"""
        node = self.get_node(node_key)
        return node.get_active_system() if node else ""

    def get_user_template(self, node_key: str) -> str:
        """获取节点的 user_template 文本。"""
        node = self.get_node(node_key)
        return node.get_active_user_template() if node else ""

    def get_field(self, node_key: str, field: str, default: Any = None) -> Any:
        """获取节点的指定字段值。

        兼容 PromptLoader.get_field() 接口。
        """
        node = self.get_node(node_key)
        if not node:
            return default

        # 特殊字段映射
        field_map = {
            "system": node.get_active_system,
            "user_template": node.get_active_user_template,
            "node_key": lambda: node.node_key,
            "name": lambda: node.name,
            "description": lambda: node.description,
            "category": lambda: node.category,
            "source": lambda: node.source,
            "output_format": lambda: node.output_format,
            "tags": lambda: node.tags,
            "variables": lambda: node.variables,
            "is_builtin": lambda: node.is_builtin,
        }

        if field in field_map:
            result = field_map[field]
            return result() if callable(result) else result

        # 下划线前缀的私有字段（如 _directives）— 从变量中查找
        if field.startswith("_"):
            for var in node.variables:
                if var.get("name") == field:
                    return var.get("value", var.get("default", default))
            return default

        return default

    def get_directives_dict(
        self, node_key: str, directives_key: str = "_directives"
    ) -> Dict[str, str]:
        """获取指令字典（如 PHASE_DIRECTIVES）。

        兼容 PromptLoader.get_directives_dict() 接口。
        """
        node = self.get_node(node_key)
        if not node:
            return {}

        # 从节点的变量中查找 directives 字段
        for var in node.variables:
            if var.get("name") == directives_key:
                raw = var.get("value", var.get("default", {}))
                if isinstance(raw, dict):
                    return {k: str(v) for k, v in raw.items()}
        return {}

    def get_list_field(self, node_key: str, field: str) -> List[str]:
        """获取列表字段（如 _sensory_rotation）。

        兼容 PromptLoader.get_list_field() 接口。
        """
        node = self.get_node(node_key)
        if not node:
            return []

        for var in node.variables:
            if var.get("name") == field:
                raw = var.get("value", var.get("default", []))
                if isinstance(raw, list):
                    return [str(x) for x in raw]
        return []

    # ─── 渲染 ───

    def render(
        self,
        node_key: str,
        variables: Optional[Dict[str, Any]] = None,
        validate_schemas: bool = False,
    ) -> Optional[RenderResult]:
        """渲染指定节点的提示词。

        这是业务代码获取最终 Prompt 的核心方法。

        Args:
            node_key: 节点唯一标识
            variables: 模板变量字典
            validate_schemas: 是否进行 Schema 校验

        Returns:
            RenderResult 或 None（节点不存在时）
        """
        node = self.get_node(node_key)
        if not node:
            return None

        engine = self._get_engine()
        var_map = variables or {}

        # 获取变量 Schema（如果启用了校验）
        var_schemas = None
        if validate_schemas:
            var_schemas = self._build_variable_schemas(node)

        return engine.render(
            system_template=node.get_active_system(),
            user_template=node.get_active_user_template(),
            variables=var_map,
            variable_schemas=var_schemas,
        )

    def render_to_prompt(
        self,
        node_key: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Optional[Prompt]:
        """渲染指定节点并返回 Prompt 值对象（直接传给 LLMService）。

        这是最高层的便捷方法，业务代码只需一行：
            prompt = registry.render_to_prompt("chapter-generation-main", vars)
            result = await llm_service.generate(prompt, config)
        """
        result = self.render(node_key, variables)
        if not result:
            return None

        system = result.system or ""
        user = result.user

        if not user or not user.strip():
            logger.warning("节点 %s 的 user prompt 渲染结果为空", node_key)
            return None

        return Prompt(system=system, user=user)

    def mock_render(self, node_key: str) -> Optional[RenderResult]:
        """沙盒渲染（保存前校验）。

        用于提示词广场：用户修改提示词后，保存前先用 mock 渲染验证。
        """
        node = self.get_node(node_key)
        if not node:
            return None

        engine = self._get_engine()
        var_schemas = self._build_variable_schema(node)

        return engine.mock_render(
            system_template=node.get_active_system(),
            user_template=node.get_active_user_template(),
            variable_schemas=var_schemas,
        )

    # ─── 分类与搜索 ───

    def get_categories(self) -> List[Dict[str, Any]]:
        """获取所有分类定义。兼容 PromptLoader.get_categories()。"""
        now = time.time()
        if (self._categories_cache is not None
                and now - self._categories_cache_ts < self._cache_ttl):
            return self._categories_cache

        mgr = self._get_manager()
        mgr.ensure_seeded()
        result = mgr.get_categories_info()
        self._categories_cache = result
        self._categories_cache_ts = now
        return result

    def list_nodes(
        self,
        category: Optional[str] = None,
        include_versions: bool = False,
    ) -> List[NodeInfo]:
        """列举提示词节点。"""
        mgr = self._get_manager()
        mgr.ensure_seeded()
        return mgr.list_nodes(
            category=category,
            include_versions=include_versions,
        )

    def search_nodes(self, query: str) -> List[NodeInfo]:
        """搜索节点。"""
        mgr = self._get_manager()
        mgr.ensure_seeded()
        return mgr.search_nodes(query)

    def exists(self, node_key: str) -> bool:
        """检查提示词是否存在。兼容 PromptLoader.exists()。"""
        return self.get_node(node_key) is not None

    @property
    def all_ids(self) -> List[str]:
        """所有已注册的提示词 ID 列表。兼容 PromptLoader.all_ids。"""
        nodes = self.list_nodes()
        return [n.node_key for n in nodes]

    @property
    def total_count(self) -> int:
        """已注册的提示词总数。兼容 PromptLoader.total_count。"""
        nodes = self.list_nodes()
        return len(nodes)

    def list_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按分类列出提示词。兼容 PromptLoader.list_by_category()。"""
        nodes = self.list_nodes(category=category, include_versions=True)
        return [n.to_detail_dict() for n in nodes]

    # ─── 缓存管理 ───

    def invalidate_cache(self, node_key: Optional[str] = None) -> None:
        """使缓存失效。

        Args:
            node_key: 指定节点 key，为 None 时清除全部缓存
        """
        if node_key:
            self._node_cache.pop(node_key, None)
            self._cache_timestamps.pop(node_key, None)
        else:
            self._node_cache.clear()
            self._cache_timestamps.clear()
            self._categories_cache = None
            self._categories_cache_ts = 0

        logger.debug("缓存已失效: %s", node_key or "全部")

    def hot_reload(self) -> None:
        """热重载：清除所有缓存，下次读取时重新从 DB 加载。"""
        self.invalidate_cache()
        logger.info("PromptRegistry: 热重载完成，缓存已清除")

    # ─── 主题 Agent 专用 ───

    def get_theme_directives(self, genre: str, method: str) -> str:
        """查询主题 Agent 的指定方法文本。

        Args:
            genre: 题材 key（如 "romance"）
            method: 方法名（如 "system_persona"）

        Returns:
            提示词文本，不存在则返回空字符串
        """
        node_key = f"theme-{genre}-{method}"
        return self.get_system(node_key) or self.get_user_template(node_key)

    def get_skill_prompt(self, skill_key: str, method: str = "context") -> str:
        """查询 Skill 的提示词。

        Args:
            skill_key: 技能 key（如 "battle_choreography"）
            method: 注入点（如 "context", "beat", "audit"）

        Returns:
            提示词文本
        """
        node_key = f"skill-{skill_key}-{method}"
        return self.get_system(node_key) or self.get_user_template(node_key)

    # ─── 内部方法 ───

    @staticmethod
    def _build_variable_schemas(node: NodeInfo) -> Dict[str, VariableSchema]:
        """从节点的 variables 列表构建 VariableSchema 字典。"""
        from infrastructure.ai.prompt_template_engine import VariableType, VariableScope

        schemas = {}
        for var_def in node.variables:
            name = var_def.get("name", "")
            if not name:
                continue

            type_str = var_def.get("type", "string")
            try:
                var_type = VariableType(type_str)
            except ValueError:
                var_type = VariableType.STRING

            scope_str = var_def.get("scope", "chapter")
            try:
                var_scope = VariableScope(scope_str)
            except ValueError:
                var_scope = VariableScope.CHAPTER

            schemas[name] = VariableSchema(
                name=name,
                display_name=var_def.get("display_name", var_def.get("desc", name)),
                type=var_type,
                required=var_def.get("required", False),
                default=var_def.get("default"),
                description=var_def.get("desc", ""),
                source=var_def.get("source", ""),
                scope=var_scope,
                enum_values=var_def.get("enum_values", []),
            )

        return schemas


# ─── 全局单例 ───

_registry_instance: Optional[PromptRegistry] = None


def get_prompt_registry() -> PromptRegistry:
    """获取全局 PromptRegistry 单例。"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = PromptRegistry()
    return _registry_instance
