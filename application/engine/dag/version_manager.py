"""DAG 版本管理器 -- 保存/回滚/对比

存储方案：
- DAG 定义: data/dag_definitions/{novel_id}.json（当前最新版本）
- DAG 版本历史: data/dag_versions/{novel_id}/v{n}.json（Git 风格快照）
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from application.engine.dag.models import DAGDefinition

logger = logging.getLogger(__name__)

_DEFAULT_DATA_ROOT = os.path.join(os.getcwd(), "data")


class DAGVersionManager:
    """DAG 版本管理器"""

    def __init__(self, data_root: Optional[str] = None):
        self._data_root = data_root or _DEFAULT_DATA_ROOT
        self._definitions_dir = os.path.join(self._data_root, "dag_definitions")
        self._versions_dir = os.path.join(self._data_root, "dag_versions")
        self._ensure_dirs()

    def _ensure_dirs(self):
        os.makedirs(self._definitions_dir, exist_ok=True)
        os.makedirs(self._versions_dir, exist_ok=True)

    def load_latest(self, novel_id: str) -> Optional[DAGDefinition]:
        path = os.path.join(self._definitions_dir, f"{novel_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return DAGDefinition(**data)
        except Exception as e:
            logger.error(f"加载 DAG 定义失败 novel={novel_id}: {e}")
            return None

    def save_version(self, novel_id: str, dag: DAGDefinition) -> int:
        current = self.load_latest(novel_id)
        if current:
            if current.fingerprint() == dag.fingerprint():
                logger.debug(f"DAG 无结构变化，跳过版本保存 novel={novel_id}")
                return current.version

        dag.version = (current.version + 1) if current else 1
        dag.metadata.updated_at = datetime.now(timezone.utc).isoformat()

        version_dir = os.path.join(self._versions_dir, novel_id)
        os.makedirs(version_dir, exist_ok=True)
        version_path = os.path.join(version_dir, f"v{dag.version}.json")
        with open(version_path, "w", encoding="utf-8") as f:
            json.dump(dag.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

        latest_path = os.path.join(self._definitions_dir, f"{novel_id}.json")
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(dag.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

        logger.info(f"DAG 版本保存成功: novel={novel_id}, version={dag.version}")
        return dag.version

    def list_versions(self, novel_id: str) -> List[Dict]:
        version_dir = os.path.join(self._versions_dir, novel_id)
        if not os.path.exists(version_dir):
            return []

        versions = []
        for filename in sorted(os.listdir(version_dir)):
            if not filename.startswith("v") or not filename.endswith(".json"):
                continue
            try:
                version_num = int(filename[1:-5])
                path = os.path.join(version_dir, filename)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                versions.append({
                    "version": version_num,
                    "name": data.get("name", ""),
                    "updated_at": data.get("metadata", {}).get("updated_at", ""),
                    "node_count": len(data.get("nodes", [])),
                    "edge_count": len(data.get("edges", [])),
                })
            except (ValueError, json.JSONDecodeError) as e:
                logger.warning(f"跳过无效版本文件 {filename}: {e}")
        return versions

    def rollback(self, novel_id: str, target_version: int) -> DAGDefinition:
        version_dir = os.path.join(self._versions_dir, novel_id)
        version_path = os.path.join(version_dir, f"v{target_version}.json")
        if not os.path.exists(version_path):
            raise ValueError(f"版本 v{target_version} 不存在: novel={novel_id}")

        with open(version_path, "r", encoding="utf-8") as f:
            dag = DAGDefinition(**json.load(f))

        new_version = self.save_version(novel_id, dag)
        logger.info(f"DAG 版本回滚: novel={novel_id}, target=v{target_version}, new_version=v{new_version}")
        return self.load_latest(novel_id)  # type: ignore

    def init_default_dag(self, novel_id: str) -> DAGDefinition:
        existing = self.load_latest(novel_id)
        if existing:
            return existing

        from application.engine.dag.models import get_default_dag
        dag = get_default_dag()
        dag.id = f"dag_{novel_id}"
        self.save_version(novel_id, dag)
        return dag

    def cleanup_old_versions(self, novel_id: str, keep_count: int = 10) -> int:
        version_dir = os.path.join(self._versions_dir, novel_id)
        if not os.path.exists(version_dir):
            return 0

        files = sorted(
            [f for f in os.listdir(version_dir) if f.startswith("v") and f.endswith(".json")],
            key=lambda f: int(f[1:-5]),
        )
        if len(files) <= keep_count:
            return 0

        to_delete = files[:-keep_count]
        for filename in to_delete:
            path = os.path.join(version_dir, filename)
            os.remove(path)
        logger.info(f"清理 {len(to_delete)} 个旧版本: novel={novel_id}")
        return len(to_delete)
