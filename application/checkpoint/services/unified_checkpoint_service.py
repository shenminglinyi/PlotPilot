"""统一 Checkpoint 服务 — 故事世界线 git 模型

合并 SnapshotService 和 CheckpointManager 的职责，实现：
- 创建/查询/列出 checkpoint（存章节指针 + 引擎状态）
- 分支管理（create_branch / list_branches）
- checkout（非破坏性恢复，自动 stash）
- hard_reset（破坏性回滚）
- 引擎状态恢复（写共享内存）
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from application.world.services.bible_snapshot_state import collect_bible_snapshot_state

logger = logging.getLogger(__name__)

# DDL moved to infrastructure/persistence/database/schema.sql (novel_checkpoints + novel_branches)
_DDL = ""  # kept for backward compatibility; schema.sql is the authoritative DDL


class UnifiedCheckpointService:
    """统一 Checkpoint 服务 — 合并 SnapshotService 和 CheckpointManager 的职责"""

    def __init__(self, db, chapter_repository, foreshadowing_repo=None, shared_memory=None):
        """
        Args:
            db: DatabaseConnection 实例
            chapter_repository: 章节仓储
            foreshadowing_repo: 伏笔仓储（可为 None）
            shared_memory: SharedStateRepository 实例（可为 None，运行时延迟获取）
        """
        self.db = db
        self.chapter_repository = chapter_repository
        self.foreshadowing_repo = foreshadowing_repo
        self._shared_memory = shared_memory
        self._tables_ensured = False

    # ==================== 内部工具 ====================

    def _ensure_tables(self) -> None:
        """DDL 已移入 schema.sql，由数据库初始化时统一执行；此方法保留供兼容调用。"""
        self._tables_ensured = True

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _json_loads_safe(self, raw: Any, default: Any) -> Any:
        if raw is None:
            return default
        if isinstance(raw, (dict, list)):
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default

    def _world_slices_by_chapter(self, novel_id: str, branch_id: str = "main") -> Dict[int, Dict[str, Any]]:
        try:
            rows = self.db.fetch_all(
                """
                SELECT chapter_number, ending_state_json, delta_actions_json, conflicts_json
                FROM chapter_evolution_snapshots
                WHERE novel_id = ? AND branch_id = ? AND status != 'stale'
                ORDER BY chapter_number ASC
                """,
                (novel_id, branch_id),
            )
        except Exception:
            return {}

        out: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            ch = int(row.get("chapter_number") or 0)
            ending = self._json_loads_safe(row.get("ending_state_json"), {})
            scene = ending.get("scene") if isinstance(ending, dict) else {}
            characters = ending.get("characters") if isinstance(ending, dict) else {}
            items = ending.get("items") if isinstance(ending, dict) else {}
            actions = self._json_loads_safe(row.get("delta_actions_json"), [])
            conflicts = self._json_loads_safe(row.get("conflicts_json"), [])
            char_list = []
            if isinstance(characters, dict):
                for cid, data in list(characters.items())[:8]:
                    data = data if isinstance(data, dict) else {}
                    char_list.append(
                        {
                            "id": cid,
                            "name": data.get("name") or cid,
                            "status": data.get("status") or "alive",
                            "location": data.get("location") or "",
                        }
                    )
            item_list = []
            if isinstance(items, dict):
                for item_id, data in list(items.items())[:8]:
                    data = data if isinstance(data, dict) else {}
                    item_list.append(
                        {
                            "id": item_id,
                            "name": data.get("name") or item_id,
                            "holder": data.get("holder") or data.get("holder_character_id") or "",
                        }
                    )
            out[ch] = {
                "chapter_number": ch,
                "time_anchor": (scene or {}).get("time_anchor", "") if isinstance(scene, dict) else "",
                "location": (scene or {}).get("location", "") if isinstance(scene, dict) else "",
                "emotional_residue": (scene or {}).get("emotional_residue", "") if isinstance(scene, dict) else "",
                "characters": char_list,
                "items": item_list,
                "actions_count": len(actions) if isinstance(actions, list) else 0,
                "conflicts_count": len(conflicts) if isinstance(conflicts, list) else 0,
            }
        return out

    def _get_or_create_branch(self, novel_id: str, branch_name: str, head_id: str) -> None:
        """获取或创建分支，并更新 head_id。"""
        try:
            row = self.db.fetch_one(
                "SELECT id FROM novel_branches WHERE novel_id = ? AND name = ?",
                (novel_id, branch_name),
            )
            if row:
                self.db.execute(
                    "UPDATE novel_branches SET head_id = ? WHERE novel_id = ? AND name = ?",
                    (head_id, novel_id, branch_name),
                )
            else:
                branch_id = str(uuid.uuid4())
                is_default = 1 if branch_name == "main" else 0
                self.db.execute(
                    """INSERT INTO novel_branches (id, novel_id, name, head_id, is_default, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (branch_id, novel_id, branch_name, head_id, is_default, self._now_iso()),
                )
            self.db.get_connection().commit()
        except Exception as e:
            logger.error("[UnifiedCheckpoint] 分支更新失败: %s", e)

    def _get_branch_head(self, novel_id: str, branch_name: str) -> Optional[str]:
        try:
            row = self.db.fetch_one(
                "SELECT head_id FROM novel_branches WHERE novel_id = ? AND name = ?",
                (novel_id, branch_name),
            )
            return row.get("head_id") if row else None
        except Exception:
            return None

    # ==================== 核心方法 ====================

    def create_checkpoint(
        self,
        novel_id: str,
        trigger_type: str,
        name: str,
        description: Optional[str] = None,
        branch_name: str = "main",
        parent_id: Optional[str] = None,
        story_state: Optional[Dict[str, Any]] = None,
        character_masks: Optional[Dict[str, Any]] = None,
        emotion_ledger: Optional[Dict[str, Any]] = None,
        active_foreshadows: Optional[List[str]] = None,
        outline: Optional[str] = None,
        recent_summary: Optional[str] = None,
    ) -> str:
        """创建统一 checkpoint，写入 novel_checkpoints 表。

        Args:
            novel_id: 小说 ID
            trigger_type: 触发类型（CHAPTER/ACT/MILESTONE/MANUAL/STASH/PRE_RESET/AUTO）
            name: checkpoint 名称
            description: 描述
            branch_name: 分支名（默认 main）
            parent_id: 父 checkpoint ID
            story_state: 故事状态（幕/阶段等）
            character_masks: 角色面具
            emotion_ledger: 情绪账本
            active_foreshadows: 活跃伏笔列表
            outline: 当前大纲
            recent_summary: 近期摘要

        Returns:
            checkpoint ID（str）
        """
        self._ensure_tables()

        from domain.novel.value_objects.novel_id import NovelId

        if parent_id is None:
            parent_id = self._get_branch_head(novel_id, branch_name)

        # 1. 采集章节指针（已完成章节）
        chapter_pointers: List[str] = []
        try:
            chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
            chapter_pointers = [str(c.id) for c in chapters if c.status.value == "completed"]
        except Exception as e:
            logger.warning("[UnifiedCheckpoint] 章节指针采集失败: %s", e)

        # 2. Bible 结构化状态；只采集 Bible 元数据和结构化条目，不深拷贝章节正文。
        bible_state: Dict[str, Any] = collect_bible_snapshot_state(self.db, novel_id)

        # 3. foreshadow_state
        foreshadow_state: Dict[str, Any] = {}
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
                logger.warning("[UnifiedCheckpoint] 伏笔状态采集失败: %s", e)

        # 4. 序列化引擎状态
        checkpoint_id = str(uuid.uuid4())
        sql = """
            INSERT INTO novel_checkpoints (
                id, novel_id, parent_id, branch_name,
                trigger_type, name, description,
                chapter_pointers, bible_state, foreshadow_state,
                story_state, character_masks, emotion_ledger,
                active_foreshadows, outline, recent_summary,
                is_active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """
        try:
            self.db.execute(sql, (
                checkpoint_id,
                novel_id,
                parent_id,
                branch_name,
                trigger_type,
                name,
                description,
                json.dumps(chapter_pointers, ensure_ascii=False),
                json.dumps(bible_state, ensure_ascii=False),
                json.dumps(foreshadow_state, ensure_ascii=False),
                json.dumps(story_state, ensure_ascii=False) if story_state is not None else "{}",
                json.dumps(character_masks, ensure_ascii=False) if character_masks is not None else "{}",
                json.dumps(emotion_ledger, ensure_ascii=False) if emotion_ledger is not None else "{}",
                json.dumps(active_foreshadows, ensure_ascii=False) if active_foreshadows is not None else "[]",
                outline if outline is not None else "",
                recent_summary if recent_summary is not None else "",
                self._now_iso(),
            ))
            self.db.get_connection().commit()
        except Exception as e:
            logger.error("[UnifiedCheckpoint] checkpoint 写入失败: %s", e)
            raise ValueError(f"checkpoint 写入失败: {e}") from e

        # 5. 更新分支 head
        self._get_or_create_branch(novel_id, branch_name, checkpoint_id)

        logger.info("[UnifiedCheckpoint] 创建 checkpoint: %s (%s) novel=%s", name, trigger_type, novel_id)
        return checkpoint_id

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """读取单个 checkpoint（解析所有 JSON 字段）。

        Args:
            checkpoint_id: checkpoint ID

        Returns:
            checkpoint 字典，不存在则返回 None
        """
        self._ensure_tables()
        try:
            row = self.db.fetch_one(
                "SELECT * FROM novel_checkpoints WHERE id = ? AND is_active = 1",
                (checkpoint_id,),
            )
            if not row:
                return None
            return self._parse_checkpoint_row(dict(row))
        except Exception as e:
            logger.error("[UnifiedCheckpoint] get_checkpoint 失败: %s", e)
            return None

    def list_checkpoints(self, novel_id: str) -> List[Dict[str, Any]]:
        """列出小说所有 checkpoint（按 created_at 倒序）。

        Args:
            novel_id: 小说 ID

        Returns:
            checkpoint 列表
        """
        self._ensure_tables()
        try:
            slices = self._world_slices_by_chapter(novel_id)
            rows = self.db.fetch_all(
                """SELECT id, novel_id, parent_id, branch_name, trigger_type, name,
                          description, anchor_chapter, is_active, created_at
                   FROM novel_checkpoints
                   WHERE novel_id = ? AND is_active = 1
                   ORDER BY created_at DESC""",
                (novel_id,),
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("[UnifiedCheckpoint] list_checkpoints 失败: %s", e)
            return []

    def get_checkpoint_graph(self, novel_id: str) -> Dict[str, Any]:
        """获取 checkpoint 有向无环图（用于世界线可视化）。

        Returns:
            {
              "nodes": [...],
              "edges": [...],
              "branches": [...],
              "head_id": str | None
            }
        """
        self._ensure_tables()
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        branches: List[Dict[str, Any]] = []
        head_id: Optional[str] = None

        try:
            rows = self.db.fetch_all(
                """SELECT id, name, trigger_type, branch_name, created_at, parent_id, anchor_chapter, story_state
                   FROM novel_checkpoints
                   WHERE novel_id = ? AND is_active = 1
                   ORDER BY created_at ASC""",
                (novel_id,),
            )
            for row in rows:
                d = dict(row)
                anchor = d.get("anchor_chapter")
                world_slice = slices.get(int(anchor or 0), {}) if anchor is not None else {}
                nodes.append({
                    "id": d["id"],
                    "name": d["name"],
                    "trigger_type": d["trigger_type"],
                    "branch_name": d["branch_name"],
                    "created_at": d["created_at"],
                    "anchor_chapter": anchor,
                    "world_slice": world_slice,
                    "rollback_slice": {
                        "to_checkpoint_id": d["id"],
                        "to_chapter": anchor,
                        "branch_name": d["branch_name"],
                    },
                })
                if d.get("parent_id"):
                    edges.append({"from": d["parent_id"], "to": d["id"]})
                story_state = self._json_loads_safe(d.get("story_state"), {})
                merge_from = story_state.get("merge_from_checkpoint_id") if isinstance(story_state, dict) else None
                if merge_from:
                    edges.append({"from": merge_from, "to": d["id"], "kind": "merge"})

            branch_rows = self.db.fetch_all(
                "SELECT id, name, head_id, is_default, storyline_id FROM novel_branches WHERE novel_id = ?",
                (novel_id,),
            )
            for br in branch_rows:
                bd = dict(br)
                branches.append(bd)
                if bd.get("is_default") == 1 or bd.get("name") == "main":
                    head_id = bd.get("head_id")
        except Exception as e:
            logger.error("[UnifiedCheckpoint] get_checkpoint_graph 失败: %s", e)

        return {"nodes": nodes, "edges": edges, "branches": branches, "head_id": head_id}

    def create_branch(
        self,
        novel_id: str,
        name: str,
        from_checkpoint_id: str,
        storyline_id: Optional[str] = None,
    ) -> str:
        """创建新分支。

        Args:
            novel_id: 小说 ID
            name: 分支名称
            from_checkpoint_id: 起点 checkpoint ID
            storyline_id: 关联故事线 ID（可选）

        Returns:
            branch ID
        """
        self._ensure_tables()
        branch_id = str(uuid.uuid4())
        try:
            self.db.execute(
                """INSERT INTO novel_branches (id, novel_id, name, head_id, is_default, storyline_id, created_at)
                   VALUES (?, ?, ?, ?, 0, ?, ?)""",
                (branch_id, novel_id, name, from_checkpoint_id, storyline_id, self._now_iso()),
            )
            self.db.get_connection().commit()
            logger.info("[UnifiedCheckpoint] 创建分支 %s novel=%s", name, novel_id)
        except Exception as e:
            logger.error("[UnifiedCheckpoint] create_branch 失败: %s", e)
            raise ValueError(f"create_branch 失败: {e}") from e
        return branch_id

    def merge_branch(
        self,
        novel_id: str,
        source_branch_id: str,
        target_branch_name: str = "main",
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> str:
        """将一个分支以 merge checkpoint 形式汇入目标分支。"""
        self._ensure_tables()
        source = self.db.fetch_one(
            "SELECT * FROM novel_branches WHERE id = ? AND novel_id = ?",
            (source_branch_id, novel_id),
        )
        if not source:
            raise ValueError("source_branch_not_found")
        source_head = source.get("head_id")
        target_head = self._get_branch_head(novel_id, target_branch_name)
        if not source_head:
            raise ValueError("source_branch_has_no_head")
        checkpoint_id = self.create_checkpoint(
            novel_id=novel_id,
            trigger_type="MERGE",
            name=name or f"{source.get('name') or '分支'} 汇入 {target_branch_name}",
            description=description or "分支汇流 checkpoint",
            branch_name=target_branch_name,
            parent_id=target_head,
            story_state={
                "merge_from_branch_id": source_branch_id,
                "merge_from_branch_name": source.get("name"),
                "merge_from_checkpoint_id": source_head,
                "merge_target_branch_name": target_branch_name,
            },
        )
        return checkpoint_id

    def list_branches(self, novel_id: str) -> List[Dict[str, Any]]:
        """列出小说所有分支。

        Args:
            novel_id: 小说 ID

        Returns:
            分支列表
        """
        self._ensure_tables()
        try:
            rows = self.db.fetch_all(
                "SELECT * FROM novel_branches WHERE novel_id = ? ORDER BY created_at ASC",
                (novel_id,),
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("[UnifiedCheckpoint] list_branches 失败: %s", e)
            return []

    def checkout(self, novel_id: str, checkpoint_id: str) -> Dict[str, Any]:
        """非破坏性 checkout：先 stash 当前状态，再恢复到指定 checkpoint。

        Args:
            novel_id: 小说 ID
            checkpoint_id: 目标 checkpoint ID

        Returns:
            {"stash_id": str, "restored_chapters": int, "deleted_chapters": int}
        """
        self._ensure_tables()

        # 1. stash 当前状态
        stash_id = self.create_checkpoint(
            novel_id=novel_id,
            trigger_type="STASH",
            name="checkout 前自动存档",
            description=f"checkout 到 {checkpoint_id} 前的自动存档",
            branch_name="main",
        )

        # 2. 加载目标 checkpoint
        cp = self.get_checkpoint(checkpoint_id)
        if not cp:
            raise ValueError(f"checkpoint 不存在: {checkpoint_id}")
        if cp.get("novel_id") != novel_id:
            raise ValueError("checkpoint 不属于该作品")

        # 3. 恢复章节
        deleted_count, restored_count = self._restore_chapters(novel_id, cp)

        # 4. 恢复引擎状态（非致命）
        self._restore_engine_state(novel_id, cp)

        # 5. 更新 main 分支 head
        self._get_or_create_branch(novel_id, "main", checkpoint_id)

        logger.info(
            "[UnifiedCheckpoint] checkout 完成: novel=%s cp=%s deleted=%d restored=%d",
            novel_id, checkpoint_id, deleted_count, restored_count,
        )
        return {
            "stash_id": stash_id,
            "restored_chapters": restored_count,
            "deleted_chapters": deleted_count,
        }

    def hard_reset(self, novel_id: str, checkpoint_id: str) -> Dict[str, Any]:
        """破坏性回滚到 checkpoint（先 stash）。

        与 checkout 的区别：stash trigger_type 为 PRE_RESET。

        Args:
            novel_id: 小说 ID
            checkpoint_id: 目标 checkpoint ID

        Returns:
            {"stash_id": str, "restored_chapters": int, "deleted_chapters": int}
        """
        self._ensure_tables()

        stash_id = self.create_checkpoint(
            novel_id=novel_id,
            trigger_type="PRE_RESET",
            name="hard_reset 前自动存档",
            description=f"hard_reset 到 {checkpoint_id} 前的自动存档",
            branch_name="main",
        )

        cp = self.get_checkpoint(checkpoint_id)
        if not cp:
            raise ValueError(f"checkpoint 不存在: {checkpoint_id}")
        if cp.get("novel_id") != novel_id:
            raise ValueError("checkpoint 不属于该作品")

        deleted_count, restored_count = self._restore_chapters(novel_id, cp)
        self._restore_engine_state(novel_id, cp)
        self._get_or_create_branch(novel_id, "main", checkpoint_id)

        logger.info(
            "[UnifiedCheckpoint] hard_reset 完成: novel=%s cp=%s deleted=%d",
            novel_id, checkpoint_id, deleted_count,
        )
        return {
            "stash_id": stash_id,
            "restored_chapters": restored_count,
            "deleted_chapters": deleted_count,
        }

    def get_branch_by_storyline(self, novel_id: str, storyline_id: str) -> Optional[Dict[str, Any]]:
        """查找与指定故事线绑定的分支。

        Args:
            novel_id: 小说 ID
            storyline_id: 故事线 ID

        Returns:
            分支 dict 或 None
        """
        self._ensure_tables()
        try:
            row = self.db.fetch_one(
                "SELECT * FROM novel_branches WHERE novel_id = ? AND storyline_id = ?",
                (novel_id, storyline_id),
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error("[UnifiedCheckpoint] get_branch_by_storyline 失败: %s", e)
            return None

    def update_branch(
        self,
        branch_id: str,
        name: Optional[str] = None,
        storyline_id: Optional[str] = None,
    ) -> None:
        """更新分支元数据（名称 / 故事线绑定）。

        Args:
            branch_id: 分支 ID
            name: 新名称（None 则不更新）
            storyline_id: 绑定的故事线 ID（None 则不更新；空字符串解绑）
        """
        self._ensure_tables()
        if name is None and storyline_id is None:
            return
        try:
            if name is not None and storyline_id is not None:
                self.db.execute(
                    "UPDATE novel_branches SET name = ?, storyline_id = ? WHERE id = ?",
                    (name, storyline_id or None, branch_id),
                )
            elif name is not None:
                self.db.execute(
                    "UPDATE novel_branches SET name = ? WHERE id = ?",
                    (name, branch_id),
                )
            else:
                self.db.execute(
                    "UPDATE novel_branches SET storyline_id = ? WHERE id = ?",
                    (storyline_id or None, branch_id),
                )
            self.db.get_connection().commit()
            logger.info("[UnifiedCheckpoint] 更新分支 id=%s", branch_id)
        except Exception as e:
            logger.error("[UnifiedCheckpoint] update_branch 失败: %s", e)

    def delete_checkpoint(self, checkpoint_id: str) -> None:
        """软删除 checkpoint（is_active=0）。

        Args:
            checkpoint_id: checkpoint ID
        """
        self._ensure_tables()
        try:
            self.db.execute(
                "UPDATE novel_checkpoints SET is_active = 0 WHERE id = ?",
                (checkpoint_id,),
            )
            self.db.get_connection().commit()
            logger.info("[UnifiedCheckpoint] 软删除 checkpoint: %s", checkpoint_id)
        except Exception as e:
            logger.error("[UnifiedCheckpoint] delete_checkpoint 失败: %s", e)

    # ==================== 私有辅助 ====================

    def _parse_checkpoint_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """解析 checkpoint 行的所有 JSON 字段。"""
        json_fields = {
            "chapter_pointers": [],
            "bible_state": {},
            "foreshadow_state": {},
            "story_state": {},
            "character_masks": {},
            "emotion_ledger": {},
            "active_foreshadows": [],
        }
        for field, default in json_fields.items():
            row[field] = self._json_loads_safe(row.get(field), default)
        row.setdefault("outline", "")
        row.setdefault("recent_summary", "")
        return row

    def _restore_chapters(self, novel_id: str, checkpoint: Dict[str, Any]):
        """删除不在 checkpoint.chapter_pointers 内的章节。

        Returns:
            (deleted_count, kept_count) 元组
        """
        from domain.novel.value_objects.novel_id import NovelId
        from domain.novel.value_objects.chapter_id import ChapterId

        raw_ptrs = checkpoint.get("chapter_pointers") or []
        valid_ids = {str(x) for x in raw_ptrs}

        try:
            all_chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
        except Exception as e:
            logger.error("[UnifiedCheckpoint] 获取章节列表失败: %s", e)
            return 0, 0

        deleted = 0
        kept = len(valid_ids)
        for chapter in all_chapters:
            cid = str(chapter.id)
            if cid not in valid_ids:
                try:
                    self.chapter_repository.delete(ChapterId(cid))
                    deleted += 1
                    logger.warning(
                        "[UnifiedCheckpoint] 回滚删除章节 id=%s number=%s",
                        cid,
                        getattr(chapter, "number", "?"),
                    )
                except Exception as e:
                    logger.error("[UnifiedCheckpoint] 删除章节失败 id=%s: %s", cid, e)

        return deleted, kept

    def _restore_engine_state(self, novel_id: str, checkpoint: Dict[str, Any]) -> None:
        """从 checkpoint 恢复引擎共享内存状态（非致命，失败只打 warning）。"""
        try:
            from application.engine.services.query_service import get_query_service
            shared = get_query_service()._shared
            story_state = checkpoint.get("story_state") or {}

            if "storylines" in story_state:
                try:
                    shared.set_storylines(novel_id, story_state["storylines"])
                except Exception as inner:
                    logger.debug("[UnifiedCheckpoint] set_storylines 跳过: %s", inner)

            if "plot_arc" in story_state:
                try:
                    shared.set_plot_arc(novel_id, story_state.get("plot_arc"))
                except Exception as inner:
                    logger.debug("[UnifiedCheckpoint] set_plot_arc 跳过: %s", inner)

            logger.info("[WorldlineCheckout] 引擎状态已从 checkpoint 恢复 novel=%s", novel_id)
        except Exception as e:
            logger.warning("[WorldlineCheckout] 引擎状态恢复失败（非致命）: %s", e)
