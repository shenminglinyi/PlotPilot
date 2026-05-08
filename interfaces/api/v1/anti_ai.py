"""Anti-AI API 端点 — 提供前端交互接口。

端点：
- POST /api/v1/anti-ai/scan — 扫描章节 AI 味
- GET /api/v1/anti-ai/metrics/{chapter_id} — 获取章节 AI 味指标
- GET /api/v1/anti-ai/categories — 获取分类信息
- GET /api/v1/anti-ai/rules — 获取规则列表
- POST /api/v1/anti-ai/allowlist — 更新白名单
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from application.audit.services.anti_ai_audit import get_anti_ai_auditor, AntiAIAuditReport
from application.engine.rules.allowlist_manager import get_allowlist_manager, AllowlistRule
from application.engine.rules.positive_framing_rules import POSITIVE_FRAMING_MAP
from infrastructure.ai.prompt_loader import get_prompt_loader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/anti-ai", tags=["Anti-AI 防御"])


# ─── 请求/响应模型 ───

class ScanRequest(BaseModel):
    """扫描请求。"""
    content: str = Field(..., description="待扫描的章节正文")
    chapter_id: str = Field("", description="章节 ID")


class ScanResponse(BaseModel):
    """扫描响应。"""
    total_hits: int
    critical_hits: int
    warning_hits: int
    severity_score: float
    overall_assessment: str
    category_distribution: Dict[str, int]
    top_patterns: List[str]
    recommendations: List[str]
    improvement_suggestions: List[str]
    hits: List[Dict[str, Any]]


class CategoryInfo(BaseModel):
    """分类信息。"""
    key: str
    name: str
    icon: str
    description: str
    color: str
    sort_order: int
    prompt_count: int = 0


class RuleInfo(BaseModel):
    """规则信息。"""
    key: str
    anti_pattern: str
    positive_action: str
    category: str
    severity: str


class AllowlistUpdateRequest(BaseModel):
    """白名单更新请求。"""
    scene_type: str
    allowed_categories: List[str] = []
    allowed_patterns: List[str] = []
    max_density_per_1000: float = 1.0
    description: str = ""


# ─── 端点 ───

@router.post("/scan", response_model=ScanResponse)
async def scan_chapter(request: ScanRequest):
    """扫描章节 AI 味。"""
    auditor = get_anti_ai_auditor()
    report = auditor.scan_chapter(request.chapter_id, request.content)

    return ScanResponse(
        total_hits=report.metrics.total_hits,
        critical_hits=report.metrics.critical_hits,
        warning_hits=report.metrics.warning_hits,
        severity_score=report.metrics.severity_score,
        overall_assessment=report.metrics.overall_assessment,
        category_distribution=report.metrics.category_distribution,
        top_patterns=report.metrics.top_patterns,
        recommendations=report.recommendations,
        improvement_suggestions=report.improvement_suggestions,
        hits=[
            {
                "pattern": h.pattern,
                "text": h.text,
                "start": h.start,
                "end": h.end,
                "severity": h.severity,
                "category": h.category,
                "replacement_hint": h.replacement_hint,
            }
            for h in report.hits
        ],
    )


@router.get("/categories", response_model=List[CategoryInfo])
async def get_categories():
    """获取提示词分类信息（含 Anti-AI）。"""
    loader = get_prompt_loader()
    categories = loader.get_categories()

    result = []
    for cat in categories:
        key = cat.get("key", "")
        prompts_in_cat = loader.list_by_category(key)
        result.append(CategoryInfo(
            key=key,
            name=cat.get("name", key),
            icon=cat.get("icon", "📝"),
            description=cat.get("description", ""),
            color=cat.get("color", "#6b7280"),
            sort_order=cat.get("sort_order", 99),
            prompt_count=len(prompts_in_cat),
        ))

    return result


@router.get("/rules", response_model=List[RuleInfo])
async def get_rules():
    """获取正向行为映射规则列表。"""
    rules = []
    for key, mapping in POSITIVE_FRAMING_MAP.items():
        rules.append(RuleInfo(
            key=key,
            anti_pattern=key,  # 规则名本身就是禁止的模式描述
            positive_action=mapping.get("action", ""),
            category=mapping.get("condition", "").split("时")[0] if "时" in mapping.get("condition", "") else "通用",
            severity="warning",  # 默认 warning 级别
        ))
    return rules


@router.post("/allowlist")
async def update_allowlist(request: AllowlistUpdateRequest):
    """更新场景化白名单。"""
    mgr = get_allowlist_manager()
    rule = AllowlistRule(
        scene_type=request.scene_type,
        allowed_categories=set(request.allowed_categories),
        allowed_patterns=set(request.allowed_patterns),
        max_density_per_1000=request.max_density_per_1000,
        description=request.description,
    )
    mgr.add_custom_rule(rule)
    return {"status": "ok", "scene_type": request.scene_type}


@router.get("/allowlist/scenes")
async def get_allowlist_scenes():
    """获取所有白名单场景类型。"""
    mgr = get_allowlist_manager()
    scenes = mgr.list_scene_types()
    result = []
    for scene in scenes:
        rule = mgr.get_rule(scene)
        result.append({
            "scene_type": scene,
            "allowed_categories": list(rule.allowed_categories),
            "allowed_patterns": list(rule.allowed_patterns),
            "max_density_per_1000": rule.max_density_per_1000,
            "description": rule.description,
        })
    return result


@router.get("/stats")
async def get_stats():
    """获取 Anti-AI 系统统计。"""
    loader = get_prompt_loader()
    anti_ai_prompts = loader.list_by_category("anti-ai")

    return {
        "total_prompts": loader.total_count,
        "anti_ai_prompts": len(anti_ai_prompts),
        "categories_count": len(loader.get_categories()),
        "cliche_patterns": 35,  # 增强版模式数
        "layers": {
            "L1_positive_framing": len(POSITIVE_FRAMING_MAP),
            "L2_protocol_rules": 5,  # P1-P5
            "L3_allowlist_scenes": len(get_allowlist_manager().list_scene_types()),
            "L4_state_vector": "active",
            "L5_context_quota": "active",
            "L6_token_guard": "active",
            "L7_audit": "active",
        },
    }
