from pathlib import Path

from application.engine.dag.models import get_default_dag
from application.engine.dag.registry import NodeRegistry
from infrastructure.ai.prompt_keys import ALL_KEYS


def test_default_dag_cpms_keys_are_registered_prompt_keys():
    import application.engine.dag.nodes  # noqa: F401 - register node metadata

    missing = []
    for node in get_default_dag().nodes:
        meta = NodeRegistry.get_meta(node.type)
        if meta and meta.cpms_node_key and meta.cpms_node_key not in ALL_KEYS:
            missing.append((node.type, meta.cpms_node_key))

    assert missing == []


def test_default_dag_cpms_keys_have_builtin_prompt_packages():
    import application.engine.dag.nodes  # noqa: F401 - register node metadata

    package_root = Path("infrastructure/ai/prompt_packages/nodes")
    missing = []
    for node in get_default_dag().nodes:
        meta = NodeRegistry.get_meta(node.type)
        if not meta or not meta.cpms_node_key:
            continue
        prompt_dir = package_root / meta.cpms_node_key
        required_files = ["package.yaml", "system.md", "user.md"]
        if not prompt_dir.is_dir() or any(not (prompt_dir / name).is_file() for name in required_files):
            missing.append((node.type, meta.cpms_node_key))

    assert missing == []
