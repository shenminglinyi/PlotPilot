"""Atomic Compare-And-Swap (CAS) mutation helpers for Prompt Plaza / Mod Hub.

Ensures that transactional mod installs, upgrades, rollbacks, and uninstalls
atomically verify observed node version and prior-field preconditions inside a
serialized SQLite IMMEDIATE write transaction, rejecting concurrent edits with
HTTP 409 Conflict instead of overwriting user-authored changes.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

from infrastructure.ai.prompt_manager import (
    PROMPT_MUTATION_LOCK,
    NodeInfo,
    PromptManager,
)
from infrastructure.persistence.database.write_dispatch import (
    sqlite_writes_bypass_queue,
)


def _new_short_id() -> str:
    return uuid.uuid4().hex[:12]


class PromptPreconditions(BaseModel):
    """Optional optimistic-concurrency preconditions for prompt mutations."""

    model_config = ConfigDict(extra="ignore")

    expected_active_version_id: Optional[str] = None
    expected_version_count: Optional[int] = None
    expected_system: Optional[str] = None
    expected_user_template: Optional[str] = None
    expected_name: Optional[str] = None
    expected_description: Optional[str] = None


def _load_locked_node_snapshot(
    conn: sqlite3.Connection,
    node_key_or_id: str,
    *,
    by_key_with_id_fallback: bool,
) -> Optional[Dict[str, Any]]:
    if by_key_with_id_fallback:
        row = conn.execute(
            "SELECT * FROM prompt_nodes WHERE node_key = ?",
            (node_key_or_id,),
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM prompt_nodes WHERE id = ?",
                (node_key_or_id,),
            ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM prompt_nodes WHERE id = ?",
            (node_key_or_id,),
        ).fetchone()

    if row is None:
        return None

    node_dict = dict(row)
    node_id = node_dict["id"]
    stats_row = conn.execute(
        "SELECT COUNT(*) AS cnt, COALESCE(MAX(version_number), 0) AS max_ver "
        "FROM prompt_versions WHERE node_id = ?",
        (node_id,),
    ).fetchone()
    version_count = int(stats_row["cnt"]) if stats_row else 0
    max_ver = int(stats_row["max_ver"]) if stats_row else 0

    active_ver_id = node_dict.get("active_version_id")
    cur_system = ""
    cur_user_template = ""
    if active_ver_id:
        ver_row = conn.execute(
            "SELECT system_prompt, user_template FROM prompt_versions WHERE id = ?",
            (active_ver_id,),
        ).fetchone()
        if ver_row is not None:
            cur_system = ver_row["system_prompt"] or ""
            cur_user_template = ver_row["user_template"] or ""

    return {
        "row": node_dict,
        "id": node_id,
        "node_key": node_dict["node_key"],
        "name": node_dict.get("name") or "",
        "description": node_dict.get("description") or "",
        "is_builtin": bool(node_dict.get("is_builtin", 0)),
        "active_version_id": active_ver_id or "",
        "version_count": version_count,
        "max_ver": max_ver,
        "system": cur_system,
        "user_template": cur_user_template,
    }


def _assert_preconditions_match(
    snapshot: Dict[str, Any],
    pre: PromptPreconditions,
    action_label: str,
) -> None:
    node_key = snapshot["node_key"]
    if (
        pre.expected_active_version_id is not None
        and snapshot["active_version_id"] != pre.expected_active_version_id
    ):
        raise HTTPException(
            status_code=409,
            detail=f"节点「{node_key}」版本已变更，已中止{action_label}以保护最新编辑内容",
        )
    if (
        pre.expected_version_count is not None
        and snapshot["version_count"] != pre.expected_version_count
    ):
        raise HTTPException(
            status_code=409,
            detail=f"节点「{node_key}」版本计数已变更，已中止{action_label}以保护最新编辑内容",
        )
    if pre.expected_system is not None and snapshot["system"] != pre.expected_system:
        raise HTTPException(
            status_code=409,
            detail=f"节点「{node_key}」System 内容已被并发修改，已中止{action_label}以防覆盖",
        )
    if (
        pre.expected_user_template is not None
        and snapshot["user_template"] != pre.expected_user_template
    ):
        raise HTTPException(
            status_code=409,
            detail=f"节点「{node_key}」User 模板已被并发修改，已中止{action_label}以防覆盖",
        )
    if pre.expected_name is not None and snapshot["name"] != pre.expected_name:
        raise HTTPException(
            status_code=409,
            detail=f"节点「{node_key}」名称已被并发修改，已中止{action_label}以防覆盖",
        )
    if (
        pre.expected_description is not None
        and snapshot["description"] != pre.expected_description
    ):
        raise HTTPException(
            status_code=409,
            detail=f"节点「{node_key}」描述已被并发修改，已中止{action_label}以防覆盖",
        )


def create_prompt_node_atomic(
    mgr: PromptManager,
    *,
    template_id: str,
    node_key: str,
    name: str,
    description: str,
    category: str,
    system: str,
    user_template: str,
) -> NodeInfo:
    mgr.ensure_seeded()
    with PROMPT_MUTATION_LOCK, sqlite_writes_bypass_queue():
        db = mgr._get_db()
        conn = db.get_connection()
        if conn.in_transaction:
            conn.commit()

        key = node_key or f"custom-{uuid.uuid4().hex[:8]}"
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = conn.execute(
                "SELECT id FROM prompt_nodes WHERE node_key = ?",
                (key,),
            ).fetchone()
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"节点键「{key}」已存在，已拒绝覆盖创建",
                )

            tid = template_id
            if not tid:
                tmpl_row = conn.execute(
                    "SELECT id FROM prompt_templates ORDER BY is_builtin DESC, created_at ASC LIMIT 1"
                ).fetchone()
                tid = tmpl_row["id"] if tmpl_row else ""
            if not tid:
                raise HTTPException(status_code=400, detail="No template available")

            node_id = _new_short_id()
            ver_id = _new_short_id()
            now = datetime.now().isoformat()

            conn.execute(
                """
                INSERT INTO prompt_nodes
                (id, template_id, node_key, name, description, category,
                 source, output_format, contract_module, contract_model, tags, variables,
                 is_builtin, sort_order, active_version_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, '', 'text', NULL, NULL, '[]', '[]', 0, 0, ?, ?, ?)
                """,
                (
                    node_id,
                    tid,
                    key,
                    name or "未命名提示词",
                    description or "",
                    category or "generation",
                    ver_id,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO prompt_versions
                (id, node_id, version_number, system_prompt, user_template,
                 change_summary, created_by, created_at)
                VALUES (?, ?, 1, ?, ?, '初始版本', 'user', ?)
                """,
                (ver_id, node_id, system or "", user_template or "", now),
            )
            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"节点键「{key}」创建冲突：{exc}",
            ) from exc
        except Exception:
            conn.rollback()
            raise

        db._maybe_checkpoint()
        created = mgr.get_node(node_id, by_key=False)
        if created is None:
            raise HTTPException(status_code=500, detail="Created prompt node could not be loaded")
        return created


def update_prompt_node_atomic(
    mgr: PromptManager,
    node_key: str,
    *,
    system: Optional[str] = None,
    user_template: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    change_summary: str = "",
    preconditions: Optional[PromptPreconditions] = None,
) -> NodeInfo:
    mgr.ensure_seeded()
    with PROMPT_MUTATION_LOCK, sqlite_writes_bypass_queue():
        db = mgr._get_db()
        conn = db.get_connection()
        if conn.in_transaction:
            conn.commit()

        conn.execute("BEGIN IMMEDIATE")
        try:
            snap = _load_locked_node_snapshot(conn, node_key, by_key_with_id_fallback=True)
            if snap is None:
                raise HTTPException(status_code=404, detail=f"Node '{node_key}' not found")

            if preconditions is not None:
                _assert_preconditions_match(snap, preconditions, "更新")

            node_id = snap["id"]
            next_ver = snap["max_ver"] + 1
            new_ver_id = _new_short_id()
            now = datetime.now().isoformat()

            new_system = system if system is not None else snap["system"]
            new_user = user_template if user_template is not None else snap["user_template"]

            conn.execute(
                """
                INSERT INTO prompt_versions
                (id, node_id, version_number, system_prompt, user_template,
                 change_summary, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'user', ?)
                """,
                (
                    new_ver_id,
                    node_id,
                    next_ver,
                    new_system,
                    new_user,
                    change_summary or f"v{next_ver} 编辑",
                    now,
                ),
            )

            set_clauses = ["active_version_id = ?", "updated_at = ?"]
            params: List[Any] = [new_ver_id, now]
            if name is not None:
                set_clauses.append("name = ?")
                params.append(name)
            if description is not None:
                set_clauses.append("description = ?")
                params.append(description)
            if tags is not None:
                set_clauses.append("tags = ?")
                params.append(json.dumps(tags, ensure_ascii=False))

            params.extend([node_id, snap["active_version_id"]])
            cur = conn.execute(
                f"UPDATE prompt_nodes SET {', '.join(set_clauses)} "
                "WHERE id = ? AND COALESCE(active_version_id, '') = ?",
                params,
            )
            if cur.rowcount != 1:
                raise HTTPException(
                    status_code=409,
                    detail=f"节点「{snap['node_key']}」发生并发版本竞争，已中止覆盖",
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        db._maybe_checkpoint()
        updated = mgr.get_node(node_id, by_key=False)
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Node '{node_key}' not found")
        return updated


def delete_prompt_node_atomic(
    mgr: PromptManager,
    node_id: str,
    *,
    preconditions: Optional[PromptPreconditions] = None,
) -> None:
    mgr.ensure_seeded()
    with PROMPT_MUTATION_LOCK, sqlite_writes_bypass_queue():
        db = mgr._get_db()
        conn = db.get_connection()
        if conn.in_transaction:
            conn.commit()

        conn.execute("BEGIN IMMEDIATE")
        try:
            snap = _load_locked_node_snapshot(conn, node_id, by_key_with_id_fallback=False)
            if snap is None:
                raise HTTPException(status_code=404, detail="Node not found")
            if snap["is_builtin"]:
                raise HTTPException(status_code=403, detail="Cannot delete built-in prompt")

            if preconditions is not None:
                _assert_preconditions_match(snap, preconditions, "删除")

            conn.execute("DELETE FROM prompt_versions WHERE node_id = ?", (node_id,))
            cur = conn.execute(
                "DELETE FROM prompt_nodes WHERE id = ? AND COALESCE(active_version_id, '') = ?",
                (node_id, snap["active_version_id"]),
            )
            if cur.rowcount != 1:
                raise HTTPException(
                    status_code=409,
                    detail=f"节点「{snap['node_key']}」在删除前发生并发变更，已中止删除",
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        db._maybe_checkpoint()
