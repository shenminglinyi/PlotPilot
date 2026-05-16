"""HTTP 能力族目录 — 前端 `src/api/*` 与 FastAPI 路由的逻辑映射（抽象层，非逐条 OpenAPI 克隆）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from application.narrative_engine.catalog import LENS_METADATA_ZH, NarrativeLens


def _family(
    *,
    id: str,
    lens: NarrativeLens,
    path_prefixes: List[str],
    client_modules: List[str],
    backend_router_hint: str,
    note_zh: str,
) -> Dict[str, Any]:
    return {
        "id": id,
        "lens": lens.value,
        "path_prefixes": path_prefixes,
        "client_modules": client_modules,
        "backend_router_hint": backend_router_hint,
        "note_zh": note_zh,
    }


# 能力族：一条代表一组紧密相关的 HTTP 前缀 + 前端模块（维护时优先改族级说明）
API_SURFACE_FAMILIES: List[Dict[str, Any]] = [
    _family(
        id="narrative_engine_read",
        lens=NarrativeLens.NARRATIVE_ENGINE,
        path_prefixes=[
            "/novels/{novel_id}/narrative-engine/story-evolution",
            "/novels/{novel_id}/narrative-engine/persona-voice/{character_id}",
            "/novels/{novel_id}/workbench-context",
        ],
        client_modules=["narrativeEngine.ts", "useWorkbench（间接）"],
        backend_router_hint="narrative_engine_routes, workbench_context_routes, query_service",
        note_zh="小说家向只读聚合与工作台 BFF；底层复用共享内存 / DB 降级。",
    ),
    _family(
        id="manuscript_novel_chapter",
        lens=NarrativeLens.MANUSCRIPT,
        path_prefixes=[
            "/novels",
            "/novels/{novel_id}",
            "/novels/{novel_id}/chapters",
            "/export/novel/{novel_id}",
            "/export/chapter/{chapter_id}",
        ],
        client_modules=["novel.ts", "chapter.ts"],
        backend_router_hint="novels.router, chapters.router, export.router",
        note_zh="作品与章节生命周期、统计、导出。",
    ),
    _family(
        id="macrocosm_bible_world",
        lens=NarrativeLens.MACROCOSM,
        path_prefixes=[
            "/bible/novels/{novel_id}/bible",
            "/novels/{novel_id}/worldbuilding",
        ],
        client_modules=["bible.ts", "worldbuilding.ts"],
        backend_router_hint="bible.router, worldbuilding_routes",
        note_zh="圣经与世界观设定；时间轴笔记供编年史消费。",
    ),
    _family(
        id="plot_structure",
        lens=NarrativeLens.PLOT_STRUCTURE,
        path_prefixes=[
            "/novels/{novel_id}/structure",
            "/planning/",
            "/novels/{novel_id}/storylines",
            "/novels/{novel_id}/plot-arc",
            "/novels/{novel_id}/scene-director/analyze",
            "/novels/{novel_id}/outline/extend",
        ],
        client_modules=["structure.ts", "planning.ts", "workflow.ts"],
        backend_router_hint="story_structure, continuous_planning_routes, generation.router",
        note_zh="幕章树、宏观/幕间规划、故事线与弧光。",
    ),
    _family(
        id="time_revision",
        lens=NarrativeLens.TIME_REVISION,
        path_prefixes=[
            "/novels/{novel_id}/chronicles",
            "/novels/{novel_id}/snapshots",
            "/novels/{novel_id}/checkpoints",
            "/novels/{novel_id}/traces",
        ],
        client_modules=["chronicles.ts", "snapshot.ts", "engineCore.ts"],
        backend_router_hint="chronicles, snapshot_routes, checkpoint_routes, trace_router",
        note_zh="纪事 × 快照 × 检查点 × 写作追溯。",
    ),
    _family(
        id="subtext_foreshadow",
        lens=NarrativeLens.SUBTEXT,
        path_prefixes=["/novels/{novel_id}/foreshadow-ledger"],
        client_modules=["foreshadow.ts"],
        backend_router_hint="foreshadow_ledger.router",
        note_zh="伏笔账本 CRUD。",
    ),
    _family(
        id="persona_voice_cast",
        lens=NarrativeLens.PERSONA_VOICE,
        path_prefixes=[
            "/novels/{novel_id}/cast",
            "/novels/{novel_id}/sandbox",
            "/novels/sandbox/generate-dialogue",
            "/novels/{novel_id}/voice/",
            "/novels/{novel_id}/monitor/",
        ],
        client_modules=["cast.ts", "sandbox.ts", "voice.ts", "voiceDrift.ts", "monitor.ts"],
        backend_router_hint="cast, sandbox, voice, monitor",
        note_zh="卡司、对白沙盒、声纹与文风监控。",
    ),
    _family(
        id="craft_quality",
        lens=NarrativeLens.CRAFT_QUALITY,
        path_prefixes=[
            "/novels/{novel_id}/guardrail/",
            "/novels/{novel_id}/chapters/{n}/review",
            "/novels/{novel_id}/writer-block/",
            "/novels/{novel_id}/macro-refactor/",
            "/anti-ai",
        ],
        client_modules=["engineCore.ts", "chapter.ts", "tools.ts", "anti-ai.ts"],
        backend_router_hint="checkpoint_routes, chapter_review, writer_block, macro_refactor, anti_ai_routes",
        note_zh="质检、审稿、张力工具、宏观手术、Anti-AI（独立前缀）。",
    ),
    _family(
        id="knowledge_story_kg",
        lens=NarrativeLens.KNOWLEDGE_GRAPH,
        path_prefixes=[
            "/novels/{novel_id}/knowledge",
            "/knowledge-graph/",
        ],
        client_modules=["knowledge.ts", "knowledgeGraph.ts"],
        backend_router_hint="knowledge.router, knowledge_graph_routes",
        note_zh="叙事知识库与知识图谱推理。",
    ),
    _family(
        id="engine_automation",
        lens=NarrativeLens.ENGINE_AUTOMATION,
        path_prefixes=[
            "/dag/",
            "/jobs/",
            "/novels/{novel_id}/context/retrieve",
            "/novels/{novel_id}/plan",
            "/autopilot/",
        ],
        client_modules=["dag.ts", "book.ts", "workflow.ts", "autopilot（若独立）"],
        backend_router_hint="dag_router, novels/jobs, context_intelligence, generation, autopilot_routes",
        note_zh="DAG 编排、异步任务、上下文检索、自动规划入口。",
    ),
    _family(
        id="chapter_elements",
        lens=NarrativeLens.PLOT_STRUCTURE,
        path_prefixes=["/chapters/{chapter_id}/elements", "/chapters/elements/"],
        client_modules=["chapterElement.ts"],
        backend_router_hint="chapter_element_routes",
        note_zh="章节元素（片场/要素）关联。",
    ),
    _family(
        id="narrative_entity_replay",
        lens=NarrativeLens.TIME_REVISION,
        path_prefixes=["/novels/{novel_id}/entities/{entity_id}/state"],
        client_modules=["tools.ts"],
        backend_router_hint="narrative_state.router",
        note_zh="实体在指定章节上的叙事重放状态。",
    ),
    _family(
        id="platform_settings",
        lens=NarrativeLens.PLATFORM,
        path_prefixes=[
            "/settings/",
            "/llm-control",
            "/system/extensions-status",
        ],
        client_modules=["settings.ts", "llmControl.ts"],
        backend_router_hint="llm_settings, llm_control, system_routes",
        note_zh="模型配置、提示词工程、扩展探测。",
    ),
    _family(
        id="platform_stats_legacy",
        lens=NarrativeLens.PLATFORM,
        path_prefixes=["/api/stats", "/api/jobs"],
        client_modules=["stats.ts", "book.ts"],
        backend_router_hint="stats_router (非 v1 前缀), legacy jobs",
        note_zh="旧版统计与任务根路径；与 v1 共存，迁移中。",
    ),
]


def build_surface_catalog_payload() -> Dict[str, Any]:
    """供 `GET /narrative-engine/surface-catalog` 序列化。"""
    lenses_out = [
        {
            "id": lens.value,
            **LENS_METADATA_ZH.get(lens.value, {"title": lens.value, "summary": ""}),
        }
        for lens in NarrativeLens
    ]
    return {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lenses": lenses_out,
        "families": list(API_SURFACE_FAMILIES),
        "notes_zh": [
            "路径均相对于 API 根 `/api/v1`，除非显式标注 legacy。",
            "能力族为逻辑分组；具体方法见各 FastAPI router 与前端 api 模块。",
            "新增前端模块时：先在此登记族或扩展现有族，再实现后端路由。",
        ],
    }
