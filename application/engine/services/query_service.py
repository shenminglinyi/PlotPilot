"""查询服务 - API 层的唯一查询入口

职责：
1. 封装所有查询逻辑
2. 提供统一的查询接口给 API 层
3. 所有查询都从共享内存读取，永不阻塞事件循环

设计原则：
- 内存优先：所有查询都从共享内存读取
- 降级友好：共享内存无数据时返回空/默认值
- 零阻塞：永不进行同步 DB 操作
"""
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from application.engine.services.shared_state_repository import (
    SharedStateRepository,
    NovelState,
    ChapterSummary,
    get_shared_state_repository,
)

logger = logging.getLogger(__name__)


@dataclass
class NovelStatusResponse:
    """小说状态响应（对应 /status 端点）"""
    novel_id: str
    title: str
    autopilot_status: str
    current_stage: str
    current_act: Optional[int]
    current_chapter_in_act: Optional[int]
    current_beat_index: int
    current_auto_chapters: int
    max_auto_chapters: int
    target_chapters: int
    target_words_per_chapter: int
    target_plan_total_words: int
    last_chapter_tension: float
    consecutive_error_count: int
    total_words: int
    completed_chapters: int
    progress_pct: float
    manuscript_chapters: int
    progress_pct_manuscript: float
    current_chapter_number: Optional[int]
    needs_review: bool
    auto_approve_mode: bool
    last_chapter_audit: Optional[Dict[str, Any]]
    audit_progress: Optional[Dict[str, Any]]
    daemon_alive: bool
    daemon_heartbeat_at: Optional[float]
    _from_shared_memory: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "title": self.title,
            "autopilot_status": self.autopilot_status,
            "current_stage": self.current_stage,
            "current_act": self.current_act,
            "current_chapter_in_act": self.current_chapter_in_act,
            "current_beat_index": self.current_beat_index,
            "current_auto_chapters": self.current_auto_chapters,
            "max_auto_chapters": self.max_auto_chapters,
            "target_chapters": self.target_chapters,
            "target_words_per_chapter": self.target_words_per_chapter,
            "target_plan_total_words": self.target_plan_total_words,
            "last_chapter_tension": self.last_chapter_tension,
            "consecutive_error_count": self.consecutive_error_count,
            "total_words": self.total_words,
            "completed_chapters": self.completed_chapters,
            "progress_pct": self.progress_pct,
            "manuscript_chapters": self.manuscript_chapters,
            "progress_pct_manuscript": self.progress_pct_manuscript,
            "current_chapter_number": self.current_chapter_number,
            "needs_review": self.needs_review,
            "auto_approve_mode": self.auto_approve_mode,
            "last_chapter_audit": self.last_chapter_audit,
            "audit_progress": self.audit_progress,
            "daemon_alive": self.daemon_alive,
            "daemon_heartbeat_at": self.daemon_heartbeat_at,
            "_from_shared_memory": self._from_shared_memory,
        }


@dataclass
class WorkbenchContextResponse:
    """工作台上下文响应（对应 /workbench-context 端点）"""
    novel_id: str
    generated_at: str
    chronicles: Dict[str, Any]
    storylines: List[Dict[str, Any]]
    plot_arc: Optional[Dict[str, Any]]
    knowledge: Optional[Dict[str, Any]]
    foreshadow_ledger: List[Dict[str, Any]]
    knowledge_graph: Dict[str, Any]
    macro: Dict[str, Any]
    sandbox: Dict[str, Any]
    chapters_digest: List[Dict[str, Any]]
    _from_shared_memory: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "generated_at": self.generated_at,
            "chronicles": self.chronicles,
            "storylines": self.storylines,
            "plot_arc": self.plot_arc,
            "knowledge": self.knowledge,
            "foreshadow_ledger": self.foreshadow_ledger,
            "knowledge_graph": self.knowledge_graph,
            "macro": self.macro,
            "sandbox": self.sandbox,
            "chapters_digest": self.chapters_digest,
            "_from_shared_memory": self._from_shared_memory,
        }


class QueryService:
    """查询服务 - API 层的唯一查询入口

    🔥 核心原则：所有查询都从共享内存读取，永不阻塞事件循环
    """

    def __init__(self, shared_state: Optional[SharedStateRepository] = None):
        self._shared = shared_state or get_shared_state_repository()

    # ==================== 小说状态 ====================

    def get_novel_status(self, novel_id: str) -> Optional[NovelStatusResponse]:
        """获取小说状态（用于 /status 端点）

        纯内存读取，纳秒级响应。
        如果共享内存没有数据，降级到数据库查询。
        """
        # 先尝试获取 NovelState 对象
        state = self._shared.get_novel_state(novel_id)
        if state is None:
            # 尝试获取原始数据（兼容旧格式）
            raw_data = self._shared.get_raw_state(novel_id)
            if raw_data is None:
                # 🔥 降级：从数据库加载
                logger.debug(f"共享内存中没有小说 {novel_id} 的数据，尝试从数据库加载")
                return self._fallback_from_db(novel_id)
            # 直接从原始数据构建响应
            return self._build_status_from_raw(novel_id, raw_data)

        # 计算进度
        total_words = 0  # 需要从章节累计
        chapters = self._shared.get_chapters(novel_id)
        completed_chapters = sum(1 for c in chapters if c.status == "completed")
        total_words = sum(c.word_count for c in chapters)

        progress_pct = 0.0
        if state.target_chapters > 0:
            progress_pct = (completed_chapters / state.target_chapters) * 100

        # 计算当前章节号
        current_chapter_number = None
        if state.current_act and state.current_chapter_in_act:
            current_chapter_number = (state.current_act - 1) * 5 + state.current_chapter_in_act

        return NovelStatusResponse(
            novel_id=state.novel_id,
            title=state.title,
            autopilot_status=state.autopilot_status,
            current_stage=state.current_stage,
            current_act=state.current_act,
            current_chapter_in_act=state.current_chapter_in_act,
            current_beat_index=state.current_beat_index,
            current_auto_chapters=state.current_auto_chapters,
            max_auto_chapters=9999,
            target_chapters=state.target_chapters,
            target_words_per_chapter=state.target_words_per_chapter,
            target_plan_total_words=state.target_chapters * state.target_words_per_chapter,
            last_chapter_tension=state.last_chapter_tension,
            consecutive_error_count=state.consecutive_error_count,
            total_words=total_words,
            completed_chapters=completed_chapters,
            progress_pct=round(progress_pct, 1),
            manuscript_chapters=completed_chapters,
            progress_pct_manuscript=round(progress_pct, 1),
            current_chapter_number=current_chapter_number,
            needs_review=state.needs_review,
            auto_approve_mode=state.auto_approve_mode,
            last_chapter_audit=None,  # 需要单独存储
            audit_progress=None,
            daemon_alive=self._shared.is_daemon_alive(),
            daemon_heartbeat_at=self._shared.get_daemon_heartbeat(),
            _from_shared_memory=True,
        )

    def _build_status_from_raw(self, novel_id: str, raw_data: Dict[str, Any]) -> NovelStatusResponse:
        """从原始数据构建状态响应（兼容旧格式）"""
        # 获取章节信息
        chapters = self._shared.get_chapters(novel_id)
        completed_chapters = raw_data.get("_cached_completed_chapters", 0) or sum(1 for c in chapters if c.status == "completed")
        total_words = raw_data.get("_cached_total_words", 0) or sum(c.word_count for c in chapters)

        target_chapters = raw_data.get("target_chapters", 0)
        progress_pct = (completed_chapters / target_chapters * 100) if target_chapters > 0 else 0

        current_act = raw_data.get("current_act")
        current_chapter_in_act = raw_data.get("current_chapter_in_act")
        current_chapter_number = raw_data.get("_cached_current_chapter_number")
        if current_chapter_number is None and current_act and current_chapter_in_act:
            current_chapter_number = (current_act - 1) * 5 + current_chapter_in_act

        return NovelStatusResponse(
            novel_id=novel_id,
            title=raw_data.get("title", ""),
            autopilot_status=raw_data.get("autopilot_status", "stopped"),
            current_stage=raw_data.get("current_stage", "writing"),
            current_act=current_act,
            current_chapter_in_act=current_chapter_in_act,
            current_beat_index=raw_data.get("current_beat_index", 0),
            current_auto_chapters=raw_data.get("current_auto_chapters", 0),
            max_auto_chapters=9999,
            target_chapters=target_chapters,
            target_words_per_chapter=raw_data.get("target_words_per_chapter", 2500),
            target_plan_total_words=target_chapters * raw_data.get("target_words_per_chapter", 2500),
            last_chapter_tension=raw_data.get("last_chapter_tension", 0),
            consecutive_error_count=raw_data.get("consecutive_error_count", 0),
            total_words=total_words,
            completed_chapters=completed_chapters,
            progress_pct=round(progress_pct, 1),
            manuscript_chapters=completed_chapters,
            progress_pct_manuscript=round(progress_pct, 1),
            current_chapter_number=current_chapter_number,
            needs_review=raw_data.get("needs_review", False),
            auto_approve_mode=raw_data.get("auto_approve_mode", False),
            last_chapter_audit=None,
            audit_progress=raw_data.get("audit_progress"),
            daemon_alive=self._shared.is_daemon_alive(),
            daemon_heartbeat_at=self._shared.get_daemon_heartbeat(),
            _from_shared_memory=True,
        )

    def _fallback_from_db(self, novel_id: str) -> Optional[NovelStatusResponse]:
        """🔥 降级：从数据库加载小说状态

        当共享内存没有数据时（如新创建的小说未同步到共享内存），
        从数据库直接读取并返回状态。
        """
        from application.paths import get_db_path
        from infrastructure.persistence.database.connection import get_database

        try:
            db_path = get_db_path()
            db = get_database(db_path)

            novel_row = db.fetch_one(
                """SELECT id, title, autopilot_status, current_stage,
                          current_act, current_chapter_in_act, current_beat_index,
                          current_auto_chapters, target_chapters, target_words_per_chapter,
                          consecutive_error_count, last_chapter_tension, auto_approve_mode
                   FROM novels WHERE id = ?""",
                (novel_id,),
            )

            if not novel_row:
                return None

            agg_rows = db.fetch_all(
                """SELECT status, COUNT(*) as cnt, SUM(LENGTH(COALESCE(content,''))) as total_wc
                   FROM chapters WHERE novel_id = ? GROUP BY status""",
                (novel_id,),
            )

            completed_chapters = 0
            manuscript_chapters = 0
            total_words = 0
            for r in agg_rows:
                s = r["status"] or ""
                wc = r["total_wc"] or 0
                total_words += wc
                if s == "completed":
                    completed_chapters += 1
                    manuscript_chapters += 1
                elif s == "draft":
                    manuscript_chapters += 1

            last_tension_row = db.fetch_one(
                """SELECT tension_score FROM chapters
                   WHERE novel_id = ? AND status = 'completed'
                   ORDER BY number DESC LIMIT 1""",
                (novel_id,),
            )
            last_tension = float(last_tension_row["tension_score"] or 0) if last_tension_row else 0.0

            draft_row = db.fetch_one(
                """SELECT MAX(number) as max_num FROM chapters
                   WHERE novel_id = ? AND status = 'draft' AND COALESCE(LENGTH(content),0) > 0""",
                (novel_id,),
            )
            if draft_row and draft_row["max_num"]:
                current_chapter_number = draft_row["max_num"]
            else:
                completed_max = db.fetch_one(
                    """SELECT MAX(number) as max_num FROM chapters WHERE novel_id = ? AND status = 'completed'""",
                    (novel_id,),
                )
                current_chapter_number = (
                    (completed_max["max_num"] + 1)
                    if (completed_max and completed_max["max_num"])
                    else None
                )

            target_chapters = novel_row["target_chapters"] or 1
            progress_pct = (completed_chapters / target_chapters * 100) if target_chapters > 0 else 0

            return NovelStatusResponse(
                novel_id=novel_id,
                title=novel_row['title'] or "",
                autopilot_status=novel_row['autopilot_status'] or "stopped",
                current_stage=novel_row['current_stage'] or "writing",
                current_act=novel_row['current_act'],
                current_chapter_in_act=novel_row['current_chapter_in_act'],
                current_beat_index=novel_row['current_beat_index'] or 0,
                current_auto_chapters=novel_row['current_auto_chapters'] or 0,
                max_auto_chapters=9999,
                target_chapters=target_chapters,
                target_words_per_chapter=novel_row['target_words_per_chapter'] or 2500,
                target_plan_total_words=target_chapters * (novel_row['target_words_per_chapter'] or 2500),
                last_chapter_tension=last_tension,
                consecutive_error_count=novel_row['consecutive_error_count'] or 0,
                total_words=total_words,
                completed_chapters=completed_chapters,
                progress_pct=round(progress_pct, 1),
                manuscript_chapters=manuscript_chapters,
                progress_pct_manuscript=round(manuscript_chapters / target_chapters * 100, 1) if target_chapters else 0,
                current_chapter_number=current_chapter_number,
                needs_review=(novel_row['current_stage'] or "") == "paused_for_review",
                auto_approve_mode=bool(novel_row['auto_approve_mode']),
                last_chapter_audit=None,
                audit_progress=None,
                daemon_alive=self._shared.is_daemon_alive(),
                daemon_heartbeat_at=self._shared.get_daemon_heartbeat(),
                _from_shared_memory=False,  # 标记数据来自数据库
            )

        except Exception as e:
            logger.error(f"从数据库加载小说状态失败: {novel_id}, {e}")
            return None

    def get_novel_status_dict(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取小说状态（字典形式，兼容旧代码）"""
        response = self.get_novel_status(novel_id)
        return response.to_dict() if response else None

    # ==================== 工作台上下文 ====================

    def get_workbench_context(self, novel_id: str) -> WorkbenchContextResponse:
        """获取工作台上下文（用于 /workbench-context 端点）

        优先从共享内存读取，如果共享内存没有数据，降级到数据库查询。
        """
        from datetime import datetime, timezone

        # 从共享内存获取所有数据
        chronicles = self._shared.get_chronicles(novel_id)
        storylines = self._shared.get_storylines(novel_id)
        plot_arc = self._shared.get_plot_arc(novel_id)
        knowledge = self._shared.get_knowledge(novel_id)
        foreshadows = self._shared.get_foreshadows(novel_id)
        chapters = self._shared.get_chapters(novel_id)

        # 🔥 如果共享内存中没有数据，降级到数据库查询
        if not storylines and not chapters:
            logger.debug(f"共享内存中没有小说 {novel_id} 的工作台数据，从数据库加载")
            return self._fallback_workbench_from_db(novel_id)

        # 计算最大章节号
        max_ch = max((c.number for c in chapters), default=1)

        return WorkbenchContextResponse(
            novel_id=novel_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            chronicles={
                "rows": chronicles,
                "max_chapter_in_book": max_ch,
                "note": "剧情节点来自共享内存",
            },
            storylines=storylines,
            plot_arc=plot_arc,
            knowledge=knowledge,
            foreshadow_ledger=foreshadows,
            knowledge_graph={"total_triples": 0, "by_source": {}},  # 需要单独处理
            macro={"narrative_event_count": 0},  # 需要单独处理
            sandbox={"bible_character_count": 0},  # 需要单独处理
            chapters_digest=[c.to_dict() for c in chapters],
            _from_shared_memory=True,
        )

    def _fallback_workbench_from_db(self, novel_id: str) -> WorkbenchContextResponse:
        """🔥 降级：从数据库加载工作台上下文"""
        from datetime import datetime, timezone
        from application.engine.services.state_bootstrap import StateBootstrap

        try:
            bootstrap = StateBootstrap()

            # 加载数据
            storylines_data = bootstrap._load_storylines(novel_id)
            chapters_data = bootstrap._load_chapters(novel_id)
            foreshadows_data = bootstrap._load_foreshadows(novel_id)
            plot_arc_data = bootstrap._load_plot_arc(novel_id)
            knowledge_data = bootstrap._load_knowledge(novel_id)
            chronicles_data = bootstrap._load_chronicles(novel_id)

            max_ch = max((c.number for c in chapters_data), default=1) if chapters_data else 1

            return WorkbenchContextResponse(
                novel_id=novel_id,
                generated_at=datetime.now(timezone.utc).isoformat(),
                chronicles={
                    "rows": chronicles_data,
                    "max_chapter_in_book": max_ch,
                    "note": "剧情节点来自数据库",
                },
                storylines=storylines_data,
                plot_arc=plot_arc_data,
                knowledge=knowledge_data,
                foreshadow_ledger=foreshadows_data,
                knowledge_graph={"total_triples": 0, "by_source": {}},
                macro={"narrative_event_count": 0},
                sandbox={"bible_character_count": 0},
                chapters_digest=[c.to_dict() for c in chapters_data],
                _from_shared_memory=False,
            )
        except Exception as e:
            logger.error(f"从数据库加载工作台上下文失败: {novel_id}, {e}")
            # 返回空数据
            return WorkbenchContextResponse(
                novel_id=novel_id,
                generated_at=datetime.now(timezone.utc).isoformat(),
                chronicles={"rows": [], "max_chapter_in_book": 1, "note": "加载失败"},
                storylines=[],
                plot_arc=None,
                knowledge=None,
                foreshadow_ledger=[],
                knowledge_graph={"total_triples": 0, "by_source": {}},
                macro={"narrative_event_count": 0},
                sandbox={"bible_character_count": 0},
                chapters_digest=[],
                _from_shared_memory=False,
            )

    # ==================== 章节列表 ====================

    def get_chapters(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取章节列表"""
        chapters = self._shared.get_chapters(novel_id)
        return [c.to_dict() for c in chapters]

    def get_chapter(self, novel_id: str, chapter_number: int) -> Optional[Dict[str, Any]]:
        """获取单个章节"""
        chapters = self._shared.get_chapters(novel_id)
        for c in chapters:
            if c.number == chapter_number:
                return c.to_dict()
        return None

    # ==================== 伏笔列表 ====================

    def get_foreshadows(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取伏笔列表"""
        return self._shared.get_foreshadows(novel_id)

    # ==================== 故事线 ====================

    def get_storylines(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取故事线列表"""
        return self._shared.get_storylines(novel_id)

    # ==================== 剧情弧光 ====================

    def get_plot_arc(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取剧情弧光"""
        return self._shared.get_plot_arc(novel_id)

    # ==================== 编年史 ====================

    def get_chronicles(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取编年史"""
        return self._shared.get_chronicles(novel_id)

    # ==================== 叙事知识 ====================

    def get_knowledge(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取叙事知识"""
        return self._shared.get_knowledge(novel_id)

    # ==================== 守护进程状态 ====================

    def is_daemon_alive(self) -> bool:
        """检查守护进程是否存活"""
        return self._shared.is_daemon_alive()

    def get_daemon_heartbeat(self) -> Optional[float]:
        """获取守护进程心跳时间"""
        return self._shared.get_daemon_heartbeat()

    # ==================== Bible（世界观） ====================

    def get_bible(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取 Bible 数据"""
        return self._shared.get_bible(novel_id)

    # ==================== 三元组（知识图谱） ====================

    def get_triples(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取三元组列表"""
        return self._shared.get_triples(novel_id)

    def get_knowledge_graph(self, novel_id: str) -> Dict[str, Any]:
        """获取知识图谱统计"""
        triples = self._shared.get_triples(novel_id)
        by_src: Dict[str, int] = {}
        for t in triples:
            src = t.get("source_type", "unknown")
            by_src[src] = by_src.get(src, 0) + 1
        return {
            "total_triples": len(triples),
            "by_source": by_src,
        }

    # ==================== 快照 ====================

    def get_snapshots(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取快照列表"""
        return self._shared.get_snapshots(novel_id)

    # ==================== 审计结果 ====================

    def get_last_audit(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取最后一次审计结果"""
        return self._shared.get_last_audit(novel_id)

    def get_audit_progress(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取审计进度"""
        return self._shared.get_audit_progress(novel_id)

    # ==================== 章节内容（完整） ====================

    def get_chapter_content(self, novel_id: str, chapter_number: int) -> Optional[str]:
        """获取章节内容（仅用于必要的场景，如导出）

        注意：章节内容可能很长，不在共享内存中存储完整内容。
        此方法返回 None，需要通过其他方式获取。
        """
        # 章节内容不在共享内存中，返回 None
        # 如果需要获取章节内容，应该在守护进程完成后通过文件读取
        return None

    # ==================== 小说列表 ====================

    def get_all_novel_ids(self) -> List[str]:
        """获取所有小说 ID"""
        return self._shared.get_all_novel_ids()

    def get_all_novels_summary(self) -> List[Dict[str, Any]]:
        """获取所有小说摘要"""
        novel_ids = self._shared.get_all_novel_ids()
        summaries = []
        for novel_id in novel_ids:
            state = self._shared.get_novel_state(novel_id)
            if state:
                summaries.append({
                    "novel_id": state.novel_id,
                    "title": state.title,
                    "autopilot_status": state.autopilot_status,
                    "current_stage": state.current_stage,
                    "current_auto_chapters": state.current_auto_chapters,
                    "target_chapters": state.target_chapters,
                })
        return summaries


# 全局实例（单例）
_query_service: Optional[QueryService] = None


def get_query_service() -> QueryService:
    """获取查询服务实例"""
    global _query_service
    if _query_service is None:
        _query_service = QueryService()
    return _query_service


def init_query_service(shared_state: SharedStateRepository) -> QueryService:
    """初始化查询服务"""
    global _query_service
    _query_service = QueryService(shared_state)
    return _query_service
