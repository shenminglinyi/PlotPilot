"""语义化快照服务（Git-like，轻量指针）

核心设计�?
1. 只存章节 ID 指针，不深拷贝正�?
2. 快照 Bible/Foreshadow/Graph 状�?
3. 支持回滚和分�?
"""
import json
import uuid
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class SnapshotService:
    """快照服务"""

    def __init__(self, db, chapter_repository, foreshadowing_repo=None):
        self.db = db
        self.chapter_repository = chapter_repository
        self.foreshadowing_repo = foreshadowing_repo

    def create_snapshot(
        self,
        novel_id: str,
        trigger_type: str,  # AUTO / MANUAL
        name: str,
        description: Optional[str] = None,
        branch_name: str = "main",
        parent_snapshot_id: Optional[str] = None
    ) -> str:
        """创建快照（只存指针）"""
        from domain.novel.value_objects.novel_id import NovelId

        # 1. 收集当前章节 ID 列表
        chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
        chapter_pointers = [c.id for c in chapters if c.status.value == "completed"]

        # 2. 序列�?Bible 状态（简化版：只记录存在性）
        bible_state = {"exists": True, "timestamp": datetime.now(timezone.utc).isoformat()}

        # 3. 序列化伏笔状�?
        foreshadow_state = {}
        if self.foreshadowing_repo:
            try:
                registry = self.foreshadowing_repo.get_by_novel_id(NovelId(novel_id))
                if registry:
                    all_fs = registry.foreshadowings
                    from domain.novel.value_objects.foreshadowing import ForeshadowingStatus
                    foreshadow_state = {
                        "count": len(all_fs),
                        "pending": len([f for f in all_fs if f.status == ForeshadowingStatus.PLANTED]),
                    }
            except Exception as e:
                logger.warning(f"伏笔状态序列化失败：{e}")

        # 4. 写入快照
        snapshot_id = str(uuid.uuid4())
        sql = """
            INSERT INTO novel_snapshots (
                id, novel_id, parent_snapshot_id, branch_name,
                trigger_type, name, description,
                chapter_pointers, bible_state, foreshadow_state,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.db.execute(sql, (
            snapshot_id,
            novel_id,
            parent_snapshot_id,
            branch_name,
            trigger_type,
            name,
            description,
            json.dumps(chapter_pointers),
            json.dumps(bible_state),
            json.dumps(foreshadow_state),
            datetime.now(timezone.utc).isoformat()
        ))
        self.db.get_connection().commit()

        logger.info(f"[Snapshot] 创建快照：{name} ({trigger_type})")
        return snapshot_id

    def list_snapshots(self, novel_id: str) -> List[Dict[str, Any]]:
        """列出所有快�?""
        sql = """
            SELECT id, name, trigger_type, branch_name, created_at, description
            FROM novel_snapshots
            WHERE novel_id = ?
            ORDER BY created_at DESC
        """
        rows = self.db.fetch_all(sql, (novel_id,))
        return [dict(row) for row in rows]

    def list_snapshots_with_pointers(self, novel_id: str) -> List[Dict[str, Any]]:
        """编年�?BFF：含 chapter_pointers，按创建时间升序（叙事轴从下往上可读）�?""
        sql = """
            SELECT id, name, trigger_type, branch_name, created_at, description, chapter_pointers
            FROM novel_snapshots
            WHERE novel_id = ?
            ORDER BY created_at ASC
        """
        rows = self.db.fetch_all(sql, (novel_id,))
        out: List[Dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            raw = d.get("chapter_pointers")
            try:
                d["chapter_pointers"] = json.loads(raw) if raw else []
            except (TypeError, json.JSONDecodeError):
                d["chapter_pointers"] = []
            out.append(d)
        return out

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """获取快照详情"""
        sql = "SELECT * FROM novel_snapshots WHERE id = ?"
        row = self.db.fetch_one(sql, (snapshot_id,))
        if not row:
            return None
        snapshot = dict(row)
        # 解析 JSON 字段
        snapshot["chapter_pointers"] = json.loads(snapshot["chapter_pointers"])
        snapshot["bible_state"] = json.loads(snapshot["bible_state"])
        snapshot["foreshadow_state"] = json.loads(snapshot["foreshadow_state"])
        return snapshot

    def rollback_to_snapshot(self, novel_id: str, snapshot_id: str) -> Dict[str, Any]:
        """回滚到快照：删除当前作品中不在快�?chapter_pointers 内的章节行�?

        Returns:
            { "deleted_chapter_ids": [...], "deleted_count": int }
        """
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            raise ValueError(f"快照不存在：{snapshot_id}")

        if snapshot.get("novel_id") != novel_id:
            raise ValueError("快照不属于该作品")

        from domain.novel.value_objects.novel_id import NovelId
        from domain.novel.value_objects.chapter_id import ChapterId

        raw_ptrs = snapshot.get("chapter_pointers") or []
        valid_chapter_ids = {str(x) for x in raw_ptrs}

        all_chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))

        if not valid_chapter_ids and all_chapters:
            raise ValueError(
                "该快照未记录任何章节指针，为避免误删全书正文已中止回�?
            )

        deleted_ids: List[str] = []
        for chapter in all_chapters:
            cid = str(chapter.id)
            if cid not in valid_chapter_ids:
                logger.warning(
                    "[Snapshot] 回滚删除章节 id=%s number=%s",
                    cid,
                    getattr(chapter, "number", "?"),
                )
                self.chapter_repository.delete(ChapterId(cid))
                deleted_ids.append(cid)

        logger.info(
            "[Snapshot] 回滚完成�?s，删�?%s �?,
            snapshot.get("name"),
            len(deleted_ids),
        )
        return {"deleted_chapter_ids": deleted_ids, "deleted_count": len(deleted_ids)}

    def branch_from_snapshot(
        self,
        novel_id: str,
        snapshot_id: str,
        branch_name: str,
        description: Optional[str] = None
    ) -> str:
        """从快照创建分�?""
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            raise ValueError(f"快照不存在：{snapshot_id}")

        # 创建新快照作为分支起�?
        new_snapshot_id = self.create_snapshot(
            novel_id=novel_id,
            trigger_type="MANUAL",
            name=f"[分支] {branch_name}",
            description=description,
            branch_name=branch_name,
            parent_snapshot_id=snapshot_id
        )

        logger.info(f"[Snapshot] 创建分支：{branch_name} from {snapshot['name']}")
        return new_snapshot_id
