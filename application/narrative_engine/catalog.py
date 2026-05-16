"""叙事引擎能力目录 — 小说家维度 × HTTP 能力族。

扩展约定：
1. 新增 `NarrativeLens` 成员（若属全新工作域）
2. 在 `api_catalog.API_SURFACE_FAMILIES` 增加一条「能力族」记录
3. 若有聚合读模型，在 `read_facade.NarrativeEngineReadFacade` 增加组装方法并在 `narrative_engine_routes` 暴露
"""

from __future__ import annotations

from enum import Enum
from typing import Dict


class NarrativeLens(str, Enum):
    """小说家视角下的能力域（用于 API 目录与聚合读模型分组）。"""

    # —— 叙事引擎聚合（BFF read model）——
    NARRATIVE_ENGINE = "narrative_engine"

    # —— 正文与作品元数据 ——
    MANUSCRIPT = "manuscript"

    # —— 世界观 / 设定 ——
    MACROCOSM = "macrocosm"

    # —— 结构：幕、章树、故事线、弧光、规划 ——
    PLOT_STRUCTURE = "plot_structure"

    # —— 时间与版本：编年史、快照、检查点、追溯 ——
    TIME_REVISION = "time_revision"

    # —— 潜文本：伏笔账本 ——
    SUBTEXT = "subtext"

    # —— 人物与声线：卡司、角色锚点、对白语料、声纹、监控 ——
    PERSONA_VOICE = "persona_voice"

    # —— 工艺与可信度：审稿、宏观手术、守门、反 AI ——
    CRAFT_QUALITY = "craft_quality"

    # —— 叙事知识 / 图谱 ——
    KNOWLEDGE_GRAPH = "knowledge_graph"

    # —— 编排自动化：DAG、长任务、上下文检索 ——
    ENGINE_AUTOMATION = "engine_automation"

    # —— 平台：模型配置、提示词工程、统计 ——
    PLATFORM = "platform"


LENS_METADATA_ZH: Dict[str, Dict[str, str]] = {
    NarrativeLens.NARRATIVE_ENGINE.value: {
        "title": "叙事引擎聚合",
        "summary": "一书一页 / 单角一线等稳定读模型，对齐工作台多域数据。",
    },
    NarrativeLens.MANUSCRIPT.value: {
        "title": "手稿与章",
        "summary": "章节 CRUD、审稿态、导出；作品列表与元数据。",
    },
    NarrativeLens.MACROCOSM.value: {
        "title": "世界观与圣经",
        "summary": "Bible、世界观表单、角色批量维护。",
    },
    NarrativeLens.PLOT_STRUCTURE.value: {
        "title": "情节结构",
        "summary": "幕→章树、连续规划、故事线、弧光、场景导演、大纲延展。",
    },
    NarrativeLens.TIME_REVISION.value: {
        "title": "时间与版本",
        "summary": "双螺旋编年史、语义快照、检查点 HEAD/回滚、写作追溯。",
    },
    NarrativeLens.SUBTEXT.value: {
        "title": "潜文本与伏笔",
        "summary": "伏笔账本 CRUD，与 Bible/引擎状态协同。",
    },
    NarrativeLens.PERSONA_VOICE.value: {
        "title": "人物与声线",
        "summary": "卡司图、角色锚点（心理/口癖/习惯动作）、正文对白语料、声纹样本、文风漂移、监控大盘。",
    },
    NarrativeLens.CRAFT_QUALITY.value: {
        "title": "工艺与可信",
        "summary": "六维守门、张力弹弓、宏观重构诊断、Anti-AI 扫描。",
    },
    NarrativeLens.KNOWLEDGE_GRAPH.value: {
        "title": "叙事知识与图谱",
        "summary": "故事知识库、三元组与推理证据链。",
    },
    NarrativeLens.ENGINE_AUTOMATION.value: {
        "title": "编排与自动化",
        "summary": "Autopilot DAG、异步 Jobs、上下文检索。",
    },
    NarrativeLens.PLATFORM.value: {
        "title": "平台与工程",
        "summary": "LLM 配置、提示词链、统计与扩展探测。",
    },
}
