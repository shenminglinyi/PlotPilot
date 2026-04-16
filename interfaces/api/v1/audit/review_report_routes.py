from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict

from application.audit.services.chapter_review_service import ChapterReviewService
from interfaces.api.dependencies import get_chapter_review_service


router = APIRouter(prefix="/api/v1/novels", tags=["review-report"])


class ReviewReportIssueResponse(BaseModel):
    severity: str
    category: str
    description: str
    location: str
    suggestion: Optional[str] = None


class ReviewReportResponse(BaseModel):
    chapter_number: int
    issues: List[ReviewReportIssueResponse]
    overall_score: float
    summary: Dict[str, int]
    reviewed_at: str


@router.get(
    "/{novel_id}/chapters/{chapter_number}/review-report",
    response_model=ReviewReportResponse,
)
async def get_review_report(
    novel_id: str,
    chapter_number: int,
    service: ChapterReviewService = Depends(get_chapter_review_service),
):
    try:
        report = await service.generate_structured_review_report(novel_id, chapter_number)
        return ReviewReportResponse(
            chapter_number=report.chapter_number,
            issues=[
                ReviewReportIssueResponse(
                    severity=issue.severity,
                    category=issue.category,
                    description=issue.description,
                    location=issue.location,
                    suggestion=issue.suggestion,
                )
                for issue in report.issues
            ],
            overall_score=report.overall_score,
            summary=report.summary,
            reviewed_at=report.reviewed_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review report generation failed: {str(e)}")
