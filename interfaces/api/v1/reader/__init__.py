"""读者模拟 Agent API 路由

提供章节级读者模拟分析的 REST 接口。
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from application.reader.services.reader_simulation_service import ReaderSimulationService
from application.reader.dtos.reader_feedback_dto import ChapterReaderReportDTO
from infrastructure.persistence.database.reader_simulation_repository import (
    ReaderSimulationRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reader", tags=["reader-simulation"])

# ─── 懒加载依赖 ─────────────────────────────────────────────

_service: Optional[ReaderSimulationService] = None
_repo: Optional[ReaderSimulationRepository] = None


def _get_service() -> ReaderSimulationService:
    global _service
    if _service is None:
        from interfaces.api.dependencies import get_chapter_repository, get_llm_service
        try:
            from interfaces.api.dependencies import get_knowledge_repository
            knowledge_repo = get_knowledge_repository()
        except Exception:
            knowledge_repo = None

        _service = ReaderSimulationService(
            chapter_repository=get_chapter_repository(),
            llm_client=get_llm_service(),
            knowledge_repository=knowledge_repo,
        )
    return _service


def _get_repo() -> ReaderSimulationRepository:
    global _repo
    if _repo is None:
        _repo = ReaderSimulationRepository()
        try:
            _repo.ensure_table()
        except Exception as e:
            logger.warning("读者模拟表初始化失败（首次使用时会自动重试）: %s", e)
    return _repo


# ─── API 端点 ────────────────────────────────────────────────

@router.post("/novels/{novel_id}/chapters/{chapter_number}/simulate")
async def simulate_readers(novel_id: str, chapter_number: int):
    """对指定章节运行三类读者模拟分析。

    模拟三种读者人设（硬核粉/休闲读者/挑刺党）阅读本章后的反馈，
    输出四维度评分：悬疑保持度、爽感评分、劝退风险、情感共鸣度。

    调用 LLM，耗时约 10-30 秒。
    """
    try:
        service = _get_service()
        report: ChapterReaderReportDTO = await service.simulate(
            novel_id=novel_id,
            chapter_number=chapter_number,
        )

        # 持久化
        try:
            repo = _get_repo()
            repo.save(
                novel_id=novel_id,
                chapter_number=chapter_number,
                overall_readability=report.overall_readability,
                chapter_hook_strength=report.chapter_hook_strength,
                pacing_verdict=report.pacing_verdict,
                avg_scores=report._compute_avg_scores(),
                feedbacks_json=json.dumps(
                    [f.to_dict() for f in report.feedbacks],
                    ensure_ascii=False,
                ),
            )
        except Exception as e:
            logger.warning("读者模拟结果持久化失败: %s", e)

        return {"success": True, "data": report.to_dict()}

    except Exception as e:
        logger.error("读者模拟失败 novel=%s ch=%d: %s", novel_id, chapter_number, e)
        raise HTTPException(status_code=500, detail=f"读者模拟分析失败: {e}")


@router.get("/novels/{novel_id}/chapters/{chapter_number}/simulation")
async def get_chapter_simulation(novel_id: str, chapter_number: int):
    """获取某章最新的读者模拟结果（不重新分析）。"""
    try:
        repo = _get_repo()
        record = repo.get_latest(novel_id, chapter_number)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=f"第{chapter_number}章尚无读者模拟记录，请先调用 POST 接口分析",
            )

        # 将 feedbacks_json 展开
        feedbacks_raw = record.get("feedbacks_json", "[]")
        try:
            feedbacks = json.loads(feedbacks_raw)
        except (json.JSONDecodeError, TypeError):
            feedbacks = []

        return {"success": True, "data": {
            "novel_id": record["novel_id"],
            "chapter_number": record["chapter_number"],
            "overall_readability": record.get("overall_readability", 50.0),
            "chapter_hook_strength": record.get("chapter_hook_strength", "medium"),
            "pacing_verdict": record.get("pacing_verdict", ""),
            "avg_scores": {
                "suspense_retention": record.get("avg_suspense_retention", 50.0),
                "thrill_score": record.get("avg_thrill_score", 50.0),
                "churn_risk": record.get("avg_churn_risk", 30.0),
                "emotional_resonance": record.get("avg_emotional_resonance", 50.0),
            },
            "feedbacks": feedbacks,
            "analyzed_at": record.get("created_at"),
        }}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取读者模拟记录失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/novels/{novel_id}/simulations")
async def list_novel_simulations(novel_id: str):
    """获取某本小说所有章节的读者模拟概览（每章最新一条）。"""
    try:
        repo = _get_repo()
        records = repo.list_by_novel(novel_id)
        items = []
        for r in records:
            items.append({
                "chapter_number": r["chapter_number"],
                "overall_readability": r.get("overall_readability", 50.0),
                "chapter_hook_strength": r.get("chapter_hook_strength", "medium"),
                "avg_scores": {
                    "suspense_retention": r.get("avg_suspense_retention", 50.0),
                    "thrill_score": r.get("avg_thrill_score", 50.0),
                    "churn_risk": r.get("avg_churn_risk", 30.0),
                    "emotional_resonance": r.get("avg_emotional_resonance", 50.0),
                },
                "analyzed_at": r.get("created_at"),
            })
        return {"success": True, "data": {
            "novel_id": novel_id,
            "chapters": items,
            "total": len(items),
        }}
    except Exception as e:
        logger.error("获取小说读者模拟列表失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/novels/{novel_id}/churn-alerts")
async def get_churn_alerts(novel_id: str, threshold: float = 60.0):
    """获取劝退风险高的章节告警列表。

    Args:
        threshold: 劝退风险阈值 (默认 60)，高于此值的章节会被标红
    """
    try:
        repo = _get_repo()
        records = repo.get_high_churn_chapters(novel_id, threshold)
        alerts = []
        for r in records:
            feedbacks_raw = r.get("feedbacks_json", "[]")
            try:
                feedbacks = json.loads(feedbacks_raw)
            except (json.JSONDecodeError, TypeError):
                feedbacks = []
            # 提取痛点汇总
            all_pain_points = []
            for fb in feedbacks:
                all_pain_points.extend(fb.get("pain_points", []))

            alerts.append({
                "chapter_number": r["chapter_number"],
                "avg_churn_risk": r.get("avg_churn_risk", 0),
                "pain_points": all_pain_points[:6],
                "pacing_verdict": r.get("pacing_verdict", ""),
                "analyzed_at": r.get("created_at"),
            })
        return {"success": True, "data": {
            "novel_id": novel_id,
            "threshold": threshold,
            "alerts": alerts,
            "total": len(alerts),
        }}
    except Exception as e:
        logger.error("获取劝退告警失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
