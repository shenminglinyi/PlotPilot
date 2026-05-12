"""Checkpoint + QualityGuardrail + StoryPhase + CharacterPsyche 统一路由

前端新增面板的统一 API 出口：
- GET  /novels/{novel_id}/checkpoints         → 列出时间线
- POST /novels/{novel_id}/checkpoints         → 手动创建
- POST /novels/{novel_id}/checkpoints/{id}/rollback → 回滚
- GET  /novels/{novel_id}/checkpoints/branches → 平行宇宙
- GET  /novels/{novel_id}/checkpoints/head     → 当前HEAD

- POST /novels/{novel_id}/guardrail/check      → 六维度质检(advise)
- POST /novels/{novel_id}/guardrail/enforce    → 六维度质检(enforce)

- GET  /novels/{novel_id}/story-phase          → 获取故事阶段
- PUT  /novels/{novel_id}/story-phase          → 更新故事阶段

- GET  /novels/{novel_id}/character-psyches       → 获取角色灵魂概览
- GET  /novels/{novel_id}/character-psyches/{name}→ 单角色灵魂详情
- POST /novels/{novel_id}/character-psyches/{name}/validate → 行为验证
- POST /novels/{novel_id}/character-psyches/{name}/extract → AI 抽取 T0/锚点写 Bible
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["engine-core"])


# ─── Pydantic DTOs ────────────────────────────────────────────────

class CheckpointDTO(BaseModel):
    id: str
    story_id: str
    trigger_type: str
    trigger_reason: str = ""
    parent_id: Optional[str] = None
    chapter_number: Optional[int] = None
    created_at: str = ""
    is_head: bool = False


class CheckpointListResponse(BaseModel):
    checkpoints: List[CheckpointDTO] = Field(default_factory=list)
    head_id: Optional[str] = None


class CreateCheckpointRequest(BaseModel):
    reason: str = "手动创建"
    chapter_number: Optional[int] = None


class CreateCheckpointResponse(BaseModel):
    checkpoint_id: str
    message: str = "Checkpoint已创建"


class RollbackResponse(BaseModel):
    checkpoint_id: str
    trigger_reason: str = ""
    message: str = "已回滚"


class BranchDTO(BaseModel):
    branch_point_id: str
    reason: str = ""
    children: List[Dict[str, Any]] = Field(default_factory=list)


class BranchesResponse(BaseModel):
    branches: List[BranchDTO] = Field(default_factory=list)


class GuardrailCheckRequest(BaseModel):
    text: str
    character_names: List[str] = Field(default_factory=list)
    chapter_goal: str = ""
    era: str = "ancient"
    scene_type: str = "auto"
    mode: str = "advise"  # advise | enforce


class GuardrailDimensionScore(BaseModel):
    name: str
    key: str
    score: float
    weight: float


class GuardrailViolationDTO(BaseModel):
    dimension: str
    type: str = ""
    severity: str = "info"
    description: str = ""
    original: str = ""
    suggestion: str = ""
    character: str = ""

    @field_validator("severity", mode="before")
    @classmethod
    def coerce_severity(cls, v: Any) -> str:
        from application.engine.services.guardrail_execution import (
            normalize_violation_severity_for_api,
        )

        return normalize_violation_severity_for_api(v)


class GuardrailCheckResponse(BaseModel):
    overall_score: float = 0.0
    passed: bool = False
    dimensions: List[GuardrailDimensionScore] = Field(default_factory=list)
    violations: List[GuardrailViolationDTO] = Field(default_factory=list)


class StoryPhaseDTO(BaseModel):
    phase: str = "setup"
    progress: float = 0.0
    description: str = ""
    can_advance: bool = False


class CharacterPsycheDTO(BaseModel):
    name: str
    role: str = ""
    core_belief: str = ""
    taboo: str = ""
    voice_tag: str = ""
    wound: str = ""
    trauma_count: int = 0


class CharacterPsycheListResponse(BaseModel):
    characters: List[CharacterPsycheDTO] = Field(default_factory=list)


class CharacterPsycheDetailDTO(BaseModel):
    name: str
    role: str = ""
    core_belief: str = ""
    taboo: str = ""
    voice_tag: str = ""
    wound: str = ""
    trauma_count: int = 0
    emotion_ledger: Dict[str, Any] = Field(default_factory=dict)
    mask_summary: str = ""


class ValidateBehaviorRequest(BaseModel):
    action: str


class ValidateBehaviorResponse(BaseModel):
    valid: bool = True
    warnings: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class ExtractCharacterPsycheResponse(BaseModel):
    """AI 抽取后写回 Bible 的结果"""
    ok: bool = True
    applied_keys: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ─── Helpers ───────────────────────────────────────────────────────

def _get_checkpoint_store():
    """获取 CheckpointStore（通过 DI）"""
    from interfaces.api.dependencies import get_checkpoint_store
    return get_checkpoint_store()


def _get_cast_graph(novel_id: str):
    """从 CastService 获取角色图"""
    from interfaces.api.dependencies import get_cast_service
    cast_service = get_cast_service()
    return cast_service.get_cast_graph(novel_id)


def _get_character_psyche_engine():
    """获取 CharacterPsycheEngine 实例"""
    try:
        from interfaces.api.dependencies import get_database
        from engine.infrastructure.memory.character_psyche import CharacterPsycheEngine
        return CharacterPsycheEngine(get_database())
    except Exception:
        return None


def _novel_exists(novel_id: str) -> bool:
    from interfaces.api.dependencies import get_novel_service
    return get_novel_service().get_novel(novel_id) is not None


# ─── Checkpoint Endpoints ──────────────────────────────────────────

@router.get("/{novel_id}/checkpoints", response_model=CheckpointListResponse)
async def list_checkpoints(novel_id: str, limit: int = 50):
    """列出小说的 Checkpoint 时间线"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    store = _get_checkpoint_store()
    try:
        head_id = await store.get_head(novel_id)
        checkpoints_data = await store.list_story_checkpoints(novel_id, limit=limit)
    except Exception as e:
        logger.warning("列出Checkpoint失败: %s", e)
        return CheckpointListResponse()

    dtos = []
    for cp in checkpoints_data:
        cp_id_str = cp.checkpoint_id.value if hasattr(cp.checkpoint_id, 'value') else str(cp.checkpoint_id)
        dtos.append(CheckpointDTO(
            id=cp_id_str,
            story_id=cp.story_id if hasattr(cp, 'story_id') else novel_id,
            trigger_type=cp.trigger_type.value if hasattr(cp.trigger_type, 'value') else str(cp.trigger_type),
            trigger_reason=cp.trigger_reason or "",
            parent_id=str(cp.parent_id) if cp.parent_id else None,
            chapter_number=cp.story_state.get("chapter_number") if isinstance(cp.story_state, dict) else None,
            created_at=cp.created_at.isoformat() if hasattr(cp, 'created_at') and cp.created_at else "",
            is_head=(cp_id_str == str(head_id)) if head_id else False,
        ))

    return CheckpointListResponse(checkpoints=dtos, head_id=str(head_id) if head_id else None)


@router.post("/{novel_id}/checkpoints", response_model=CreateCheckpointResponse)
async def create_checkpoint(novel_id: str, body: CreateCheckpointRequest):
    """手动创建 Checkpoint"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    from engine.application.checkpoint_manager.manager import CheckpointManager

    store = _get_checkpoint_store()
    manager = CheckpointManager(store)

    try:
        cp_id = await manager.on_chapter_completed(
            story_id=novel_id,
            chapter_number=body.chapter_number or 0,
            story_state={"manual": True, "reason": body.reason},
            character_masks={},
            emotion_ledger={},
            active_foreshadows=[],
            recent_summary=body.reason,
        )
        return CreateCheckpointResponse(checkpoint_id=cp_id.value if hasattr(cp_id, 'value') else str(cp_id))
    except Exception as e:
        logger.error("创建Checkpoint失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{novel_id}/checkpoints/{checkpoint_id}/rollback", response_model=RollbackResponse)
async def rollback_checkpoint(novel_id: str, checkpoint_id: str):
    """回滚到指定 Checkpoint"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    from engine.core.value_objects.checkpoint import CheckpointId
    from engine.application.checkpoint_manager.manager import CheckpointManager

    store = _get_checkpoint_store()
    manager = CheckpointManager(store)

    try:
        cp = await manager.rollback(novel_id, CheckpointId(checkpoint_id))
        if cp is None:
            raise HTTPException(status_code=404, detail="Checkpoint not found")
        return RollbackResponse(
            checkpoint_id=checkpoint_id,
            trigger_reason=cp.trigger_reason,
            message=f"已回滚到: {cp.trigger_reason}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("回滚失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{novel_id}/checkpoints/branches", response_model=BranchesResponse)
async def list_branches(novel_id: str):
    """列出平行宇宙分支"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    from engine.application.checkpoint_manager.manager import CheckpointManager

    store = _get_checkpoint_store()
    manager = CheckpointManager(store)

    try:
        branches = await manager.list_branches(novel_id)
        return BranchesResponse(branches=[
            BranchDTO(
                branch_point_id=b["branch_point"],
                reason=b.get("reason", ""),
                children=b.get("children", []),
            )
            for b in branches
        ])
    except Exception as e:
        logger.warning("列出分支失败: %s", e)
        return BranchesResponse()


@router.get("/{novel_id}/checkpoints/head")
async def get_head_checkpoint(novel_id: str):
    """获取当前 HEAD Checkpoint"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    store = _get_checkpoint_store()
    try:
        head_id = await store.get_head(novel_id)
        if not head_id:
            return {"head_id": None, "state": None}
        cp = await store.load(head_id)
        if not cp:
            return {"head_id": str(head_id), "state": None}
        return {
            "head_id": str(head_id),
            "state": {
                "trigger_type": cp.trigger_type.value if hasattr(cp.trigger_type, 'value') else str(cp.trigger_type),
                "trigger_reason": cp.trigger_reason,
                "story_state": cp.story_state,
                "active_foreshadows": cp.active_foreshadows,
            },
        }
    except Exception as e:
        logger.warning("获取HEAD失败: %s", e)
        return {"head_id": None, "state": None}


# ─── Guardrail Endpoints ───────────────────────────────────────────

@router.post("/{novel_id}/guardrail/check", response_model=GuardrailCheckResponse)
async def guardrail_check(novel_id: str, body: GuardrailCheckRequest):
    """六维度质量检查"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    try:
        from application.engine.services.guardrail_execution import run_guardrail_sync

        dto = run_guardrail_sync(
            novel_id,
            body.text,
            body.chapter_goal,
            body.character_names or None,
            body.era,
            body.scene_type,
            body.mode,
        )
        return GuardrailCheckResponse.model_validate(dto)
    except Exception as e:
        logger.error("质量检查失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ─── StoryPhase Endpoints ──────────────────────────────────────────

@router.get("/{novel_id}/story-phase", response_model=StoryPhaseDTO)
async def get_story_phase(novel_id: str):
    """获取小说的故事阶段"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    from application.narrative_engine.story_phase_resolution import resolve_story_phase_payload

    payload = resolve_story_phase_payload(novel_id)
    return StoryPhaseDTO(**payload)


@router.put("/{novel_id}/story-phase", response_model=StoryPhaseDTO)
async def update_story_phase(novel_id: str, body: StoryPhaseDTO):
    """更新小说的故事阶段"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    try:
        from engine.core.entities.story import StoryPhase as StoryPhaseEnum
        new_phase = StoryPhaseEnum(body.phase)
    except (ValueError, ImportError):
        new_phase = body.phase

    try:
        from interfaces.api.dependencies import get_novel_service
        novel_service = get_novel_service()
        novel = novel_service.get_novel(novel_id)
        if novel and hasattr(novel, 'story_phase'):
            novel.story_phase = new_phase
            return StoryPhaseDTO(
                phase=body.phase,
                progress=body.progress,
                description=body.description,
                can_advance=body.can_advance,
            )
    except Exception as e:
        logger.warning("更新StoryPhase失败: %s", e)

    return body


# ─── Character Psyche Endpoints ──────────────────────────────────

def _get_bible_characters(novel_id: str) -> List[Dict[str, Any]]:
    """从 bible_characters 表直接读取角色数据（始终可靠的主数据源）"""
    try:
        from interfaces.api.dependencies import get_database
        db = get_database()
        with db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, name, description, mental_state, verbal_tic, idle_behavior,
                       mental_state_reason, public_profile, hidden_profile, reveal_chapter,
                       core_belief, moral_taboos_json, voice_profile_json, active_wounds_json
                FROM bible_characters WHERE novel_id = ? ORDER BY name
                """,
                (novel_id,),
            ).fetchall()
            import json as _json
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                for jk, dk, empty in (
                    ("moral_taboos_json", "moral_taboos", []),
                    ("voice_profile_json", "voice_profile", {}),
                    ("active_wounds_json", "active_wounds", []),
                ):
                    raw_j = d.pop(jk, None)
                    try:
                        parsed = json.loads(raw_j) if raw_j else empty
                        if not isinstance(parsed, type(empty)):
                            parsed = empty
                        d[dk] = parsed
                    except Exception:
                        d[dk] = empty
                out.append(d)
            return out
    except Exception as e:
        logger.debug("读取 bible_characters 失败: %s", e)
        return []


def _world_snippet_from_bible_for_extract(bible: Any, max_len: int = 2400) -> str:
    """拼一段世界观/文风提要，供角色抽取提示用。"""
    parts: List[str] = []
    for sn in getattr(bible, "style_notes", None) or []:
        c = getattr(sn, "content", "") or ""
        if c.strip():
            parts.append(f"【文风】{c.strip()[:800]}")
    for ws in getattr(bible, "world_settings", None) or []:
        nm = getattr(ws, "name", "") or ""
        ds = getattr(ws, "description", "") or ""
        if nm or ds:
            parts.append(f"【{nm}】{ds[:500]}")
    blob = "\n".join(parts)
    return blob[:max_len]


def _merge_character_from_extract(base: Any, data: Dict[str, Any]) -> tuple[Any, List[str]]:
    """将 LLM JSON 合并进 Bible CharacterDTO；返回 (merged_dto, applied_keys)。"""
    from dataclasses import replace

    applied: List[str] = []

    d_core = (data.get("core_belief") or "").strip()
    core_belief = d_core[:2000] if d_core else base.core_belief
    if d_core:
        applied.append("core_belief")

    moral_taboos = list(base.moral_taboos)
    d_taboo = data.get("moral_taboos")
    if isinstance(d_taboo, list) and d_taboo:
        moral_taboos = [str(x).strip()[:500] for x in d_taboo[:6] if str(x).strip()]
        if moral_taboos:
            applied.append("moral_taboos")

    voice_profile = dict(base.voice_profile or {})
    d_vp = data.get("voice_profile")
    if isinstance(d_vp, dict) and d_vp:
        for k in ("style", "sentence_pattern", "speech_tempo"):
            vv = d_vp.get(k)
            if isinstance(vv, str) and vv.strip():
                voice_profile[k] = vv.strip()[:600]
        if voice_profile != dict(base.voice_profile or {}):
            applied.append("voice_profile")

    active_wounds = list(base.active_wounds or [])
    d_aw = data.get("active_wounds")
    if isinstance(d_aw, list) and d_aw:
        nw: List[Dict[str, str]] = []
        for it in d_aw[:4]:
            if isinstance(it, dict):
                t = str(it.get("trigger", "") or "").strip()[:400]
                e = str(it.get("effect", "") or "").strip()[:400]
                if t or e:
                    nw.append({"trigger": t, "effect": e})
        if nw:
            active_wounds = nw
            applied.append("active_wounds")

    d_ms = (data.get("mental_state") or "").strip()
    mental_state = d_ms[:80] if d_ms else base.mental_state
    if d_ms:
        applied.append("mental_state")

    d_msr = (data.get("mental_state_reason") or "").strip()
    mental_state_reason = d_msr[:1200] if d_msr else base.mental_state_reason
    if d_msr:
        applied.append("mental_state_reason")

    d_vt = (data.get("verbal_tic") or "").strip()
    verbal_tic = d_vt[:500] if d_vt else base.verbal_tic
    if d_vt:
        applied.append("verbal_tic")

    d_ib = (data.get("idle_behavior") or "").strip()
    idle_behavior = d_ib[:500] if d_ib else base.idle_behavior
    if d_ib:
        applied.append("idle_behavior")

    d_pub = (data.get("public_profile") or "").strip()
    public_profile = d_pub[:4000] if d_pub else base.public_profile
    if d_pub:
        applied.append("public_profile")

    d_hid = (data.get("hidden_profile") or "").strip()
    hidden_profile = d_hid[:4000] if d_hid else base.hidden_profile
    if d_hid:
        applied.append("hidden_profile")

    reveal_chapter = base.reveal_chapter
    d_rc = data.get("reveal_chapter")
    if d_rc is not None:
        try:
            rc_int = int(d_rc)
            if rc_int >= 1:
                reveal_chapter = rc_int
                applied.append("reveal_chapter")
        except (TypeError, ValueError):
            pass

    merged = replace(
        base,
        core_belief=core_belief,
        moral_taboos=moral_taboos,
        voice_profile=voice_profile,
        active_wounds=active_wounds,
        mental_state=mental_state or "NORMAL",
        mental_state_reason=mental_state_reason,
        verbal_tic=verbal_tic,
        idle_behavior=idle_behavior,
        public_profile=public_profile,
        hidden_profile=hidden_profile,
        reveal_chapter=reveal_chapter,
    )
    return merged, applied


def _extract_core_belief(description: str, relationships: list) -> str:
    """从 Bible description 和关系列表中推断核心信念

    专业小说家视角：核心信念 = 角色做价值选择时的底层驱动力
    提取策略：寻找「相信/认为/坚守/信奉/绝不/必须」等信念关键词句
    """
    if not description:
        return ""
    import re
    # 匹配信念句式
    patterns = [
        r'(?:坚信|深信|信奉|笃信|相信|认为|坚守|秉持)([^，。！？；\n]+)',
        r'(?:绝不|绝不|从不|绝不|誓死|宁死)([^，。！？；\n]+)',
        r'(?:唯一|只有|只要)([^，。！？；\n]+?)(?:才|就|能|会)',
        r'(?:底线|原则|信条|准则)(?:是|：|:)([^，。！？；\n]+)',
    ]
    for pat in patterns:
        m = re.search(pat, description)
        if m:
            return m.group(0).strip()
    return ""


def _extract_taboo(description: str) -> str:
    """从 Bible description 中推断绝对禁忌

    专业小说家视角：绝对禁忌 = 角色绝不做的事，触碰即崩
    """
    if not description:
        return ""
    import re
    patterns = [
        r'绝不([^，。！？；\n]+)',
        r'(?:禁忌|底线|禁区|逆鳞)(?:是|：|:)([^，。！？；\n]+)',
        r'(?:绝不会|绝不|从不)([^，。！？；\n]+)',
    ]
    matches = []
    for pat in patterns:
        for m in re.finditer(pat, description):
            matches.append(m.group(0).strip())
    return "、".join(matches[:3]) if matches else ""


def _extract_voice_tag(description: str, verbal_tic: str = "") -> str:
    """推断语言风格标签

    专业小说家视角：声线 = 角色说话的方式，比内容更能定义角色
    """
    if verbal_tic:
        return f"口头禅：{verbal_tic}"
    if not description:
        return ""
    import re
    tags = []
    if re.search(r'冷|冰|阴|漠|淡', description):
        tags.append("冷峻")
    elif re.search(r'热|笑|开朗|豪爽|爽朗', description):
        tags.append("豪爽")
    elif re.search(r'沉|稳|静|深思|寡言', description):
        tags.append("沉稳")
    elif re.search(r'傲|狂|张狂|不屑|高高在上', description):
        tags.append("傲慢")
    elif re.search(r'谨|小心|谨慎|防备|警惕', description):
        tags.append("谨慎")
    if re.search(r'短句|惜字如金|沉默寡言|不苟言笑', description):
        tags.append("惜字如金")
    elif re.search(r'话多|唠叨|滔滔不绝|啰嗦', description):
        tags.append("话多")
    return "、".join(tags) if tags else ""


def _extract_wound(description: str, mental_state: str = "") -> str:
    """从 description 和 mental_state 推断未愈合创伤

    专业小说家视角：创伤 = 角色的条件反射触发器，决定在压力下的非理性行为
    """
    if not description:
        return ""
    import re
    # 创伤句式
    patterns = [
        r'(?:曾被|曾经|过去|当年)([^，。！？；\n]+?)(?:背叛|伤害|抛弃|欺骗|打击)',
        r'(?:失去|丧|死)([^，。！？；\n]{2,15})',
        r'(?:创伤|阴影|梦魇|心结|伤疤)(?:是|：|:)([^，。！？；\n]+)',
        r'(?:害怕|恐惧|畏惧)([^，。！？；\n]+)',
    ]
    for pat in patterns:
        m = re.search(pat, description)
        if m:
            return m.group(0).strip()
    # mental_state 异常时推断有创伤
    if mental_state and mental_state not in ("NORMAL", "正常", ""):
        return f"当前心理状态异常：{mental_state}"
    return ""


def _build_psyche_from_bible(
    char: Dict[str, Any],
    cast_char: Optional[Any] = None,
) -> CharacterPsycheDTO:
    """从 Bible 角色行构建 CharacterPsycheDTO

    Args:
        char: bible_characters 表的行 dict
        cast_char: 可选的 CastGraphDTO.characters 元素（用于补充 role/traits）
    """
    desc = char.get("description", "") or ""
    mental = char.get("mental_state", "") or ""
    verbal = char.get("verbal_tic", "") or ""
    role = ""
    if cast_char and hasattr(cast_char, "role"):
        role = cast_char.role or ""
    if not role:
        # 从 description 推断 role
        import re
        role_match = re.search(
            r'(主角|主人公|反派|boss|配角|师父|师傅|师妹|师兄|师弟|师姐|长辈|首领|掌门|长老|圣子|郡主|公子|小姐)',
            desc,
        )
        if role_match:
            role = role_match.group(1)

    stored_cb = (char.get("core_belief") or "").strip()
    core_belief = stored_cb if stored_cb else _extract_core_belief(desc, [])

    moral_taboos = char.get("moral_taboos") or []
    if isinstance(moral_taboos, list) and moral_taboos:
        taboo = "、".join(str(x).strip() for x in moral_taboos[:5] if str(x).strip())
    else:
        taboo = _extract_taboo(desc)

    vp = char.get("voice_profile") or {}
    if isinstance(vp, dict) and str(vp.get("style", "") or "").strip():
        voice_tag = str(vp.get("style")).strip()
    else:
        voice_tag = _extract_voice_tag(desc, verbal)

    aw = char.get("active_wounds") or []
    wound = ""
    if isinstance(aw, list) and aw and isinstance(aw[0], dict):
        t = str(aw[0].get("trigger", "") or "").strip()
        e = str(aw[0].get("effect", "") or "").strip()
        wound = (f"{t}→{e}" if t and e else (t or e)).strip()
    if not wound:
        wound = _extract_wound(desc, mental)

    return CharacterPsycheDTO(
        name=char.get("name", ""),
        role=role,
        core_belief=core_belief,
        taboo=taboo,
        voice_tag=voice_tag,
        wound=wound,
        trauma_count=0,
    )


@router.get("/{novel_id}/character-psyches", response_model=CharacterPsycheListResponse)
async def list_character_psyches(novel_id: str):
    """获取角色心理画像概览列表

    数据源优先级：
    1. CharacterPsycheEngine（四维模型，需 autopilot 落库）
    2. Bible 角色设定 + 知识三元组（始终可用）
    """
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    try:
        # 从 Bible 获取基础角色列表（主数据源，始终有数据）
        bible_chars = _get_bible_characters(novel_id)
        if not bible_chars:
            return CharacterPsycheListResponse()

        # 构建 CastGraph name→DTO 索引（用于补充 role 等信息）
        cast_index: Dict[str, Any] = {}
        try:
            cast_graph = _get_cast_graph(novel_id)
            for ch in (cast_graph.characters or []):
                cast_index[ch.name] = ch
        except Exception:
            pass

        # 尝试从 CharacterPsycheEngine 叠加四维数据
        psyche_engine = _get_character_psyche_engine()
        characters = []
        for bc in bible_chars:
            # 先构建基础画像
            cast_char = cast_index.get(bc["name"])
            dto = _build_psyche_from_bible(bc, cast_char)

            # 如果 PsycheEngine 有数据，覆盖四维字段
            if psyche_engine:
                try:
                    char_id = bc.get("id", "") or bc["name"]
                    psyche_data = await psyche_engine.load_character(str(char_id))
                    if psyche_data:
                        dto = CharacterPsycheDTO(
                            name=psyche_data.name,
                            role=dto.role or getattr(psyche_data, 'role', ''),
                            core_belief=psyche_data.core_belief or dto.core_belief,
                            taboo="、".join(psyche_data.moral_taboos) if psyche_data.moral_taboos else dto.taboo,
                            voice_tag=psyche_data.voice_profile.style if psyche_data.voice_profile else dto.voice_tag,
                            wound=psyche_data.active_wounds[0].description if psyche_data.active_wounds else dto.wound,
                            trauma_count=len(psyche_data.evolution_patches),
                        )
                except Exception:
                    pass

            characters.append(dto)

        return CharacterPsycheListResponse(characters=characters)
    except Exception as e:
        logger.warning("获取角色心理画像列表失败: %s", e)
        return CharacterPsycheListResponse()


@router.get("/{novel_id}/character-psyches/{character_name}", response_model=CharacterPsycheDetailDTO)
async def get_character_psyche(novel_id: str, character_name: str):
    """获取单个角色心理画像详情

    数据源优先级：
    1. CharacterPsycheEngine（四维模型 + 面具，需 autopilot 落库）
    2. Bible 角色设定 + 知识三元组推断（始终可用）
    """
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    try:
        # 从 Bible 查找目标角色
        bible_chars = _get_bible_characters(novel_id)
        target_bible = None
        for bc in bible_chars:
            if bc["name"] == character_name:
                target_bible = bc
                break

        if not target_bible:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_name}' not found in Bible",
            )

        # 从 CastGraph 补充
        cast_char = None
        try:
            cast_graph = _get_cast_graph(novel_id)
            for ch in (cast_graph.characters or []):
                if ch.name == character_name:
                    cast_char = ch
                    break
        except Exception:
            pass

        # 构建基础画像
        base_dto = _build_psyche_from_bible(target_bible, cast_char)
        desc = target_bible.get("description", "") or ""
        mental = target_bible.get("mental_state", "") or ""
        idle = target_bible.get("idle_behavior", "") or ""

        # 构建 mask_summary（作家视角的角色速写）
        mask_parts = [f"[角色速写 - {target_bible['name']}]"]
        if base_dto.core_belief:
            mask_parts.append(f"核心信念：{base_dto.core_belief}")
        if base_dto.taboo:
            mask_parts.append(f"绝对禁忌：{base_dto.taboo}")
        if base_dto.voice_tag:
            mask_parts.append(f"语言指纹：{base_dto.voice_tag}")
        if base_dto.wound:
            mask_parts.append(f"旧伤/条件反射：{base_dto.wound}")
        if mental and mental != "NORMAL":
            mask_parts.append(f"当前心理状态：{mental}")
        if idle:
            mask_parts.append(f"待机小动作：{idle}")
        if desc and not base_dto.core_belief:
            # 没有信念时用 description 前半段作为速写
            mask_parts.append(f"人设概要：{desc[:80]}")
        mask_summary = "\n".join(mask_parts)

        # 尝试从 CharacterPsycheEngine 获取四维增强数据
        psyche_engine = _get_character_psyche_engine()
        if psyche_engine:
            char_id = target_bible.get("id", "") or character_name
            try:
                psyche_data = await psyche_engine.load_character(str(char_id))
                if psyche_data:
                    mask = await psyche_engine.compute_mask(str(char_id), 0)
                    engine_mask_summary = mask.to_t0_fact_lock() if mask else ""
                    return CharacterPsycheDetailDTO(
                        name=psyche_data.name,
                        role=base_dto.role or getattr(psyche_data, 'role', ''),
                        core_belief=psyche_data.core_belief or base_dto.core_belief,
                        taboo="、".join(psyche_data.moral_taboos) if psyche_data.moral_taboos else base_dto.taboo,
                        voice_tag=psyche_data.voice_profile.style if psyche_data.voice_profile else base_dto.voice_tag,
                        wound=psyche_data.active_wounds[0].description if psyche_data.active_wounds else base_dto.wound,
                        trauma_count=len(psyche_data.evolution_patches),
                        emotion_ledger={},
                        mask_summary=engine_mask_summary or mask_summary,
                    )
            except Exception as e:
                logger.debug("PsycheEngine 增强失败，使用 Bible 基础画像: %s", e)

        # 返回 Bible 基础画像
        return CharacterPsycheDetailDTO(
            name=target_bible["name"],
            role=base_dto.role,
            core_belief=base_dto.core_belief,
            taboo=base_dto.taboo,
            voice_tag=base_dto.voice_tag,
            wound=base_dto.wound,
            trauma_count=0,
            emotion_ledger={},
            mask_summary=mask_summary,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取角色心理画像详情失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{novel_id}/character-psyches/{character_name}/validate", response_model=ValidateBehaviorResponse)
async def validate_character_behavior(novel_id: str, character_name: str, body: ValidateBehaviorRequest):
    """验证角色行为是否符合心理画像设定

    数据源优先级：
    1. CharacterPsycheEngine 面具验证（精确四维匹配）
    2. Bible 角色设定构建的基础面具（从设定推断）
    """
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    try:
        # 优先使用 CharacterPsycheEngine 的面具验证
        psyche_engine = _get_character_psyche_engine()
        if psyche_engine:
            # 通过 Bible 查找角色 ID
            bible_chars = _get_bible_characters(novel_id)
            for bc in bible_chars:
                if bc["name"] == character_name:
                    char_id = bc.get("id", "") or character_name
                    try:
                        mask = await psyche_engine.compute_mask(str(char_id), 0)
                        if mask:
                            result = mask.validate_behavior(body.action)
                            if isinstance(result, dict):
                                return ValidateBehaviorResponse(
                                    valid=result.get("valid", True),
                                    warnings=result.get("warnings", []),
                                    suggestions=result.get("suggestions", []),
                                )
                    except Exception as e:
                        logger.debug("PsycheEngine 验证失败，回退到 Bible 面具: %s", e)
                    break

        # 回退：从 Bible 构建基础面具验证
        from engine.core.value_objects.character_mask import CharacterMask
        bible_chars = _get_bible_characters(novel_id)
        target = None
        for bc in bible_chars:
            if bc["name"] == character_name:
                target = bc
                break

        desc = (target.get("description", "") or "") if target else ""
        mental = (target.get("mental_state", "") or "") if target else ""
        taboo_str = _extract_taboo(desc)

        mask = CharacterMask(
            character_id=(target.get("id", "") or "") if target else "",
            name=character_name,
            core_belief=_extract_core_belief(desc, []),
            moral_taboos=[t.strip() for t in taboo_str.split("、") if t.strip()] if taboo_str else [],
        )
        result = mask.validate_behavior(body.action)
        if isinstance(result, dict):
            return ValidateBehaviorResponse(
                valid=result.get("valid", True),
                warnings=result.get("warnings", []),
                suggestions=result.get("suggestions", []),
            )
        return ValidateBehaviorResponse(valid=bool(result))
    except Exception as e:
        logger.warning("行为验证失败: %s", e)
        return ValidateBehaviorResponse(valid=True, warnings=[f"验证服务不可用: {e}"])


@router.post(
    "/{novel_id}/character-psyches/{character_name}/extract",
    response_model=ExtractCharacterPsycheResponse,
)
async def extract_character_psyche_to_bible(novel_id: str, character_name: str):
    """用 LLM 从 Bible 角色条目中抽取 T0/声线/创伤/锚点等，写回 Bible（与引导页落库同源）。

    人可在工作台或世界观中继续改字段；本接口为覆盖式合并：仅当模型返回非空字段时才覆盖对应项。
    """
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    from interfaces.api.dependencies import get_bible_service, get_llm_service
    from domain.ai.services.llm_service import GenerationConfig
    from domain.ai.value_objects.prompt import Prompt
    from application.ai.llm_json_extract import parse_llm_json_to_dict
    from application.world.dtos.bible_dto import CharacterDTO

    bible_service = get_bible_service()
    bible = bible_service.get_bible_by_novel(novel_id)
    if bible is None:
        raise HTTPException(status_code=404, detail="Bible not found")

    target: Optional[CharacterDTO] = None
    for c in bible.characters:
        if c.name == character_name:
            target = c
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"Character '{character_name}' not found in Bible")

    char_payload = {
        "id": target.id,
        "name": target.name,
        "description": target.description,
        "relationships": target.relationships,
        "public_profile": target.public_profile,
        "hidden_profile": target.hidden_profile,
        "reveal_chapter": target.reveal_chapter,
        "mental_state": target.mental_state,
        "mental_state_reason": target.mental_state_reason,
        "verbal_tic": target.verbal_tic,
        "idle_behavior": target.idle_behavior,
        "core_belief": target.core_belief,
        "moral_taboos": target.moral_taboos,
        "voice_profile": target.voice_profile,
        "active_wounds": target.active_wounds,
    }
    world_snippet = _world_snippet_from_bible_for_extract(bible)

    system = (
        "你是长篇小说角色设定编辑。根据作品 Bible 中的单条角色记录与可选的世界观提要，"
        "抽取写章时可用的结构化锚点。只输出一个 JSON 对象，不要 markdown 围栏，不要解释。"
    )
    schema_hint = """输出 JSON 须严格包含下列键（字符串用中文，可简短）：
{
  "core_belief": "",
  "moral_taboos": [],
  "voice_profile": {"style":"","sentence_pattern":"","speech_tempo":""},
  "active_wounds": [{"trigger":"","effect":""}],
  "mental_state": "NORMAL",
  "mental_state_reason": "",
  "verbal_tic": "",
  "idle_behavior": "",
  "public_profile": "",
  "hidden_profile": "",
  "reveal_chapter": null
}
约束：moral_taboos 最多 5 条；active_wounds 最多 3 条；句子简练；无把握时 mental_state 用 NORMAL。"""
    user = (
        f"世界观/文风提要（可为空）：\n{world_snippet or '（无）'}\n\n"
        f"当前角色 JSON：\n{json.dumps(char_payload, ensure_ascii=False)}\n\n"
        f"{schema_hint}"
    )

    llm = get_llm_service()
    prompt = Prompt(system=system, user=user)
    config = GenerationConfig(max_tokens=1400, temperature=0.35)
    try:
        result = await llm.generate(prompt, config)
        raw = result.content if hasattr(result, "content") else str(result)
    except Exception as e:
        logger.error("character extract LLM 失败: %s", e)
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {e}") from e

    data, errs = parse_llm_json_to_dict(raw)
    if not data:
        raise HTTPException(
            status_code=422,
            detail="无法解析模型 JSON：" + ("; ".join(errs) if errs else "空对象"),
        )

    merged, applied = _merge_character_from_extract(target, data)
    if not applied:
        return ExtractCharacterPsycheResponse(
            ok=True,
            applied_keys=[],
            warnings=["模型未返回新的非空字段，未写库。可补充简介或换模型后重试。"],
        )

    new_chars: List[CharacterDTO] = []
    for c in bible.characters:
        new_chars.append(merged if c.id == target.id else c)

    try:
        bible_service.update_bible(
            novel_id,
            characters=new_chars,
            world_settings=list(bible.world_settings),
            locations=list(bible.locations),
            timeline_notes=list(bible.timeline_notes),
            style_notes=list(bible.style_notes),
        )
    except Exception as e:
        logger.error("character extract 写 Bible 失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

    warnings: List[str] = []
    if errs:
        warnings.extend(errs)
    return ExtractCharacterPsycheResponse(ok=True, applied_keys=applied, warnings=warnings)
