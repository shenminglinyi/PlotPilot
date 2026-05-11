from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

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


def _openai_compatible_models_base(base_url: str) -> str:
    """OpenAI 兼容列表接口为 GET {base}/models，其中 base 必须带版本路径（通常为 /v1）。

    用户常只填 ``https://网关主机``，会误请求 ``/models`` 而非 ``/v1/models``，导致 400/HTML。
    若 URL 已包含非根 path（如火山 /api/v3、智谱 /api/paas/v4），则原样保留。
    """
    default = 'https://api.openai.com/v1'
    raw = (base_url or '').strip()
    if not raw:
        return default
    if '://' not in raw:
        raw = f'https://{raw}'
    parsed = urlparse(raw)
    path = (parsed.path or '').rstrip('/')
    if not path:
        path = '/v1'
    else:
        path = '/' + path.lstrip('/')
    return urlunparse(
        (parsed.scheme or 'https', parsed.netloc, path, '', '', ''),
    ).rstrip('/')


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
        openai_base = _openai_compatible_models_base(base_url)
        url = f'{openai_base}/models'
        headers = {
            'Authorization': f'Bearer {api_key}',
        }

    try:
        # 不向子进程继承 HTTP(S)_PROXY：本机 Clash/V2 等监听 127.0.0.1 时，httpx 走代理易导致
        # start_tls / BrokenResourceError，而国内直连 API 域名通常无需系统代理。
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            try:
                data = response.json()
            except json.JSONDecodeError:
                snippet = (response.text or '')[:240].replace('\n', ' ')
                raise HTTPException(
                    status_code=502,
                    detail=f'上游未返回 JSON（请检查 Base URL 与协议是否匹配 OpenAI 兼容）。请求 URL：{url}。片段：{snippet}',
                )
        normalized = _normalize_model_items(data)
        return ModelListResponse(
            success=True,
            items=normalized,
            count=len(normalized),
        )
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or '')[:400].replace('\n', ' ')
        raise HTTPException(
            status_code=502,
            detail=f'上游模型列表 HTTP {exc.response.status_code}：{body or exc.response.reason_phrase}（请求 {url}）',
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f'连接上游失败：{exc}（请求 {url}）。'
                '若日志里出现连向 127.0.0.1 某端口，多为系统 HTTP 代理注入导致 TLS 异常；'
                '当前接口已禁用继承环境代理，请更新后端后重试。仍失败请检查本机防火墙/DNS。'
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'拉取模型列表失败：{exc}') from exc


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


# ------------------------------------------------------------------
# 导出 / 导入（必须在 /prompts/{node_key} 之前注册，否则 export/import 会被当成 node_key）
# ------------------------------------------------------------------


class ImportPayload(BaseModel):
    """导入请求体：接受广场导出 JSON 格式或含 prompts 数组的旧版结构。"""

    model_config = ConfigDict(extra="ignore")

    # JSON 里常为 _meta，避免与动态路径参数混淆；用别名接收
    meta: Optional[Dict[str, Any]] = Field(default=None, validation_alias="_meta")
    categories: Optional[List[Dict[str, Any]]] = None
    prompts: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("/prompts/export")
async def export_prompts() -> Dict[str, Any]:
    """导出所有提示词为 JSON（与提示词广场 / 备份兼容）。"""
    from datetime import datetime

    mgr = get_prompt_manager()
    mgr.ensure_seeded()

    categories = mgr.get_categories_info()
    nodes = mgr.list_nodes(include_versions=True)
    prompts_export = []
    for node in nodes:
        detail = node.to_detail_dict()
        prompts_export.append(
            {
                "id": detail.get("node_key", detail["id"]),
                "name": detail["name"],
                "description": detail.get("description", ""),
                "category": detail.get("category", "generation"),
                "source": detail.get("source", ""),
                "builtin": detail.get("is_builtin", False),
                "tags": detail.get("tags", []),
                "variables": detail.get("variables", []),
                "output_format": detail.get("output_format", "text"),
                "contract_module": detail.get("contract_module"),
                "contract_model": detail.get("contract_model"),
                "system": detail.get("system", ""),
                "user_template": detail.get("user_template", ""),
            }
        )

    return {
        "_meta": {
            "version": "1.0.2",
            "description": "PlotPilot 提示词导出",
            "exported_at": datetime.now().isoformat(),
            "source": "prompt_plaza_export",
        },
        "categories": [
            {
                "key": c["key"],
                "name": c["name"],
                "icon": c["icon"],
                "description": c.get("description", ""),
                "color": c.get("color", ""),
            }
            for c in categories
        ],
        "prompts": prompts_export,
    }


@router.post("/prompts/import")
async def import_prompts(payload: ImportPayload) -> Dict[str, Any]:
    """导入提示词 JSON（覆盖或新增节点）。"""
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

    templates = mgr.list_templates()
    builtin_tmpl = next((t for t in templates if t.is_builtin), None)
    target_template_id = (
        builtin_tmpl.id if builtin_tmpl else (templates[0].id if templates else "")
    )
    if not target_template_id:
        tmpl = mgr.create_template(name="导入模板", description="从 JSON 导入")
        target_template_id = tmpl.id

    for idx, p in enumerate(raw_prompts):
        try:
            node_key = p.get("id", "") or p.get("node_key", "")
            name = p.get("name", f"导入提示词-{idx + 1}")
            system_content = p.get("system", "")
            user_content = p.get("user_template", "")

            if not node_key:
                skipped_count += 1
                continue

            existing = mgr.get_node(node_key, by_key=True)

            meta: Dict[str, Any] = {}
            for k in (
                "description",
                "tags",
                "variables",
                "output_format",
                "contract_module",
                "contract_model",
                "source",
                "category",
            ):
                if k in p:
                    meta[k] = p.get(k)

            if existing:
                mgr.update_node(
                    existing.id,
                    system_prompt=system_content or None,
                    user_template=user_content or None,
                    change_summary=f"导入更新 ({now})",
                    name=name or None,
                    **meta,
                )
                updated_count += 1
            else:
                mgr.create_node(
                    template_id=target_template_id,
                    node_key=node_key,
                    name=name,
                    system_prompt=system_content,
                    user_template=user_content,
                    description=p.get("description", ""),
                    category=p.get("category", "generation"),
                    tags=p.get("tags", []),
                    variables=p.get("variables", []),
                    output_format=p.get("output_format", "text"),
                    source=p.get("source", ""),
                    contract_module=p.get("contract_module"),
                    contract_model=p.get("contract_model"),
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
        "errors": errors[:20],
        "message": (
            f"导入完成：新建 {created_count}，更新 {updated_count}"
            + (f"，跳过 {skipped_count}" if skipped_count else "")
        ),
    }


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


# ======================================================================
# CPMS 增强端点：单节点调试 / COT 展示 / 沙盒渲染校验 / 变量注册表 / 绑定管理
# ======================================================================


class PromptDebugRequest(BaseModel):
    """请求体：单节点调试渲染（含诊断信息）。"""

    variables: Dict[str, Any] = Field(default_factory=dict)
    validate_schemas: bool = True


class PromptSandboxRequest(BaseModel):
    """请求体：沙盒渲染校验（保存前预检）。"""

    system: str = ""
    user_template: str = ""
    variables: Dict[str, Any] = Field(default_factory=dict)


@router.post('/prompts/{node_key}/debug')
async def debug_prompt_node(
    node_key: str,
    payload: PromptDebugRequest,
) -> Dict[str, Any]:
    """单节点调试：渲染 + 完整诊断信息（缺失变量、类型校验、渲染耗时）。

    用于提示词广场的"调试模式"——用户输入变量后实时查看渲染结果和诊断。
    """
    from infrastructure.ai.prompt_registry import get_prompt_registry

    registry = get_prompt_registry()

    # 获取节点
    node = registry.get_node(node_key)
    if node is None:
        # 尝试按 ID
        mgr = get_prompt_manager()
        mgr.ensure_seeded()
        node = mgr.get_node(node_key, by_key=False)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Prompt node '{node_key}' not found")

    # 使用 PromptRegistry.render 获取完整 RenderResult
    import time as _time
    t0 = _time.monotonic()
    result = registry.render(
        node_key if registry.get_node(node_key) else node.node_key,
        variables=payload.variables,
        validate_schemas=payload.validate_schemas,
    )
    elapsed_ms = int((_time.monotonic() - t0) * 1000)

    if result is None:
        return {
            "success": False,
            "error": "渲染失败：模板引擎返回 None",
            "node_key": node_key,
            "elapsed_ms": elapsed_ms,
        }

    return {
        "success": result.success,
        "system": result.system,
        "user": result.user,
        "diagnostics": {
            "errors": result.errors,
            "warnings": result.warnings,
            "missing_variables": result.missing_variables,
            "rendered_variables": result.rendered_variables,
            "missing_required": result.missing_required,
        },
        "node_key": node_key,
        "node_name": node.name,
        "variables_provided": list(payload.variables.keys()),
        "elapsed_ms": elapsed_ms,
    }


@router.get('/prompts/{node_key}/chain')
async def get_prompt_chain(node_key: str) -> Dict[str, Any]:
    """COT 展示：获取节点的完整调用链（绑定关系 + 上下游依赖）。

    返回：
    - 节点本身信息
    - 绑定的工作流/服务
    - 被哪些其他节点引用（依赖图）
    - 变量来源追踪
    """
    from infrastructure.ai.prompt_registry import get_prompt_registry

    registry = get_prompt_registry()

    node = registry.get_node(node_key)
    if node is None:
        mgr = get_prompt_manager()
        mgr.ensure_seeded()
        node = mgr.get_node(node_key, by_key=False)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Prompt node '{node_key}' not found")

    # 获取绑定信息（遍历所有工作流查找引用此节点的绑定）
    bindings = []
    reverse_deps = []
    try:
        from infrastructure.ai.prompt_binding_store import get_binding_store
        store = get_binding_store()
        for wf in store.list_workflows():
            for b in wf.bindings:
                if b.node_key == node.node_key:
                    bindings.append({
                        "workflow_id": b.workflow_id,
                        "workflow_name": wf.name,
                        "slot": b.slot,
                        "priority": b.priority,
                        "enabled": b.enabled,
                    })
                    reverse_deps.append({
                        "workflow_id": b.workflow_id,
                        "workflow_name": wf.name,
                        "slot": b.slot,
                    })
    except Exception as exc:
        logger.debug("绑定查询失败: %s", exc)

    # 变量来源追踪
    variable_sources = []
    for var_def in node.variables:
        var_name = var_def.get("name", "")
        var_source = var_def.get("source", "seed")
        variable_sources.append({
            "name": var_name,
            "type": var_def.get("type", "string"),
            "source": var_source,
            "required": var_def.get("required", False),
            "default": var_def.get("default"),
        })

    return {
        "node_key": node.node_key,
        "node_name": node.name,
        "category": node.category,
        "source": node.source,
        "bindings": bindings,
        "reverse_dependencies": reverse_deps,
        "variables": variable_sources,
        "version_count": len(node.versions) if hasattr(node, 'versions') and node.versions else 1,
    }


@router.post('/prompts/{node_key}/sandbox')
async def sandbox_render(
    node_key: str,
    payload: PromptSandboxRequest,
) -> Dict[str, Any]:
    """沙盒渲染校验：保存前预检。

    用户在提示词广场编辑模板后，保存前先用沙盒渲染验证：
    - 语法是否正确（Jinja2 / format_map）
    - 变量引用是否匹配
    - 渲染结果预览
    """
    from infrastructure.ai.prompt_template_engine import get_template_engine

    engine = get_template_engine()

    # 使用传入的 system/user_template 进行沙盒渲染
    import time as _time
    t0 = _time.monotonic()
    try:
        result = engine.render(
            system_template=payload.system,
            user_template=payload.user_template,
            variables=payload.variables,
        )
    except Exception as exc:
        return {
            "valid": False,
            "error": f"模板语法错误: {exc}",
            "system_preview": "",
            "user_preview": "",
        }
    elapsed_ms = int((_time.monotonic() - t0) * 1000)

    # 提取模板中引用的变量名
    import re
    system_vars = set(re.findall(r'\{(\w+)\}', payload.system))
    user_vars = set(re.findall(r'\{(\w+)\}', payload.user_template))
    all_template_vars = system_vars | user_vars
    provided_vars = set(payload.variables.keys())
    missing_vars = all_template_vars - provided_vars

    return {
        "valid": result.success and len(result.errors) == 0,
        "errors": result.errors,
        "warnings": result.warnings,
        "missing_variables": list(missing_vars),
        "missing_required": result.missing_required,
        "system_preview": (result.system or "")[:2000],
        "user_preview": (result.user or "")[:2000],
        "template_variables": {
            "system": list(system_vars),
            "user": list(user_vars),
            "all": list(all_template_vars),
        },
        "provided_variables": list(provided_vars),
        "elapsed_ms": elapsed_ms,
    }


@router.get('/prompts/variables')
async def list_variables(
    node_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """全局变量注册表：列出所有变量 Schema。

    可选按 node_key 过滤特定节点的变量。
    """
    from infrastructure.ai.variable_registry import get_variable_registry

    vreg = get_variable_registry()
    vreg.seed_builtin_variables()

    if node_key:
        # 过滤特定节点
        from infrastructure.ai.prompt_registry import get_prompt_registry
        registry = get_prompt_registry()
        node = registry.get_node(node_key)
        if node is None:
            return []
        return [
            {
                "name": var_def.get("name", ""),
                "display_name": var_def.get("display_name", var_def.get("desc", "")),
                "type": var_def.get("type", "string"),
                "required": var_def.get("required", False),
                "default": var_def.get("default"),
                "description": var_def.get("desc", ""),
                "source": var_def.get("source", ""),
                "scope": var_def.get("scope", "chapter"),
                "enum_values": var_def.get("enum_values", []),
            }
            for var_def in node.variables
        ]

    # 返回全部已注册的变量
    all_schemas = vreg.get_all_schemas()
    return [
        {
            "name": s.name,
            "display_name": s.display_name,
            "type": s.type.value if hasattr(s.type, 'value') else str(s.type),
            "required": s.required,
            "default": s.default,
            "description": s.description,
            "source": s.source,
            "scope": s.scope.value if hasattr(s.scope, 'value') else str(s.scope),
            "enum_values": s.enum_values,
        }
        for s in all_schemas.values()
    ]


@router.get('/prompts/{node_key}/bindings')
async def get_node_bindings(node_key: str) -> Dict[str, Any]:
    """获取节点的绑定关系（哪些工作流/服务使用了此提示词）。"""
    from infrastructure.ai.prompt_registry import get_prompt_registry

    registry = get_prompt_registry()
    node = registry.get_node(node_key)
    if node is None:
        mgr = get_prompt_manager()
        mgr.ensure_seeded()
        node = mgr.get_node(node_key, by_key=False)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Prompt node '{node_key}' not found")

    bindings = []
    try:
        from infrastructure.ai.prompt_binding_store import get_binding_store
        store = get_binding_store()
        for wf in store.list_workflows():
            for b in wf.bindings:
                if b.node_key == node.node_key:
                    bindings.append({
                        "id": b.id,
                        "workflow_id": b.workflow_id,
                        "workflow_name": wf.name,
                        "node_key": b.node_key,
                        "slot": b.slot,
                        "priority": b.priority,
                        "enabled": b.enabled,
                    })
    except Exception as exc:
        logger.debug("绑定查询失败: %s", exc)

    return {
        "node_key": node.node_key,
        "node_name": node.name,
        "bindings": bindings,
        "binding_count": len(bindings),
    }
