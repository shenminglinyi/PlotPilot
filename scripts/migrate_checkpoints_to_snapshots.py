#!/usr/bin/env python3
"""
迁移 checkpoints 表数据到 novel_snapshots 表

用法:
    python scripts/migrate_checkpoints_to_snapshots.py --db path/to/database.db
    python scripts/migrate_checkpoints_to_snapshots.py --env production

功能:
    1. 备份 checkpoints 表
    2. 迁移数据到 novel_snapshots 表
    3. 验证迁移完整性
"""
import argparse
import json
import logging
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CheckpointMigrator:
    """Checkpoint 到 Snapshot 的迁移器"""

    # 触发类型映射: checkpoint.trigger_type -> snapshot.trigger_type
    TRIGGER_TYPE_MAP = {
        'chapter': 'AUTO',
        'act': 'AUTO',
        'milestone': 'AUTO',
        'manual': 'MANUAL',
        'AUTO': 'AUTO',
        'MANUAL': 'MANUAL',
    }

    def __init__(self, db_path: str):
        """初始化迁移器

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"数据库文件不存在: {db_path}")

        self.conn: Optional[sqlite3.Connection] = None
        self.stats = {
            'checkpoints_found': 0,
            'checkpoints_migrated': 0,
            'checkpoints_skipped': 0,
            'errors': [],
        }

    def connect(self):
        """连接数据库"""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        logger.info(f"已连接数据库: {self.db_path}")

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("数据库连接已关闭")

    def backup_checkpoints_table(self) -> Path:
        """备份 checkpoints 表

        Returns:
            备份文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        backup_path = self.db_path.parent / f"checkpoints_backup_{timestamp}_{unique_id}.db"

        logger.info(f"开始备份 checkpoints 表到: {backup_path}")

        # 创建备份（使用 copy 而非 move，确保原始文件安全）
        temp_backup = self.db_path.parent / f"temp_backup_{timestamp}_{unique_id}.db"
        shutil.copy2(self.db_path, temp_backup)

        # 从备份中只保留 checkpoints 相关表
        backup_conn = None
        try:
            backup_conn = sqlite3.connect(str(temp_backup))
            # 获取所有表名
            cursor = backup_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            all_tables = [row[0] for row in cursor.fetchall()]

            # 定义允许保留的表（白名单）
            allowed_tables = {'checkpoints', 'checkpoint_heads'}

            # 删除不在白名单中的表（使用参数化查询避免 SQL 注入）
            for table in all_tables:
                if table not in allowed_tables:
                    # 使用参数化查询防止 SQL 注入
                    # 注意：SQLite 不支持表名参数化，但我们已经通过白名单验证
                    # 白名单验证是最安全的方式
                    if table.isidentifier():  # 额外验证：确保是有效的标识符
                        backup_conn.execute(f"DROP TABLE IF EXISTS [{table}]")

            backup_conn.commit()
        finally:
            if backup_conn:
                backup_conn.close()

        # 使用 copy 而非 rename，确保备份文件独立存在
        shutil.copy2(temp_backup, backup_path)

        # 清理临时备份
        temp_backup.unlink()

        logger.info(f"✓ checkpoints 表已备份到: {backup_path}")
        return backup_path

    def verify_novel_snapshots_has_engine_state(self) -> bool:
        """验证 novel_snapshots 表包含引擎状态字段

        Returns:
            是否包含所有必需字段
        """
        required_columns = [
            'story_state', 'character_masks', 'emotion_ledger',
            'active_foreshadows', 'outline', 'recent_chapters_summary'
        ]

        cursor = self.conn.execute("PRAGMA table_info(novel_snapshots)")
        columns = {row[1] for row in cursor.fetchall()}

        missing = [col for col in required_columns if col not in columns]

        if missing:
            logger.error(f"novel_snapshots 表缺少引擎状态字段: {missing}")
            logger.error("请先运行 Task 1 的数据库迁移: add_engine_state_to_snapshots.sql")
            return False

        logger.info("✓ novel_snapshots 表包含所有必需的引擎状态字段")
        return True

    def get_all_checkpoints(self) -> List[Dict]:
        """获取所有活跃的 checkpoint 记录

        Returns:
            checkpoint 记录列表
        """
        cursor = self.conn.execute(
            """SELECT * FROM checkpoints
               WHERE is_active = 1
               ORDER BY created_at ASC"""
        )
        checkpoints = [dict(row) for row in cursor.fetchall()]
        logger.info(f"找到 {len(checkpoints)} 条活跃 checkpoint 记录")
        return checkpoints

    def checkpoint_exists_in_snapshots(self, checkpoint_id: str) -> bool:
        """检查 checkpoint 是否已存在于 novel_snapshots

        Args:
            checkpoint_id: checkpoint ID

        Returns:
            是否已存在
        """
        cursor = self.conn.execute(
            "SELECT id FROM novel_snapshots WHERE id = ?",
            (checkpoint_id,)
        )
        return cursor.fetchone() is not None

    def map_trigger_type(self, checkpoint_trigger: str) -> str:
        """映射触发类型

        Args:
            checkpoint_trigger: checkpoint 的触发类型

        Returns:
            snapshot 的触发类型
        """
        return self.TRIGGER_TYPE_MAP.get(checkpoint_trigger, 'MANUAL')

    def migrate_checkpoint(self, checkpoint: Dict) -> bool:
        """迁移单个 checkpoint 到 novel_snapshots

        Args:
            checkpoint: checkpoint 记录

        Returns:
            是否成功
        """
        checkpoint_id = checkpoint['id']

        # 检查是否已存在
        if self.checkpoint_exists_in_snapshots(checkpoint_id):
            logger.warning(f"Checkpoint {checkpoint_id} 已存在于 novel_snapshots，跳过")
            self.stats['checkpoints_skipped'] += 1
            return True

        # 准备迁移数据
        try:
            novel_id = checkpoint['story_id']
            parent_snapshot_id = checkpoint.get('parent_id')
            trigger_type = self.map_trigger_type(checkpoint['trigger_type'])
            name = checkpoint.get('trigger_reason', 'Migrated Checkpoint')
            branch_name = 'main'

            # 引擎状态字段（直接复制）
            story_state = checkpoint.get('story_state', '{}')
            character_masks = checkpoint.get('character_masks', '{}')
            emotion_ledger = checkpoint.get('emotion_ledger', '{}')
            active_foreshadows = checkpoint.get('active_foreshadows', '[]')
            outline = checkpoint.get('outline', '')
            recent_chapters_summary = checkpoint.get('recent_chapters_summary', '')

            # chapter_pointers 默认为空列表（checkpoint 不存储章节指针）
            chapter_pointers = '[]'

            # bible_state 和 foreshadow_state 默认为空（checkpoint 不存储这些）
            bible_state = '{}'
            foreshadow_state = '{}'

            # 插入到 novel_snapshots
            self.conn.execute(
                """INSERT INTO novel_snapshots
                   (id, novel_id, parent_snapshot_id, branch_name,
                    trigger_type, name, description,
                    chapter_pointers, bible_state, foreshadow_state,
                    story_state, character_masks, emotion_ledger,
                    active_foreshadows, outline, recent_chapters_summary,
                    created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    checkpoint_id, novel_id, parent_snapshot_id, branch_name,
                    trigger_type, name, None,
                    chapter_pointers, bible_state, foreshadow_state,
                    story_state, character_masks, emotion_ledger,
                    active_foreshadows, outline, recent_chapters_summary,
                    checkpoint.get('created_at')
                )
            )

            logger.debug(f"✓ 已迁移 checkpoint: {checkpoint_id}")
            self.stats['checkpoints_migrated'] += 1
            return True

        except Exception as e:
            error_msg = f"迁移 checkpoint {checkpoint_id} 失败: {e}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
            return False

    def migrate_checkpoint_heads(self) -> int:
        """迁移 checkpoint_heads 表到 novel_snapshots

        Returns:
            迁移的 HEAD 记录数量
        """
        cursor = self.conn.execute("SELECT * FROM checkpoint_heads")
        heads = cursor.fetchall()
        logger.info(f"找到 {len(heads)} 条 checkpoint_heads 记录")

        # 注意: novel_snapshots 没有 HEAD 指针概念
        # 这些信息仅用于日志记录，不实际迁移
        for head in heads:
            logger.info(
                f"  - Story {head['story_id']} HEAD -> {head['checkpoint_id']}"
            )

        return len(heads)

    def verify_migration(self) -> Tuple[bool, Dict]:
        """验证迁移完整性

        Returns:
            (是否成功, 验证统计)
        """
        logger.info("开始验证迁移完整性...")

        verification = {
            'original_checkpoints': 0,
            'migrated_checkpoints': 0,
            'missing_checkpoints': [],
            'data_integrity_ok': True,
        }

        # 统计原始 checkpoint 数量
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE is_active = 1"
        )
        verification['original_checkpoints'] = cursor.fetchone()[0]

        # 统计迁移后的 snapshot 数量（只计算从 checkpoint 迁移的）
        cursor = self.conn.execute(
            """SELECT COUNT(*) FROM novel_snapshots
               WHERE chapter_pointers = '[]'"""
        )
        verification['migrated_checkpoints'] = cursor.fetchone()[0]

        # 检查每个 checkpoint 是否都成功迁移
        cursor = self.conn.execute(
            "SELECT id FROM checkpoints WHERE is_active = 1"
        )
        checkpoint_ids = [row[0] for row in cursor.fetchall()]

        for cid in checkpoint_ids:
            cursor = self.conn.execute(
                "SELECT id FROM novel_snapshots WHERE id = ?",
                (cid,)
            )
            if not cursor.fetchone():
                verification['missing_checkpoints'].append(cid)

        if verification['missing_checkpoints']:
            verification['data_integrity_ok'] = False
            logger.error(
                f"发现缺失的 checkpoint: {verification['missing_checkpoints']}"
            )

        # 验证引擎状态字段是否正确迁移
        if verification['data_integrity_ok']:
            # 随机抽查一条记录
            cursor = self.conn.execute(
                """SELECT id, story_state, character_masks, emotion_ledger,
                          active_foreshadows, outline, recent_chapters_summary
                   FROM novel_snapshots
                   WHERE chapter_pointers = '[]'
                   LIMIT 1"""
            )
            sample = cursor.fetchone()
            if sample:
                logger.info("样本记录验证:")
                logger.info(f"  ID: {sample[0]}")
                logger.info(f"  story_state: {sample[1][:50]}...")
                logger.info(f"  character_masks: {sample[2][:50]}...")

        success = verification['data_integrity_ok']
        return success, verification

    def run_migration(self, dry_run: bool = False) -> bool:
        """执行完整迁移流程

        Args:
            dry_run: 是否只做预演，不实际修改数据库

        Returns:
            是否成功
        """
        logger.info("="*60)
        logger.info("开始 Checkpoint -> Snapshot 迁移")
        logger.info("="*60)

        # 备份文件路径（在连接前创建）
        backup_path = None

        try:
            # 1. 备份 checkpoints 表（在连接数据库前进行）
            if not dry_run:
                backup_path = self.backup_checkpoints_table()
                logger.info(f"备份文件: {backup_path}")

            # 2. 连接数据库
            self.connect()

            # 3. 验证 novel_snapshots 表结构
            if not self.verify_novel_snapshots_has_engine_state():
                return False

            # 4. 获取所有 checkpoint
            checkpoints = self.get_all_checkpoints()
            self.stats['checkpoints_found'] = len(checkpoints)

            if not checkpoints:
                logger.info("没有需要迁移的 checkpoint 记录")
                return True

            # 5. 开始事务（显式事务管理）
            if not dry_run:
                logger.info("开始事务...")
                self.conn.execute("BEGIN TRANSACTION")

            # 6. 迁移每个 checkpoint
            logger.info(f"开始迁移 {len(checkpoints)} 条 checkpoint 记录...")

            for idx, checkpoint in enumerate(checkpoints, 1):
                logger.info(f"[{idx}/{len(checkpoints)}] 迁移 {checkpoint['id']}")
                if not dry_run:
                    self.migrate_checkpoint(checkpoint)

            # 7. 检查是否有迁移错误
            if not dry_run and self.stats['errors']:
                logger.error(f"发现 {len(self.stats['errors'])} 个迁移错误，正在回滚事务...")
                self.conn.rollback()
                logger.error("✗ 事务已回滚，数据库未修改")
                logger.error("错误详情:")
                for error in self.stats['errors']:
                    logger.error(f"  - {error}")
                return False

            # 8. 迁移 checkpoint_heads（仅记录日志）
            if not dry_run:
                self.migrate_checkpoint_heads()

            # 9. 提交事务
            if not dry_run:
                self.conn.commit()
                logger.info("✓ 事务已提交")

            # 10. 验证迁移
            if not dry_run:
                success, verification = self.verify_migration()

                logger.info("="*60)
                logger.info("迁移统计:")
                logger.info(f"  找到 checkpoint: {self.stats['checkpoints_found']}")
                logger.info(f"  成功迁移: {self.stats['checkpoints_migrated']}")
                logger.info(f"  跳过已存在: {self.stats['checkpoints_skipped']}")
                logger.info(f"  错误数量: {len(self.stats['errors'])}")

                if self.stats['errors']:
                    logger.error("错误详情:")
                    for error in self.stats['errors']:
                        logger.error(f"  - {error}")

                logger.info("="*60)
                logger.info("验证统计:")
                for key, value in verification.items():
                    if isinstance(value, list):
                        logger.info(f"  {key}: {len(value)} 项")
                    else:
                        logger.info(f"  {key}: {value}")

                if success:
                    logger.info("="*60)
                    logger.info("✓ 迁移成功完成!")
                    logger.info("="*60)
                else:
                    logger.error("="*60)
                    logger.error("✗ 迁移验证失败!")
                    logger.error("="*60)

                return success

            else:
                logger.info("[DRY RUN] 预演完成，未实际修改数据库")
                return True

        except Exception as e:
            logger.error(f"迁移过程出错: {e}", exc_info=True)
            if self.conn:
                logger.error("正在回滚事务...")
                self.conn.rollback()
                logger.error("✗ 事务已回滚")
            return False

        finally:
            self.close()


def get_db_path(args) -> str:
    """根据参数获取数据库路径

    Args:
        args: 命令行参数

    Returns:
        数据库文件路径
    """
    if args.db:
        return args.db

    # 根据 --env 参数确定配置文件
    # 这里简化处理，实际项目中应该读取配置文件
    if args.env == 'development':
        default_path = Path(__file__).parent.parent / "data" / "development.db"
    elif args.env == 'production':
        default_path = Path(__file__).parent.parent / "data" / "production.db"
    else:
        default_path = Path(__file__).parent.parent / "data" / "plotpilot.db"

    if not default_path.exists():
        raise FileNotFoundError(
            f"数据库文件不存在: {default_path}\n"
            f"请使用 --db 参数指定数据库路径"
        )

    return str(default_path)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='迁移 checkpoints 表数据到 novel_snapshots 表'
    )
    parser.add_argument(
        '--db',
        type=str,
        help='数据库文件路径'
    )
    parser.add_argument(
        '--env',
        type=str,
        choices=['development', 'production'],
        help='环境名称 (development/production)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='预演模式，不实际修改数据库'
    )

    args = parser.parse_args()

    if not args.db and not args.env:
        parser.error("必须指定 --db 或 --env 参数")

    try:
        db_path = get_db_path(args)
        logger.info(f"数据库路径: {db_path}")

        migrator = CheckpointMigrator(db_path)
        success = migrator.run_migration(dry_run=args.dry_run)

        exit(0 if success else 1)

    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        exit(1)


if __name__ == '__main__':
    main()
