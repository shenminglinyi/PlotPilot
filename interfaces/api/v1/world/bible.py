"""Bible API 路由"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Union
import logging
import json
import asyncio

from application.world.services.bible_service import BibleService
from application.world.services.auto_bible_generator import AutoBibleGenerator
from application.world.services.auto_knowledge_generator import AutoKnowledgeGenerator
from application.world.dtos.bible_dto import BibleDTO
from interfaces.api.dependencies import (
    get_bible_service,
    get_auto_bible_generator,
    get_auto_knowledge_generator
)
from domain.shared.exceptions import EntityNotFoundError
from application.world.bible_generation_state import (
    clear_bible_generation_state,
    get_bible_generation_state,
    record_bible_generation_failure,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/bible", tags=["bible"])


# Request Models
class CreateBibleRequest(BaseModel):
    """创建 Bible 请求"""
    bible_id: str = Field(..., description="Bible ID")
    novel_id: str = Field(..., description="小说 ID")


class AddCharacterRequest(BaseModel):
    """添加人物请求"""
    character_id: str = Field(..., description="人物 ID")
    name: str = Field(..., description="人物名称")
    description: str = Field(..., description="人物描述")


class AddWorldSettingRequest(BaseModel):
    """添加世界设定请求"""
    setting_id: str = Field(..., description="设定 ID")
    name: str = Field(..., description="设定名称")
    description: str = Field(..., description="设定描述")
    setting_type: str = Field(..., description="设定类型")


class AddLocationRequest(BaseModel):
    """添加地点请求"""
    location_id: str = Field(..., description="地点 ID")
    name: str = Field(..., description="地点名称")
    description: str = Field(..., description="地点描述")
    location_type: str = Field(..., description="地点类型")
    parent_id: Optional[str] = Field(default=None, description="父地点 id，根为 null")


class AddTimelineNoteRequest(BaseModel):
    """添加时间线笔记请求"""
    note_id: str = Field(..., description="笔记 ID")
    event: str = Field(..., description="事件")
    time_point: str = Field(..., description="时间点")
    description: str = Field(..., description="描述")


class AddStyleNoteRequest(BaseModel):
    """添加风格笔记请求"""
    note_id: str = Field(..., description="笔记 ID")
    category: str = Field(..., description="类别")
    content: str = Field(..., description="内容")


class BibleCharacterRelationshipItem(BaseModel):
    """Bible 人物关系项（与 LLM 输出的 target/relation/description 对象一致）"""

    model_config = ConfigDict(extra="allow")

    target: Optional[str] = None
    relation: Optional[str] = None
    description: Optional[str] = None


class CharacterData(BaseModel):
    """人物数据"""
    id: str = Field(..., description="人物 ID")
    name: str = Field(..., description="人物名称")
    description: str = Field(..., description="人物描述")
    relationships: list[Union[str, BibleCharacterRelationshipItem]] = Field(
        default_factory=list,
        description="关系列表：字符串或结构化对象",
    )
    mental_state: Optional[str] = Field(
        default=None,
        description="心理状态；省略则保留库中旧值（新角色默认 NORMAL）",
    )
    verbal_tic: Optional[str] = Field(default=None, description="口头禅；省略则保留库中旧值")
    idle_behavior: Optional[str] = Field(
        default=None,
        description="待机动作/小动作；省略则保留库中旧值",
    )


class WorldSettingData(BaseModel):
    """世界设定数据"""
    id: str = Field(..., description="设定 ID")
    name: str = Field(..., description="设定名称")
    description: str = Field(..., description="设定描述")
    setting_type: str = Field(..., description="设定类型")


class LocationData(BaseModel):
    """地点数据"""
    id: str = Field(..., description="地点 ID")
    name: str = Field(..., description="地点名称")
    description: str = Field(..., description="地点描述")
    location_type: str = Field(..., description="地点类型")
    parent_id: Optional[str] = Field(default=None, description="父地点 id，根为 null")


class TimelineNoteData(BaseModel):
    """时间线笔记数据"""
    id: str = Field(..., description="笔记 ID")
    event: str = Field(..., description="事件")
    time_point: str = Field(..., description="时间点")
    description: str = Field(..., description="描述")


class StyleNoteData(BaseModel):
    """风格笔记数据"""
    id: str = Field(..., description="笔记 ID")
    category: str = Field(..., description="类别")
    content: str = Field(..., description="内容")


class BulkUpdateBibleRequest(BaseModel):
    """批量更新 Bible 请求"""
    characters: list[CharacterData] = Field(default_factory=list, description="人物列表")
    world_settings: list[WorldSettingData] = Field(default_factory=list, description="世界设定列表")
    locations: list[LocationData] = Field(default_factory=list, description="地点列表")
    timeline_notes: list[TimelineNoteData] = Field(default_factory=list, description="时间线笔记列表")
    style_notes: list[StyleNoteData] = Field(default_factory=list, description="风格笔记列表")


# Routes
@router.post("/novels/{novel_id}/generate", status_code=202)
async def generate_bible(
    novel_id: str,
    background_tasks: BackgroundTasks,
    stage: str = "all",  # all / worldbuilding / characters / locations
    bible_generator: AutoBibleGenerator = Depends(get_auto_bible_generator),
    knowledge_generator: AutoKnowledgeGenerator = Depends(get_auto_knowledge_generator)
):
    """手动触发 Bible 和 Knowledge 生成（异步）

    支持分阶段生成：
    - stage=all: 一次性生成所有内容（默认，向后兼容）
    - stage=worldbuilding: 只生成世界观（5维度）和文风公约
    - stage=characters: 基于已有世界观生成人物
    - stage=locations: 基于已有世界观和人物生成地点

    用户创建小说后，前端调用此接口开始生成 Bible。
    生成过程在后台进行，前端应轮询 /bible/novels/{novel_id}/bible/status 检查状态。

    Args:
        novel_id: 小说 ID
        stage: 生成阶段
        background_tasks: FastAPI 后台任务
        bible_generator: Bible 生成器
        knowledge_generator: Knowledge 生成器

    Returns:
        202 Accepted，表示生成任务已启动
    """
    async def _generate_task():
        logger.info("Bible generation task started for %s, stage=%s", novel_id, stage)
        clear_bible_generation_state(novel_id)
        try:
            # 获取小说信息（需要 premise 和 target_chapters）
            from interfaces.api.dependencies import get_novel_service
            novel_service = get_novel_service()
            novel = novel_service.get_novel(novel_id)
            if not novel:
                logger.error(f"Novel not found: {novel_id}")
                record_bible_generation_failure(novel_id, stage, "小说不存在，无法生成 Bible")
                return

            # 使用 premise（故事梗概）生成 Bible，如果没有则使用 title
            premise = novel.premise if novel.premise else novel.title

            # 生成 Bible（支持分阶段）
            bible_data = await bible_generator.generate_and_save(
                novel_id,
                premise,
                novel.target_chapters,
                stage=stage
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
                novel.title,
                bible_summary
            )
            logger.info(f"Bible and Knowledge generated successfully for {novel_id}")
            clear_bible_generation_state(novel_id)
        except Exception as e:
            import traceback
            logger.error("Bible generation task failed for %s: %s", novel_id, e)
            logger.error(traceback.format_exc())
            record_bible_generation_failure(novel_id, stage, str(e))

    background_tasks.add_task(_generate_task)

    return {
        "message": "Bible generation started",
        "novel_id": novel_id,
        "status_url": f"/api/v1/bible/novels/{novel_id}/bible/status"
    }


# ---------------------------------------------------------------------------
# SSE 流式生成接口：逐步推送每个维度的生成进度和数据
# ---------------------------------------------------------------------------

def _sse_fmt(event: str, data: dict) -> str:
    """格式化单条 SSE 消息。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _parse_dimension_json(raw_text: str, dim_key: str) -> dict:
    """解析 LLM 流式输出的维度 JSON，返回 {field_key: field_value} 字典。"""
    from application.world.services.auto_bible_generator import (
        _sanitize_llm_json_output,
        _repair_json_string,
    )

    content = _sanitize_llm_json_output(raw_text)
    if not content:
        return {}

    # 尝试解析 JSON
    parsed = None
    for attempt in range(3):
        try:
            parsed = json.loads(content)
            break
        except (json.JSONDecodeError, ValueError):
            if attempt == 0:
                content = _repair_json_string(content)
            elif attempt == 1:
                # 尝试提取最外层 JSON 对象
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end > start:
                    content = content[start:end + 1]
                    content = _repair_json_string(content)

    if not isinstance(parsed, dict):
        return {}

    # 标准化：只保留字符串字段
    normalized = {}
    for k, v in parsed.items():
        if isinstance(v, str) and v.strip():
            normalized[k] = v.strip()
        elif isinstance(v, (list, dict)):
            normalized[k] = str(v)
    return normalized


async def _sse_bible_generator(
    novel_id: str,
    stage: str,
    bible_generator: AutoBibleGenerator,
    knowledge_generator: AutoKnowledgeGenerator,
):
    """SSE 生成器：逐步推送 Bible 生成进度和数据片段。"""
    from interfaces.api.dependencies import get_novel_service

    # ── 起始 ──
    yield _sse_fmt("phase", {"phase": "init", "message": "正在准备生成环境..."})
    await asyncio.sleep(0)

    clear_bible_generation_state(novel_id)

    # 获取小说信息
    try:
        novel_service = get_novel_service()
        novel = novel_service.get_novel(novel_id)
        if not novel:
            yield _sse_fmt("error", {"message": "小说不存在，无法生成 Bible"})
            return
        premise = novel.premise if novel.premise else novel.title
    except Exception as e:
        yield _sse_fmt("error", {"message": f"获取小说信息失败: {e}"})
        return

    # 确保Bible记录存在
    try:
        existing_bible = bible_generator.bible_service.get_bible_by_novel(novel_id)
        if not existing_bible:
            bible_generator.bible_service.create_bible(f"{novel_id}-bible", novel_id)
    except Exception:
        try:
            bible_generator.bible_service.create_bible(f"{novel_id}-bible", novel_id)
        except Exception as e:
            yield _sse_fmt("error", {"message": f"创建 Bible 记录失败: {e}"})
            return

    try:
        if stage in ("all", "worldbuilding"):
            # ── 世界观生成（逐维度流式） ──
            yield _sse_fmt("phase", {"phase": "worldbuilding", "message": "AI 正在构建世界观（5维度框架）..."})
            await asyncio.sleep(0)

            # 1. 先生成文风公约（快速，独立调用）
            yield _sse_fmt("phase", {"phase": "worldbuilding_style", "message": "正在生成文风公约..."})
            await asyncio.sleep(0)
            try:
                style_text = await bible_generator._generate_style(premise, novel.target_chapters)
                if style_text:
                    yield _sse_fmt("data", {"type": "style", "content": style_text})
                    # 保存文风
                    try:
                        bible_generator.bible_service.add_style_note(
                            novel_id=novel_id,
                            note_id=f"{novel_id}-style-1",
                            category="文风公约",
                            content=style_text,
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("Style generation failed (non-fatal): %s", e)

            # 2. 逐维度流式生成世界观（每维度一次 LLM 流式请求，边接收 token 边推送）
            dim_keys = ["core_rules", "geography", "society", "culture", "daily_life"]
            dim_labels = {
                "core_rules": "核心法则",
                "geography": "地理生态",
                "society": "社会结构",
                "culture": "历史文化",
                "daily_life": "沉浸感细节",
            }
            accumulated_wb: dict = {}  # 已生成的维度数据，用于上下文传递

            for dim_key in dim_keys:
                dim_label = dim_labels[dim_key]

                # 通知前端"即将生成该维度"
                yield _sse_fmt("phase", {"phase": f"worldbuilding_{dim_key}", "message": f"正在构建{dim_label}..."})
                await asyncio.sleep(0)

                # ── 维度级流式：一次 LLM 调用流式输出整个维度 JSON ──
                # 逐 token 推送 worldbuilding_dim_chunk（前端可逐字看到内容）
                # 维度完成后推送每个字段的 worldbuilding_field 事件
                try:
                    parts: list[str] = []
                    async for chunk in bible_generator._stream_single_dimension(
                        premise, novel.target_chapters, dim_key, accumulated_wb,
                    ):
                        parts.append(chunk)
                        # 逐 token 推送 SSE（让前端看到逐字生成）
                        yield _sse_fmt("data", {
                            "type": "worldbuilding_dim_chunk",
                            "dimension": dim_key,
                            "chunk": chunk,
                        })
                        await asyncio.sleep(0)

                    full_text = "".join(parts).strip()
                    dim_data = _parse_dimension_json(full_text, dim_key)
                except Exception as e:
                    logger.error("Failed to stream dimension %s: %s", dim_key, e)
                    dim_data = {}

                if dim_data:
                    accumulated_wb[dim_key] = dim_data
                    # 逐字段推送完整的字段值（前端更新最终状态）
                    for field_key, field_value in dim_data.items():
                        if field_value:
                            yield _sse_fmt("data", {
                                "type": "worldbuilding_field",
                                "dimension": dim_key,
                                "field": field_key,
                                "value": field_value,
                            })
                            await asyncio.sleep(0.05)

                    # 即时保存该维度到数据库
                    try:
                        await bible_generator._save_worldbuilding(novel_id, {dim_key: dim_data})
                    except Exception as e:
                        logger.warning("Failed to save dimension %s via SSE: %s", dim_key, e)

                await asyncio.sleep(0.1)  # 给前端渲染数据的时间

            yield _sse_fmt("phase", {"phase": "worldbuilding_done", "message": "世界观生成完成！"})

        if stage in ("all", "characters"):
            # ── 人物生成（流式 LLM） ──
            yield _sse_fmt("phase", {"phase": "characters", "message": "AI 正在生成主要角色..."})
            await asyncio.sleep(0)

            existing_worldbuilding = bible_generator._load_worldbuilding(novel_id)
            chars_payload = []
            character_ids = []
            used_char_ids = set()

            async for item in bible_generator._stream_generate_characters(
                premise, novel.target_chapters, existing_worldbuilding
            ):
                if item["type"] == "character":
                    char_data = item["content"]
                    chars_payload.append(char_data)
                    idx = item["index"]
                    yield _sse_fmt("phase", {"phase": f"character_{idx}", "message": f"正在生成角色：{char_data.get('name', '...')}..."})
                    yield _sse_fmt("data", {
                        "type": "character",
                        "index": idx,
                        "content": char_data,
                    })
                    # 即时落库
                    character_id = f"{novel_id}-char-{idx+1}"
                    if character_id in used_char_ids:
                        character_id = f"{novel_id}-char-{idx+1}-{len(used_char_ids)}"
                    used_char_ids.add(character_id)
                    try:
                        bible_generator.bible_service.add_character(
                            novel_id=novel_id,
                            character_id=character_id,
                            name=char_data["name"],
                            description=f"{char_data.get('role', '')} - {char_data.get('description', '')}",
                            relationships=char_data.get("relationships", []),
                        )
                        character_ids.append((character_id, char_data))
                    except Exception:
                        pass
                elif item["type"] == "chunk":
                    # 透传 LLM 原始 chunk（前端可用于打字效果）
                    yield _sse_fmt("data", {
                        "type": "character_chunk",
                        "chunk": item["text"],
                    })

            # 生成人物关系三元组
            if bible_generator.triple_repository and character_ids:
                await bible_generator._generate_character_triples(novel_id, character_ids)

            yield _sse_fmt("phase", {"phase": "characters_done", "message": f"人物生成完成！共 {len(chars_payload)} 个角色"})

        if stage in ("all", "locations"):
            # ── 地点生成（流式 LLM） ──
            yield _sse_fmt("phase", {"phase": "locations", "message": "AI 正在生成地图系统..."})
            await asyncio.sleep(0)

            existing_worldbuilding = bible_generator._load_worldbuilding(novel_id)
            existing_characters = bible_generator._load_characters(novel_id)
            locs_payload = []
            location_ids = []

            async for item in bible_generator._stream_generate_locations(
                premise, novel.target_chapters, existing_worldbuilding, existing_characters
            ):
                if item["type"] == "location":
                    loc_data = item["content"]
                    locs_payload.append(loc_data)
                    idx = item["index"]
                    yield _sse_fmt("phase", {"phase": f"location_{idx}", "message": f"正在生成地点：{loc_data.get('name', '...')}..."})
                    yield _sse_fmt("data", {
                        "type": "location",
                        "index": idx,
                        "content": loc_data,
                    })
                    # 即时落库
                    prepared = bible_generator._prepare_locations_for_save(novel_id, [loc_data])
                    for pd in prepared:
                        try:
                            bible_generator.bible_service.add_location(
                                novel_id=novel_id,
                                location_id=pd["location_id"],
                                name=pd["name"],
                                description=pd["description"],
                                location_type=pd["location_type"],
                                connections=pd.get("connections", []),
                                parent_id=pd.get("parent_id"),
                            )
                            location_ids.append((pd["location_id"], pd))
                        except Exception:
                            pass
                elif item["type"] == "chunk":
                    yield _sse_fmt("data", {
                        "type": "location_chunk",
                        "chunk": item["text"],
                    })

            # 生成地点关系三元组
            if bible_generator.triple_repository and location_ids:
                await bible_generator._generate_location_triples(novel_id, location_ids)

            yield _sse_fmt("phase", {"phase": "locations_done", "message": f"地图生成完成！共 {len(locs_payload)} 个地点"})

        # ── 知识库生成 ──
        yield _sse_fmt("phase", {"phase": "knowledge", "message": "正在构建知识库..."})
        await asyncio.sleep(0)

        try:
            bible = bible_generator.bible_service.get_bible_by_novel(novel_id)
            if bible:
                chars = bible.characters or []
                locs = bible.locations or []
                char_desc = "、".join(f"{c.name}" for c in chars[:5])
                loc_desc = "、".join(c.name for c in locs[:3])
                style_notes = bible.style_notes or []
                style_text = "；".join(n.content for n in style_notes if n.content)
                bible_summary = f"主要角色：{char_desc}。重要地点：{loc_desc}。文风：{style_text}。"
                await knowledge_generator.generate_and_save(novel_id, novel.title, bible_summary)
        except Exception as e:
            logger.warning("Knowledge generation failed (non-fatal): %s", e)

        clear_bible_generation_state(novel_id)
        yield _sse_fmt("done", {"message": "全部生成完成！", "novel_id": novel_id})

    except Exception as e:
        import traceback
        logger.error("SSE Bible generation failed for %s: %s", novel_id, e)
        logger.error(traceback.format_exc())
        record_bible_generation_failure(novel_id, stage, str(e))
        yield _sse_fmt("error", {"message": f"生成失败: {e}"})


@router.post("/novels/{novel_id}/generate-stream/")
@router.post("/novels/{novel_id}/generate-stream")
async def generate_bible_stream(
    novel_id: str,
    stage: str = "worldbuilding",
    bible_generator: AutoBibleGenerator = Depends(get_auto_bible_generator),
    knowledge_generator: AutoKnowledgeGenerator = Depends(get_auto_knowledge_generator),
):
    """SSE 流式 Bible 生成接口。

    逐维度逐字段推送生成进度和数据片段，每生成一个字段立即推送，前端可实时渲染。

    事件类型：
    - phase: 阶段变更（init / worldbuilding / worldbuilding_{dim} / worldbuilding_{dim}_{field} / characters / locations / knowledge / *_done）
    - data: 数据片段（style / worldbuilding_field / character / location）
    - done: 全部完成
    - error: 错误
    """
    return StreamingResponse(
        _sse_bible_generator(novel_id, stage, bible_generator, knowledge_generator),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/novels/{novel_id}/bible", response_model=BibleDTO, status_code=201)
async def create_bible(
    novel_id: str,
    request: CreateBibleRequest,
    service: BibleService = Depends(get_bible_service)
):
    """为小说创建 Bible

    Args:
        novel_id: 小说 ID
        request: 创建 Bible 请求
        service: Bible 服务

    Returns:
        创建的 Bible DTO
    """
    return service.create_bible(request.bible_id, novel_id)


# 注意：必须先注册比 `/novels/{id}/bible` 更长的路径，避免与 `{novel_id}` 匹配歧义
@router.get("/novels/{novel_id}/bible/generation-feedback")
async def get_bible_generation_feedback(novel_id: str):
    """新书向导轮询用：最近一次 Bible 异步生成失败原因（成功或未失败时为 null）。"""
    state = get_bible_generation_state(novel_id)
    if not state:
        return {"novel_id": novel_id, "error": None, "stage": None, "at": None}
    return {
        "novel_id": novel_id,
        "error": state.get("error"),
        "stage": state.get("stage"),
        "at": state.get("at"),
    }


@router.get("/novels/{novel_id}/bible/status")
async def get_bible_status(
    novel_id: str,
    service: BibleService = Depends(get_bible_service)
):
    """检查 Bible 生成状态

    Args:
        novel_id: 小说 ID
        service: Bible 服务

    Returns:
        状态信息：{ "exists": bool, "ready": bool }
    """
    try:
        bible = service.get_bible_by_novel(novel_id)
        exists = bible is not None
        # 修改ready逻辑：只要有文风公约或世界观就算ready（支持分阶段生成）
        ready = exists and (len(bible.style_notes) > 0 or len(bible.world_settings) > 0 or len(bible.characters) > 0)

        return {
            "exists": exists,
            "ready": ready,
            "novel_id": novel_id
        }
    except Exception as e:
        logger.exception("get_bible_status failed for novel_id=%s", novel_id)
        raise HTTPException(status_code=500, detail=f"检查 Bible 状态失败: {e}") from e


@router.get("/novels/{novel_id}/bible", response_model=BibleDTO)
async def get_bible_by_novel(
    novel_id: str,
    service: BibleService = Depends(get_bible_service)
):
    """获取小说的 Bible

    Args:
        novel_id: 小说 ID
        service: Bible 服务

    Returns:
        Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    bible = service.get_bible_by_novel(novel_id)
    if bible is None:
        raise HTTPException(
            status_code=404,
            detail=f"Bible not found for novel: {novel_id}"
        )
    return bible


@router.get("/novels/{novel_id}/bible/characters", response_model=list)
async def list_characters(
    novel_id: str,
    service: BibleService = Depends(get_bible_service)
):
    """列出 Bible 中的所有人物

    Args:
        novel_id: 小说 ID
        service: Bible 服务

    Returns:
        人物 DTO 列表

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    bible = service.get_bible_by_novel(novel_id)
    if bible is None:
        raise HTTPException(
            status_code=404,
            detail=f"Bible not found for novel: {novel_id}"
        )
    return bible.characters


@router.post("/novels/{novel_id}/bible/characters", response_model=BibleDTO)
async def add_character(
    novel_id: str,
    request: AddCharacterRequest,
    service: BibleService = Depends(get_bible_service)
):
    """添加人物到 Bible

    Args:
        novel_id: 小说 ID
        request: 添加人物请求
        service: Bible 服务

    Returns:
        更新后的 Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    try:
        return service.add_character(
            novel_id=novel_id,
            character_id=request.character_id,
            name=request.name,
            description=request.description
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/novels/{novel_id}/bible/world-settings", response_model=BibleDTO)
async def add_world_setting(
    novel_id: str,
    request: AddWorldSettingRequest,
    service: BibleService = Depends(get_bible_service)
):
    """添加世界设定到 Bible

    Args:
        novel_id: 小说 ID
        request: 添加世界设定请求
        service: Bible 服务

    Returns:
        更新后的 Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    try:
        return service.add_world_setting(
            novel_id=novel_id,
            setting_id=request.setting_id,
            name=request.name,
            description=request.description,
            setting_type=request.setting_type
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/novels/{novel_id}/bible/locations", response_model=BibleDTO)
async def add_location(
    novel_id: str,
    request: AddLocationRequest,
    service: BibleService = Depends(get_bible_service)
):
    """添加地点到 Bible

    Args:
        novel_id: 小说 ID
        request: 添加地点请求
        service: Bible 服务

    Returns:
        更新后的 Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    try:
        return service.add_location(
            novel_id=novel_id,
            location_id=request.location_id,
            name=request.name,
            description=request.description,
            location_type=request.location_type,
            parent_id=request.parent_id,
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/novels/{novel_id}/bible/timeline-notes", response_model=BibleDTO)
async def add_timeline_note(
    novel_id: str,
    request: AddTimelineNoteRequest,
    service: BibleService = Depends(get_bible_service)
):
    """添加时间线笔记到 Bible

    Args:
        novel_id: 小说 ID
        request: 添加时间线笔记请求
        service: Bible 服务

    Returns:
        更新后的 Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    try:
        return service.add_timeline_note(
            novel_id=novel_id,
            note_id=request.note_id,
            event=request.event,
            time_point=request.time_point,
            description=request.description
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/novels/{novel_id}/bible/style-notes", response_model=BibleDTO)
async def add_style_note(
    novel_id: str,
    request: AddStyleNoteRequest,
    service: BibleService = Depends(get_bible_service)
):
    """添加风格笔记到 Bible

    Args:
        novel_id: 小说 ID
        request: 添加风格笔记请求
        service: Bible 服务

    Returns:
        更新后的 Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    try:
        return service.add_style_note(
            novel_id=novel_id,
            note_id=request.note_id,
            category=request.category,
            content=request.content
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/novels/{novel_id}/bible", response_model=BibleDTO)
async def bulk_update_bible(
    novel_id: str,
    request: BulkUpdateBibleRequest,
    service: BibleService = Depends(get_bible_service)
):
    """批量更新 Bible 的所有数据

    Args:
        novel_id: 小说 ID
        request: 批量更新请求
        service: Bible 服务

    Returns:
        更新后的 Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在或参数无效
    """
    try:
        return service.update_bible(
            novel_id=novel_id,
            characters=request.characters,
            world_settings=request.world_settings,
            locations=request.locations,
            timeline_notes=request.timeline_notes,
            style_notes=request.style_notes
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
