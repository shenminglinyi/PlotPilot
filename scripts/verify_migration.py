#!/usr/bin/env python3
"""
验证 checkpoints 到 novel_snapshots 的迁移

用法:
    python scripts/verify_migration.py --db path/to/database.db
    python scripts/verify_migration.py --env production

功能:
    1. 检查表结构是否包含所有必需字段
    2. 验证数据完整性
    3. 统计迁移记录数量
"""
import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MigrationVerifier:
    """迁移验证器"""

    def __init__(self, db_path: str):
        """初始化验证器

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"数据库文件不存在: {db_path}")

        self.conn: sqlite3.Connection = None

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

    def check_table_exists(self, table_name: str) -> bool:
        """检查表是否存在

        Args:
            table_name: 表名

        Returns:
            是否存在
        """
        cursor = self.conn.execute(
            """SELECT name FROM sqlite_master
               WHERE type='table' AND name=?""",
            (table_name,)
        )
        return cursor.fetchone() is not None

    def get_table_columns(self, table_name: str) -> Dict[str, str]:
        """获取表的列信息

        Args:
            table_name: 表名

        Returns:
            列名 -> 数据类型的字典
        """
        cursor = self.conn.execute(f"PRAGMA table_info({table_name})")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        return columns

    def verify_checkpoints_table_structure(self) -> Tuple[bool, Dict]:
        """验证 checkpoints 表结构

        Returns:
            (是否通过, 详细信息)
        """
        logger.info("="*60)
        logger.info("验证 checkpoints 表结构")
        logger.info("="*60)

        result = {
            'table_exists': False,
            'has_required_columns': False,
            'missing_columns': [],
            'columns': {}
        }

        # 检查表是否存在
        if not self.check_table_exists('checkpoints'):
            logger.error("✗ checkpoints 表不存在")
            return False, result

        result['table_exists'] = True
        logger.info("✓ checkpoints 表存在")

        # 检查必需列
        required_columns = {
            'id': 'TEXT',
            'story_id': 'TEXT',
            'parent_id': 'TEXT',
            'trigger_type': 'TEXT',
            'trigger_reason': 'TEXT',
            'story_state': 'TEXT',
            'character_masks': 'TEXT',
            'emotion_ledger': 'TEXT',
            'active_foreshadows': 'TEXT',
            'outline': 'TEXT',
            'recent_chapters_summary': 'TEXT',
            'is_active': 'INTEGER',
            'created_at': 'TIMESTAMP',
        }

        columns = self.get_table_columns('checkpoints')
        result['columns'] = columns

        missing = []
        for col_name, col_type in required_columns.items():
            if col_name not in columns:
                missing.append(col_name)
            elif columns[col_name] != col_type:
                logger.warning(
                    f"  列 {col_name} 类型不匹配: "
                    f"期望 {col_type}, 实际 {columns[col_name]}"
                )

        result['missing_columns'] = missing

        if missing:
            logger.error(f"✗ 缺少列: {missing}")
            result['has_required_columns'] = False
            return False, result

        result['has_required_columns'] = True
        logger.info("✓ checkpoints 表包含所有必需列")
        return True, result

    def verify_novel_snapshots_table_structure(self) -> Tuple[bool, Dict]:
        """验证 novel_snapshots 表结构

        Returns:
            (是否通过, 详细信息)
        """
        logger.info("="*60)
        logger.info("验证 novel_snapshots 表结构")
        logger.info("="*60)

        result = {
            'table_exists': False,
            'has_engine_state_columns': False,
            'missing_columns': [],
            'columns': {}
        }

        # 检查表是否存在
        if not self.check_table_exists('novel_snapshots'):
            logger.error("✗ novel_snapshots 表不存在")
            return False, result

        result['table_exists'] = True
        logger.info("✓ novel_snapshots 表存在")

        # 检查引擎状态列（Task 1 添加的字段）
        engine_state_columns = {
            'story_state': 'TEXT',
            'character_masks': 'TEXT',
            'emotion_ledger': 'TEXT',
            'active_foreshadows': 'TEXT',
            'outline': 'TEXT',
            'recent_chapters_summary': 'TEXT',
        }

        columns = self.get_table_columns('novel_snapshots')
        result['columns'] = columns

        missing = []
        for col_name, col_type in engine_state_columns.items():
            if col_name not in columns:
                missing.append(col_name)

        result['missing_columns'] = missing

        if missing:
            logger.error(f"✗ 缺少引擎状态列: {missing}")
            logger.error("  请先运行 Task 1 的数据库迁移: add_engine_state_to_snapshots.sql")
            result['has_engine_state_columns'] = False
            return False, result

        result['has_engine_state_columns'] = True
        logger.info("✓ novel_snapshots 表包含所有引擎状态列")
        return True, result

    def verify_data_integrity(self) -> Tuple[bool, Dict]:
        """验证数据完整性

        Returns:
            (是否通过, 详细信息)
        """
        logger.info("="*60)
        logger.info("验证数据完整性")
        logger.info("="*60)

        result = {
            'checkpoints_count': 0,
            'active_checkpoints': 0,
            'snapshots_count': 0,
            'migrated_checkpoints': 0,
            'missing_migrations': [],
            'orphaned_checkpoints': [],
        }

        # 统计 checkpoints
        cursor = self.conn.execute("SELECT COUNT(*) FROM checkpoints")
        result['checkpoints_count'] = cursor.fetchone()[0]
        logger.info(f"checkpoints 总数: {result['checkpoints_count']}")

        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE is_active = 1"
        )
        result['active_checkpoints'] = cursor.fetchone()[0]
        logger.info(f"活跃 checkpoints: {result['active_checkpoints']}")

        # 统计 novel_snapshots
        cursor = self.conn.execute("SELECT COUNT(*) FROM novel_snapshots")
        result['snapshots_count'] = cursor.fetchone()[0]
        logger.info(f"novel_snapshots 总数: {result['snapshots_count']}")

        # 统计从 checkpoint 迁移的 snapshot（chapter_pointers 为空）
        cursor = self.conn.execute(
            """SELECT COUNT(*) FROM novel_snapshots
               WHERE chapter_pointers = '[]'"""
        )
        result['migrated_checkpoints'] = cursor.fetchone()[0]
        logger.info(f"从 checkpoint 迁移的 snapshot: {result['migrated_checkpoints']}")

        # 检查每个活跃 checkpoint 是否都已迁移
        cursor = self.conn.execute(
            "SELECT id, story_id FROM checkpoints WHERE is_active = 1"
        )
        checkpoints = cursor.fetchall()

        missing = []
        for checkpoint in checkpoints:
            cursor = self.conn.execute(
                "SELECT id FROM novel_snapshots WHERE id = ?",
                (checkpoint['id'],)
            )
            if not cursor.fetchone():
                missing.append({
                    'id': checkpoint['id'],
                    'story_id': checkpoint['story_id']
                })

        result['missing_migrations'] = missing

        if missing:
            logger.error(f"✗ 发现 {len(missing)} 个未迁移的 checkpoint:")
            for item in missing[:5]:  # 只显示前5个
                logger.error(f"  - {item['id']} (story: {item['story_id']})")
            if len(missing) > 5:
                logger.error(f"  ... 还有 {len(missing) - 5} 个")
        else:
            logger.info("✓ 所有活跃 checkpoint 都已迁移")

        # 检查孤立 checkpoint（story_id 不存在）
        cursor = self.conn.execute(
            """SELECT c.id, c.story_id
               FROM checkpoints c
               LEFT JOIN novels n ON c.story_id = n.id
               WHERE c.is_active = 1 AND n.id IS NULL"""
        )
        orphaned = cursor.fetchall()
        result['orphaned_checkpoints'] = [dict(row) for row in orphaned]

        if orphaned:
            logger.warning(f"⚠ 发现 {len(orphaned)} 个孤立 checkpoint (story_id 不存在):")
            for item in orphaned[:5]:
                logger.warning(f"  - {item['id']} (story_id: {item['story_id']})")
        else:
            logger.info("✓ 没有孤立 checkpoint")

        # 验证数据一致性
        success = (len(missing) == 0)
        return success, result

    def verify_engine_state_data(self) -> Tuple[bool, Dict]:
        """验证引擎状态数据

        Returns:
            (是否通过, 详细信息)
        """
        logger.info("="*60)
        logger.info("验证引擎状态数据")
        logger.info("="*60)

        result = {
            'sample_size': 0,
            'valid_json_count': 0,
            'invalid_json_fields': [],
        }

        # 随机抽取 5 条迁移的 snapshot 检查引擎状态字段
        cursor = self.conn.execute(
            """SELECT id, story_state, character_masks, emotion_ledger,
                          active_foreshadows, outline, recent_chapters_summary
               FROM novel_snapshots
               WHERE chapter_pointers = '[]'
               LIMIT 5"""
        )
        samples = cursor.fetchall()
        result['sample_size'] = len(samples)

        if not samples:
            logger.warning("没有找到迁移的 snapshot 记录")
            return True, result

        json_fields = [
            'story_state', 'character_masks', 'emotion_ledger',
            'active_foreshadows'
        ]

        for sample in samples:
            sample_dict = dict(sample)
            snapshot_id = sample_dict['id']

            for field in json_fields:
                value = sample_dict.get(field, '')
                try:
                    if value:
                        json.loads(value)
                except json.JSONDecodeError as e:
                    error_msg = f"{snapshot_id}.{field}: {e}"
                    result['invalid_json_fields'].append(error_msg)
                    logger.error(f"  ✗ {error_msg}")

        result['valid_json_count'] = result['sample_size'] * len(json_fields) - len(result['invalid_json_fields'])

        if result['invalid_json_fields']:
            logger.error(f"✗ 发现无效 JSON 字段: {len(result['invalid_json_fields'])}")
            return False, result

        logger.info(f"✓ 所有样本的引擎状态字段 JSON 格式正确 ({result['sample_size']} 条)")
        return True, result

    def generate_report(self) -> Dict:
        """生成完整验证报告

        Returns:
            验证报告
        """
        logger.info("\n" + "="*60)
        logger.info("开始生成验证报告")
        logger.info("="*60 + "\n")

        report = {
            'database_path': str(self.db_path),
            'checkpoints_structure': {},
            'snapshots_structure': {},
            'data_integrity': {},
            'engine_state_data': {},
            'all_checks_passed': False,
        }

        # 1. 验证 checkpoints 表结构
        success1, result1 = self.verify_checkpoints_table_structure()
        report['checkpoints_structure'] = result1

        # 2. 验证 novel_snapshots 表结构
        success2, result2 = self.verify_novel_snapshots_table_structure()
        report['snapshots_structure'] = result2

        # 3. 验证数据完整性
        success3, result3 = self.verify_data_integrity()
        report['data_integrity'] = result3

        # 4. 验证引擎状态数据
        success4, result4 = self.verify_engine_state_data()
        report['engine_state_data'] = result4

        # 总结
        report['all_checks_passed'] = all([success1, success2, success3, success4])

        logger.info("\n" + "="*60)
        logger.info("验证报告总结")
        logger.info("="*60)
        logger.info(f"checkpoints 表结构: {'✓ 通过' if success1 else '✗ 失败'}")
        logger.info(f"novel_snapshots 表结构: {'✓ 通过' if success2 else '✗ 失败'}")
        logger.info(f"数据完整性: {'✓ 通过' if success3 else '✗ 失败'}")
        logger.info(f"引擎状态数据: {'✓ 通过' if success4 else '✗ 失败'}")
        logger.info("="*60)

        if report['all_checks_passed']:
            logger.info("✓✓✓ 所有验证项目通过!")
        else:
            logger.error("✗✗✗ 部分验证项目失败!")

        logger.info("="*60 + "\n")

        return report

    def run_verification(self) -> bool:
        """执行完整验证流程

        Returns:
            是否所有检查都通过
        """
        try:
            self.connect()
            report = self.generate_report()
            return report['all_checks_passed']

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
        default_path = Path(__file__).parent.parent / "data" / "aitext.db"

    if not default_path.exists():
        raise FileNotFoundError(
            f"数据库文件不存在: {default_path}\n"
            f"请使用 --db 参数指定数据库路径"
        )

    return str(default_path)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='验证 checkpoints 到 novel_snapshots 的迁移'
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
        '--output',
        type=str,
        help='输出报告文件路径 (JSON)'
    )

    args = parser.parse_args()

    if not args.db and not args.env:
        parser.error("必须指定 --db 或 --env 参数")

    try:
        db_path = get_db_path(args)
        logger.info(f"数据库路径: {db_path}")

        verifier = MigrationVerifier(db_path)
        success = verifier.run_verification()

        # 如果指定了输出文件，保存报告
        if args.output:
            import json
            report = verifier.generate_report()
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            logger.info(f"验证报告已保存到: {output_path}")

        exit(0 if success else 1)

    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        exit(1)


if __name__ == '__main__':
    main()
