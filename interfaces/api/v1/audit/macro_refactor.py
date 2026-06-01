"""Macro Refactor API endpoints."""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from application.audit.services.macro_refactor_scanner import MacroRefactorScanner
from application.audit.services.macro_refactor_proposal_service import (
    MacroRefactorProposalError,
    MacroRefactorProposalService,
)
from application.audit.services.mutation_applier import MutationApplier
from application.audit.services.macro_diagnosis_service import MacroDiagnosisService
from application.audit.dtos.macro_refactor_dto import (
    LogicBreakpoint,
    RefactorProposalRequest,
    RefactorProposal,
    ApplyMutationRequest,
    ApplyMutationResponse
)
from interfaces.api.dependencies import (
    get_macro_refactor_scanner,
    get_macro_refactor_proposal_service,
    get_mutation_applier,
    get_macro_diagnosis_service
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["macro-refactor"])


@router.get("/{novel_id}/macro-refactor/breakpoints", response_model=List[LogicBreakpoint])
async def scan_breakpoints(
    novel_id: str,
    trait: str = Query(..., description="Target character trait (e.g., '冷酷')"),
    conflict_tags: Optional[str] = Query(None, description="Custom conflict tags (comma-separated)"),
    scanner: MacroRefactorScanner = Depends(get_macro_refactor_scanner)
) -> List[LogicBreakpoint]:
    """
    Scan for logic breakpoints where events conflict with character traits.

    This endpoint analyzes all narrative events in a novel to identify points
    where event tags conflict with a specified character trait.

    Args:
        novel_id: The novel ID
        trait: Target character trait to check for conflicts (e.g., "冷酷", "理性")
        conflict_tags: Optional comma-separated list of custom conflict tags
        scanner: Injected macro refactor scanner service

    Returns:
        List of logic breakpoints with conflict details

    Raises:
        HTTPException: 500 if internal error occurs
    """
    try:
        # Parse conflict_tags if provided
        parsed_conflict_tags = None
        if conflict_tags:
            parsed_conflict_tags = [tag.strip() for tag in conflict_tags.split(",") if tag.strip()]

        # Scan for breakpoints
        breakpoints = scanner.scan_breakpoints(
            novel_id=novel_id,
            trait=trait,
            conflict_tags=parsed_conflict_tags
        )

        logger.info(f"Scanned novel {novel_id} for trait '{trait}', found {len(breakpoints)} breakpoints")
        return breakpoints

    except Exception as e:
        logger.error(f"Error scanning breakpoints: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{novel_id}/macro-refactor/proposals", response_model=RefactorProposal)
async def generate_proposal(
    novel_id: str,
    request: RefactorProposalRequest = Body(...),
    proposal_service: MacroRefactorProposalService = Depends(get_macro_refactor_proposal_service)
) -> RefactorProposal:
    """
    Generate refactor proposal using LLM.

    This endpoint analyzes a narrative event and generates structured suggestions
    for fixing character trait conflicts or narrative inconsistencies.

    Args:
        novel_id: The novel ID
        request: Refactor proposal request with event details and author intent
        proposal_service: Injected macro refactor proposal service

    Returns:
        RefactorProposal with natural language suggestions and structured mutations

    Raises:
        HTTPException: 500 if internal error occurs
    """
    try:
        # Generate proposal using LLM
        proposal = await proposal_service.generate_proposal(request)

        logger.info(
            f"Generated proposal for novel {novel_id}, event {request.event_id}: "
            f"{len(proposal.suggested_mutations)} mutations"
        )
        return proposal

    except MacroRefactorProposalError as e:
        logger.error(f"Error generating proposal: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating proposal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{novel_id}/macro-refactor/apply", response_model=ApplyMutationResponse)
async def apply_mutations(
    novel_id: str,
    request: ApplyMutationRequest = Body(...),
    mutation_applier: MutationApplier = Depends(get_mutation_applier)
) -> ApplyMutationResponse:
    """
    Apply mutations to a narrative event.

    This endpoint applies a list of mutations (add_tag, remove_tag, replace_summary)
    to a specific narrative event, updating it atomically.

    Args:
        novel_id: The novel ID
        request: Apply mutation request with event_id, mutations, and optional reason
        mutation_applier: Injected mutation applier service

    Returns:
        ApplyMutationResponse with success status, updated event, and applied mutations

    Raises:
        HTTPException: 400 if event not found, 500 if internal error occurs
    """
    try:
        # Apply mutations
        result = mutation_applier.apply_mutations(
            novel_id=novel_id,
            event_id=request.event_id,
            mutations=request.mutations,
            reason=request.reason
        )

        logger.info(
            f"Applied {len(result['applied_mutations'])} mutations to event {request.event_id} "
            f"in novel {novel_id}"
        )

        return ApplyMutationResponse(
            success=result["success"],
            updated_event=result["updated_event"],
            applied_mutations=result["applied_mutations"]
        )

    except ValueError as e:
        logger.warning(f"Event not found: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error applying mutations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ========== 宏观诊断结果 API ==========

@router.get("/{novel_id}/macro-refactor/diagnosis/latest")
async def get_latest_diagnosis(
    novel_id: str,
    diagnosis_service: MacroDiagnosisService = Depends(get_macro_diagnosis_service)
) -> Optional[Dict[str, Any]]:
    """
    获取最新的宏观诊断结果。

    返回最近一次自动或手动触发的诊断结果，包括：
    - 触发原因
    - 扫描的人设标签
    - 发现的冲突断点列表
    - 诊断状态和创建时间

    Args:
        novel_id: 小说 ID
        diagnosis_service: 宏观诊断服务

    Returns:
        最新诊断结果，无结果返回 null

    Raises:
        HTTPException: 500 if internal error occurs
    """
    try:
        result = diagnosis_service.get_latest_result(novel_id)
        return result
    except Exception as e:
        logger.error(f"Error getting latest diagnosis for novel {novel_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{novel_id}/macro-refactor/diagnosis/history")
async def list_diagnosis_history(
    novel_id: str,
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results"),
    diagnosis_service: MacroDiagnosisService = Depends(get_macro_diagnosis_service)
) -> List[Dict[str, Any]]:
    """
    获取宏观诊断历史列表。

    按时间倒序返回诊断结果列表，可用于追踪诊断历史。

    Args:
        novel_id: 小说 ID
        limit: 最大返回数量（默认 10，最大 50）
        diagnosis_service: 宏观诊断服务

    Returns:
        诊断结果列表

    Raises:
        HTTPException: 500 if internal error occurs
    """
    try:
        results = diagnosis_service.list_results(novel_id, limit)
        return results
    except Exception as e:
        logger.error(f"Error listing diagnosis history for novel {novel_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{novel_id}/macro-refactor/diagnosis/run")
async def run_manual_diagnosis(
    novel_id: str,
    traits: Optional[str] = Query(None, description="Comma-separated traits to scan (optional, defaults to built-in)"),
    diagnosis_service: MacroDiagnosisService = Depends(get_macro_diagnosis_service)
) -> Dict[str, Any]:
    """
    手动触发宏观诊断。

    立即执行全人设扫描并返回结果。结果会存储到数据库供后续查询。

    Args:
        novel_id: 小说 ID
        traits: 可选的人设标签列表（逗号分隔），不提供则使用内置规则
        diagnosis_service: 宏观诊断服务

    Returns:
        诊断结果

    Raises:
        HTTPException: 500 if internal error occurs
    """
    try:
        # 解析 traits 参数
        scan_traits = None
        if traits:
            scan_traits = [t.strip() for t in traits.split(",") if t.strip()]

        result = diagnosis_service.run_full_diagnosis(
            novel_id=novel_id,
            trigger_reason="手动触发",
            traits=scan_traits
        )

        return result.to_dict()
    except Exception as e:
        logger.error(f"Error running manual diagnosis for novel {novel_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{novel_id}/macro-refactor/diagnosis/{diagnosis_id}/resolve")
async def mark_diagnosis_resolved(
    novel_id: str,
    diagnosis_id: str,
    diagnosis_service: MacroDiagnosisService = Depends(get_macro_diagnosis_service)
) -> Dict[str, Any]:
    """
    标记诊断结果为已解决。

    已解决的诊断结果不会再注入到后续章节生成的提示词中。
    适用于作者已处理完冲突断点（修复或确认忽略）的情况。

    Args:
        novel_id: 小说 ID
        diagnosis_id: 诊断结果 ID
        diagnosis_service: 宏观诊断服务

    Returns:
        {"success": true/false, "message": "..."}

    Raises:
        HTTPException: 500 if internal error occurs
    """
    try:
        success = diagnosis_service.mark_resolved(novel_id, diagnosis_id, resolved_by="manual")
        
        if success:
            return {"success": True, "message": "诊断结果已标记为已解决，不会再注入提示词"}
        else:
            return {"success": False, "message": "标记失败，请检查诊断结果 ID"}
            
    except Exception as e:
        logger.error(f"Error marking diagnosis as resolved: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

