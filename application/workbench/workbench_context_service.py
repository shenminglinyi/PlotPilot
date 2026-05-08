"""构建「工作台上下文」聚合载荷：故事线/弧光、编年史、叙事知识、关系图统计、伏笔、宏观事件数、沙盒依赖等。"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from application.codex.chronicles_service import build_chronicles_rows
from domain.novel.value_objects.novel_id import NovelId

logger = logging.getLogger(__name__)


def _storyline_dict(storyline) -> Dict[str, Any]:
    return {
        "id": storyline.id,
        "storyline_type": storyline.storyline_type.value,
        "status": storyline.status.value,
        "estimated_chapter_start": storyline.estimated_chapter_start,
        "estimated_chapter_end": storyline.estimated_chapter_end,
        "name": getattr(storyline, "name", "") or "",
        "description": getattr(storyline, "description", "") or "",
    }


def _plot_arc_dict(plot_arc) -> Dict[str, Any]:
    return {
        "id": plot_arc.id,
        "novel_id": str(plot_arc.novel_id) if hasattr(plot_arc, "novel_id") else "",
        "key_points": [
            {
                "chapter_number": p.chapter_number,
                "tension": p.tension.value if hasattr(p.tension, "value") else int(p.tension),
                "description": p.description,
                "point_type": p.point_type.value if hasattr(p.point_type, "value") else str(p.point_type),
            }
            for p in plot_arc.key_points
        ],
    }


def _foreshadow_entry_dict(entry) -> Dict[str, Any]:
    return {
        "id": entry.id,
        "chapter": entry.chapter,
        "character_id": entry.character_id,
        "question": entry.question,
        "status": entry.status,
        "consumed_at_chapter": entry.consumed_at_chapter,
        "created_at": entry.created_at.isoformat() if entry.created_at else "",
    }


def _knowledge_dict(knowledge) -> Dict[str, Any]:
    return {
        "version": knowledge.version,
        "premise_lock": knowledge.premise_lock or "",
        "chapters": [
            {
                "chapter_id": ch.chapter_id,
                "summary": ch.summary,
                "key_events": ch.key_events,
                "open_threads": ch.open_threads,
                "consistency_note": ch.consistency_note,
                "beat_sections": list(ch.beat_sections or []),
                "sync_status": ch.sync_status,
            }
            for ch in knowledge.chapters
        ],
        "facts": [
            {
                "id": fact.id,
                "subject": fact.subject,
                "predicate": fact.predicate,
                "object": fact.object,
                "chapter_id": fact.chapter_id,
                "note": fact.note or "",
            }
            for fact in knowledge.facts
        ],
    }


def _count_narrative_events(db, novel_id: str) -> int:
    try:
        row = db.fetch_one(
            "SELECT COUNT(*) AS c FROM narrative_events WHERE novel_id = ?",
            (novel_id,),
        )
        if row is None:
            return 0
        return int(row["c"] if isinstance(row, dict) else row[0])
    except Exception as e:
        logger.debug("narrative_events count skip: %s", e)
        return 0


async def build_workbench_context_bundle(
    novel_id: str,
    *,
    novel_service,
    bible_service,
    chapter_repo,
    snapshot_service,
    storyline_manager,
    plot_arc_repo,
    knowledge_service,
    foreshadowing_repo,
    triple_repository,
    db_connection,
) -> Dict[str, Any]:
    """与各独立 GET 使用相同仓储/领域逻辑，供单次 BFF 拉取。

    🔥 架构优化：所有同步 DB 调用包装到线程池，避免阻塞事件循环。
    SQLite WAL 模式下，跨进程写操作会持有锁，同步读取会被阻塞。
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    # 使用共享线程池（与 SSE 相同）
    loop = asyncio.get_running_loop()

    # 🔥 同步 DB 操作包装到线程池
    def _sync_db_operations():
        if novel_service.get_novel(novel_id) is None:
            return None

        # —— 全息编年史（与 chronicles 路由一致）——
        bible = bible_service.get_bible_by_novel(novel_id)
        notes_tuples: List[tuple] = []
        if bible and bible.timeline_notes:
            for n in bible.timeline_notes:
                notes_tuples.append((n.id, n.time_point or "", n.event or "", n.description or ""))

        chapters = chapter_repo.list_by_novel(NovelId(novel_id))
        id_to_number = {c.id: c.number for c in chapters}
        max_ch = max((c.number for c in chapters), default=1)
        chapter_digest = []
        for c in sorted(chapters, key=lambda x: x.number):
            wc = getattr(c, "word_count", None)
            wv = int(wc.value) if wc is not None and hasattr(wc, "value") else 0
            chapter_digest.append(
                {
                    "id": c.id,
                    "number": c.number,
                    "title": getattr(c, "title", "") or "",
                    "word_count": wv,
                }
            )

        try:
            snapshots_raw: List[Dict[str, Any]] = snapshot_service.list_snapshots_with_pointers(novel_id)
        except sqlite3.OperationalError as e:
            logger.warning("workbench-context: novel_snapshots unreadable: %s", e)
            snapshots_raw = []

        raw_rows = build_chronicles_rows(notes_tuples, snapshots_raw, id_to_number)
        chronicle_rows: List[Dict[str, Any]] = []
        for r in raw_rows:
            chronicle_rows.append(
                {
                    "chapter_index": r["chapter_index"],
                    "story_events": list(r["story_events"]),
                    "snapshots": list(r["snapshots"]),
                }
            )

        # —— 故事线 · 弧光 ——
        storylines = storyline_manager.repository.get_by_novel_id(NovelId(novel_id))
        storyline_list = [_storyline_dict(s) for s in storylines]

        plot_arc = plot_arc_repo.get_by_novel_id(NovelId(novel_id))
        plot_arc_payload: Optional[Dict[str, Any]] = None
        if plot_arc is not None:
            plot_arc_payload = _plot_arc_dict(plot_arc)

        # —— 叙事知识 ——
        knowledge = knowledge_service.get_knowledge(novel_id)
        knowledge_payload = _knowledge_dict(knowledge)

        # —— 伏笔账本 ——
        foreshadow_entries: List[Dict[str, Any]] = []
        registry = foreshadowing_repo.get_by_novel_id(NovelId(novel_id))
        if registry and registry.subtext_entries:
            foreshadow_entries = [_foreshadow_entry_dict(e) for e in registry.subtext_entries]

        return {
            "chronicle_rows": chronicle_rows,
            "max_ch": max_ch,
            "storyline_list": storyline_list,
            "plot_arc_payload": plot_arc_payload,
            "knowledge_payload": knowledge_payload,
            "foreshadow_entries": foreshadow_entries,
            "chapter_digest": chapter_digest,
            "bible": bible,
            "macro_events": _count_narrative_events(db_connection, novel_id),
        }

    try:
        # 🔥 2 秒超时保护，避免 DB 被锁时长时间阻塞
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _sync_db_operations),
            timeout=2.0
        )
    except asyncio.TimeoutError:
        logger.warning("workbench-context DB 操作超时 novel=%s", novel_id)
        return {
            "error": "db_timeout",
            "novel_id": novel_id,
            "message": "数据库繁忙，请稍后重试",
        }

    if result is None:
        return {"error": "novel_not_found", "novel_id": novel_id}

    chronicle_rows = result["chronicle_rows"]
    max_ch = result["max_ch"]
    storyline_list = result["storyline_list"]
    plot_arc_payload = result["plot_arc_payload"]
    knowledge_payload = result["knowledge_payload"]
    foreshadow_entries = result["foreshadow_entries"]
    chapter_digest = result["chapter_digest"]
    bible = result["bible"]
    macro_events = result["macro_events"]

    # —— 关系图（三元组统计，与 statistics 路由同口径）——
    kg: Dict[str, Any] = {"total_triples": 0, "by_source": {}}
    try:
        all_triples = await triple_repository.get_by_novel(novel_id)
        kg["total_triples"] = len(all_triples)
        by_src: Dict[str, int] = {}
        for t in all_triples:
            src = t.source_type.value if hasattr(t.source_type, "value") else str(t.source_type)
            by_src[src] = by_src.get(src, 0) + 1
        kg["by_source"] = by_src
    except Exception as e:
        logger.warning("workbench-context kg stats: %s", e)

    # —— 对话沙盒：Bible 角色数 ——
    bible_character_count = 0
    if bible and getattr(bible, "characters", None):
        bible_character_count = len(bible.characters)

    return {
        "novel_id": novel_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chronicles": {
            "rows": chronicle_rows,
            "max_chapter_in_book": max_ch,
            "note": "剧情节点来自 Bible.timeline_notes；快照来自 novel_snapshots。",
        },
        "storylines": storyline_list,
        "plot_arc": plot_arc_payload,
        "knowledge": knowledge_payload,
        "foreshadow_ledger": foreshadow_entries,
        "knowledge_graph": kg,
        "macro": {"narrative_event_count": macro_events},
        "sandbox": {"bible_character_count": bible_character_count},
        "chapters_digest": chapter_digest,
    }
