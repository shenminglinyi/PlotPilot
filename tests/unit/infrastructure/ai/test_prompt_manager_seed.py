from datetime import datetime

from infrastructure.ai.prompt_manager import PromptManager
from infrastructure.persistence.database.connection import DatabaseConnection


def test_prompt_manager_adds_new_builtin_seed_nodes_to_existing_database(tmp_path):
    """已有内置模板包时，新版内置节点也应补进提示词广场。"""
    db = DatabaseConnection(str(tmp_path / "prompt-seed.db"))
    conn = db.get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO prompt_templates
        (id, name, description, category, version, author, icon, color, is_builtin, metadata, created_at, updated_at)
        VALUES ('builtin-template', '旧内置包', '', 'builtin', '1.0.0', 'system', 'x', '#000', 1, '{}', ?, ?)
        """,
        (now, now),
    )
    conn.commit()

    manager = PromptManager(db)

    assert manager.ensure_seeded() is True

    node = manager.get_node("rewrite-dialogue-subtext")
    assert node is not None
    assert node.is_builtin is True
    assert "潜台词" in node.get_active_system()
