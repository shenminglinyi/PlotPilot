"""SQLite DAG 版本仓库实现"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from application.engine.dag.models import DAGDefinition, DAGMetadata, EdgeDefinition, NodeDefinition
from domain.engine.dag.repositories.dag_version_repository import DAGVersionRepository
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SqliteDAGVersionRepository(DAGVersionRepository):
    """SQLite DAG 版本仓库实现"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def get_latest(self, novel_id: str) -> Optional[DAGDefinition]:
        """获取最新版本"""
        sql = """
            SELECT * FROM dag_versions
            WHERE novel_id = ?
            ORDER BY version DESC
            LIMIT 1
        """
        row = self.db.fetch_one(sql, (novel_id,))
        if not row:
            return None
        return self._row_to_dag(row)

    def get_by_version(self, novel_id: str, version: int) -> Optional[DAGDefinition]:
        """获取指定版本"""
        sql = "SELECT * FROM dag_versions WHERE novel_id = ? AND version = ?"
        row = self.db.fetch_one(sql, (novel_id, version))
        if not row:
            return None
        return self._row_to_dag(row)

    def save(self, novel_id: str, dag: DAGDefinition) -> int:
        """保存新版本"""
        # 1. 获取当前最新版本
        current = self.get_latest(novel_id)

        # 2. 如果 fingerprint 未变化，返回当前版本（不保存）
        if current and current.fingerprint() == dag.fingerprint():
            logger.debug(f"DAG 无结构变化，跳过版本保存 novel={novel_id}")
            return current.version

        # 3. 计算新版本号
        new_version = (current.version + 1) if current else 1
        dag.version = new_version
        dag.metadata.updated_at = datetime.now(timezone.utc).isoformat()

        # 4. 插入数据库
        insert_sql = """
            INSERT INTO dag_versions (
                id, novel_id, version, dag_id, name, description,
                nodes_json, edges_json, fingerprint, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        version_id = str(uuid.uuid4())
        nodes_json = json.dumps([n.model_dump(mode="json") for n in dag.nodes], ensure_ascii=False)
        edges_json = json.dumps([e.model_dump(mode="json") for e in dag.edges], ensure_ascii=False)

        created_at = dag.metadata.created_at or datetime.now(timezone.utc).isoformat()

        self.db.execute(insert_sql, (
            version_id,
            novel_id,
            new_version,
            dag.id,
            dag.name,
            dag.description,
            nodes_json,
            edges_json,
            dag.fingerprint(),
            created_at,
            dag.metadata.updated_at
        ))
        self.db.commit()

        logger.info(f"DAG 版本保存成功: novel={novel_id}, version={new_version}")
        return new_version

    def list_versions(self, novel_id: str) -> List[Dict]:
        """列出所有版本摘要"""
        sql = """
            SELECT
                version,
                name,
                updated_at,
                fingerprint
            FROM dag_versions
            WHERE novel_id = ?
            ORDER BY version DESC
        """
        rows = self.db.fetch_all(sql, (novel_id,))

        versions = []
        for row in rows:
            # 解析 JSON 以计算节点数和边数
            dag = self.get_by_version(novel_id, row['version'])
            versions.append({
                "version": row['version'],
                "name": row['name'],
                "updated_at": row['updated_at'],
                "node_count": len(dag.nodes) if dag else 0,
                "edge_count": len(dag.edges) if dag else 0,
            })

        return versions

    def delete_old_versions(self, novel_id: str, keep_count: int) -> int:
        """删除旧版本，保留最新的 keep_count 个"""
        # 1. 查询需要删除的版本
        sql = """
            SELECT id FROM dag_versions
            WHERE novel_id = ?
            ORDER BY version DESC
            LIMIT -1 OFFSET ?
        """
        rows = self.db.fetch_all(sql, (novel_id, keep_count))

        if not rows:
            return 0

        # 2. 删除旧版本
        ids_to_delete = [row['id'] for row in rows]
        placeholders = ','.join('?' * len(ids_to_delete))
        delete_sql = f"DELETE FROM dag_versions WHERE id IN ({placeholders})"
        self.db.execute(delete_sql, tuple(ids_to_delete))
        self.db.commit()

        logger.info(f"清理 {len(ids_to_delete)} 个旧版本: novel={novel_id}")
        return len(ids_to_delete)

    def get_version_count(self, novel_id: str) -> int:
        """获取版本总数"""
        sql = "SELECT COUNT(*) as count FROM dag_versions WHERE novel_id = ?"
        row = self.db.fetch_one(sql, (novel_id,))
        return row['count'] if row else 0

    def _row_to_dag(self, row: dict) -> DAGDefinition:
        """将数据库行转换为 DAGDefinition"""
        nodes = [NodeDefinition(**n) for n in json.loads(row['nodes_json'])]
        edges = [EdgeDefinition(**e) for e in json.loads(row['edges_json'])]

        return DAGDefinition(
            id=row['dag_id'],
            name=row['name'],
            version=row['version'],
            description=row['description'] or '',
            nodes=nodes,
            edges=edges,
            metadata=DAGMetadata(
                created_at=row.get('created_at', ''),
                updated_at=row['updated_at'],
                created_by='system'  # 可扩展为从数据库读取
            )
        )
