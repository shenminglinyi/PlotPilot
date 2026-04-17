"""Novel API 路由"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel, Field
import logging
import uuid

from application.core.services.novel_service import NovelService
from application.world.services.auto_bible_generator import AutoBibleGenerator
from application.world.services.auto_knowledge_generator import AutoKnowledgeGenerator
from application.core.dtos.novel_dto import NovelDTO
from interfaces.api.dependencies import (
    get_novel_service,
    get_auto_bible_generator,
    get_auto_knowledge_generator,
    get_custom_skill_repository,
)
from domain.shared.exceptions import EntityNotFoundError
from application.config import AppConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["novels"])


# Request Models
class CreateNovelRequest(BaseModel):
    """创建小说请求"""
    novel_id: str = Field(..., description="小说 ID")
    title: str = Field(..., description="小说标题")
    author: str = Field(..., description="作者")
    target_chapters: int = Field(..., gt=0, description="目标章节数")
    target_words_per_chapter: int = Field(default=AppConfig.DEFAULT_WORDS_PER_CHAPTER, gt=0, description="每章目标字数")
    premise: str = Field(default="", description="故事梗概/创意")
    genre: str = Field(default="", description="题材类型（可选，如 xuanhuan/suspense/romance）")


class UpdateStageRequest(BaseModel):
    """更新阶段请求"""
    stage: str = Field(..., description="小说阶段")


class UpdateNovelRequest(BaseModel):
    """更新小说基本信息请求"""
    title: str = Field(None, description="小说标题")
    author: str = Field(None, description="作者")
    target_chapters: int = Field(None, gt=0, description="目标章节数")
    target_words_per_chapter: int = Field(None, gt=0, description="每章目标字数")
    premise: str = Field(None, description="故事梗概/创意")
    genre: str = Field(None, description="题材类型（可选）")


class UpdateAutoApproveRequest(BaseModel):
    """更新全自动模式请求"""
    auto_approve_mode: bool = Field(..., description="是否开启全自动模式（跳过所有人工审阅）")


class UpdateThemeAgentEnabledRequest(BaseModel):
    """更新专项题材 Agent 开关请求"""
    theme_agent_enabled: bool = Field(..., description="是否启用专项题材 Agent")


class UpdateThemeSkillsRequest(BaseModel):
    """更新启用的增强技能请求"""
    skill_keys: List[str] = Field(..., description="启用的增强技能 key 列表")


class CreateCustomSkillRequest(BaseModel):
    """创建自定义增强技能请求"""
    skill_name: str = Field(..., description="技能名称", min_length=1, max_length=50)
    skill_description: str = Field(default="", description="技能描述", max_length=200)
    context_prompt: str = Field(default="", description="上下文增强提示词（每章生成时注入到写作上下文中）")
    beat_prompt: str = Field(default="", description="节拍增强提示词（每个节拍生成时注入到指令中）")
    beat_triggers: str = Field(default="", description="节拍触发关键词（逗号分隔，为空则对所有节拍生效）")
    audit_checks: List[str] = Field(default_factory=list, description="审计检查项列表（章后审计时追加的检查点）")


class UpdateCustomSkillRequest(BaseModel):
    """更新自定义增强技能请求"""
    skill_name: Optional[str] = Field(None, description="技能名称", min_length=1, max_length=50)
    skill_description: Optional[str] = Field(None, description="技能描述", max_length=200)
    context_prompt: Optional[str] = Field(None, description="上下文增强提示词")
    beat_prompt: Optional[str] = Field(None, description="节拍增强提示词")
    beat_triggers: Optional[str] = Field(None, description="节拍触发关键词")
    audit_checks: Optional[List[str]] = Field(None, description="审计检查项列表")


async def _generate_bible_background(
    novel_id: str,
    title: str,
    target_chapters: int,
    bible_generator: AutoBibleGenerator,
    knowledge_generator: AutoKnowledgeGenerator
):
    """后台任务：生成 Bible 和 Knowledge"""
    bible_summary = ""
    try:
        bible_data = await bible_generator.generate_and_save(
            novel_id,
            title,
            target_chapters
        )
        # 构建 Bible 摘要供 Knowledge 生成使用
        chars = bible_data.get("characters", [])
        locs = bible_data.get("locations", [])
        char_desc = "、".join(f"{c['name']}（{c.get('role', '')}）" for c in chars[:5])
        loc_desc = "、".join(c['name'] for c in locs[:3])
        bible_summary = f"主要角色：{char_desc}。重要地点：{loc_desc}。文风：{bible_data.get('style', '')}。"

        # 生成初始 Knowledge
        await knowledge_generator.generate_and_save(
            novel_id,
            title,
            bible_summary
        )
        logger.info(f"Bible and Knowledge generated successfully for {novel_id}")
    except Exception as e:
        logger.error(f"Failed to generate Bible/Knowledge for {novel_id}: {e}")


# Routes
@router.post("/", response_model=NovelDTO, status_code=201)
async def create_novel(
    request: CreateNovelRequest,
    service: NovelService = Depends(get_novel_service)
):
    """创建新小说（不自动生成 Bible）

    创建小说后，前端应该：
    1. 调用 POST /bible/novels/{novel_id}/generate 触发 Bible 生成
    2. 轮询 GET /bible/novels/{novel_id}/bible/status 检查生成状态
    3. 引导用户确认 Bible
    4. 用户手动触发规划（通过 POST /novels/{novel_id}/structure/plan 接口）

    Args:
        request: 创建小说请求
        service: Novel 服务

    Returns:
        创建的小说 DTO
    """
    # 只创建小说实体，不生成 Bible
    novel_dto = service.create_novel(
        novel_id=request.novel_id,
        title=request.title,
        author=request.author,
        target_chapters=request.target_chapters,
        target_words_per_chapter=request.target_words_per_chapter,
        premise=request.premise,
        genre=request.genre,
    )

    return novel_dto


@router.get("/{novel_id}", response_model=NovelDTO)
async def get_novel(
    novel_id: str,
    service: NovelService = Depends(get_novel_service)
):
    """获取小说详情

    Args:
        novel_id: 小说 ID
        service: Novel 服务

    Returns:
        小说 DTO

    Raises:
        HTTPException: 如果小说不存在
    """
    novel = service.get_novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"Novel not found: {novel_id}")
    return novel


@router.get("/", response_model=List[NovelDTO])
async def list_novels(service: NovelService = Depends(get_novel_service)):
    """列出所有小说

    Args:
        service: Novel 服务

    Returns:
        小说 DTO 列表
    """
    return service.list_novels()


@router.put("/{novel_id}", response_model=NovelDTO)
async def update_novel(
    novel_id: str,
    request: UpdateNovelRequest,
    service: NovelService = Depends(get_novel_service)
):
    """更新小说基本信息

    Args:
        novel_id: 小说 ID
        request: 更新小说请求
        service: Novel 服务

    Returns:
        更新后的小说 DTO

    Raises:
        HTTPException: 如果小说不存在
    """
    try:
        return service.update_novel(
            novel_id,
            request.title,
            request.author,
            request.target_chapters,
            request.premise,
            request.genre,
            request.target_words_per_chapter,
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{novel_id}/stage", response_model=NovelDTO)
async def update_novel_stage(
    novel_id: str,
    request: UpdateStageRequest,
    service: NovelService = Depends(get_novel_service)
):
    """更新小说阶段

    Args:
        novel_id: 小说 ID
        request: 更新阶段请求
        service: Novel 服务

    Returns:
        更新后的小说 DTO

    Raises:
        HTTPException: 如果小说不存在
    """
    try:
        return service.update_novel_stage(novel_id, request.stage)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{novel_id}", status_code=204)
async def delete_novel(
    novel_id: str,
    service: NovelService = Depends(get_novel_service)
):
    """删除小说

    Args:
        novel_id: 小说 ID
        service: Novel 服务
    """
    service.delete_novel(novel_id)


@router.patch("/{novel_id}/auto-approve-mode", response_model=NovelDTO)
async def update_auto_approve_mode(
    novel_id: str,
    request: UpdateAutoApproveRequest,
    service: NovelService = Depends(get_novel_service)
):
    """更新全自动模式设置
    
    Args:
        novel_id: 小说 ID
        request: 更新全自动模式请求
        service: Novel 服务
        
    Returns:
        更新后的小说 DTO
        
    Raises:
        HTTPException: 如果小说不存在
    """
    try:
        return service.update_auto_approve_mode(novel_id, request.auto_approve_mode)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{novel_id}/theme-agent-enabled", response_model=NovelDTO)
async def update_theme_agent_enabled(
    novel_id: str,
    request: UpdateThemeAgentEnabledRequest,
    service: NovelService = Depends(get_novel_service)
):
    """更新专项题材 Agent 开关

    Args:
        novel_id: 小说 ID
        request: 更新专项题材 Agent 请求
        service: Novel 服务

    Returns:
        更新后的小说 DTO

    Raises:
        HTTPException: 如果小说不存在
    """
    try:
        return service.update_theme_agent_enabled(novel_id, request.theme_agent_enabled)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{novel_id}/theme-skills/available")
async def get_available_theme_skills(
    novel_id: str,
    service: NovelService = Depends(get_novel_service),
    custom_repo=Depends(get_custom_skill_repository),
):
    """获取小说可用的增强技能列表（内置 + 自定义，根据题材过滤）

    Args:
        novel_id: 小说 ID
        service: Novel 服务
        custom_repo: 自定义技能仓储

    Returns:
        可用的增强技能列表
    """
    novel = service.get_novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"Novel not found: {novel_id}")

    genre = novel.genre or ""

    # 内置技能
    builtin_skills = service.get_available_theme_skills(genre)
    for s in builtin_skills:
        s["source"] = "builtin"

    # 自定义技能
    custom_rows = custom_repo.list_by_novel(novel_id)
    custom_skills = []
    for row in custom_rows:
        custom_skills.append({
            "key": row["skill_key"],
            "name": row["skill_name"],
            "description": row["skill_description"],
            "compatible_genres": row.get("compatible_genres", []),
            "source": "custom",
            "id": row["id"],
            "context_prompt": row.get("context_prompt", ""),
            "beat_prompt": row.get("beat_prompt", ""),
            "beat_triggers": row.get("beat_triggers", ""),
            "audit_checks": row.get("audit_checks", []),
        })

    return {
        "novel_id": novel_id,
        "genre": genre,
        "available_skills": builtin_skills + custom_skills,
        "enabled_skills": novel.enabled_theme_skills,
    }


@router.patch("/{novel_id}/theme-skills", response_model=NovelDTO)
async def update_enabled_theme_skills(
    novel_id: str,
    request: UpdateThemeSkillsRequest,
    service: NovelService = Depends(get_novel_service)
):
    """更新小说启用的增强技能

    Args:
        novel_id: 小说 ID
        request: 更新技能请求（包含要启用的技能 key 列表）
        service: Novel 服务

    Returns:
        更新后的小说 DTO

    Raises:
        HTTPException: 如果小说不存在
    """
    try:
        return service.update_enabled_theme_skills(novel_id, request.skill_keys)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── 自定义增强技能 CRUD ───


@router.post("/{novel_id}/theme-skills/custom", status_code=201)
async def create_custom_skill(
    novel_id: str,
    request: CreateCustomSkillRequest,
    service: NovelService = Depends(get_novel_service),
    custom_repo=Depends(get_custom_skill_repository),
):
    """创建自定义增强技能

    用户填写提示词内容，系统将其包装为 ThemeSkill 注入写作管线。

    Args:
        novel_id: 小说 ID
        request: 创建自定义技能请求
    """
    novel = service.get_novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"Novel not found: {novel_id}")

    skill_id = f"custom-{uuid.uuid4().hex[:12]}"
    # 自动生成 skill_key（基于名称的拼音/简写，取唯一后缀）
    skill_key = f"custom_{uuid.uuid4().hex[:8]}"

    skill_data = {
        "id": skill_id,
        "novel_id": novel_id,
        "skill_key": skill_key,
        "skill_name": request.skill_name,
        "skill_description": request.skill_description,
        "compatible_genres": [novel.genre] if novel.genre else [],
        "context_prompt": request.context_prompt,
        "beat_prompt": request.beat_prompt,
        "beat_triggers": request.beat_triggers,
        "audit_checks": request.audit_checks,
    }

    custom_repo.save(skill_data)

    return {
        **skill_data,
        "key": skill_key,
        "source": "custom",
    }


@router.put("/{novel_id}/theme-skills/custom/{skill_id}")
async def update_custom_skill(
    novel_id: str,
    skill_id: str,
    request: UpdateCustomSkillRequest,
    service: NovelService = Depends(get_novel_service),
    custom_repo=Depends(get_custom_skill_repository),
):
    """更新自定义增强技能"""
    existing = custom_repo.get_by_id(skill_id)
    if not existing or existing["novel_id"] != novel_id:
        raise HTTPException(status_code=404, detail="Custom skill not found")

    # 合并更新
    if request.skill_name is not None:
        existing["skill_name"] = request.skill_name
    if request.skill_description is not None:
        existing["skill_description"] = request.skill_description
    if request.context_prompt is not None:
        existing["context_prompt"] = request.context_prompt
    if request.beat_prompt is not None:
        existing["beat_prompt"] = request.beat_prompt
    if request.beat_triggers is not None:
        existing["beat_triggers"] = request.beat_triggers
    if request.audit_checks is not None:
        existing["audit_checks"] = request.audit_checks

    custom_repo.save(existing)
    return {**existing, "key": existing["skill_key"], "source": "custom"}


@router.delete("/{novel_id}/theme-skills/custom/{skill_id}", status_code=204)
async def delete_custom_skill(
    novel_id: str,
    skill_id: str,
    custom_repo=Depends(get_custom_skill_repository),
):
    """删除自定义增强技能"""
    existing = custom_repo.get_by_id(skill_id)
    if not existing or existing["novel_id"] != novel_id:
        raise HTTPException(status_code=404, detail="Custom skill not found")
    custom_repo.delete(skill_id)


@router.get("/{novel_id}/statistics")
async def get_novel_statistics(
    novel_id: str,
    service: NovelService = Depends(get_novel_service)
):
    """获取小说统计信息

    Args:
        novel_id: 小说 ID
        service: Novel 服务

    Returns:
        统计信息字典

    Raises:
        HTTPException: 如果小说不存在
    """
    try:
        return service.get_novel_statistics(novel_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
