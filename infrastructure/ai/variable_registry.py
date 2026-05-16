"""VariableRegistry — CPMS 全局变量注册表。

核心设计：
- 所有提示词模板中使用的变量都有统一的注册和 Schema 定义
- 提供类型安全的变量访问接口
- 支持变量作用域（全局/小说/章节/场景/节拍）
- 广场 UI 可浏览所有可用变量（类似表达式编辑器）
- 变量数据存入数据库，支持热更新

Architecture:
  VariableRegistry
    ├─ register()          — 注册变量
    ├─ validate()          — 校验变量集
    ├─ get_schemas_for_node() — 获取节点所需的变量 Schema
    ├─ resolve()           — 解析变量值（支持多级路径如 bible.character.name）
    └─ suggest_variables() — 为广场 UI 提供可用变量列表
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from infrastructure.ai.prompt_template_engine import (
    VariableSchema,
    VariableScope,
    VariableType,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class VariableRegistry:
    """CPMS 全局变量注册表。

    职责：
    1. 统一管理所有提示词模板中使用的变量定义
    2. 提供类型安全的变量访问和校验
    3. 支持变量作用域和默认值
    4. 为广场 UI 提供可用变量面板
    5. 变量注册数据存入 DB（持久化 + 热更新）
    """

    def __init__(self, db_connection=None):
        self._db = db_connection
        # 内存缓存：name -> VariableSchema
        self._schemas: Dict[str, VariableSchema] = {}
        self._loaded = False

    def _get_db(self):
        if self._db is not None:
            return self._db
        from infrastructure.persistence.database.connection import get_database
        return get_database()

    def _ensure_loaded(self) -> None:
        """从 DB 加载变量注册表（惰性加载，只加载一次）。"""
        if self._loaded:
            return

        db = self._get_db()
        conn = db.get_connection()

        try:
            rows = conn.execute(
                "SELECT * FROM variable_registry ORDER BY scope, name"
            ).fetchall()

            for row in rows:
                try:
                    var_type = VariableType(row["type"])
                except ValueError:
                    var_type = VariableType.STRING

                try:
                    var_scope = VariableScope(row["scope"])
                except ValueError:
                    var_scope = VariableScope.CHAPTER

                default_val = row.get("default_value")
                if default_val is not None and isinstance(default_val, str):
                    try:
                        default_val = json.loads(default_val)
                    except (json.JSONDecodeError, TypeError):
                        pass

                enum_values = row.get("enum_values", "[]")
                if isinstance(enum_values, str):
                    try:
                        enum_values = json.loads(enum_values)
                    except (json.JSONDecodeError, TypeError):
                        enum_values = []

                self._schemas[row["name"]] = VariableSchema(
                    name=row["name"],
                    display_name=row.get("display_name", row["name"]),
                    type=var_type,
                    required=bool(row.get("is_required", 0)),
                    default=default_val,
                    description=row.get("description", ""),
                    source=row.get("source", ""),
                    scope=var_scope,
                    enum_values=enum_values,
                    examples=row.get("examples", "[]") if isinstance(row.get("examples"), list) else [],
                )

            self._loaded = True
            logger.info("VariableRegistry: 已加载 %d 个变量定义", len(self._schemas))

        except Exception as exc:
            logger.warning("VariableRegistry: 从 DB 加载失败 (%s)，使用空注册表", exc)
            self._loaded = True  # 避免反复重试

    # ─── 注册 ───

    def register(self, schema: VariableSchema, persist: bool = True) -> None:
        """注册变量定义。

        Args:
            schema: 变量 Schema
            persist: 是否持久化到 DB
        """
        self._ensure_loaded()
        self._schemas[schema.name] = schema

        if persist:
            self._persist_schema(schema)

    def register_batch(self, schemas: List[VariableSchema]) -> int:
        """批量注册变量定义。返回新增数量。"""
        self._ensure_loaded()
        count = 0
        for schema in schemas:
            if schema.name not in self._schemas:
                self.register(schema, persist=True)
                count += 1
            else:
                # 更新（如果 Schema 有变化）
                existing = self._schemas[schema.name]
                if self._schema_changed(existing, schema):
                    self._schemas[schema.name] = schema
                    self._persist_schema(schema)
                    count += 1
        return count

    def unregister(self, name: str) -> bool:
        """取消注册变量。"""
        self._ensure_loaded()
        if name not in self._schemas:
            return False

        del self._schemas[name]
        db = self._get_db()
        conn = db.get_connection()
        conn.execute("DELETE FROM variable_registry WHERE name = ?", (name,))
        conn.commit()
        return True

    # ─── 查询 ───

    def get_schema(self, name: str) -> Optional[VariableSchema]:
        """获取变量 Schema。"""
        self._ensure_loaded()
        return self._schemas.get(name)

    def get_schemas_for_node(self, node_key: str) -> Dict[str, VariableSchema]:
        """获取指定节点所需的变量 Schema。

        从 PromptManager 获取节点的变量列表，再从注册表匹配 Schema。
        """
        self._ensure_loaded()

        from infrastructure.ai.prompt_manager import get_prompt_manager
        mgr = get_prompt_manager()
        mgr.ensure_seeded()

        node = mgr.get_node(node_key, by_key=True)
        if not node:
            return {}

        result: Dict[str, VariableSchema] = {}
        for var_def in node.variables:
            var_name = var_def.get("name", "")
            if not var_name:
                continue

            # 优先从注册表获取
            if var_name in self._schemas:
                result[var_name] = self._schemas[var_name]
            else:
                # 从节点的变量定义构建临时 Schema
                type_str = var_def.get("type", "string")
                try:
                    var_type = VariableType(type_str)
                except ValueError:
                    var_type = VariableType.STRING

                result[var_name] = VariableSchema(
                    name=var_name,
                    display_name=var_def.get("display_name", var_def.get("desc", var_name)),
                    type=var_type,
                    required=var_def.get("required", False),
                    default=var_def.get("default"),
                    description=var_def.get("desc", ""),
                )

        return result

    def get_all_schemas(self) -> Dict[str, VariableSchema]:
        """获取所有已注册的变量 Schema。"""
        self._ensure_loaded()
        return dict(self._schemas)

    def get_schemas_by_scope(self, scope: VariableScope) -> Dict[str, VariableSchema]:
        """按作用域获取变量 Schema。"""
        self._ensure_loaded()
        return {
            name: schema
            for name, schema in self._schemas.items()
            if schema.scope == scope
        }

    # ─── 校验 ───

    def validate(
        self,
        variables: Dict[str, Any],
        required_only: bool = False,
    ) -> ValidationResult:
        """校验变量值是否符合注册表定义。

        Args:
            variables: 实际提供的变量字典
            required_only: 是否只校验必填变量
        """
        self._ensure_loaded()

        result = ValidationResult()
        schemas = self._schemas if not required_only else {
            k: v for k, v in self._schemas.items() if v.required
        }

        for name, schema in schemas.items():
            value = variables.get(name)
            is_valid, error_msg = schema.validate_value(value)
            if not is_valid:
                result.is_valid = False
                result.errors.append(error_msg)
                if "缺失" in error_msg:
                    result.missing_required.append(name)
                else:
                    result.type_mismatches.append(error_msg)

        return result

    # ─── 广场 UI 支持 ───

    def suggest_variables(
        self,
        scope: Optional[VariableScope] = None,
        prefix: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """为广场 UI 提供可用变量列表。

        类似现代化无代码平台的表达式编辑器，
        用户在编辑提示词时可点击插入变量。
        """
        self._ensure_loaded()

        result = []
        for name, schema in sorted(self._schemas.items()):
            if scope and schema.scope != scope:
                continue
            if prefix and not name.startswith(prefix):
                continue

            result.append({
                "name": schema.name,
                "display_name": schema.display_name,
                "type": schema.type.value,
                "scope": schema.scope.value,
                "required": schema.required,
                "default": schema.default,
                "description": schema.description,
                "source": schema.source,
                "examples": schema.examples[:3],
                "insert_text": f"{{{{{name}}}}}",  # 用户可插入的格式
            })

        return result

    def get_scopes_summary(self) -> Dict[str, int]:
        """各作用域的变量数量。"""
        self._ensure_loaded()
        summary: Dict[str, int] = {}
        for schema in self._schemas.values():
            key = schema.scope.value
            summary[key] = summary.get(key, 0) + 1
        return summary

    # ─── 内部方法 ───

    def _persist_schema(self, schema: VariableSchema) -> None:
        """持久化变量 Schema 到 DB。"""
        db = self._get_db()
        conn = db.get_connection()

        default_json = json.dumps(schema.default, ensure_ascii=False) if schema.default is not None else None
        enum_json = json.dumps(schema.enum_values, ensure_ascii=False) if schema.enum_values else "[]"
        examples_json = json.dumps(schema.examples[:5], ensure_ascii=False) if schema.examples else "[]"
        now = datetime.now().isoformat()

        conn.execute("""
            INSERT OR REPLACE INTO variable_registry
            (name, display_name, type, scope, is_required, default_value,
             description, source, enum_values, examples, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            schema.name,
            schema.display_name,
            schema.type.value,
            schema.scope.value,
            1 if schema.required else 0,
            default_json,
            schema.description,
            schema.source,
            enum_json,
            examples_json,
            now,
        ))
        conn.commit()

    @staticmethod
    def _schema_changed(old: VariableSchema, new: VariableSchema) -> bool:
        """检查 Schema 是否有变化。"""
        return (
            old.type != new.type
            or old.required != new.required
            or old.default != new.default
            or old.scope != new.scope
            or old.description != new.description
            or old.display_name != new.display_name
        )

    # ─── 种子初始化 ───

    def seed_builtin_variables(self) -> None:
        """从已入库的 CPMS 节点（prompt_packages 种子）提取并注册变量。"""
        self._ensure_loaded()

        from infrastructure.ai.prompt_manager import get_prompt_manager
        mgr = get_prompt_manager()
        mgr.ensure_seeded()

        nodes = mgr.list_nodes(include_versions=True)
        count = 0

        for node in nodes:
            for var_def in node.variables:
                var_name = var_def.get("name", "")
                if not var_name or var_name.startswith("_") or var_name in self._schemas:
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

                schema = VariableSchema(
                    name=var_name,
                    display_name=var_def.get("display_name", var_def.get("desc", var_name)),
                    type=var_type,
                    required=var_def.get("required", False),
                    default=var_def.get("default"),
                    description=var_def.get("desc", ""),
                    source=f"prompt:{node.node_key}",
                    scope=var_scope,
                    enum_values=var_def.get("enum_values", []),
                )

                self._schemas[var_name] = schema
                self._persist_schema(schema)
                count += 1

        if count > 0:
            logger.info("VariableRegistry: 从种子文件注册了 %d 个新变量", count)


# ─── 全局单例 ───

_registry_instance: Optional[VariableRegistry] = None


def get_variable_registry() -> VariableRegistry:
    """获取全局 VariableRegistry 单例。"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = VariableRegistry()
    return _registry_instance
