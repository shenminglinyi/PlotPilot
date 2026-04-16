"""Voice API 路由"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from typing import List, Optional

from application.analyst.services.voice_sample_service import VoiceSampleService
from interfaces.api.dependencies import (
    get_voice_sample_service,
    get_voice_fingerprint_service,
    get_voice_drift_service,
)
from domain.shared.exceptions import EntityNotFoundError


router = APIRouter(tags=["voice"])


# Request Models
class VoiceSampleRequest(BaseModel):
    """文风样本请求"""
    ai_original: str = Field(..., min_length=1, description="AI 原文")
    author_refined: str = Field(..., min_length=1, description="作者改稿")
    chapter_number: int = Field(..., ge=1, description="章节号")
    scene_type: Optional[str] = Field(default="general", description="场景类型")


# Response Models
class VoiceSampleResponse(BaseModel):
    """文风样本响应"""
    sample_id: str = Field(..., description="样本 ID")


class VoiceFingerprintResponse(BaseModel):
    """文风指纹响应"""
    adjective_density: float = Field(..., description="形容词密度")
    avg_sentence_length: float = Field(..., description="平均句长")
    sentence_count: int = Field(..., description="句子数量")
    sample_count: int = Field(..., description="样本数量")
    last_updated: str = Field(..., description="最后更新时间")


@router.post(
    "/novels/{novel_id}/voice/samples",
    response_model=VoiceSampleResponse,
    status_code=201,
    summary="创建文风样本",
    description="添加 AI 原文和作者改稿的文风样本对"
)
def create_voice_sample(
    novel_id: str = Path(..., description="小说 ID"),
    request: VoiceSampleRequest = ...,
    service: VoiceSampleService = Depends(get_voice_sample_service)
) -> VoiceSampleResponse:
    """
    创建文风样本

    Args:
        novel_id: 小说 ID
        request: 文风样本请求
        service: 文风样本服务

    Returns:
        VoiceSampleResponse: 包含样本 ID 的响应
    """
    try:
        sample_id = service.append_sample(
            novel_id=novel_id,
            chapter_number=request.chapter_number,
            scene_type=request.scene_type,
            ai_original=request.ai_original,
            author_refined=request.author_refined
        )
        return VoiceSampleResponse(sample_id=sample_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create voice sample: {str(e)}")


@router.get(
    "/novels/{novel_id}/voice/fingerprint",
    response_model=VoiceFingerprintResponse,
    status_code=200,
    summary="获取文风指纹",
    description="获取小说的文风指纹统计数据"
)
def get_voice_fingerprint(
    novel_id: str = Path(..., description="小说 ID"),
    pov_character_id: Optional[str] = Query(None, description="POV 角色 ID"),
    service=Depends(get_voice_fingerprint_service)
) -> VoiceFingerprintResponse:
    """
    获取文风指纹

    Args:
        novel_id: 小说 ID
        pov_character_id: 可选的 POV 角色 ID
        service: 文风指纹服务

    Returns:
        VoiceFingerprintResponse: 文风指纹数据
    """
    try:
        fingerprint = service.fingerprint_repo.get_by_novel(novel_id, pov_character_id)
        if not fingerprint:
            # 返回默认的空指纹而不是 404
            return VoiceFingerprintResponse(
                adjective_density=0.0,
                avg_sentence_length=0.0,
                sentence_count=0,
                sample_count=0,
                last_updated=datetime.now().isoformat()
            )

        return VoiceFingerprintResponse(
            adjective_density=fingerprint["adjective_density"],
            avg_sentence_length=fingerprint["avg_sentence_length"],
            sentence_count=fingerprint["sentence_count"],
            sample_count=fingerprint["sample_count"],
            last_updated=fingerprint["last_updated"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get voice fingerprint: {str(e)}")


# ----- 文风漂移监控 -----

class StyleScoreItem(BaseModel):
    chapter_number: int
    similarity_score: float
    adjective_density: float
    avg_sentence_length: float
    sentence_count: int
    computed_at: str


class DriftReportResponse(BaseModel):
    novel_id: str
    scores: List[StyleScoreItem]
    drift_alert: bool
    alert_threshold: float
    alert_consecutive: int


class ScoreChapterRequest(BaseModel):
    chapter_number: int = Field(..., ge=1)
    content: str = Field(..., min_length=1)
    pov_character_id: Optional[str] = None


class ScoreChapterResponse(BaseModel):
    chapter_number: int
    similarity_score: Optional[float]
    drift_alert: bool


@router.post(
    "/novels/{novel_id}/voice/drift/score",
    response_model=ScoreChapterResponse,
    status_code=200,
    summary="计算章节文风评分",
    description="计算指定章节内容与作者指纹的相似度并持久化"
)
def score_chapter_style(
    novel_id: str = Path(..., description="小说 ID"),
    request: ScoreChapterRequest = ...,
    service=Depends(get_voice_drift_service),
) -> ScoreChapterResponse:
    try:
        result = service.score_chapter(
            novel_id=novel_id,
            chapter_number=request.chapter_number,
            content=request.content,
            pov_character_id=request.pov_character_id,
        )
        return ScoreChapterResponse(
            chapter_number=result["chapter_number"],
            similarity_score=result["similarity_score"],
            drift_alert=result["drift_alert"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to score chapter: {str(e)}")


@router.get(
    "/novels/{novel_id}/voice/drift",
    response_model=DriftReportResponse,
    status_code=200,
    summary="获取文风漂移报告",
    description="返回全量章节评分序列与当前漂移告警状态"
)
def get_drift_report(
    novel_id: str = Path(..., description="小说 ID"),
    service=Depends(get_voice_drift_service),
) -> DriftReportResponse:
    try:
        report = service.get_drift_report(novel_id)
        return DriftReportResponse(
            novel_id=report["novel_id"],
            scores=[StyleScoreItem(**s) for s in report["scores"]],
            drift_alert=report["drift_alert"],
            alert_threshold=report["alert_threshold"],
            alert_consecutive=report["alert_consecutive"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get drift report: {str(e)}")
