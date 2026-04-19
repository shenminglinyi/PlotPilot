"""Writer Block API endpoints."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from application.analyst.services.tension_analyzer import TensionAnalyzer
from application.workbench.dtos.writer_block_dto import TensionSlingshotRequest, TensionDiagnosis
from interfaces.api.dependencies import get_tension_analyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["writer-block"])


@router.post("/{novel_id}/writer-block/tension-slingshot", response_model=TensionDiagnosis)
async def tension_slingshot(
    novel_id: str,
    request: TensionSlingshotRequest,
    analyzer: TensionAnalyzer = Depends(get_tension_analyzer)
) -> TensionDiagnosis:
    """
    Analyze writer's block and generate breakthrough suggestions.

    This endpoint analyzes the tension level of a specific chapter,
    diagnoses the root cause of writer's block, and provides concrete
    actionable suggestions to break through.

    Args:
        novel_id: The novel ID
        request: Tension slingshot request with chapter number and optional stuck reason
        analyzer: Injected tension analyzer service

    Returns:
        TensionDiagnosis with diagnosis, tension level, missing elements, and suggestions

    Raises:
        HTTPException: 400 if validation fails, 500 if internal error occurs
    """
    try:
        # Validate novel_id matches request
        if request.novel_id != novel_id:
            raise HTTPException(
                status_code=400,
                detail="Novel ID in path does not match request body"
            )

        # Analyze tension
        diagnosis = await analyzer.analyze_tension(request)

        logger.info(
            f"Analyzed tension for novel {novel_id}, chapter {request.chapter_number}: "
            f"level={diagnosis.tension_level}, missing={len(diagnosis.missing_elements)}"
        )
        return diagnosis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing tension: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
