"""PromptBindingStore — CPMS 工作流绑定存储。

核心设计：
- 定义"工作流"到"提示词节点"的绑定关系
- 支持槽位（slot）和优先级（priority）概念
- 绑定关系存入数据库，广场可编辑
- 运行时按优先级组装完整的 system prompt

Example:
    chapter-generation 工作流绑定了：
    - ("chapter-generation-main", "system_prefix", priority=1)
    - ("anti-ai-behavior-protocol", "system_rules", priority=2)
    - ("anti-ai-character-state-lock", "system_lock", priority=3)
    - ("beat-focus-instructions", "beat_template", priority=1)
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class BindingEntry:
    """单条绑定记录：一个提示词节点在工作流中的位置。"""
    id: str
    workflow_id: str              # 如 "chapter-generation"
    node_key: str                 # 如 "anti-ai-behavior-protocol"
    slot: str                     # 如 "system_prefix", "system_rules"
    priority: int = 50            # 同一 slot 内的优先级（小数字优先）
    is_required: bool = False     # 是否必须（缺失则报错）
    enabled: bool = True          # 是否启用（广场可切换）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "node_key": self.node_key,
            "slot": self.slot,
            "priority": self.priority,
            "is_required": self.is_required,
            "enabled": self.enabled,
        }


@dataclass
class WorkflowDefinition:
    """工作流定义：包含名称、描述和绑定列表。"""
    id: str
    name: str
    description: str = ""
    bindings: List[BindingEntry] = field(default_factory=list)

    def get_bindings_by_slot(self, slot: str) -> List[BindingEntry]:
        """获取指定槽位的绑定列表（按优先级排序）。"""
        return sorted(
            [b for b in self.bindings if b.slot == slot and b.enabled],
            key=lambda b: b.priority,
        )

    def get_ordered_bindings(self) -> List[BindingEntry]:
        """获取所有绑定的有序列表（先按 slot 排序，再按 priority 排序）。"""
        return sorted(
            [b for b in self.bindings if b.enabled],
            key=lambda b: (b.slot, b.priority),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "bindings": [b.to_dict() for b in self.bindings],
            "slot_summary": self._slot_summary(),
        }

    def _slot_summary(self) -> Dict[str, int]:
        """每个 slot 的绑定数量。"""
        summary: Dict[str, int] = {}
        for b in self.bindings:
            if b.enabled:
                summary[b.slot] = summary.get(b.slot, 0) + 1
        return summary


class PromptBindingStore:
    """CPMS 工作流绑定存储。

    职责：
    1. 管理"工作流 -> 提示词节点"的绑定关系
    2. 按优先级组装工作流的完整 prompt
    3. 支持广场 UI 的绑定编辑
    4. 内置种子绑定（系统默认工作流配置）
    """

    def __init__(self, db_connection=None):
        self._db = db_connection

    def _get_db(self):
        if self._db is not None:
            return self._db
        from infrastructure.persistence.database.connection import get_database
        return get_database()

    # ─── 查询 ───

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """获取工作流定义（含所有绑定）。"""
        db = self._get_db()
        conn = db.get_connection()

        wf_row = conn.execute(
            "SELECT * FROM prompt_workflows WHERE id = ?",
            (workflow_id,),
        ).fetchone()

        if not wf_row:
            return None

        bind_rows = conn.execute(
            "SELECT * FROM prompt_bindings WHERE workflow_id = ? ORDER BY slot, priority",
            (workflow_id,),
        ).fetchall()

        bindings = [
            BindingEntry(
                id=r["id"],
                workflow_id=r["workflow_id"],
                node_key=r["node_key"],
                slot=r["slot"],
                priority=r["priority"],
                is_required=bool(r.get("is_required", 0)),
                enabled=bool(r.get("enabled", 1)),
            )
            for r in bind_rows
        ]

        return WorkflowDefinition(
            id=wf_row["id"],
            name=wf_row["name"],
            description=wf_row.get("description", ""),
            bindings=bindings,
        )

    def list_workflows(self) -> List[WorkflowDefinition]:
        """列出所有工作流定义。"""
        db = self._get_db()
        conn = db.get_connection()
        rows = conn.execute(
            "SELECT id FROM prompt_workflows ORDER BY sort_order, name"
        ).fetchall()
        return [self.get_workflow(r["id"]) for r in rows]

    # ─── CRUD ───

    def create_workflow(
        self,
        workflow_id: str,
        name: str,
        description: str = "",
    ) -> WorkflowDefinition:
        """创建工作流定义。"""
        db = self._get_db()
        conn = db.get_connection()
        now = datetime.now().isoformat()

        conn.execute("""
            INSERT INTO prompt_workflows
            (id, name, description, is_builtin, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, 0, 0, ?, ?)
        """, (workflow_id, name, description, now, now))
        conn.commit()

        return WorkflowDefinition(id=workflow_id, name=name, description=description)

    def add_binding(
        self,
        workflow_id: str,
        node_key: str,
        slot: str,
        priority: int = 50,
        is_required: bool = False,
    ) -> BindingEntry:
        """向工作流添加绑定。"""
        db = self._get_db()
        conn = db.get_connection()
        now = datetime.now().isoformat()
        bind_id = uuid.uuid4().hex[:12]

        conn.execute("""
            INSERT INTO prompt_bindings
            (id, workflow_id, node_key, slot, priority, is_required, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (bind_id, workflow_id, node_key, slot, priority,
              1 if is_required else 0, now, now))
        conn.commit()

        return BindingEntry(
            id=bind_id,
            workflow_id=workflow_id,
            node_key=node_key,
            slot=slot,
            priority=priority,
            is_required=is_required,
            enabled=True,
        )

    def remove_binding(self, binding_id: str) -> bool:
        """移除绑定。"""
        db = self._get_db()
        conn = db.get_connection()
        cursor = conn.execute(
            "DELETE FROM prompt_bindings WHERE id = ? AND is_required = 0",
            (binding_id,),
        )
        conn.commit()
        return cursor.rowcount > 0

    def toggle_binding(self, binding_id: str, enabled: bool) -> bool:
        """切换绑定启用状态（广场中切换）。"""
        db = self._get_db()
        conn = db.get_connection()
        conn.execute(
            "UPDATE prompt_bindings SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, datetime.now().isoformat(), binding_id),
        )
        conn.commit()
        return True

    # ─── 运行时组装 ───

    def assemble_workflow_prompt(
        self,
        workflow_id: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, str]]:
        """组装工作流的完整 prompt（按 slot 和 priority 拼接）。"""
        from infrastructure.ai.prompt_registry import get_prompt_registry

        wf = self.get_workflow(workflow_id)
        if not wf:
            return None

        registry = get_prompt_registry()
        var_map = variables or {}

        system_parts: List[str] = []
        user_parts: List[str] = []

        for binding in wf.get_ordered_bindings():
            render_result = registry.render(binding.node_key, var_map)
            if render_result:
                if binding.slot.startswith("user"):
                    if render_result.user:
                        user_parts.append(render_result.user)
                else:
                    if render_result.system:
                        system_parts.append(render_result.system)

        return {
            "system": "\n\n".join(system_parts) if system_parts else "",
            "user": "\n\n".join(user_parts) if user_parts else "",
        }

    # ─── 种子绑定 ───

    def seed_builtin_workflows(self) -> None:
        """初始化内置工作流绑定。"""
        db = self._get_db()
        conn = db.get_connection()

        existing = conn.execute(
            "SELECT COUNT(*) AS c FROM prompt_workflows WHERE is_builtin = 1"
        ).fetchone()

        if existing["c"] > 0:
            return

        now = datetime.now().isoformat()

        # 章节生成工作流
        self._insert_workflow(conn, "chapter-generation", "章节生成工作流",
                              "AutoNovelGenerationWorkflow 的核心提示词组合", True, 0, now)
        self._insert_binding(conn, "chapter-generation", "chapter-generation-main",
                             "system_main", 10, True, now)
        self._insert_binding(conn, "chapter-generation", "anti-ai-behavior-protocol",
                             "system_rules", 20, False, now)
        self._insert_binding(conn, "chapter-generation", "anti-ai-character-state-lock",
                             "system_lock", 30, False, now)
        self._insert_binding(conn, "chapter-generation", "beat-focus-instructions",
                             "user_beat", 10, False, now)

        # Bible 生成工作流
        self._insert_workflow(conn, "bible-generation", "Bible 生成工作流",
                              "世界观与人物设定的生成提示词组合", True, 1, now)
        self._insert_binding(conn, "bible-generation", "bible-all",
                             "system_main", 10, True, now)

        # 审计工作流
        self._insert_workflow(conn, "chapter-audit", "章节审计工作流",
                              "章后审计的提示词组合", True, 2, now)

        conn.commit()
        logger.info("PromptBindingStore: 已初始化内置工作流绑定")

    @staticmethod
    def _insert_workflow(conn, wf_id: str, name: str, desc: str,
                         is_builtin: bool, sort_order: int, now: str) -> None:
        conn.execute("""
            INSERT OR IGNORE INTO prompt_workflows
            (id, name, description, is_builtin, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (wf_id, name, desc, 1 if is_builtin else 0, sort_order, now, now))

    @staticmethod
    def _insert_binding(conn, wf_id: str, node_key: str, slot: str,
                        priority: int, is_required: bool, now: str) -> None:
        bind_id = uuid.uuid4().hex[:12]
        conn.execute("""
            INSERT OR IGNORE INTO prompt_bindings
            (id, workflow_id, node_key, slot, priority, is_required, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (bind_id, wf_id, node_key, slot, priority,
              1 if is_required else 0, now, now))


# ─── 全局单例 ───

_store_instance: Optional[PromptBindingStore] = None


def get_binding_store() -> PromptBindingStore:
    """获取全局 PromptBindingStore 单例。"""
    global _store_instance
    if _store_instance is None:
        _store_instance = PromptBindingStore()
    return _store_instance
