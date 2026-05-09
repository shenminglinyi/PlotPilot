"""迁移 DAG 版本从文件系统到数据库

用法：
    python -m infrastructure.persistence.database.migrate_dag_versions

幂等性：可重复执行，已迁移的数据不会重复插入
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict

from application.engine.dag.models import DAGDefinition
from infrastructure.persistence.database.connection import get_database
from infrastructure.persistence.database.sqlite_dag_version_repository import (
    SqliteDAGVersionRepository,
)

logger = logging.getLogger(__name__)


def migrate_dag_versions(
    definitions_dir: str = "data/dag_definitions",
    versions_dir: str = "data/dag_versions",
    dry_run: bool = False,
) -> Dict[str, int]:
    """迁移 DAG 版本到数据库

    Args:
        definitions_dir: DAG 定义目录（最新版本）
        versions_dir: DAG 版本历史目录
        dry_run: 是否只预览不实际执行

    Returns:
        迁移统计：{"novels_migrated": N, "versions_migrated": M, "errors": E}
    """
    db = get_database()
    repo = SqliteDAGVersionRepository(db)

    stats = {"novels_migrated": 0, "versions_migrated": 0, "errors": 0, "skipped": 0}

    # 1. 检查版本历史目录
    versions_path = Path(versions_dir)
    if not versions_path.exists():
        logger.info(f"版本历史目录不存在: {versions_dir}")
        return stats

    # 2. 遍历所有小说的版本目录
    for novel_dir in versions_path.iterdir():
        if not novel_dir.is_dir():
            continue

        novel_id = novel_dir.name
        logger.info(f"开始迁移小说: {novel_id}")

        # 3. 检查是否已迁移（幂等性）
        existing_count = repo.get_version_count(novel_id)
        if existing_count > 0:
            logger.info(f"小说 {novel_id} 已存在 {existing_count} 个版本，跳过迁移")
            stats["skipped"] += 1
            continue

        # 4. 查找所有版本文件
        version_files = sorted(
            [f for f in novel_dir.glob("v*.json")],
            key=lambda f: int(f.stem[1:]),  # 按 version 数字排序
        )

        if not version_files:
            logger.warning(f"小说 {novel_id} 无版本文件")
            continue

        # 5. 逐个迁移版本
        try:
            for version_file in version_files:
                version_num = int(version_file.stem[1:])

                with open(version_file, "r", encoding="utf-8") as f:
                    dag_data = json.load(f)

                dag = DAGDefinition(**dag_data)

                if not dry_run:
                    # 直接插入数据库，跳过 fingerprint 检查（历史数据）
                    _insert_version_directly(db, novel_id, dag)

                logger.info(f"迁移版本: {novel_id} v{version_num}")
                stats["versions_migrated"] += 1

            stats["novels_migrated"] += 1

        except Exception as e:
            logger.error(f"迁移失败: {novel_id} - {e}")
            stats["errors"] += 1

    return stats


def _insert_version_directly(db, novel_id: str, dag: DAGDefinition) -> None:
    """直接插入版本到数据库（跳过 fingerprint 检查）"""
    version_id = str(uuid.uuid4())
    nodes_json = json.dumps([n.model_dump(mode="json") for n in dag.nodes], ensure_ascii=False)
    edges_json = json.dumps([e.model_dump(mode="json") for e in dag.edges], ensure_ascii=False)

    sql = """
        INSERT INTO dag_versions (
            id, novel_id, version, dag_id, name, description,
            nodes_json, edges_json, fingerprint, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    db.execute(
        sql,
        (
            version_id,
            novel_id,
            dag.version,
            dag.id,
            dag.name,
            dag.description,
            nodes_json,
            edges_json,
            dag.fingerprint(),
            dag.metadata.created_at,
            dag.metadata.updated_at,
        ),
    )
    db.commit()


def cleanup_old_files(
    definitions_dir: str = "data/dag_definitions",
    versions_dir: str = "data/dag_versions",
    backup_suffix: str = ".bak",
) -> int:
    """清理已迁移的文件（重命名为 .bak）

    Args:
        definitions_dir: DAG 定义目录
        versions_dir: DAG 版本历史目录
        backup_suffix: 备份后缀（默认 .bak）

    Returns:
        清理的文件数量
    """
    cleaned = 0

    # 重命名整个目录
    for dir_path in [definitions_dir, versions_dir]:
        path = Path(dir_path)
        if path.exists():
            backup_path = path.parent / f"{path.name}{backup_suffix}"
            path.rename(backup_path)
            logger.info(f"重命名: {path} -> {backup_path}")
            cleaned += 1

    return cleaned


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # 执行迁移
    stats = migrate_dag_versions(
        definitions_dir="data/dag_definitions",
        versions_dir="data/dag_versions",
        dry_run="--dry-run" in sys.argv,
    )

    print("\n迁移统计:")
    print(f"  小说数: {stats['novels_migrated']}")
    print(f"  版本数: {stats['versions_migrated']}")
    print(f"  跳过数: {stats['skipped']}")
    print(f"  错误数: {stats['errors']}")

    if "--dry-run" in sys.argv:
        print("\n[DRY RUN] 未实际写入数据库")
    elif stats["errors"] == 0 and "--no-cleanup" not in sys.argv:
        print(
            "\n迁移成功，是否清理旧文件？（将重命名为 .bak）"
        )
        response = input("输入 'yes' 确认: ")
        if response.lower() == "yes":
            cleaned = cleanup_old_files(
                backup_suffix=datetime.now().strftime(".bak_%Y%m%d_%H%M%S")
            )
            print(f"已清理 {cleaned} 个目录")
