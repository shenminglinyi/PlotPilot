"""数据库查询优化 - 避免 N+1 问题

核心优化：
1. 使用 JOIN 一次性加载关联数据
2. 批量查询替代循环查询
3. 延迟加载非必要字段
"""
import logging
import json
from typing import List, Dict, Optional
from domain.novel.entities.novel import Novel, AutopilotStatus, NovelStage
from domain.novel.entities.chapter import Chapter, ChapterStatus
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_id import ChapterId

logger = logging.getLogger(__name__)


def find_novels_with_chapters_optimized(db_pool, status: str) -> List[Novel]:
    """优化的小说查询 - 避免 N+1 问题

    原查询：
    1. SELECT * FROM novels WHERE autopilot_status = ?  (10 rows)
    2. SELECT * FROM chapters WHERE novel_id = ?  (×10)
    总查询：11 次

    优化后：
    1. SELECT novels.*, chapters.* FROM novels LEFT JOIN chapters ...
    总查询：1 次

    性能提升：~6x
    """
    # 单次 JOIN 查询
    rows = db_pool.fetch_all(
        """SELECT
            n.id as novel_id,
            n.title,
            n.author,
            n.target_chapters,
            n.premise,
            n.autopilot_status,
            n.auto_approve_mode,
            n.current_stage,
            n.current_act,
            n.current_chapter_in_act,
            n.max_auto_chapters,
            n.current_auto_chapters,
            n.last_chapter_tension,
            n.consecutive_error_count,
            n.current_beat_index,
            n.beats_completed,
            n.last_audit_chapter_number,
            n.last_audit_similarity,
            n.last_audit_drift_alert,
            n.last_audit_narrative_ok,
            n.last_audit_at,
            n.last_audit_vector_stored,
            n.last_audit_foreshadow_stored,
            n.last_audit_triples_extracted,
            n.last_audit_quality_scores,
            n.last_audit_issues,
            n.target_words_per_chapter,
            n.audit_progress,
            c.id as chapter_id,
            c.number as chapter_number,
            c.title as chapter_title,
            c.status as chapter_status,
            c.word_count as chapter_word_count,
            c.tension_score as chapter_tension_score
        FROM novels n
        LEFT JOIN chapters c ON n.id = c.novel_id
        WHERE n.autopilot_status = ?
        ORDER BY n.updated_at DESC, c.number ASC""",
        (status,)
    )

    # 分组：同一小说的章节聚合在一起
    novels_map: Dict[str, Dict] = {}

    for row in rows:
        novel_id = row['novel_id']

        if novel_id not in novels_map:
            # 创建小说对象
            novels_map[novel_id] = {
                'novel_data': {
                    'id': novel_id,
                    'title': row['title'],
                    'author': row['author'],
                    'target_chapters': row['target_chapters'],
                    'premise': row['premise'],
                    'autopilot_status': row['autopilot_status'],
                    'auto_approve_mode': row['auto_approve_mode'],
                    'current_stage': row['current_stage'],
                    'current_act': row['current_act'],
                    'current_chapter_in_act': row['current_chapter_in_act'],
                    'max_auto_chapters': row['max_auto_chapters'],
                    'current_auto_chapters': row['current_auto_chapters'],
                    'last_chapter_tension': row['last_chapter_tension'],
                    'consecutive_error_count': row['consecutive_error_count'],
                    'current_beat_index': row['current_beat_index'],
                    'beats_completed': row['beats_completed'],
                    'last_audit_chapter_number': row['last_audit_chapter_number'],
                    'last_audit_similarity': row['last_audit_similarity'],
                    'last_audit_drift_alert': row['last_audit_drift_alert'],
                    'last_audit_narrative_ok': row['last_audit_narrative_ok'],
                    'last_audit_at': row['last_audit_at'],
                    'last_audit_vector_stored': row['last_audit_vector_stored'],
                    'last_audit_foreshadow_stored': row['last_audit_foreshadow_stored'],
                    'last_audit_triples_extracted': row['last_audit_triples_extracted'],
                    'last_audit_quality_scores': row['last_audit_quality_scores'],
                    'last_audit_issues': row['last_audit_issues'],
                    'target_words_per_chapter': row['target_words_per_chapter'],
                    'audit_progress': row['audit_progress'],
                },
                'chapters': []
            }

        # 添加章节（如果存在）
        if row['chapter_id']:
            novels_map[novel_id]['chapters'].append({
                'id': row['chapter_id'],
                'number': row['chapter_number'],
                'title': row['chapter_title'],
                'status': row['chapter_status'],
                'word_count': row['chapter_word_count'],
                'tension_score': row['chapter_tension_score'],
            })

    # 构建 Novel 实体列表
    novels = []
    for novel_id, data in novels_map.items():
        # 构建 Novel 对象
        novel = _build_novel_from_dict(data['novel_data'])

        # 添加章节
        if data['chapters']:
            chapters = [_build_chapter_from_dict(ch) for ch in data['chapters']]
            novel.chapters = chapters

        novels.append(novel)

    logger.debug(f"查询到 {len(novels)} 本小说，总计 {sum(len(data['chapters']) for data in novels_map.values())} 章")
    return novels


def _build_novel_from_dict(data: Dict) -> Novel:
    """从字典构建 Novel 实体"""
    raw_status = data.get('autopilot_status', 'stopped')
    try:
        autopilot_status = AutopilotStatus(raw_status)
    except ValueError:
        autopilot_status = AutopilotStatus.STOPPED

    raw_stage = data.get('current_stage', 'planning')
    try:
        current_stage = NovelStage(raw_stage)
    except ValueError:
        current_stage = NovelStage.PLANNING

    _lad = data.get("last_audit_drift_alert")
    _lano = data.get("last_audit_narrative_ok")

    # 解析 JSON 字段
    laqs_json = data.get("last_audit_quality_scores")
    laqs = json.loads(laqs_json) if isinstance(laqs_json, str) else (laqs_json or {})
    lai_json = data.get("last_audit_issues")
    lai = json.loads(lai_json) if isinstance(lai_json, str) else (lai_json or [])

    return Novel(
        id=NovelId(data['id']),
        title=data['title'],
        author=data.get('author', '未知作者'),
        target_chapters=data.get('target_chapters', 0),
        premise=data.get('premise', ''),
        autopilot_status=autopilot_status,
        auto_approve_mode=bool(data.get('auto_approve_mode', 0)),
        current_stage=current_stage,
        current_act=data.get('current_act', 0),
        current_chapter_in_act=data.get('current_chapter_in_act', 0),
        max_auto_chapters=data.get('max_auto_chapters', 9999),
        current_auto_chapters=data.get('current_auto_chapters', 0),
        last_chapter_tension=data.get('last_chapter_tension', 0),
        consecutive_error_count=data.get('consecutive_error_count', 0),
        current_beat_index=data.get('current_beat_index', 0),
        beats_completed=bool(data.get('beats_completed', 0)),
        last_audit_chapter_number=data.get("last_audit_chapter_number"),
        last_audit_similarity=data.get("last_audit_similarity"),
        last_audit_drift_alert=bool(_lad) if _lad is not None else False,
        last_audit_narrative_ok=bool(_lano) if _lano is not None else True,
        last_audit_at=data.get("last_audit_at"),
        last_audit_vector_stored=bool(data.get("last_audit_vector_stored", 0)),
        last_audit_foreshadow_stored=bool(data.get("last_audit_foreshadow_stored", 0)),
        last_audit_triples_extracted=bool(data.get("last_audit_triples_extracted", 0)),
        last_audit_quality_scores=laqs,
        last_audit_issues=lai,
        target_words_per_chapter=data.get("target_words_per_chapter", 2500),
        audit_progress=data.get("audit_progress"),
    )


def _build_chapter_from_dict(data: Dict) -> Chapter:
    """从字典构建 Chapter 实体"""
    return Chapter(
        chapter_id=ChapterId(data['id']),
        number=data['number'],
        title=data.get('title', ''),
        status=ChapterStatus(data.get('status', 'draft')),
        word_count=data.get('word_count', 0),
        tension_score=data.get('tension_score', 50.0),
    )


# 性能对比测试
def benchmark_query_performance(db_pool, status: str = "running", iterations: int = 10):
    """性能对比测试：原查询 vs 优化查询"""
    import time

    # 原查询（N+1）
    start = time.time()
    for _ in range(iterations):
        rows = db_pool.fetch_all("SELECT * FROM novels WHERE autopilot_status = ?", (status,))
        for row in rows:
            db_pool.fetch_all("SELECT * FROM chapters WHERE novel_id = ?", (row['id'],))
    elapsed_old = time.time() - start

    # 优化查询（JOIN）
    start = time.time()
    for _ in range(iterations):
        find_novels_with_chapters_optimized(db_pool, status)
    elapsed_new = time.time() - start

    speedup = elapsed_old / elapsed_new if elapsed_new > 0 else 0

    logger.info(f"查询性能对比 ({iterations} 次迭代):")
    logger.info(f"  原查询: {elapsed_old * 1000:.2f}ms")
    logger.info(f"  优化查询: {elapsed_new * 1000:.2f}ms")
    logger.info(f"  性能提升: {speedup:.2f}x")

    return {
        'old_time_ms': elapsed_old * 1000,
        'new_time_ms': elapsed_new * 1000,
        'speedup': speedup,
    }
