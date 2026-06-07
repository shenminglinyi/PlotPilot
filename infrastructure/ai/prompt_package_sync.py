"""Utilities for forcing built-in CPMS nodes to the packaged source."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from infrastructure.ai.prompt_registry import get_prompt_registry


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def force_sync_builtin_prompt_node(db, *, node_key: str, change_summary: str) -> bool:
    from infrastructure.ai.prompt_manager import get_prompt_manager
    from infrastructure.ai.prompt_seed.loader import NODES_DIR, load_node_dir
    from infrastructure.ai.prompt_seed.normalize import normalize_prompt_record

    node_dir = NODES_DIR / node_key
    if not node_dir.is_dir():
        raise FileNotFoundError(f"missing prompt package node directory: {node_dir}")

    manager = get_prompt_manager()
    manager.ensure_seeded()

    prompt_record = normalize_prompt_record(load_node_dir(node_dir))
    now = datetime.now().isoformat()
    conn = db.get_connection()

    node_row = conn.execute(
        "SELECT id, template_id, active_version_id FROM prompt_nodes WHERE node_key = ?",
        (node_key,),
    ).fetchone()
    if node_row is None:
        template_row = conn.execute(
            "SELECT id FROM prompt_templates WHERE is_builtin = 1 LIMIT 1"
        ).fetchone()
        if template_row is None:
            raise RuntimeError("builtin prompt template package not found")
        node_id = _uid()
        version_id = _uid()
        conn.execute(
            """
            INSERT INTO prompt_nodes (
                id, template_id, node_key, name, description, category, source,
                output_format, contract_module, contract_model, tags, variables,
                system_file, is_builtin, sort_order, active_version_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """,
            (
                node_id,
                template_row["id"],
                node_key,
                prompt_record.get("name", ""),
                prompt_record.get("description", ""),
                prompt_record.get("category", "generation"),
                prompt_record.get("source", ""),
                prompt_record.get("output_format", "text"),
                prompt_record.get("contract_module"),
                prompt_record.get("contract_model"),
                json.dumps(prompt_record.get("tags", []), ensure_ascii=False),
                json.dumps(prompt_record.get("variables", []), ensure_ascii=False),
                prompt_record.get("system_file"),
                int(prompt_record.get("sort_order", 0)),
                version_id,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO prompt_versions (
                id, node_id, version_number, system_prompt, user_template,
                change_summary, created_by, created_at
            ) VALUES (?, ?, 1, ?, ?, ?, 'system', ?)
            """,
            (
                version_id,
                node_id,
                prompt_record.get("system", ""),
                prompt_record.get("user_template", ""),
                change_summary,
                now,
            ),
        )
        conn.commit()
        get_prompt_registry().invalidate_cache(node_key)
        return True

    current_row = conn.execute(
        """
        SELECT v.system_prompt, v.user_template, v.created_by, n.variables, n.name, n.description,
               n.category, n.source, n.output_format, n.sort_order
        FROM prompt_nodes n
        JOIN prompt_versions v ON n.active_version_id = v.id
        WHERE n.id = ?
        """,
        (node_row["id"],),
    ).fetchone()
    if current_row is None:
        raise RuntimeError(f"prompt node missing active version: {node_key}")

    new_vars_json = json.dumps(prompt_record.get("variables", []), ensure_ascii=False, sort_keys=True)
    current_vars_json = json.dumps(
        json.loads(current_row["variables"]) if current_row["variables"] else [],
        ensure_ascii=False,
        sort_keys=True,
    )
    unchanged = (
        (current_row["system_prompt"] or "") == (prompt_record.get("system", "") or "")
        and (current_row["user_template"] or "") == (prompt_record.get("user_template", "") or "")
        and current_vars_json == new_vars_json
        and (current_row["name"] or "") == (prompt_record.get("name", "") or "")
        and (current_row["description"] or "") == (prompt_record.get("description", "") or "")
        and (current_row["category"] or "") == (prompt_record.get("category", "") or "")
        and (current_row["source"] or "") == (prompt_record.get("source", "") or "")
        and (current_row["output_format"] or "") == (prompt_record.get("output_format", "") or "")
        and int(current_row["sort_order"] or 0) == int(prompt_record.get("sort_order", 0))
    )
    if unchanged:
        get_prompt_registry().invalidate_cache(node_key)
        return False

    if (current_row["created_by"] or "system") == "user":
        # Respect user-adopted prompt versions. Contract ensure/sync callers still
        # get a fresh registry read, but packaged prompt text must not take over
        # the active user version on the next click/regenerate.
        get_prompt_registry().invalidate_cache(node_key)
        return False

    version_row = conn.execute(
        "SELECT COALESCE(MAX(version_number), 0) AS max_version FROM prompt_versions WHERE node_id = ?",
        (node_row["id"],),
    ).fetchone()
    next_version = int((version_row["max_version"] if version_row else 0) or 0) + 1
    version_id = _uid()
    conn.execute(
        """
        INSERT INTO prompt_versions (
            id, node_id, version_number, system_prompt, user_template,
            change_summary, created_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'system', ?)
        """,
        (
            version_id,
            node_row["id"],
            next_version,
            prompt_record.get("system", ""),
            prompt_record.get("user_template", ""),
            change_summary,
            now,
        ),
    )
    conn.execute(
        """
        UPDATE prompt_nodes
        SET active_version_id = ?, name = ?, description = ?, category = ?, source = ?,
            output_format = ?, tags = ?, variables = ?, system_file = ?, sort_order = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            version_id,
            prompt_record.get("name", ""),
            prompt_record.get("description", ""),
            prompt_record.get("category", "generation"),
            prompt_record.get("source", ""),
            prompt_record.get("output_format", "text"),
            json.dumps(prompt_record.get("tags", []), ensure_ascii=False),
            json.dumps(prompt_record.get("variables", []), ensure_ascii=False),
            prompt_record.get("system_file"),
            int(prompt_record.get("sort_order", 0)),
            now,
            node_row["id"],
        ),
    )
    conn.commit()
    get_prompt_registry().invalidate_cache(node_key)
    return True
