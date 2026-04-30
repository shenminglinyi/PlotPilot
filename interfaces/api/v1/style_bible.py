"""写作手法知识库 API 路由。"""
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from application.style_bible.dtos import (
    StyleProfileGenerateRequestDTO,
    StyleProfileGenerateResultDTO,
    StyleProfileMatchReportDTO,
    StylePromptOverlayDTO,
    StyleSampleDTO,
    StyleSampleImportRequestDTO,
    StyleSampleImportResultDTO,
    StyleTechniqueCardDTO,
)
from application.style_bible.services.style_profile_service import StyleProfileService
from application.style_bible.services.style_prompt_overlay_service import (
    StylePromptOverlayService,
)
from domain.style_bible.entities import StyleProfile, StyleSample, StyleTechniqueCard
from domain.style_bible.repositories import StyleBibleRepository
from interfaces.api.dependencies import (
    get_style_bible_repository,
    get_style_profile_service,
    get_style_prompt_overlay_service,
)


router = APIRouter(prefix="/style-bible", tags=["style-bible"])


class ImportStyleSampleRequest(BaseModel):
    title: str
    content: str
    source_type: str = "reference"
    genre: str = ""
    scene_type: str = ""
    pov: str = ""
    allowed_for_generation: bool = False
    novel_id: str = ""
    profile_id: str = ""
    create_profile: bool = False
    profile_name: str = ""


class GenerateStyleProfileRequest(BaseModel):
    novel_id: str = ""
    name: str = "写作手法档案"
    description: str = ""
    sample_ids: List[str] = Field(default_factory=list)
    use_llm: bool = False
    llm_profile_id: str = ""


class UpdateTechniqueCardRequest(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    scene_type: Optional[str] = None
    rule_text: Optional[str] = None
    example_summary: Optional[str] = None
    prompt_instruction: Optional[str] = None
    enabled: Optional[bool] = None
    weight: Optional[float] = None

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class BuildStyleOverlayRequest(BaseModel):
    novel_id: str = ""
    style_profile_id: str
    scene_type: str = ""
    max_cards: int = Field(default=6, ge=1, le=12)


class MatchStyleProfileRequest(BaseModel):
    novel_id: str = ""
    content: str


@router.post("/samples", response_model=StyleSampleImportResultDTO)
def import_style_sample(
    request: ImportStyleSampleRequest,
    service: StyleProfileService = Depends(get_style_profile_service),
):
    """导入参考样本，自动切分并分析指标。"""
    try:
        return service.import_sample(StyleSampleImportRequestDTO(**request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/samples", response_model=List[StyleSampleDTO])
def list_style_samples(
    novel_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    repository: StyleBibleRepository = Depends(get_style_bible_repository),
):
    """列出参考样本。"""
    return [
        _sample_to_dto(sample)
        for sample in repository.list_samples(novel_id=novel_id, profile_id=profile_id)
    ]


@router.get("/samples/{sample_id}", response_model=StyleSampleDTO)
def get_style_sample(
    sample_id: str,
    repository: StyleBibleRepository = Depends(get_style_bible_repository),
):
    """获取参考样本详情。"""
    sample = repository.get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="style sample not found")
    return _sample_to_dto(sample)


@router.post("/profiles", response_model=StyleProfileGenerateResultDTO)
def generate_style_profile(
    request: GenerateStyleProfileRequest,
    service: StyleProfileService = Depends(get_style_profile_service),
):
    """从样本生成可编辑写作手法档案。"""
    try:
        return service.generate_profile_from_samples(
            StyleProfileGenerateRequestDTO(**request.model_dump())
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/profiles", response_model=List[dict[str, Any]])
def list_style_profiles(
    novel_id: Optional[str] = None,
    status: Optional[str] = None,
    repository: StyleBibleRepository = Depends(get_style_bible_repository),
):
    """列出写作手法档案。"""
    return [_profile_detail(repository, profile) for profile in repository.list_profiles(novel_id, status)]


@router.get("/profiles/{profile_id}", response_model=dict[str, Any])
def get_style_profile(
    profile_id: str,
    repository: StyleBibleRepository = Depends(get_style_bible_repository),
):
    """获取写作手法档案与技法卡。"""
    profile = repository.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="style profile not found")
    return _profile_detail(repository, profile)


@router.post("/profiles/{profile_id}/match", response_model=StyleProfileMatchReportDTO)
def match_style_profile(
    profile_id: str,
    request: MatchStyleProfileRequest,
    service: StyleProfileService = Depends(get_style_profile_service),
):
    """评估正文与写作手法档案的匹配度。"""
    try:
        return service.match_text(profile_id, request.content, novel_id=request.novel_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/cards/{card_id}", response_model=StyleTechniqueCardDTO)
def update_style_technique_card(
    card_id: str,
    request: UpdateTechniqueCardRequest,
    repository: StyleBibleRepository = Depends(get_style_bible_repository),
):
    """更新技法卡文本或启用状态。"""
    card = repository.get_technique_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="style technique card not found")
    changes = request.changes()
    if not changes:
        raise HTTPException(status_code=400, detail="No technique card fields provided")
    for key, value in changes.items():
        setattr(card, key, value)
    updated = repository.update_technique_card(StyleTechniqueCard(**card.__dict__))
    return _card_to_dto(updated)


@router.post("/overlay/preview", response_model=StylePromptOverlayDTO)
def preview_style_overlay(
    request: BuildStyleOverlayRequest,
    service: StylePromptOverlayService = Depends(get_style_prompt_overlay_service),
):
    """预览写作手法库注入到章节生成前的提示词片段。"""
    return service.build_overlay(
        request.novel_id,
        request.style_profile_id,
        scene_type=request.scene_type,
        max_cards=request.max_cards,
    )


def _sample_to_dto(sample: StyleSample) -> StyleSampleDTO:
    return StyleSampleDTO(
        id=sample.id,
        title=sample.title,
        content=sample.content,
        source_type=sample.source_type,
        genre=sample.genre,
        scene_type=sample.scene_type,
        pov=sample.pov,
        allowed_for_generation=sample.allowed_for_generation,
        novel_id=sample.novel_id,
        profile_id=sample.profile_id,
        content_hash=sample.content_hash,
        char_count=sample.char_count,
    )


def _profile_detail(
    repository: StyleBibleRepository,
    profile: StyleProfile,
) -> dict[str, Any]:
    return {
        "profile": {
            "id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "status": profile.status,
            "novel_id": profile.novel_id,
            "profile": profile.profile,
            "metrics": profile.metrics,
            "rules": profile.rules,
            "forbidden_patterns": profile.forbidden_patterns,
            "version": profile.version,
        },
        "cards": [
            _card_to_dto(card)
            for card in repository.list_technique_cards(profile.id)
        ],
    }


def _card_to_dto(card: StyleTechniqueCard) -> StyleTechniqueCardDTO:
    return StyleTechniqueCardDTO(
        id=card.id,
        profile_id=card.profile_id,
        title=card.title,
        category=card.category,
        scene_type=card.scene_type,
        rule_text=card.rule_text,
        example_summary=card.example_summary,
        prompt_instruction=card.prompt_instruction,
        enabled=card.enabled,
        weight=card.weight,
    )
