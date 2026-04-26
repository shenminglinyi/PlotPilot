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
        from infrastructure.ai.llm_client import LLMClient
        try:
            from interfaces.api.dependencies import get_knowledge_repository
            knowledge_repo = get_knowledge_repository()
        except Exception:
            knowledge_repo = None

        # 使用 LLMClient 包装器（接受字符串 prompt，自动构建 GenerationConfig）
        llm_client = LLMClient(provider=get_llm_service())

        _service = ReaderSimulationService(
            chapter_repository=get_chapter_repository(),
            llm_client=llm_client,
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

    Returns:
        200: 成功，data 为完整读者模拟报告
        400: 章节不存在或内容为空（不是 LLM 问题）
        502: LLM 调用或解析失败（is_fallback=True 情况）
        500: 其他意外错误

    Notes:
        - 降级结果（LLM 失败等）**不会持久化**，避免后续查询返回假数据
        - 持久化失败会在响应中通过 meta.persisted=false 明确告知，不会静默
    """
    try:
        service = _get_service()
        report: ChapterReaderReportDTO = await service.simulate(
            novel_id=novel_id,
            chapter_number=chapter_number,
        )
    except Exception as e:
        logger.exception(
            "读者模拟意外失败 novel=%s ch=%d", novel_id, chapter_number
        )
        raise HTTPException(
            status_code=500,
            detail=f"读者模拟分析失败: {type(e).__name__}: {e}",
        )

    # 降级分支（章节不存在/LLM 失败等）：拒绝持久化，返回更明确的状态码
    if report.is_fallback:
        msg = report.error_message or "读者模拟失败"
        # 「章节不存在/内容为空」是客户端问题，其他是上游 LLM 问题
        is_client_error = (
            "章节不存在" in msg or "章节内容为空" in msg
        )
        status_code = 400 if is_client_error else 502
        logger.warning(
            "读者模拟降级 novel=%s ch=%d status=%d: %s",
            novel_id, chapter_number, status_code, msg,
        )
        raise HTTPException(status_code=status_code, detail=msg)

    # 正常结果：尝试持久化，失败时将状态透出给客户端而非静默
    persisted = True
    persist_error: Optional[str] = None
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
        persisted = False
        persist_error = f"{type(e).__name__}: {e}"
        logger.exception(
            "读者模拟结果持久化失败 novel=%s ch=%d", novel_id, chapter_number
        )

    return {
        "success": True,
        "data": report.to_dict(),
        "meta": {
            "persisted": persisted,
            "persist_error": persist_error,
        },
    }


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
