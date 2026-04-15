from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from application.ai.llm_control_service import (
    LLMControlConfig,
    LLMControlPanelData,
    LLMProfile,
    LLMTestResult,
    LLMControlService,
)
from infrastructure.ai.provider_factory import LLMProviderFactory
from infrastructure.ai.prompt_manager import get_prompt_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/llm-control', tags=['llm-control'])

_service = LLMControlService()
_factory = LLMProviderFactory(_service)


# ---------- 模型列表拉取 ----------

class ModelListRequest(BaseModel):
    """请求体：根据 API Key 和 Base URL 拉取可用模型列表。"""
    protocol: str = 'openai'
    base_url: str = ''
    api_key: str = ''
    timeout_ms: int = 30000


class ModelItem(BaseModel):
    id: str = ''
    name: str = ''
    owned_by: str = ''


class ModelListResponse(BaseModel):
    success: bool = True
    items: List[ModelItem] = Field(default_factory=list)
    count: int = 0


def _normalize_model_items(data: Dict[str, Any]) -> List[ModelItem]:
    """将不同网关的 /models 响应统一为 ModelItem 列表。"""
    items: List[ModelItem] = []
    raw_list = data.get('data', [])
    if not isinstance(raw_list, list):
        return items
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        items.append(ModelItem(
            id=str(entry.get('id', '')),
            name=str(entry.get('id', '')),  # 多数网关不返回 name，回退到 id
            owned_by=str(entry.get('owned_by', '')),
        ))
    return items


@router.post('/models', response_model=ModelListResponse)
async def list_models(payload: ModelListRequest) -> ModelListResponse:
    """根据当前配置的 endpoint 拉取模型列表（OpenAI / Anthropic 兼容）。"""
    candidate = payload.model_dump()
    if not candidate.get('api_key'):
        # 尝试从当前激活配置中获取 key 作为 fallback
        active = _service.get_active_profile()
        if active:
            candidate['api_key'] = active.api_key

    api_format = (candidate.get('protocol') or '').strip().lower()
    api_key = (candidate.get('api_key') or '').strip()
    if not api_key:
        raise HTTPException(status_code=400, detail='API key is required to fetch model list')

    base_url = (candidate.get('base_url') or '').strip()
    timeout = max(1.0, (candidate.get('timeout_ms') or 30000) / 1000)

    if api_format == 'anthropic':
        url = f"{(base_url or 'https://api.anthropic.com').rstrip('/')}/v1/models"
        headers = {
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
        }
    else:
        url = f"{(base_url or 'https://api.openai.com/v1').rstrip('/')}/models"
        headers = {
            'Authorization': f'Bearer {api_key}',
        }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
        normalized = _normalize_model_items(data)
        return ModelListResponse(
            success=True,
            items=normalized,
            count=len(normalized),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f'Failed to fetch model list: {exc}') from exc


# ---------- 核心 CRUD + 测试 ----------

@router.get('', response_model=LLMControlPanelData)
async def get_llm_control_panel() -> LLMControlPanelData:
    return _service.get_control_panel_data()


@router.put('', response_model=LLMControlPanelData)
async def save_llm_control_panel(config: LLMControlConfig) -> LLMControlPanelData:
    saved = _service.save_config(config)
    return LLMControlPanelData(
        config=saved,
        presets=_service.get_presets(),
        runtime=_service.get_runtime_summary(saved),
    )


@router.post('/test', response_model=LLMTestResult)
async def test_llm_profile(profile: LLMProfile) -> LLMTestResult:
    try:
        return await _service.test_profile_model(profile, _factory.create_from_profile)
    except Exception as exc:
        logger.error('测试 LLM 配置失败: %s', exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ======================================================================
# 提示词广场 API (Prompt Plaza) — 数据库驱动 + 版本管理
# ======================================================================


class PromptUpdateRequest(BaseModel):
    """请求体：更新提示词节点内容（自动创建新版本）。"""
    system: Optional[str] = None
    user_template: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    change_summary: str = ""


class PromptRenderRequest(BaseModel):
    """请求体：渲染提示词模板。"""
    variables: Dict[str, Any] = Field(default_factory=dict)


class CreateNodeRequest(BaseModel):
    """请求体：创建自定义提示词节点。"""
    template_id: str = ""
    node_key: str = ""
    name: str = ""
    description: str = ""
    category: str = "generation"
    system: str = ""
    user_template: str = ""


class CreateTemplateRequest(BaseModel):
    """请求体：创建自定义模板包。"""
    name: str = ""
    description: str = ""
    category: str = "user"


# ------------------------------------------------------------------
# 统计 & 分类
# ------------------------------------------------------------------

@router.get('/prompts/stats')
async def get_prompt_stats() -> Dict[str, Any]:
    """获取提示词库统计信息。"""
    mgr = get_prompt_manager()
    mgr.ensure_seeded()
    return mgr.get_stats()


@router.get('/prompts/categories-info')
async def get_categories_info() -> List[Dict[str, Any]]:
    """获取分类定义（含各分类的节点计数）。"""
    mgr = get_prompt_manager()
    mgr.ensure_seeded()
    return mgr.get_categories_info()


# ------------------------------------------------------------------
# 模板包 CRUD
# ------------------------------------------------------------------

@router.get('/prompts/templates')
async def list_templates() -> List[Dict[str, Any]]:
    """列出所有模板包。"""
    mgr = get_prompt_manager()
    mgr.ensure_seeded()
    return [t.to_dict() for t in mgr.list_templates()]


@router.post('/prompts/templates')
async def create_template(payload: CreateTemplateRequest) -> Dict[str, Any]:
    """创建自定义模板包。"""
    mgr = get_prompt_manager()
    tmpl = mgr.create_template(
        name=payload.name or "未命名模板",
        description=payload.description,
        category=payload.category,
    )
    return {"status": "ok", "template": tmpl.to_dict()}


# ------------------------------------------------------------------
# 节点 CRUD
# ------------------------------------------------------------------

@router.get('/prompts')
async def list_prompts(
    category: Optional[str] = None,
    template_id: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """列举所有提示词节点（支持分类/模板过滤和搜索）。"""
    mgr = get_prompt_manager()
    mgr.ensure_seeded()

    if search and search.strip():
        nodes = mgr.search_nodes(search.strip())
    else:
        nodes = mgr.list_nodes(category=category, template_id=template_id,
                               include_versions=True)

    return [n.to_dict() for n in nodes]


@router.get('/prompts/by-category')
async def list_prompts_by_category() -> Dict[str, List[Dict[str, Any]]]:
    """按分类分组的提示词列表（用于前端分类卡片展示）。"""
    mgr = get_prompt_manager()
    mgr.ensure_seeded()
    grouped = mgr.get_nodes_by_category()
    result: Dict[str, List[Dict[str, Any]]] = {}
    for cat, nodes in grouped.items():
        result[cat] = [n.to_dict() for n in nodes]
    return result


@router.get('/prompts/{node_key}')
async def get_node_detail(node_key: str) -> Dict[str, Any]:
    """获取单个节点的完整详情（含激活版本的完整 system/user 内容）。"""
    mgr = get_prompt_manager()
    mgr.ensure_seeded()
    node = mgr.get_node(node_key, by_key=True)
    if node is None:
        # 尝试按 ID 查找
        node = mgr.get_node(node_key, by_key=False)
    if node is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt node '{node_key}' not found",
        )
    return node.to_detail_dict()


@router.post('/prompts/nodes')
async def create_node(payload: CreateNodeRequest) -> Dict[str, Any]:
    """创建自定义提示词节点。"""
    mgr = get_prompt_manager()
    mgr.ensure_seeded()

    # 如果没指定 template_id，使用内置模板包
    templates = mgr.list_templates()
    tid = payload.template_id or (templates[0].id if templates else "")
    if not tid:
        raise HTTPException(status_code=400, detail="No template available")

    key = payload.node_key or f"custom-{uuid.uuid4().hex[:8]}"
    node = mgr.create_node(
        template_id=tid,
        node_key=key,
        name=payload.name or "未命名提示词",
        system_prompt=payload.system,
        user_template=payload.user_template,
        description=payload.description,
        category=payload.category,
    )
    return {"status": "ok", "node": node.to_dict()}


@router.delete('/prompts/nodes/{node_id}')
async def delete_node(node_id: str) -> Dict[str, str]:
    """删除自定义节点（内置节点不允许删除）。"""
    mgr = get_prompt_manager()
    mgr.ensure_seeded()
    node = mgr.get_node(node_id, by_key=False)
    if node and node.is_builtin:
        raise HTTPException(status_code=403, detail="Cannot delete built-in prompt")
    success = mgr.delete_node(node_id)
    if not success:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"status": "ok", "node_id": node_id}


# ------------------------------------------------------------------
# 版本管理（核心！）
# ------------------------------------------------------------------

@router.get('/prompts/{node_key}/versions')
async def list_node_versions(node_key: str) -> List[Dict[str, Any]]:
    """获取节点的所有版本历史（时间线）。"""
    mgr = get_prompt_manager()
    mgr.ensure_seeded()
    node = mgr.get_node(node_key, by_key=True) or mgr.get_node(node_key, by_key=False)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_key}' not found")
    versions = mgr.get_node_versions(node.id)
    return [v.to_dict() for v in versions]


@router.get('/prompts/versions/{version_id}')
async def get_version_detail(version_id: str) -> Dict[str, Any]:
    """获取单个版本的完整内容。"""
    mgr = get_prompt_manager()
    ver = mgr.get_version(version_id)
    if not ver:
        raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found")
    return ver.to_detail_dict()


@router.put('/prompts/{node_key}')
async def update_node(node_key: str, payload: PromptUpdateRequest) -> Dict[str, Any]:
    """更新节点 —— 自动创建新版本（不覆盖历史）。"""
    mgr = get_prompt_manager()
    mgr.ensure_seeded()
    node = mgr.get_node(node_key, by_key=True) or mgr.get_node(node_key, by_key=False)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_key}' not found")

    updated = mgr.update_node(
        node.id,
        system_prompt=payload.system,
        user_template=payload.user_template,
        change_summary=payload.change_summary,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
    )
    return {
        "status": "ok",
        "node": updated.to_dict() if updated else None,
        "message": "已创建新版本",
    }


@router.post('/prompts/{node_key}/rollback/{version_id}')
async def rollback_node(node_key: str, version_id: str) -> Dict[str, Any]:
    """回滚节点到指定历史版本（创建回滚快照）。"""
    mgr = get_prompt_manager()
    mgr.ensure_seeded()
    node = mgr.get_node(node_key, by_key=True) or mgr.get_node(node_key, by_key=False)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_key}' not found")

    rolled_back = mgr.rollback_node(node.id, version_id)
    if not rolled_back:
        raise HTTPException(status_code=400, detail="Rollback failed")

    return {
        "status": "ok",
        "node": rolled_back.to_dict(),
        "message": f"已回滚到版本 {version_id}",
    }


@router.get('/prompts/compare/{v1_id}/{v2_id}')
async def compare_versions(v1_id: str, v2_id: str) -> Dict[str, Any]:
    """对比两个版本的差异。"""
    mgr = get_prompt_manager()
    try:
        return mgr.compare_versions(v1_id, v2_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ------------------------------------------------------------------
# 渲染
# ------------------------------------------------------------------

@router.post('/prompts/{node_key}/render')
async def render_prompt(
    node_key: str,
    payload: PromptRenderRequest,
) -> Dict[str, str]:
    """渲染指定提示词（传入变量，返回渲染后的 system/user）。"""
    mgr = get_prompt_manager()
    mgr.ensure_seeded()
    result = mgr.render(node_key, payload.variables)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{node_key}' not found")
    return result


# ------------------------------------------------------------------
# 导出 / 导入
# ------------------------------------------------------------------


class ImportPayload(BaseModel):
    """导入请求体：接受 prompts_defaults.json 格式或导出格式。"""
    _meta: Optional[Dict[str, Any]] = None
    categories: Optional[List[Dict[str, Any]]] = None
    prompts: List[Dict[str, Any]] = Field(default_factory=list)


@router.get('/prompts/export')
async def export_prompts() -> Dict[str, Any]:
    """导出所有提示词为 JSON（兼容 prompts_defaults.json 格式）。

    导出的 JSON 可通过 /import 端点重新导入，实现备份/迁移。
    """
    from datetime import datetime
    mgr = get_prompt_manager()
    mgr.ensure_seeded()

    # 收集分类定义
    categories = mgr.get_categories_info()

    # 收集所有节点（含激活版本内容）
    nodes = mgr.list_nodes(include_versions=True)
    prompts_export = []
    for node in nodes:
        detail = node.to_detail_dict()
        prompts_export.append({
            "id": detail.get("node_key", detail["id"]),
            "name": detail["name"],
            "description": detail.get("description", ""),
            "category": detail.get("category", "generation"),
            "source": detail.get("source", ""),
            "builtin": detail.get("is_builtin", False),
            "tags": detail.get("tags", []),
            "variables": detail.get("variables", []),
            "output_format": detail.get("output_format", "text"),
            "system": detail.get("system", ""),
            "user_template": detail.get("user_template", ""),
        })

    return {
        "_meta": {
            "version": "1.0.0",
            "description": "PlotPilot 提示词导出",
            "exported_at": datetime.now().isoformat(),
            "source": "prompt_plaza_export",
        },
        "categories": [
            {"key": c["key"], "name": c["name"], "icon": c["icon"],
             "description": c.get("description", ""), "color": c.get("color", "")}
            for c in categories
        ],
        "prompts": prompts_export,
    }


@router.post('/prompts/import')
async def import_prompts(payload: ImportPayload) -> Dict[str, Any]:
    """导入提示词 JSON（覆盖或新增节点）。

    支持：
    - 完整的 prompts_defaults.json 格式（含 _meta/categories/prompts）
    - 仅 prompts 数组的简化格式

    匹配逻辑：按 node_key 匹配已存在节点 → 更新；不存在的 → 新建。
    """
    from datetime import datetime
    mgr = get_prompt_manager()
    mgr.ensure_seeded()

    raw_prompts = payload.prompts
    if not raw_prompts:
        raise HTTPException(status_code=400, detail="导入数据为空：缺少 prompts 数组")

    now = datetime.now().isoformat()
    created_count = 0
    updated_count = 0
    skipped_count = 0
    errors: List[str] = []

    # 获取或创建目标模板包（优先使用内置模板包）
    templates = mgr.list_templates()
    builtin_tmpl = next((t for t in templates if t.is_builtin), None)
    target_template_id = builtin_tmpl.id if builtin_tmpl else (
        templates[0].id if templates else ""
    )
    if not target_template_id:
        # 兜底：创建一个
        tmpl = mgr.create_template(name="导入模板", description="从 JSON 导入")
        target_template_id = tmpl.id

    for idx, p in enumerate(raw_prompts):
        try:
            node_key = p.get("id", "") or p.get("node_key", "")
            name = p.get("name", f"导入提示词-{idx + 1}")
            system_content = p.get("system", "")
            user_content = p.get("user_template", "")

            if not node_key:
                # 无 key 的跳过
                skipped_count += 1
                continue

            # 尝试按 key 查找已有节点
            existing = mgr.get_node(node_key, by_key=True)

            tags_json = json.dumps(p.get("tags", []), ensure_ascii=False)
            vars_json = json.dumps(p.get("variables", []), ensure_ascii=False)

            if existing:
                # 已存在 → 更新（创建新版本）
                mgr.update_node(
                    existing.id,
                    system_prompt=system_content or None,
                    user_template=user_content or None,
                    change_summary=f"导入更新 ({now})",
                    name=name or None,
                    description=p.get("description"),
                    tags=p.get("tags"),
                )
                updated_count += 1
            else:
                # 不存在 → 新建节点
                mgr.create_node(
                    template_id=target_template_id,
                    node_key=node_key,
                    name=name,
                    system_prompt=system_content,
                    user_template=user_content,
                    description=p.get("description", ""),
                    category=p.get("category", "generation"),
                )
                created_count += 1

        except Exception as exc:
            key_hint = p.get("id", "") or p.get("name", f"index-{idx}")
            errors.append(f"{key_hint}: {exc}")
            skipped_count += 1

    return {
        "status": "ok",
        "summary": {
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "total": len(raw_prompts),
        },
        "errors": errors[:20],  # 最多返回前 20 条错误
        "message": (
            f"导入完成：新建 {created_count}，更新 {updated_count}"
            + (f"，跳过 {skipped_count}" if skipped_count else "")
        ),
    }
