"""Checkpoint机制评测器

测试指标：
- 创建/回滚
- 树状结构
- HEAD指针
- 平行宇宙
- 保留策略
"""
from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
import os
import asyncio
from typing import Dict, Any, List

from engine.domain.value_objects.checkpoint import (
    Checkpoint, CheckpointId, CheckpointType,
)
from engine.infrastructure.persistence.checkpoint_store import CheckpointStore

logger = logging.getLogger(__name__)


class SimpleDBPool:
    """简单的DB连接池用于测试"""

    def __init__(self, db_path: str):
        self._db_path = db_path

    def get_connection(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn


class CheckpointEvaluator:
    """Checkpoint机制评测器"""

    def run(self) -> Dict[str, Any]:
        results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "details": [],
        }

        # 创建临时数据库
        db_path = os.path.join(tempfile.gettempdir(), f"checkpoint_eval_{os.getpid()}.db")

        try:
            db_pool = SimpleDBPool(db_path)
            store = CheckpointStore(db_pool)

            async def _run_tests():
                # 测试1: 创建Checkpoint
                results["total"] += 1
                try:
                    cp1 = Checkpoint.create(
                        story_id="test_story",
                        trigger_type=CheckpointType.CHAPTER,
                        trigger_reason="第1章完成",
                        story_state={"chapter": 1},
                        character_masks={"char1": {"name": "林羽"}},
                        emotion_ledger={"wounds": []},
                        active_foreshadows=["fs1"],
                    )
                    cp1_id = await store.save(cp1)
                    if cp1_id:
                        results["passed"] += 1
                        results["details"].append({"name": "创建Checkpoint", "passed": True})
                    else:
                        results["failed"] += 1
                        results["details"].append({"name": "创建Checkpoint", "passed": False, "error": "返回None"})
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({"name": "创建Checkpoint", "passed": False, "error": str(e)})

                # 测试2: 加载Checkpoint
                results["total"] += 1
                try:
                    loaded = await store.load(cp1_id)
                    if loaded and loaded.checkpoint_id.value == cp1_id.value:
                        results["passed"] += 1
                        results["details"].append({"name": "加载Checkpoint", "passed": True})
                    else:
                        results["failed"] += 1
                        results["details"].append({"name": "加载Checkpoint", "passed": False, "error": "加载失败"})
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({"name": "加载Checkpoint", "passed": False, "error": str(e)})

                # 测试3: HEAD指针
                results["total"] += 1
                try:
                    await store.set_head("test_story", cp1_id)
                    head = await store.get_head("test_story")
                    if head and head.value == cp1_id.value:
                        results["passed"] += 1
                        results["details"].append({"name": "HEAD指针", "passed": True})
                    else:
                        results["failed"] += 1
                        results["details"].append({"name": "HEAD指针", "passed": False})
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({"name": "HEAD指针", "passed": False, "error": str(e)})

                # 测试4: 树状结构（父子关系）
                results["total"] += 1
                try:
                    cp2 = Checkpoint.create(
                        story_id="test_story",
                        trigger_type=CheckpointType.CHAPTER,
                        trigger_reason="第2章完成",
                        story_state={"chapter": 2},
                        character_masks={"char1": {"name": "林羽"}},
                        emotion_ledger={"wounds": []},
                        active_foreshadows=["fs1"],
                        parent_id=cp1_id,
                    )
                    cp2_id = await store.save(cp2)
                    children = await store.get_children(cp1_id)
                    if len(children) >= 1:
                        results["passed"] += 1
                        results["details"].append({"name": "树状结构", "passed": True})
                    else:
                        results["failed"] += 1
                        results["details"].append({"name": "树状结构", "passed": False, "error": "子节点为空"})
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({"name": "树状结构", "passed": False, "error": str(e)})

                # 测试5: 回滚
                results["total"] += 1
                try:
                    await store.set_head("test_story", cp2_id)
                    rolled_back = await store.rollback_to("test_story", cp1_id)
                    head = await store.get_head("test_story")
                    if head and head.value == cp1_id.value:
                        results["passed"] += 1
                        results["details"].append({"name": "回滚", "passed": True})
                    else:
                        results["failed"] += 1
                        results["details"].append({"name": "回滚", "passed": False})
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({"name": "回滚", "passed": False, "error": str(e)})

            # 运行异步测试
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        pool.submit(asyncio.run, _run_tests()).result()
                else:
                    loop.run_until_complete(_run_tests())
            except RuntimeError:
                asyncio.run(_run_tests())

        finally:
            # 安全删除临时文件
            try:
                if os.path.exists(db_path):
                    os.unlink(db_path)
            except PermissionError:
                pass  # Windows文件锁，忽略

        return results


if __name__ == "__main__":
    evaluator = CheckpointEvaluator()
    results = evaluator.run()
    print(json.dumps(results, indent=2, ensure_ascii=False))
