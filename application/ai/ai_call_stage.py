"""AI 调用阶段分类（前后端共享单源）。

三段式: "{domain}.{phase}.{detail}"
- domain: 业务域 (autopilot / pipeline / dag / audit / analyst / blueprint / world / memory / evolution / reader / prop / engine)
- phase: 阶段 (macro / act / chapter / review / generate / compile / extract / simulate)
- detail: 具体动作

前端 TypeScript 镜像: frontend/src/constants/aiCallStages.ts
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple


class StageDef(NamedTuple):
    key: str          # "pipeline.chapter.prose"
    label: str        # "正文撰写"
    domain: str       # "pipeline"
    semantic: str     # "write" | "plan" | "audit" | "sync" | "review" | "generate"


AI_CALL_STAGES: List[StageDef] = [
    # ── Autopilot Daemon ──
    StageDef("autopilot.macro.planning",       "宏观规划",   "autopilot", "plan"),
    StageDef("autopilot.act.beat_sheet",       "幕级节拍",   "autopilot", "plan"),
    StageDef("autopilot.act.planning",         "幕级规划",   "autopilot", "plan"),
    StageDef("autopilot.post_chapter.pipeline","章后管线",   "autopilot", "sync"),

    # ── Story Pipeline (10 步) ──
    StageDef("pipeline.chapter.script",        "剧本生成",   "pipeline",  "plan"),
    StageDef("pipeline.chapter.prose",         "正文撰写",   "pipeline",  "write"),
    StageDef("pipeline.chapter.validate",      "策略校验",   "pipeline",  "audit"),
    StageDef("pipeline.chapter.voice",         "文风审计",   "pipeline",  "audit"),
    StageDef("pipeline.chapter.tension",       "张力打分",   "pipeline",  "audit"),

    # ── DAG Engine ──
    StageDef("dag.planning.outline",           "大纲规划",   "dag",       "plan"),
    StageDef("dag.planning.beat",              "节拍规划",   "dag",       "plan"),
    StageDef("dag.execution.prose",            "正文执行",   "dag",       "write"),
    StageDef("dag.execution.supplement",       "补充生成",   "dag",       "write"),
    StageDef("dag.review.consistency",         "一致性审查", "dag",       "audit"),
    StageDef("dag.review.quality",             "质量审查",   "dag",       "audit"),
    StageDef("dag.validation.gate",            "门禁校验",   "dag",       "audit"),
    StageDef("dag.anti_ai.detect",             "反AI检测",   "dag",       "audit"),
    StageDef("dag.world.context",              "世界观上下文","dag",       "sync"),
    StageDef("dag.props.extract",              "道具提取",   "dag",       "sync"),

    # ── Audit ──
    StageDef("audit.chapter.review",           "章节审稿",   "audit",     "audit"),
    StageDef("audit.macro.refactor",           "宏观重构",   "audit",     "audit"),

    # ── Analyst ──
    StageDef("analyst.style.drift",            "风格漂移",   "analyst",   "audit"),
    StageDef("analyst.tension.score",          "张力评分",   "analyst",   "audit"),
    StageDef("analyst.voice.analyze",          "声线分析",   "analyst",   "audit"),

    # ── Blueprint ──
    StageDef("blueprint.beat.generate",        "节拍生成",   "blueprint", "plan"),
    StageDef("blueprint.continuous.plan",      "连续规划",   "blueprint", "plan"),
    StageDef("blueprint.volume.summary",       "卷总结",     "blueprint", "sync"),

    # ── World ──
    StageDef("world.bible.generate",           "圣经生成",   "world",     "generate"),
    StageDef("world.knowledge.extract",        "知识抽取",   "world",     "sync"),
    StageDef("world.narrative.sync",           "叙事同步",   "world",     "sync"),

    # ── Memory ──
    StageDef("memory.context.compile",         "上下文编译", "memory",    "sync"),
    StageDef("memory.emotion.extract",         "情感抽取",   "memory",    "sync"),

    # ── Evolution ──
    StageDef("evolution.state.change",         "状态变更",   "evolution", "sync"),

    # ── Reader ──
    StageDef("reader.simulation.run",          "读者模拟",   "reader",    "audit"),

    # ── Prop ──
    StageDef("prop.llm.extract",               "道具LLM提取","prop",      "sync"),

    # ── Engine / Misc ──
    StageDef("engine.scene.generate",          "场景生成",   "engine",    "write"),
    StageDef("engine.scene.director",          "场景导演",   "engine",    "plan"),
    StageDef("engine.chapter.bridge",          "章节桥接",   "engine",    "plan"),
    StageDef("engine.beat.cot",                "节拍思维链", "engine",    "plan"),
]


STAGE_BY_KEY: Dict[str, StageDef] = {s.key: s for s in AI_CALL_STAGES}


def get_stage(key: str) -> StageDef | None:
    return STAGE_BY_KEY.get(key)


def get_stage_label(key: str) -> str:
    s = STAGE_BY_KEY.get(key)
    return s.label if s else key


def list_stages_by_domain(domain: str) -> List[StageDef]:
    return [s for s in AI_CALL_STAGES if s.domain == domain]
