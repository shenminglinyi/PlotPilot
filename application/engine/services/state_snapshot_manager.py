"""状态快照管理器 - 原子状态持久化和崩溃恢复

核心设计：
1. AtomicStateTransaction: 原子事务，保证章节内容和节拍索引同时写入
2. StateSnapshotManager: 定期快照到磁盘，重启后恢复
3. 断点续写上下文恢复：确保重启后续写衔接

解决问题：
- current_beat_index 和章节内容分开保存导致数据不一致
- 重启后上下文丢失，续写不衔接
"""
import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ChapterSnapshot:
    """章节状态快照"""
    novel_id: str
    chapter_number: int
    beat_index: int
    content_preview: str  # 内容预览（前500字）
    word_count: int
    status: str  # draft, completed
    updated_at: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class NovelStateSnapshot:
    """小说状态快照"""
    novel_id: str
    current_stage: str
    current_act: int
    current_chapter_in_act: int
    current_beat_index: int
    current_auto_chapters: int
    autopilot_status: str
    last_chapter_tension: int
    created_at: float
    updated_at: float

    def to_dict(self) -> Dict:
        return asdict(self)


class AtomicStateTransaction:
    """原子状态事务

    保证章节内容和节拍索引在同一个事务中写入，
    避免崩溃后数据不一致。

    使用方式：
        with AtomicStateTransaction(db_path, novel_id) as txn:
            txn.save_chapter_content(chapter_num, content, "draft", beat_index)
            txn.commit()  # 原子写入
    """

    def __init__(self, db_path: str, novel_id: str):
        self._db_path = db_path
        self._novel_id = novel_id
        self._conn: Optional[sqlite3.Connection] = None
        self._changes: List[Tuple[str, Dict]] = []
        self._committed = False
        self._rolled_back = False

    def __enter__(self):
        # 独立物理连接（非 DatabaseConnection）：commit/rollback 会 close，避免与普通线程本地连接混用后被误关。
        self._conn = sqlite3.connect(self._db_path, timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        # BEGIN IMMEDIATE 立即获取写锁，避免死锁
        self._conn.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        elif not self._committed:
            self.rollback()
        return False  # 不抑制异常

    def save_chapter_content(
        self,
        chapter_number: int,
        content: str,
        status: str = "draft",
        beat_index: int = 0,
    ) -> None:
        """保存章节内容（延迟到 commit）"""
        self._changes.append((
            "chapter",
            {
                "chapter_number": chapter_number,
                "content": content,
                "status": status,
                "beat_index": beat_index,
            }
        ))

    def save_beat_index(self, beat_index: int) -> None:
        """保存节拍索引"""
        self._changes.append((
            "beat_index",
            {"beat_index": beat_index}
        ))

    def save_stage(self, stage: str) -> None:
        """保存当前阶段"""
        self._changes.append((
            "stage",
            {"stage": stage}
        ))

    def commit(self) -> bool:
        """原子提交所有变更"""
        if self._committed or self._rolled_back or not self._conn:
            return False

        try:
            for change_type, data in self._changes:
                if change_type == "chapter":
                    self._write_chapter(data)
                elif change_type == "beat_index":
                    self._write_beat_index(data)
                elif change_type == "stage":
                    self._write_stage(data)

            self._conn.commit()
            self._committed = True
            logger.debug(
                f"[AtomicTransaction] 已提交 {len(self._changes)} 个变更 "
                f"for novel={self._novel_id}"
            )
            return True

        except Exception as e:
            logger.error(f"[AtomicTransaction] 提交失败: {e}")
            try:
                self._conn.rollback()
            except Exception:
                pass
            self._rolled_back = True
            return False

        finally:
            self._close_connection()

    def rollback(self) -> None:
        """回滚事务"""
        if self._conn and not self._committed and not self._rolled_back:
            try:
                self._conn.rollback()
            except Exception:
                pass
            self._rolled_back = True
        self._close_connection()
        self._changes.clear()

    def _close_connection(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _write_chapter(self, data: Dict) -> None:
        """写入章节"""
        self._conn.execute("""
            INSERT INTO chapters (novel_id, number, content, status, word_count, updated_at)
            VALUES (?, ?, ?, ?, LENGTH(?), CURRENT_TIMESTAMP)
            ON CONFLICT(novel_id, number) DO UPDATE SET
                content = excluded.content,
                status = excluded.status,
                word_count = excluded.word_count,
                updated_at = CURRENT_TIMESTAMP
        """, (
            self._novel_id,
            data["chapter_number"],
            data["content"],
            data["status"],
            data["content"],
        ))

    def _write_beat_index(self, data: Dict) -> None:
        """写入节拍索引"""
        self._conn.execute("""
            UPDATE novels SET current_beat_index = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (data["beat_index"], self._novel_id))

    def _write_stage(self, data: Dict) -> None:
        """写入阶段"""
        self._conn.execute("""
            UPDATE novels SET current_stage = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (data["stage"], self._novel_id))


class StateSnapshotManager:
    """状态快照管理器

    功能：
    1. 定期快照共享状态到磁盘
    2. 启动时从磁盘恢复
    3. 崩溃恢复支持
    """

    def __init__(self, db_path: str, snapshot_dir: str = None):
        self._db_path = db_path
        self._snapshot_dir = Path(snapshot_dir or "data/snapshots")
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def begin_transaction(self, novel_id: str) -> AtomicStateTransaction:
        """开始原子事务"""
        return AtomicStateTransaction(self._db_path, novel_id)

    def save_snapshot(self, novel_id: str) -> bool:
        """保存完整快照到磁盘"""
        try:
            snapshot = self._collect_snapshot(novel_id)
            if not snapshot:
                return False

            snapshot_path = self._snapshot_dir / f"{novel_id}.json"
            temp_path = snapshot_path.with_suffix(".tmp")

            # 原子写入：先写临时文件，再重命名
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)

            os.replace(temp_path, snapshot_path)
            logger.debug(f"[StateSnapshot] 已保存快照: {novel_id}")
            return True

        except Exception as e:
            logger.error(f"[StateSnapshot] 保存快照失败: {e}")
            return False

    def restore_snapshot(self, novel_id: str) -> Optional[Dict]:
        """从磁盘恢复快照"""
        snapshot_path = self._snapshot_dir / f"{novel_id}.json"

        if not snapshot_path.exists():
            return None

        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[StateSnapshot] 恢复快照失败: {e}")
            return None

    def sync_shared_state_to_disk(
        self,
        shared_state: Dict,
        novel_id: str
    ) -> bool:
        """同步共享状态到磁盘"""
        with self._lock:
            snapshot_path = self._snapshot_dir / f"{novel_id}_shared.json"
            temp_path = snapshot_path.with_suffix(".tmp")

            try:
                snapshot = {
                    "novel_id": novel_id,
                    "state": shared_state,
                    "timestamp": time.time(),
                }
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, ensure_ascii=False)
                os.replace(temp_path, snapshot_path)
                return True
            except Exception as e:
                logger.warning(f"[StateSnapshot] 同步共享状态失败: {e}")
                return False

    def restore_shared_state_from_disk(self, novel_id: str) -> Optional[Dict]:
        """从磁盘恢复共享状态"""
        snapshot_path = self._snapshot_dir / f"{novel_id}_shared.json"

        if not snapshot_path.exists():
            return None

        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 检查快照是否过期（超过 1 小时）
            timestamp = data.get("timestamp", 0)
            if time.time() - timestamp > 3600:
                logger.info(f"[StateSnapshot] 快照已过期，忽略: {novel_id}")
                return None

            return data.get("state")
        except Exception as e:
            logger.warning(f"[StateSnapshot] 恢复共享状态失败: {e}")
            return None

    def _collect_snapshot(self, novel_id: str) -> Optional[Dict]:
        """收集快照数据"""
        try:
            from infrastructure.persistence.database.connection import get_database

            db = get_database(self._db_path)

            novel_row = db.fetch_one("SELECT * FROM novels WHERE id = ?", (novel_id,))

            if not novel_row:
                return None

            current_chapter = novel_row["current_auto_chapters"] or 0
            chapter_rows = db.fetch_all(
                """SELECT number, status, word_count, current_beat_index
                   FROM chapters
                   WHERE novel_id = ? AND number >= ?
                   ORDER BY number""",
                (novel_id, max(0, current_chapter - 5)),
            )

            return {
                "novel": dict(novel_row),
                "recent_chapters": [dict(r) for r in chapter_rows],
                "timestamp": time.time(),
            }

        except Exception as e:
            logger.error(f"[StateSnapshot] 收集快照失败: {e}")
            return None

    def list_snapshots(self) -> List[str]:
        """列出所有快照"""
        snapshots = []
        for path in self._snapshot_dir.glob("*.json"):
            if not path.name.endswith("_shared.json"):
                snapshots.append(path.stem)
        return snapshots

    def delete_snapshot(self, novel_id: str) -> bool:
        """删除快照"""
        deleted = False
        for suffix in ["", "_shared"]:
            path = self._snapshot_dir / f"{novel_id}{suffix}.json"
            if path.exists():
                try:
                    path.unlink()
                    deleted = True
                except Exception:
                    pass
        return deleted

    def cleanup_old_snapshots(self, max_age_hours: float = 24.0) -> int:
        """清理过期快照"""
        cleaned = 0
        threshold = time.time() - max_age_hours * 3600

        for path in self._snapshot_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                timestamp = data.get("timestamp", 0)
                if timestamp < threshold:
                    path.unlink()
                    cleaned += 1
            except Exception:
                pass

        if cleaned > 0:
            logger.info(f"[StateSnapshot] 清理了 {cleaned} 个过期快照")

        return cleaned


class ChapterAftermathRecovery:
    """章节后续恢复

    处理崩溃后的数据恢复，确保续写衔接。
    """

    def __init__(self, db_path: str, snapshot_manager: StateSnapshotManager):
        self._db_path = db_path
        self._snapshot_manager = snapshot_manager

    def recover_incomplete_chapters(self, novel_id: str) -> List[Dict]:
        """恢复未完成的章节

        检查 DB 中的 draft 章节，与快照对比，找出需要恢复的章节。

        Returns:
            需要恢复的章节列表
        """
        recovered = []

        try:
            from infrastructure.persistence.database.connection import get_database

            snapshot = self._snapshot_manager.restore_snapshot(novel_id)
            if not snapshot:
                return recovered

            db = get_database(self._db_path)
            draft_rows = db.fetch_all(
                """SELECT id, number, content, status, word_count
                   FROM chapters
                   WHERE novel_id = ? AND status = 'draft'
                   ORDER BY number""",
                (novel_id,),
            )

            for row in draft_rows:
                snapshot_chapters = snapshot.get("recent_chapters", [])
                matched = next(
                    (sc for sc in snapshot_chapters if sc["number"] == row["number"]),
                    None
                )

                if matched:
                    db_word_count = row["word_count"] or 0
                    snapshot_word_count = matched.get("word_count", 0)

                    if snapshot_word_count > db_word_count:
                        recovered.append({
                            "chapter_number": row["number"],
                            "reason": "snapshot_newer",
                            "db_word_count": db_word_count,
                            "snapshot_word_count": snapshot_word_count,
                        })

        except Exception as e:
            logger.error(f"[AftermathRecovery] 恢复章节失败: {e}")

        return recovered

    def get_continuation_context(
        self,
        novel_id: str,
        chapter_number: int
    ) -> Optional[str]:
        """获取续写上下文

        从共享状态快照中恢复已生成的内容，用于续写衔接。

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号

        Returns:
            已生成的内容（用于续写上下文）
        """
        # 1. 尝试从共享状态恢复
        shared_state = self._snapshot_manager.restore_shared_state_from_disk(novel_id)
        if shared_state:
            # 检查是否有缓存的内容
            cached_content = shared_state.get("_cached_chapter_content")
            if cached_content:
                return cached_content

        # 2. 从 DB 读取
        try:
            from infrastructure.persistence.database.connection import get_database

            row = get_database(self._db_path).fetch_one(
                "SELECT content FROM chapters WHERE novel_id = ? AND number = ?",
                (novel_id, chapter_number),
            )

            if row and row["content"]:
                return row["content"]

        except Exception as e:
            logger.warning(f"[AftermathRecovery] 读取章节内容失败: {e}")

        return None
