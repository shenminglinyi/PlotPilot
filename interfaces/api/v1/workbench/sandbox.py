"""Sandbox API endpoints for dialogue whitelist and simulation."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from domain.ai.services.llm_service import GenerationConfig
from application.workbench.services.sandbox_dialogue_service import SandboxDialogueService
from application.workbench.dtos.sandbox_dto import DialogueWhitelistResponse
from interfaces.api.dependencies import get_sandbox_dialogue_service, get_bible_service, get_llm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["sandbox"])


class CharacterAnchorResponse(BaseModel):
    """角色心理锚点响应"""
    character_id: str
    character_name: str
    mental_state: str
    verbal_tic: str
    idle_behavior: str


class UpdateCharacterAnchorRequest(BaseModel):
    """保存角色声线锚点到 Bible（bible_characters）"""
    mental_state: str = "NORMAL"
    verbal_tic: str = ""
    idle_behavior: str = ""


class GenerateDialogueRequest(BaseModel):
    """生成对话请求"""
    novel_id: str
    character_id: str
    scene_prompt: str
    mental_state: Optional[str] = None
    verbal_tic: Optional[str] = None
    idle_behavior: Optional[str] = None


class GenerateDialogueResponse(BaseModel):
    """生成对话响应"""
    dialogue: str
    character_name: str


@router.get("/{novel_id}/sandbox/dialogue-whitelist", response_model=DialogueWhitelistResponse)
async def get_dialogue_whitelist(
    novel_id: str,
    chapter_number: Optional[int] = Query(None, ge=1, description="Filter by chapter number"),
    speaker: Optional[str] = Query(None, description="Filter by speaker name"),
    service: SandboxDialogueService = Depends(get_sandbox_dialogue_service)
) -> DialogueWhitelistResponse:
    """
    Get dialogue whitelist for sandbox simulation.

    This endpoint retrieves all dialogues available for sandbox scenario planning,
    with optional filters for chapter and speaker.

    Args:
        novel_id: The novel ID
        chapter_number: Optional chapter filter (must be >= 1)
        speaker: Optional speaker name filter
        service: Injected sandbox dialogue service

    Returns:
        DialogueWhitelistResponse containing filtered dialogues

    Raises:
        HTTPException: 500 if internal error occurs
    """
    try:
        result = service.get_dialogue_whitelist(
            novel_id=novel_id,
            chapter_number=chapter_number,
            speaker=speaker
        )
        return result

    except Exception as e:
        logger.error(f"Error retrieving dialogue whitelist: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{novel_id}/sandbox/character/{character_id}/anchor", response_model=CharacterAnchorResponse)
async def get_character_anchor(
    novel_id: str,
    character_id: str,
    bible_service = Depends(get_bible_service)
):
    """
    获取角色心理锚点数据

    返回角色的心理状态、口头禅、待机动作等锚点信息
    """
    try:
        # 从 Bible 获取角色信息
        bible = bible_service.get_bible_by_novel(novel_id)

        if not bible:
            raise HTTPException(status_code=404, detail=f"Bible not found for novel {novel_id}")

        # 查找指定角色
        character = None
        for char in bible.characters:
            if char.id == character_id:
                character = char
                break

        if not character:
            raise HTTPException(status_code=404, detail=f"Character {character_id} not found")

        return CharacterAnchorResponse(
            character_id=character_id,
            character_name=character.name,
            mental_state=getattr(character, "mental_state", None) or "NORMAL",
            verbal_tic=getattr(character, "verbal_tic", None) or "",
            idle_behavior=getattr(character, "idle_behavior", None) or "",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching character anchor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch character anchor")


@router.patch(
    "/{novel_id}/sandbox/character/{character_id}/anchor",
    response_model=CharacterAnchorResponse,
)
async def patch_character_anchor(
    novel_id: str,
    character_id: str,
    request: UpdateCharacterAnchorRequest,
    bible_service=Depends(get_bible_service),
):
    """将心理状态、口头禅、待机动作写入 bible_characters。"""
    from domain.shared.exceptions import EntityNotFoundError

    try:
        dto = bible_service.update_character_voice_anchors(
            novel_id,
            character_id,
            mental_state=request.mental_state,
            verbal_tic=request.verbal_tic,
            idle_behavior=request.idle_behavior,
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return CharacterAnchorResponse(
        character_id=dto.id,
        character_name=dto.name,
        mental_state=dto.mental_state,
        verbal_tic=dto.verbal_tic,
        idle_behavior=dto.idle_behavior,
    )


@router.post("/sandbox/generate-dialogue", response_model=GenerateDialogueResponse)
async def generate_dialogue(
    request: GenerateDialogueRequest,
    bible_service = Depends(get_bible_service),
    llm_service = Depends(get_llm_service),
    sandbox_service: SandboxDialogueService = Depends(get_sandbox_dialogue_service),
):
    """
    AI 生成对话

    根据角色锚点、Bible 关系和历史对白样本，生成更贴近角色的对话
    """
    try:
        bible = bible_service.get_bible_by_novel(request.novel_id)
        if not bible:
            raise HTTPException(status_code=404, detail="Bible not found")
        ch = next((c for c in bible.characters if c.id == request.character_id), None)
        if not ch:
            raise HTTPException(status_code=404, detail=f"Character {request.character_id} not found")

        character_name = ch.name

        mental_state = (
            request.mental_state
            if request.mental_state is not None
            else (getattr(ch, "mental_state", None) or "NORMAL")
        )
        verbal_tic = (
            request.verbal_tic if request.verbal_tic is not None else (getattr(ch, "verbal_tic", None) or "")
        )
        idle_behavior = (
            request.idle_behavior
            if request.idle_behavior is not None
            else (getattr(ch, "idle_behavior", None) or "")
        )

        recent_dialogues = sandbox_service.get_recent_character_dialogues(
            request.novel_id,
            speaker=character_name,
            limit=4,
        )
        prompt = sandbox_service.build_dialogue_generation_prompt(
            character=ch,
            scene_prompt=request.scene_prompt,
            mental_state=mental_state,
            verbal_tic=verbal_tic,
            idle_behavior=idle_behavior,
            all_characters=bible.characters,
            recent_dialogues=recent_dialogues,
        )
        config = GenerationConfig(max_tokens=240, temperature=0.85)

        result = await llm_service.generate(prompt, config)
        dialogue = sandbox_service.clean_generated_dialogue(result.content, character_name)
        if not dialogue:
            raise RuntimeError("LLM returned empty dialogue content")

        return GenerateDialogueResponse(
            dialogue=dialogue,
            character_name=character_name
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating dialogue: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate dialogue")

