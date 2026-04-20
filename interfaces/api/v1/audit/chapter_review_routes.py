"""
章节审稿 API 路由
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from application.audit.services.chapter_review_service import ChapterReviewService
from interfaces.api.dependencies import get_chapter_review_service


router = APIRouter(prefix="/chapter-reviews", tags=["chapter-reviews"])


class ConsistencyIssueResponse(BaseModel):
    """一致性问题响应"""
    issue_type: str
    severity: str
    description: str
    location: str
    suggestion: Optional[str] = None


class ChapterReviewResponse(BaseModel):
    """章节审稿响应"""
    chapter_number: int
    issues: List[ConsistencyIssueResponse]
    overall_score: float
    improvement_suggestions: List[str]
    reviewed_at: str


@router.post("/{novel_id}/chapters/{chapter_number}", response_model=ChapterReviewResponse)
async def review_chapter(
    novel_id: str,
    chapter_number: int,
    service: ChapterReviewService = Depends(get_chapter_review_service)
):
    """
    审稿章节

    对指定章节进行一致性检查和质量审核，包括：
    - 人物一致性检查
    - 时间线一致性检查
    - 故事线连贯性检查
    - 伏笔使用检查
    - 改进建议生成
    """
    try:
        result = await service.review_chapter(novel_id, chapter_number)

        return ChapterReviewResponse(
            chapter_number=result.chapter_number,
            issues=[
                ConsistencyIssueResponse(
                    issue_type=issue.issue_type,
                    severity=issue.severity,
                    description=issue.description,
                    location=issue.location,
                    suggestion=issue.suggestion
                )
                for issue in result.issues
            ],
            overall_score=result.overall_score,
            improvement_suggestions=result.improvement_suggestions,
            reviewed_at=result.reviewed_at.isoformat()
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {str(e)}")
