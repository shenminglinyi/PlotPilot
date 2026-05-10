"""语义化快照服务（Git-like，轻量指针）

核心设计：
1. 只存章节 ID 指针，不深拷贝正文
2. 快照 Bible/Foreshadow/Graph 状态
3. 支持回滚和分支
"""
import json
import uuid
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

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
        parent_snapshot_id: Optional[str] = None,
        # 引擎状态参数（用于统一 Checkpoint 系统）
        story_state: Optional[Dict[str, Any]] = None,
        character_masks: Optional[Dict[str, Any]] = None,
        emotion_ledger: Optional[Dict[str, Any]] = None,
        active_foreshadows: Optional[List[str]] = None,
        outline: Optional[str] = None,
        recent_summary: Optional[str] = None,
    ) -> str:
        """创建快照（只存指针）

        Args:
            novel_id: 小说ID
            trigger_type: 触发类型（AUTO/MANUAL）
            name: 快照名称
            description: 快照描述
            branch_name: 分支名称
            parent_snapshot_id: 父快照ID
            story_state: 故事状态（当前幕、章节数、阶段等）
            character_masks: 角色当前面具（character_id → CharacterMask）
            emotion_ledger: 情绪账本
            active_foreshadows: 活跃伏笔列表
            outline: 当前大纲
            recent_summary: 近期章节摘要

        Returns:
            快照ID
        """
        from domain.novel.value_objects.novel_id import NovelId

        # 1. 收集当前章节 ID 列表
        chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
        chapter_pointers = [c.id for c in chapters if c.status.value == "completed"]

        # 2. 序列化 Bible 状态（简化版：只记录存在性）
        bible_state = {"exists": True, "timestamp": datetime.utcnow().isoformat()}

        # 3. 序列化伏笔状态
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

        # 4. 序列化引擎状态（默认值处理）
        engine_story_state = json.dumps(story_state) if story_state is not None else "{}"
        engine_character_masks = json.dumps(character_masks) if character_masks is not None else "{}"
        engine_emotion_ledger = json.dumps(emotion_ledger) if emotion_ledger is not None else "{}"
        engine_active_foreshadows = json.dumps(active_foreshadows) if active_foreshadows is not None else "[]"
        engine_outline = outline if outline is not None else ""
        engine_recent_summary = recent_summary if recent_summary is not None else ""

        # 5. 写入快照
        snapshot_id = str(uuid.uuid4())
        sql = """
            INSERT INTO novel_snapshots (
                id, novel_id, parent_snapshot_id, branch_name,
                trigger_type, name, description,
                chapter_pointers, bible_state, foreshadow_state,
                story_state, character_masks, emotion_ledger,
                active_foreshadows, outline, recent_chapters_summary,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            engine_story_state,
            engine_character_masks,
            engine_emotion_ledger,
            engine_active_foreshadows,
            engine_outline,
            engine_recent_summary,
            datetime.utcnow().isoformat()
        ))
        self.db.get_connection().commit()

        logger.info(f"[Snapshot] 创建快照：{name} ({trigger_type})")
        return snapshot_id

    def list_snapshots(self, novel_id: str) -> List[Dict[str, Any]]:
        """列出所有快照"""
        sql = """
            SELECT id, name, trigger_type, branch_name, created_at, description
            FROM novel_snapshots
            WHERE novel_id = ?
            ORDER BY created_at DESC
        """
        rows = self.db.fetch_all(sql, (novel_id,))
        return [dict(row) for row in rows]

    def list_snapshots_with_pointers(self, novel_id: str) -> List[Dict[str, Any]]:
        """编年史 BFF：含 chapter_pointers，按创建时间升序（叙事轴从下往上可读）。"""
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
        """获取快照详情

        Args:
            snapshot_id: 快照ID

        Returns:
            快照详情字典，包含章节指针、引擎状态等信息，如果快照不存在则返回None
        """
        sql = "SELECT * FROM novel_snapshots WHERE id = ?"
        row = self.db.fetch_one(sql, (snapshot_id,))
        if not row:
            return None
        snapshot = dict(row)

        # 解析 JSON 字段（章节指针和伏笔状态）
        try:
            snapshot["chapter_pointers"] = json.loads(snapshot.get("chapter_pointers", "[]"))
            snapshot["bible_state"] = json.loads(snapshot.get("bible_state", "{}"))
            snapshot["foreshadow_state"] = json.loads(snapshot.get("foreshadow_state", "{}"))
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"快照字段解析失败：{e}")
            snapshot["chapter_pointers"] = []
            snapshot["bible_state"] = {}
            snapshot["foreshadow_state"] = {}

        # 解析引擎状态字段（如果存在）
        try:
            snapshot["story_state"] = json.loads(snapshot.get("story_state", "{}"))
            snapshot["character_masks"] = json.loads(snapshot.get("character_masks", "{}"))
            snapshot["emotion_ledger"] = json.loads(snapshot.get("emotion_ledger", "{}"))
            snapshot["active_foreshadows"] = json.loads(snapshot.get("active_foreshadows", "[]"))
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"引擎状态字段解析失败：{e}")
            snapshot["story_state"] = {}
            snapshot["character_masks"] = {}
            snapshot["emotion_ledger"] = {}
            snapshot["active_foreshadows"] = []

        # 文本字段直接返回（outline 和 recent_chapters_summary）
        snapshot["outline"] = snapshot.get("outline", "")
        snapshot["recent_chapters_summary"] = snapshot.get("recent_chapters_summary", "")

        return snapshot

    def rollback_to_snapshot(self, novel_id: str, snapshot_id: str) -> Dict[str, Any]:
        """回滚到快照：删除当前作品中不在快照 chapter_pointers 内的章节行，并恢复引擎状态。

        Args:
            novel_id: 小说ID
            snapshot_id: 快照ID

        Returns:
            {
                "deleted_chapter_ids": [...],
                "deleted_count": int,
                "has_engine_state": bool  # 快照是否包含引擎状态
            }
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
                "该快照未记录任何章节指针，为避免误删全书正文已中止回滚"
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

        # TODO: 恢复引擎状态（需要集成 MemoryOrchestrator）
        # 从快照中提取引擎状态
        # story_state = snapshot.get("story_state", {})
        # character_masks = snapshot.get("character_masks", {})
        # emotion_ledger = snapshot.get("emotion_ledger", {})
        # active_foreshadows = snapshot.get("active_foreshadows", [])
        # outline = snapshot.get("outline", "")
        # recent_summary = snapshot.get("recent_chapters_summary", "")
        #
        # 调用 MemoryOrchestrator 恢复状态：
        # await memory_orchestrator.restore_state(
        #     story_id=novel_id,
        #     story_state=story_state,
        #     character_masks=character_masks,
        #     emotion_ledger=emotion_ledger,
        #     active_foreshadows=active_foreshadows,
        #     outline=outline,
        #     recent_summary=recent_summary
        # )

        # 判断是否包含引擎状态
        has_engine_state = (
            snapshot.get("story_state") or
            snapshot.get("character_masks") or
            snapshot.get("emotion_ledger") or
            snapshot.get("active_foreshadows") or
            snapshot.get("outline") or
            snapshot.get("recent_chapters_summary")
        )

        logger.info(
            "[Snapshot] 回滚完成：%s，删除 %s 章",
            snapshot.get("name"),
            len(deleted_ids),
        )
        return {
            "deleted_chapter_ids": deleted_ids,
            "deleted_count": len(deleted_ids),
            "has_engine_state": bool(has_engine_state)
        }

    def branch_from_snapshot(
        self,
        novel_id: str,
        snapshot_id: str,
        branch_name: str,
        description: Optional[str] = None
    ) -> str:
        """从快照创建分支"""
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            raise ValueError(f"快照不存在：{snapshot_id}")

        # 创建新快照作为分支起点
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
