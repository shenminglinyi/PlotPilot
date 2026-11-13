"""Unit tests for atomic CAS preconditions on Prompt Plaza / Mod Hub mutations."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from infrastructure.ai.prompt_manager import PromptManager
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.write_dispatch import (
    sqlite_writes_bypass_queue,
)
from interfaces.api.v1.workbench.prompt_mutation_cas import (
    PromptPreconditions,
    create_prompt_node_atomic,
    delete_prompt_node_atomic,
    update_prompt_node_atomic,
)


def _init_prompt_schema(db: DatabaseConnection) -> PromptManager:
    with sqlite_writes_bypass_queue():
        conn = db.get_connection()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS prompt_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT 'user',
                version TEXT DEFAULT '1.0.0',
                author TEXT DEFAULT '',
                icon TEXT DEFAULT '',
                color TEXT DEFAULT '#1f5e5b',
                is_builtin INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS prompt_nodes (
                id TEXT PRIMARY KEY,
                template_id TEXT NOT NULL,
                node_key TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT 'generation',
                source TEXT DEFAULT '',
                output_format TEXT DEFAULT 'text',
                contract_module TEXT,
                contract_model TEXT,
                tags TEXT DEFAULT '[]',
                variables TEXT DEFAULT '[]',
                system_file TEXT,
                is_builtin INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                active_version_id TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS prompt_versions (
                id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                system_prompt TEXT DEFAULT '',
                user_template TEXT DEFAULT '',
                change_summary TEXT DEFAULT '',
                created_by TEXT DEFAULT 'user',
                created_at TEXT
            );
            INSERT INTO prompt_templates (id, name, is_builtin)
            VALUES ('tmpl-builtin', 'Builtin Template', 1);
            INSERT INTO prompt_nodes (
                id, template_id, node_key, name, description, is_builtin, active_version_id
            ) VALUES (
                'node-builtin-1', 'tmpl-builtin', 'chapter-generation-main',
                'Main Chapter', 'Builtin desc', 1, 'ver-builtin-1'
            );
            INSERT INTO prompt_versions (
                id, node_id, version_number, system_prompt, user_template, created_by
            ) VALUES (
                'ver-builtin-1', 'node-builtin-1', 1, 'ORIG_SYSTEM', '{context}', 'system'
            );
            """
        )
        conn.commit()
    mgr = PromptManager(db_connection=db)
    mgr._seeded = True
    return mgr


def test_create_prompt_node_atomic_rejects_duplicate_key_with_409(tmp_path: Path) -> None:
    db = DatabaseConnection(str(tmp_path / "cas_create.db"))
    try:
        mgr = _init_prompt_schema(db)
        created = create_prompt_node_atomic(
            mgr,
            template_id="tmpl-builtin",
            node_key="custom-mod-node",
            name="Mod Node",
            description="Initial summary",
            category="creative",
            system="MOD_SYS_V1",
            user_template="{tpl_0}",
        )
        detail = created.to_detail_dict()
        assert detail["active_version_id"]
        assert detail["version_count"] == 1
        assert detail["system"] == "MOD_SYS_V1"

        with pytest.raises(HTTPException) as exc_info:
            create_prompt_node_atomic(
                mgr,
                template_id="tmpl-builtin",
                node_key="custom-mod-node",
                name="Colliding Node",
                description="Should fail",
                category="creative",
                system="OVERWRITE",
                user_template="{bad}",
            )
        assert exc_info.value.status_code == 409
        live = mgr.get_node("custom-mod-node", by_key=True)
        assert live is not None
        assert live.get_active_system() == "MOD_SYS_V1"
    finally:
        db.close_all(skip_checkpoint=True)


def test_update_prompt_node_atomic_enforces_version_and_field_preconditions(
    tmp_path: Path,
) -> None:
    db = DatabaseConnection(str(tmp_path / "cas_update.db"))
    try:
        mgr = _init_prompt_schema(db)
        created = create_prompt_node_atomic(
            mgr,
            template_id="tmpl-builtin",
            node_key="owned-custom-b",
            name="Custom B",
            description="Desc V1",
            category="creative",
            system="SYS_V1",
            user_template="{T0}",
        )
        observed = created.to_detail_dict()

        # Simulate concurrent user save changing user_template from {T0} -> {U}
        intervening = update_prompt_node_atomic(
            mgr,
            "owned-custom-b",
            user_template="{U_USER_SAVED}",
            change_summary="User manual edit",
        )
        assert intervening.version_count == 2
        assert intervening.get_active_user_template() == "{U_USER_SAVED}"

        # Stale forward mutation carrying pre-edit preconditions MUST fail with 409 and preserve {U_USER_SAVED}
        with pytest.raises(HTTPException) as exc_info:
            update_prompt_node_atomic(
                mgr,
                "owned-custom-b",
                system="SYS_V2",
                user_template="{T1}",
                name="Custom B V2",
                description="Desc V2",
                change_summary="Stale mod upgrade",
                preconditions=PromptPreconditions(
                    expected_active_version_id=observed["active_version_id"],
                    expected_version_count=observed["version_count"],
                    expected_system="SYS_V1",
                    expected_user_template="{T0}",
                    expected_name="Custom B",
                    expected_description="Desc V1",
                ),
            )
        assert exc_info.value.status_code == 409

        after_conflict = mgr.get_node("owned-custom-b", by_key=True)
        assert after_conflict is not None
        assert after_conflict.version_count == 2
        assert after_conflict.get_active_user_template() == "{U_USER_SAVED}"
        assert after_conflict.get_active_system() == "SYS_V1"

        # Matching preconditions succeed cleanly
        fresh = after_conflict.to_detail_dict()
        updated = update_prompt_node_atomic(
            mgr,
            "owned-custom-b",
            system="SYS_V2",
            change_summary="Recomputed mod upgrade preserving U",
            preconditions=PromptPreconditions(
                expected_active_version_id=fresh["active_version_id"],
                expected_version_count=fresh["version_count"],
                expected_system=fresh["system"],
                expected_user_template=fresh["user_template"],
            ),
        )
        assert updated.version_count == 3
        assert updated.get_active_system() == "SYS_V2"
        assert updated.get_active_user_template() == "{U_USER_SAVED}"
    finally:
        db.close_all(skip_checkpoint=True)


def test_delete_prompt_node_atomic_protects_builtin_and_concurrent_user_edits(
    tmp_path: Path,
) -> None:
    db = DatabaseConnection(str(tmp_path / "cas_delete.db"))
    try:
        mgr = _init_prompt_schema(db)

        with pytest.raises(HTTPException) as builtin_err:
            delete_prompt_node_atomic(mgr, "node-builtin-1")
        assert builtin_err.value.status_code == 403

        custom = create_prompt_node_atomic(
            mgr,
            template_id="tmpl-builtin",
            node_key="temp-custom",
            name="Temp Custom",
            description="",
            category="creative",
            system="OWNED_BLOCK",
            user_template="{init}",
        )
        snap = custom.to_detail_dict()

        # User edits custom node right before delete arrives
        edited = update_prompt_node_atomic(
            mgr,
            "temp-custom",
            user_template="{user_customized}",
            change_summary="User edited before delete",
        )

        with pytest.raises(HTTPException) as conflict_err:
            delete_prompt_node_atomic(
                mgr,
                custom.id,
                preconditions=PromptPreconditions(
                    expected_active_version_id=snap["active_version_id"],
                    expected_version_count=snap["version_count"],
                    expected_system=snap["system"],
                    expected_user_template=snap["user_template"],
                ),
            )
        assert conflict_err.value.status_code == 409
        assert mgr.get_node(custom.id, by_key=False) is not None

        # Delete with matching latest preconditions succeeds
        latest = edited.to_detail_dict()
        delete_prompt_node_atomic(
            mgr,
            custom.id,
            preconditions=PromptPreconditions(
                expected_active_version_id=latest["active_version_id"],
                expected_version_count=latest["version_count"],
                expected_system=latest["system"],
                expected_user_template=latest["user_template"],
            ),
        )
        assert mgr.get_node(custom.id, by_key=False) is None
    finally:
        db.close_all(skip_checkpoint=True)
