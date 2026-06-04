from __future__ import annotations

import sqlite3
from pathlib import Path

from infrastructure.ai.prompt_package_sync import force_sync_builtin_prompt_node


class _Db:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE prompt_templates (
                id TEXT PRIMARY KEY,
                is_builtin INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE prompt_nodes (
                id TEXT PRIMARY KEY,
                template_id TEXT NOT NULL,
                node_key TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT NOT NULL DEFAULT 'generation',
                source TEXT DEFAULT '',
                output_format TEXT DEFAULT 'text',
                contract_module TEXT,
                contract_model TEXT,
                tags TEXT NOT NULL DEFAULT '[]',
                variables TEXT NOT NULL DEFAULT '[]',
                system_file TEXT,
                is_builtin INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                active_version_id TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE prompt_versions (
                id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                system_prompt TEXT NOT NULL DEFAULT '',
                user_template TEXT NOT NULL DEFAULT '',
                change_summary TEXT DEFAULT '',
                created_by TEXT DEFAULT 'system',
                created_at TEXT
            );
            """
        )

    def get_connection(self):
        return self.conn


class _Registry:
    def __init__(self):
        self.invalidated = []

    def invalidate_cache(self, node_key: str) -> None:
        self.invalidated.append(node_key)


class _Manager:
    def ensure_seeded(self) -> bool:
        return True


def test_force_sync_builtin_prompt_node_preserves_active_user_version(monkeypatch, tmp_path):
    db = _Db()
    registry = _Registry()

    tmp_path.mkdir(parents=True, exist_ok=True)
    node_dir = Path(tmp_path) / "planning-plot-outline"
    node_dir.mkdir()

    db.conn.execute(
        "INSERT INTO prompt_templates (id, is_builtin) VALUES (?, ?)",
        ("template-1", 1),
    )
    db.conn.execute(
        """
        INSERT INTO prompt_nodes (
            id, template_id, node_key, name, description, category, source,
            output_format, tags, variables, is_builtin, sort_order,
            active_version_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "node-1",
            "template-1",
            "planning-plot-outline",
            "Plot outline planning",
            "desc",
            "planning",
            "seed",
            "json",
            "[]",
            '[{"name":"novel.title","type":"string"}]',
            1,
            24,
            "ver-user",
            "now",
            "now",
        ),
    )
    db.conn.execute(
        """
        INSERT INTO prompt_versions (
            id, node_id, version_number, system_prompt, user_template,
            change_summary, created_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ver-system",
            "node-1",
            1,
            "system old",
            "user old",
            "seed",
            "system",
            "now",
        ),
    )
    db.conn.execute(
        """
        INSERT INTO prompt_versions (
            id, node_id, version_number, system_prompt, user_template,
            change_summary, created_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ver-user",
            "node-1",
            2,
            "system adopted by user",
            "user adopted by user",
            "adopted",
            "user",
            "now",
        ),
    )
    db.conn.commit()

    monkeypatch.setattr(
        "infrastructure.ai.prompt_manager.get_prompt_manager",
        lambda: _Manager(),
    )
    monkeypatch.setattr(
        "infrastructure.ai.prompt_seed.loader.NODES_DIR",
        tmp_path,
    )
    monkeypatch.setattr(
        "infrastructure.ai.prompt_seed.loader.load_node_dir",
        lambda _node_dir: {
            "id": "planning-plot-outline",
            "name": "Plot outline planning",
            "description": "updated desc from package",
            "category": "planning",
            "source": "package",
            "output_format": "json",
            "tags": ["planning"],
            "variables": [{"name": "novel.title", "type": "string"}],
            "system_file": "system.md",
            "sort_order": 24,
            "system": "system from package",
            "user_template": "user from package",
        },
    )
    monkeypatch.setattr(
        "infrastructure.ai.prompt_package_sync.get_prompt_registry",
        lambda: registry,
    )

    changed = force_sync_builtin_prompt_node(
        db,
        node_key="planning-plot-outline",
        change_summary="sync package",
    )

    active = db.conn.execute(
        """
        SELECT v.id, v.system_prompt, v.user_template, v.created_by
        FROM prompt_nodes n
        JOIN prompt_versions v ON n.active_version_id = v.id
        WHERE n.node_key = ?
        """,
        ("planning-plot-outline",),
    ).fetchone()
    version_count = db.conn.execute(
        "SELECT COUNT(*) AS count FROM prompt_versions WHERE node_id = ?",
        ("node-1",),
    ).fetchone()["count"]

    assert changed is False
    assert dict(active) == {
        "id": "ver-user",
        "system_prompt": "system adopted by user",
        "user_template": "user adopted by user",
        "created_by": "user",
    }
    assert version_count == 2
    assert registry.invalidated == ["planning-plot-outline"]
