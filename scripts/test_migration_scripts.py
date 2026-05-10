#!/usr/bin/env python3
"""
测试迁移脚本

创建一个临时测试数据库，验证迁移脚本能够正常工作。
"""
import sqlite3
import tempfile
from pathlib import Path


def create_test_database(db_path: Path):
    """创建测试数据库

    Args:
        db_path: 数据库文件路径
    """
    conn = sqlite3.connect(str(db_path))

    # 创建 novels 表
    conn.execute("""
        CREATE TABLE novels (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            slug TEXT NOT NULL
        )
    """)

    # 创建 checkpoints 表
    conn.execute("""
        CREATE TABLE checkpoints (
            id TEXT PRIMARY KEY,
            story_id TEXT NOT NULL,
            parent_id TEXT,
            trigger_type TEXT NOT NULL,
            trigger_reason TEXT NOT NULL DEFAULT '',
            story_state TEXT NOT NULL DEFAULT '{}',
            character_masks TEXT NOT NULL DEFAULT '{}',
            emotion_ledger TEXT NOT NULL DEFAULT '{}',
            active_foreshadows TEXT NOT NULL DEFAULT '[]',
            outline TEXT NOT NULL DEFAULT '',
            recent_chapters_summary TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 创建 novel_snapshots 表（包含引擎状态字段）
    conn.execute("""
        CREATE TABLE novel_snapshots (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            parent_snapshot_id TEXT,
            branch_name TEXT NOT NULL DEFAULT 'main',
            trigger_type TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            chapter_pointers TEXT NOT NULL,
            bible_state TEXT,
            foreshadow_state TEXT,
            graph_state TEXT,
            story_state TEXT DEFAULT '{}',
            character_masks TEXT DEFAULT '{}',
            emotion_ledger TEXT DEFAULT '{}',
            active_foreshadows TEXT DEFAULT '[]',
            outline TEXT DEFAULT '',
            recent_chapters_summary TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 创建 checkpoint_heads 表
    conn.execute("""
        CREATE TABLE checkpoint_heads (
            story_id TEXT PRIMARY KEY,
            checkpoint_id TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 插入测试数据
    conn.execute("INSERT INTO novels VALUES ('novel-1', '测试小说', 'test-novel')")

    # 插入测试 checkpoint 数据
    conn.execute("""
        INSERT INTO checkpoints VALUES (
            'checkpoint-1',
            'novel-1',
            NULL,
            'chapter',
            '第1章完成',
            '{"chapter": 1}',
            '{"protagonist": {"name": "张三"}}',
            '{"joy": 0.8}',
            '[]',
            '初始大纲',
            '第1章摘要',
            1,
            '2024-01-01 10:00:00'
        )
    """)

    conn.execute("""
        INSERT INTO checkpoints VALUES (
            'checkpoint-2',
            'novel-1',
            'checkpoint-1',
            'manual',
            '手动保存',
            '{"chapter": 2}',
            '{"protagonist": {"name": "张三", "age": 25}}',
            '{"joy": 0.6, "tension": 0.4}',
            '[{"id": "f1", "content": "伏笔1"}]',
            '更新大纲',
            '第2章摘要',
            1,
            '2024-01-02 10:00:00'
        )
    """)

    conn.execute("""
        INSERT INTO checkpoint_heads VALUES (
            'novel-1',
            'checkpoint-2',
            '2024-01-02 10:00:00'
        )
    """)

    conn.commit()
    conn.close()


def test_migration_scripts():
    """测试迁移脚本"""
    import subprocess
    import sys

    # 创建临时数据库
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        print(f"创建测试数据库: {db_path}")

        create_test_database(db_path)

        # 验证初始数据
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM checkpoints")
        checkpoint_count = cursor.fetchone()[0]
        print(f"测试数据库中的 checkpoint 数量: {checkpoint_count}")
        assert checkpoint_count == 2, f"预期 2 个 checkpoint，实际 {checkpoint_count}"

        cursor = conn.execute("SELECT COUNT(*) FROM novel_snapshots")
        snapshot_count = cursor.fetchone()[0]
        print(f"测试数据库中的 snapshot 数量: {snapshot_count}")
        assert snapshot_count == 0, f"预期 0 个 snapshot，实际 {snapshot_count}"

        conn.close()

        # 测试验证脚本（迁移前）
        print("\n运行验证脚本（迁移前）...")
        result = subprocess.run(
            [
                sys.executable,
                "scripts/verify_migration.py",
                "--db", str(db_path)
            ],
            capture_output=True,
            text=True
        )

        print("验证脚本输出:")
        print(result.stdout)
        if result.stderr:
            print("错误输出:")
            print(result.stderr)

        # 验证脚本应该失败（因为还没有迁移）
        assert result.returncode != 0, "验证脚本应该失败（未迁移）"

        # 测试迁移脚本（dry-run）
        print("\n测试迁移脚本（dry-run）...")
        result = subprocess.run(
            [
                sys.executable,
                "scripts/migrate_checkpoints_to_snapshots.py",
                "--db", str(db_path),
                "--dry-run"
            ],
            capture_output=True,
            text=True
        )

        print("迁移脚本输出:")
        print(result.stdout)
        if result.stderr:
            print("错误输出:")
            print(result.stderr)

        assert result.returncode == 0, "迁移脚本（dry-run）应该成功"

        # 验证 dry-run 没有修改数据库
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM novel_snapshots")
        snapshot_count = cursor.fetchone()[0]
        print(f"dry-run 后的 snapshot 数量: {snapshot_count}")
        assert snapshot_count == 0, "dry-run 不应该修改数据库"
        conn.close()

        # 测试实际迁移
        print("\n运行实际迁移...")
        result = subprocess.run(
            [
                sys.executable,
                "scripts/migrate_checkpoints_to_snapshots.py",
                "--db", str(db_path)
            ],
            capture_output=True,
            text=True
        )

        print("迁移脚本输出:")
        print(result.stdout)
        if result.stderr:
            print("错误输出:")
            print(result.stderr)

        assert result.returncode == 0, f"迁移脚本应该成功，退出码: {result.returncode}"

        # 验证迁移结果
        conn = sqlite3.connect(str(db_path))

        # 检查 snapshot 数量
        cursor = conn.execute("SELECT COUNT(*) FROM novel_snapshots")
        snapshot_count = cursor.fetchone()[0]
        print(f"\n迁移后的 snapshot 数量: {snapshot_count}")
        assert snapshot_count == 2, f"预期 2 个 snapshot，实际 {snapshot_count}"

        # 检查迁移的数据
        cursor = conn.execute(
            """SELECT id, novel_id, trigger_type, name, story_state, character_masks
               FROM novel_snapshots
               ORDER BY created_at"""
        )
        snapshots = cursor.fetchall()

        # 验证第一个 snapshot
        snap1 = snapshots[0]
        assert snap1[0] == 'checkpoint-1', f"ID 应为 'checkpoint-1'，实际 {snap1[0]}"
        assert snap1[1] == 'novel-1', f"novel_id 应为 'novel-1'，实际 {snap1[1]}"
        assert snap1[2] == 'AUTO', f"trigger_type 应为 'AUTO'，实际 {snap1[2]}"
        assert snap1[3] == '第1章完成', f"name 应为 '第1章完成'，实际 {snap1[3]}"
        assert snap1[4] == '{"chapter": 1}', f"story_state 不正确: {snap1[4]}"

        # 验证第二个 snapshot
        snap2 = snapshots[1]
        assert snap2[0] == 'checkpoint-2', f"ID 应为 'checkpoint-2'，实际 {snap2[0]}"
        assert snap2[2] == 'MANUAL', f"trigger_type 应为 'MANUAL'，实际 {snap2[2]}"

        conn.close()

        # 测试验证脚本（迁移后）
        print("\n运行验证脚本（迁移后）...")
        result = subprocess.run(
            [
                sys.executable,
                "scripts/verify_migration.py",
                "--db", str(db_path)
            ],
            capture_output=True,
            text=True
        )

        print("验证脚本输出:")
        print(result.stdout)
        if result.stderr:
            print("错误输出:")
            print(result.stderr)

        assert result.returncode == 0, f"验证脚本应该成功，退出码: {result.returncode}"

        print("\n✓ 所有测试通过!")


if __name__ == '__main__':
    test_migration_scripts()
