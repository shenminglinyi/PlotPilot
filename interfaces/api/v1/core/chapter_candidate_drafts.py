"""Chapter candidate draft API routes."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from application.core.dtos.chapter_candidate_draft_dto import ChapterCandidateDraftDTO
from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt
from domain.shared.exceptions import EntityNotFoundError
from interfaces.api.dependencies import (
    get_chapter_aftermath_pipeline,
    get_chapter_candidate_draft_service,
    get_database,
    get_llm_service,
    get_llm_provider_factory,
    get_novel_service,
    get_snapshot_service,
)


async def _run_candidate_draft_aftermath(
    novel_id: str,
    chapter_number: int,
    content: str,
    pipeline: ChapterAftermathPipeline,
) -> None:
    await pipeline.run_after_chapter_saved(novel_id, chapter_number, content)
    try:
        from interfaces.api.dependencies import get_continuity_overview_service

        get_continuity_overview_service().auto_record_chapter_signals(
            novel_id,
            chapter_number,
            content,
        )
    except Exception:
        # 连续性结构化沉淀是章后增强，不应阻断候选稿采纳主链路。
        return


router = APIRouter(prefix="/novels", tags=["chapter-candidate-drafts"])


class CreateChapterCandidateDraftRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=50)
    title: str = Field(default="", max_length=200)
    content: str = Field(..., min_length=1)
    rationale: str = Field(default="", max_length=2000)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    branch_name: str = Field(default="main", max_length=100)


class ChapterCandidateDraftResponse(BaseModel):
    id: str
    novel_id: str
    chapter_number: int
    branch_name: str
    source: str
    status: str
    title: str
    content: str
    rationale: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    @classmethod
    def from_dto(cls, dto: ChapterCandidateDraftDTO) -> "ChapterCandidateDraftResponse":
        return cls(
            id=dto.id,
            novel_id=dto.novel_id,
            chapter_number=dto.chapter_number,
            branch_name=dto.branch_name,
            source=dto.source,
            status=dto.status,
            title=dto.title,
            content=dto.content,
            rationale=dto.rationale,
            metadata=dto.metadata,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


class AcceptChapterCandidateDraftResponse(BaseModel):
    draft: ChapterCandidateDraftResponse
    chapter: Dict[str, Any]
    snapshot_id: str


class CandidateParagraphCompareItem(BaseModel):
    index: int
    type: str
    primary: str
    candidate: str
    similarity: float


class CandidateDraftCompareResponse(BaseModel):
    draft: ChapterCandidateDraftResponse
    primary_word_count: int
    candidate_word_count: int
    similarity: float
    paragraphs: List[CandidateParagraphCompareItem]


class CandidateBranchSummary(BaseModel):
    branch_name: str
    draft_count: int
    accepted_count: int
    updated_at: str = ""


class MergeBranchRequest(BaseModel):
    source_branch: str = Field(..., min_length=1, max_length=100)
    target_branch: str = Field(default="main", max_length=100)
    rule: str = Field(default="latest_candidate", max_length=80)


class BranchMemoryImpactItem(BaseModel):
    label: str
    level: str
    detail: str


class BranchMemoryDiffResponse(BaseModel):
    novel_id: str
    chapter_number: int
    source_branch: str
    target_branch: str
    source_draft_count: int
    target_draft_count: int
    source_latest_draft_id: str = ""
    target_latest_draft_id: str = ""
    similarity: float
    memory_impacts: List[BranchMemoryImpactItem]


class ExternalModelTaskRequest(BaseModel):
    id: str = ""
    chapter_number: int = Field(..., ge=1)
    model: str = ""
    prompt: str = ""
    instruction: str = ""
    source_draft_id: str = ""
    candidate_draft_id: str = ""
    response_preview: str = ""
    status: str = "prompted"
    execution_mode: str = "copy_paste"


class ExternalModelTaskResponse(BaseModel):
    id: str
    novel_id: str
    chapter_number: int
    model: str
    prompt: str
    instruction: str
    source_draft_id: str
    candidate_draft_id: str
    response_preview: str
    status: str
    execution_mode: str
    created_at: str
    updated_at: str


class GenerateCandidateDraftRequest(BaseModel):
    chapter_number: int = Field(..., ge=1)
    outline: str = Field(..., min_length=1)
    current_content: str = ""
    branch_name: str = "main"
    title: str = ""
    source: str = "direct-model"
    model_label: str = ""
    llm_profile_id: str = ""
    task_prompt: str = ""
    max_tokens: int = Field(default=4096, ge=256, le=32000)
    temperature: float = Field(default=0.8, ge=0, le=2)


class GenerateCandidateDraftResponse(BaseModel):
    draft: ChapterCandidateDraftResponse
    task: ExternalModelTaskResponse


class SupervisorReviewCandidateDraftRequest(BaseModel):
    model_label: str = ""
    llm_profile_id: str = ""
    focus: str = "检查记忆、连续性、战力崩坏和采纳建议。"
    max_tokens: int = Field(default=2048, ge=256, le=16000)
    temperature: float = Field(default=0.2, ge=0, le=2)


class SupervisorReviewCandidateDraftResponse(BaseModel):
    draft_id: str
    model_label: str
    review: str
    task: ExternalModelTaskResponse


def _task_row_to_response(row: Dict[str, Any]) -> ExternalModelTaskResponse:
    return ExternalModelTaskResponse(
        id=str(row.get("id") or ""),
        novel_id=str(row.get("novel_id") or ""),
        chapter_number=int(row.get("chapter_number") or 0),
        model=str(row.get("model") or ""),
        prompt=str(row.get("prompt") or ""),
        instruction=str(row.get("instruction") or ""),
        source_draft_id=str(row.get("source_draft_id") or ""),
        candidate_draft_id=str(row.get("candidate_draft_id") or ""),
        response_preview=str(row.get("response_preview") or ""),
        status=str(row.get("status") or "prompted"),
        execution_mode=str(row.get("execution_mode") or "copy_paste"),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _upsert_external_model_task(db, novel_id: str, request: ExternalModelTaskRequest) -> Dict[str, Any]:
    task_id = request.id.strip() or str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    existing = db.fetch_one("SELECT id, created_at FROM external_model_tasks WHERE id = ?", (task_id,))
    if existing:
        db.execute(
            """
            UPDATE external_model_tasks
            SET novel_id = ?, chapter_number = ?, model = ?, prompt = ?, instruction = ?,
                source_draft_id = ?, candidate_draft_id = ?, response_preview = ?,
                status = ?, execution_mode = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                novel_id,
                request.chapter_number,
                request.model,
                request.prompt,
                request.instruction,
                request.source_draft_id,
                request.candidate_draft_id,
                request.response_preview,
                request.status,
                request.execution_mode,
                now,
                task_id,
            ),
        )
    else:
        db.execute(
            """
            INSERT INTO external_model_tasks (
                id, novel_id, chapter_number, model, prompt, instruction,
                source_draft_id, candidate_draft_id, response_preview,
                status, execution_mode, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                novel_id,
                request.chapter_number,
                request.model,
                request.prompt,
                request.instruction,
                request.source_draft_id,
                request.candidate_draft_id,
                request.response_preview,
                request.status,
                request.execution_mode,
                now,
                now,
            ),
        )
    db.commit()
    return db.fetch_one("SELECT * FROM external_model_tasks WHERE id = ?", (task_id,)) or {}


def _mark_external_task_status(db, novel_id: str, candidate_draft_id: str, status: str) -> None:
    if not candidate_draft_id:
        return
    db.execute(
        """
        UPDATE external_model_tasks
        SET status = ?, updated_at = ?
        WHERE novel_id = ? AND candidate_draft_id = ?
        """,
        (status, datetime.utcnow().isoformat(), novel_id, candidate_draft_id),
    )
    db.commit()


@router.post(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts",
    response_model=ChapterCandidateDraftResponse,
    status_code=201,
)
async def create_candidate_draft(
    novel_id: str,
    request: CreateChapterCandidateDraftRequest,
    chapter_number: int = Path(..., ge=1),
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")

    draft = service.create_draft(
        novel_id=novel_id,
        chapter_number=chapter_number,
        source=request.source,
        title=request.title,
        content=request.content,
        rationale=request.rationale,
        metadata=request.metadata,
        branch_name=request.branch_name,
    )
    return ChapterCandidateDraftResponse.from_dto(draft)


@router.post(
    "/{novel_id}/candidate-drafts/generate",
    response_model=GenerateCandidateDraftResponse,
    status_code=201,
)
async def generate_candidate_draft(
    novel_id: str,
    request: GenerateCandidateDraftRequest,
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
    llm_service: LLMService = Depends(get_llm_service),
    llm_provider_factory=Depends(get_llm_provider_factory),
    db=Depends(get_database),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")

    system = (
        "你是 PlotPilot 内部直连写作模型。你只输出完整章节正文，"
        "不要输出解释、标题、分析、Markdown 代码块或候选稿说明。"
    )
    user = "\n".join(
        [
            f"小说 ID：{novel_id}",
            f"章节：第 {request.chapter_number} 章",
            f"写作模型标签：{request.model_label or '当前激活 LLM 配置'}",
            "",
            "【任务约束】",
            request.task_prompt.strip() or "根据大纲生成或改写本章正文。",
            "",
            "【章节大纲】",
            request.outline.strip(),
            "",
            "【当前主稿】",
            request.current_content.strip() or "（当前主稿为空，请生成完整章节正文。）",
            "",
            "【输出要求】",
            "1. 保留已确定事实、角色关系、伏笔和战力规则。",
            "2. 若是改稿，只改正文表达和必要衔接，不要改动无关剧情。",
            "3. 输出会进入候选稿，不会直接覆盖主稿。",
        ]
    )
    prompt = Prompt(system=system, user=user)
    model_service = (
        llm_provider_factory.create_by_profile_id(request.llm_profile_id)
        if request.llm_profile_id.strip()
        else llm_service
    )
    try:
        result = await model_service.generate(
            prompt,
            GenerationConfig(max_tokens=request.max_tokens, temperature=request.temperature),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"模型生成失败：{exc}") from exc

    content = result.content.strip()
    draft = service.create_draft(
        novel_id=novel_id,
        chapter_number=request.chapter_number,
        source=request.source or "direct-model",
        title=request.title or f"第{request.chapter_number}章 直连模型候选稿",
        content=content,
        rationale=request.task_prompt or request.outline,
        metadata={
            "direct_model": True,
            "model_label": request.model_label,
            "llm_profile_id": request.llm_profile_id,
            "outline": request.outline,
            "execution_mode": "direct_api",
        },
        branch_name=request.branch_name or "main",
    )
    task_row = _upsert_external_model_task(
        db,
        novel_id,
        ExternalModelTaskRequest(
            chapter_number=request.chapter_number,
            model=request.model_label or "active-llm",
            prompt=user,
            instruction=request.task_prompt or request.outline,
            candidate_draft_id=draft.id,
            response_preview=content[:160],
            status="imported",
            execution_mode="direct_api",
        ),
    )
    return GenerateCandidateDraftResponse(
        draft=ChapterCandidateDraftResponse.from_dto(draft),
        task=_task_row_to_response(task_row),
    )


@router.get(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts",
    response_model=List[ChapterCandidateDraftResponse],
)
async def list_candidate_drafts(
    novel_id: str,
    chapter_number: int = Path(..., ge=1),
    branch_name: Optional[str] = None,
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")

    drafts = service.list_drafts(
        novel_id,
        chapter_number,
        branch_name=branch_name,
    )
    return [ChapterCandidateDraftResponse.from_dto(item) for item in drafts]


@router.get(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts/branches",
    response_model=List[CandidateBranchSummary],
)
async def list_candidate_branches(
    novel_id: str,
    chapter_number: int = Path(..., ge=1),
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")
    return [CandidateBranchSummary(**item) for item in service.list_branch_summaries(novel_id, chapter_number)]


@router.get(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts/{draft_id}/compare",
    response_model=CandidateDraftCompareResponse,
)
async def compare_candidate_draft(
    novel_id: str,
    draft_id: str,
    chapter_number: int = Path(..., ge=1),
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")
    try:
        payload = service.compare_with_primary(draft_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    draft = payload["draft"]
    if draft.novel_id != novel_id or draft.chapter_number != chapter_number:
        raise HTTPException(status_code=400, detail="Draft chapter mismatch")
    return CandidateDraftCompareResponse(
        draft=ChapterCandidateDraftResponse.from_dto(draft),
        primary_word_count=payload["primary_word_count"],
        candidate_word_count=payload["candidate_word_count"],
        similarity=payload["similarity"],
        paragraphs=[CandidateParagraphCompareItem(**item) for item in payload["paragraphs"]],
    )


@router.post(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts/merge-branch",
    response_model=ChapterCandidateDraftResponse,
    status_code=201,
)
async def merge_candidate_branch(
    request: MergeBranchRequest,
    novel_id: str,
    chapter_number: int = Path(..., ge=1),
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")
    try:
        draft = service.merge_branch_to_candidate(
            novel_id=novel_id,
            chapter_number=chapter_number,
            source_branch=request.source_branch,
            target_branch=request.target_branch,
            rule=request.rule,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return ChapterCandidateDraftResponse.from_dto(draft)


@router.get(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts/branch-memory-diff",
    response_model=BranchMemoryDiffResponse,
)
async def get_candidate_branch_memory_diff(
    novel_id: str,
    chapter_number: int = Path(..., ge=1),
    source_branch: str = "main",
    target_branch: str = "main",
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")
    payload = service.build_branch_memory_diff(
        novel_id=novel_id,
        chapter_number=chapter_number,
        source_branch=source_branch,
        target_branch=target_branch,
    )
    return BranchMemoryDiffResponse(**payload)


@router.post(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts/{draft_id}/supervisor-review",
    response_model=SupervisorReviewCandidateDraftResponse,
    status_code=201,
)
async def review_candidate_draft_with_supervisor(
    request: SupervisorReviewCandidateDraftRequest,
    novel_id: str,
    draft_id: str,
    chapter_number: int = Path(..., ge=1),
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
    llm_service: LLMService = Depends(get_llm_service),
    llm_provider_factory=Depends(get_llm_provider_factory),
    db=Depends(get_database),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")
    try:
        compare_payload = service.compare_with_primary(draft_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    draft = compare_payload["draft"]
    if draft.novel_id != novel_id or draft.chapter_number != chapter_number:
        raise HTTPException(status_code=400, detail="Draft chapter mismatch")

    primary_text = "\n\n".join(
        item.get("primary", "")
        for item in compare_payload.get("paragraphs", [])
        if item.get("primary")
    )
    system = (
        "你是 PlotPilot 的审稿/记忆监督模型。你不改写正文，只做采纳前检查。"
        "请用中文输出结构化意见，重点指出需要作者确认或写入记忆系统的事项。"
    )
    user = "\n".join(
        [
            f"小说 ID：{novel_id}",
            f"章节：第 {chapter_number} 章",
            f"审稿/记忆模型标签：{request.model_label or '当前激活 LLM 配置'}",
            "",
            "【检查重点】",
            request.focus.strip() or "检查记忆、连续性、战力崩坏和采纳建议。",
            "",
            "【当前主稿】",
            primary_text.strip() or "（当前主稿为空）",
            "",
            "【候选稿】",
            draft.content.strip(),
            "",
            "【输出格式】",
            "1. 采纳建议：建议采纳 / 建议修改后采纳 / 不建议采纳。",
            "2. 记忆影响：列出会新增或改变的事实、关系、伏笔、战力状态。",
            "3. 连续性风险：列出可能冲突或需要补写的地方。",
            "4. 必须保留与禁止改动：给出简短清单。",
        ]
    )
    model_service = (
        llm_provider_factory.create_by_profile_id(request.llm_profile_id)
        if request.llm_profile_id.strip()
        else llm_service
    )
    try:
        result = await model_service.generate(
            Prompt(system=system, user=user),
            GenerationConfig(max_tokens=request.max_tokens, temperature=request.temperature),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"监督模型检查失败：{exc}") from exc

    review = result.content.strip()
    task_row = _upsert_external_model_task(
        db,
        novel_id,
        ExternalModelTaskRequest(
            chapter_number=chapter_number,
            model=request.model_label or "supervisor-llm",
            prompt=user,
            instruction=request.focus,
            candidate_draft_id=draft.id,
            response_preview=review[:160],
            status="reviewed",
            execution_mode="supervisor_api",
        ),
    )
    return SupervisorReviewCandidateDraftResponse(
        draft_id=draft.id,
        model_label=request.model_label,
        review=review,
        task=_task_row_to_response(task_row),
    )


@router.get(
    "/{novel_id}/external-model-tasks",
    response_model=List[ExternalModelTaskResponse],
)
async def list_external_model_tasks(
    novel_id: str,
    chapter_number: Optional[int] = None,
    db=Depends(get_database),
):
    sql = "SELECT * FROM external_model_tasks WHERE novel_id = ?"
    params: List[Any] = [novel_id]
    if chapter_number is not None:
        sql += " AND chapter_number = ?"
        params.append(chapter_number)
    sql += " ORDER BY updated_at DESC LIMIT 200"
    rows = db.fetch_all(sql, tuple(params))
    return [_task_row_to_response(row) for row in rows]


@router.post(
    "/{novel_id}/external-model-tasks",
    response_model=ExternalModelTaskResponse,
    status_code=201,
)
async def upsert_external_model_task(
    request: ExternalModelTaskRequest,
    novel_id: str,
    db=Depends(get_database),
):
    row = _upsert_external_model_task(db, novel_id, request)
    return _task_row_to_response(row)


@router.post(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts/{draft_id}/accept",
    response_model=AcceptChapterCandidateDraftResponse,
)
async def accept_candidate_draft(
    novel_id: str,
    draft_id: str,
    background_tasks: BackgroundTasks,
    chapter_number: int = Path(..., ge=1),
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
    pipeline: ChapterAftermathPipeline = Depends(get_chapter_aftermath_pipeline),
    snapshot_service=Depends(get_snapshot_service),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")

    try:
        accepted = service.accept_draft_as_primary(draft_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    draft = accepted["draft"]
    chapter = accepted["chapter"]

    if draft.novel_id != novel_id or draft.chapter_number != chapter_number:
        raise HTTPException(status_code=400, detail="Draft chapter mismatch")

    snapshot_id = snapshot_service.create_snapshot(
        novel_id=novel_id,
        trigger_type="MANUAL",
        name=f"[候选稿采纳] 第{chapter_number}章 · {draft.source}",
        description=draft.rationale or "accept candidate draft as primary chapter",
        branch_name=draft.branch_name or "main",
    )
    background_tasks.add_task(
        _run_candidate_draft_aftermath,
        novel_id,
        chapter_number,
        chapter.content,
        pipeline,
    )
    _mark_external_task_status(get_database(), novel_id, draft.id, "accepted")
    return AcceptChapterCandidateDraftResponse(
        draft=ChapterCandidateDraftResponse.from_dto(draft),
        chapter={
            "id": chapter.id,
            "novel_id": chapter.novel_id,
            "number": chapter.number,
            "title": chapter.title,
            "content": chapter.content,
            "word_count": chapter.word_count,
            "status": chapter.status,
        },
        snapshot_id=snapshot_id,
    )


@router.post(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts/{draft_id}/reject",
    response_model=ChapterCandidateDraftResponse,
)
async def reject_candidate_draft(
    novel_id: str,
    draft_id: str,
    chapter_number: int = Path(..., ge=1),
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")
    try:
        draft = service.reject_draft(draft_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if draft.novel_id != novel_id or draft.chapter_number != chapter_number:
        raise HTTPException(status_code=400, detail="Draft chapter mismatch")
    return ChapterCandidateDraftResponse.from_dto(draft)
