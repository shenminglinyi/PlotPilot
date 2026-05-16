"""Pipeline Context — 管线执行的上下文和结果容器

PipelineContext 是贯穿整个管线的数据载体，每个 _step_xxx() 方法
读取和修改它。PipelineResult 是管线最终的输出。

设计原则：
- Context 是可变的（步骤往里塞数据），Result 是不可变的（管线输出）
- Context 携带所有步骤需要的依赖（novel_id, chapter_number, DB连接等）
- 步骤之间通过 Context 传递数据，不直接耦合
- 依赖通过 inject() 方法设置，不是构造参数（避免超长构造函数）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PipelineContext:
    """管线执行上下文 — 贯穿所有步骤的数据载体

    使用方式：
        ctx = PipelineContext(novel_id="novel-123", chapter_number=5)
        ctx.inject(
            novel_repository=repo,
            llm_service=llm,
            context_builder=cb,
            ...
        )
        result = await pipeline.run_chapter(ctx)
    """

    # ═══ 核心标识（必须设置） ═══
    novel_id: str = ""
    chapter_number: int = 0

    # ═══ 输入数据 ═══
    outline: str = ""                            # 章节大纲
    target_word_count: int = 2500                # 目标字数
    phase: str = "opening"                       # 当前故事阶段 (opening/development/convergence/finale)
    auto_approve_mode: bool = False              # 全自动模式
    genre: str = ""                              # 题材 (xuanhuan/xianxia/urban/mystery/short_drama)
    era: str = "ancient"                         # 时代背景

    # ═══ 步骤1产出：章节定位 ═══
    chapter_node: Optional[Any] = None           # StoryNode 实例
    needs_buffer: bool = False                   # 是否需要余韵章
    buffer_reason: str = ""                      # 余韵章原因

    # ═══ 步骤2产出：上下文 ═══
    context_text: str = ""                       # 组装后的上下文
    context_tokens: int = 0                      # 上下文 token 数
    voice_anchors: str = ""                      # 声线锚点
    bundle: Optional[Dict[str, Any]] = None      # chapter_workflow.prepare_chapter_generation() 的完整 bundle

    # ═══ 步骤3产出：节拍 ═══
    beats: List[Any] = field(default_factory=list)  # Beat 列表
    beat_sheet: Optional[Any] = None             # 规划阶段的 BeatSheet

    # ═══ 步骤4产出：生成内容 ═══
    chapter_content: str = ""                    # 章节正文（最终版）
    word_count: int = 0                          # 实际字数
    raw_beat_contents: List[str] = field(default_factory=list)  # 各节拍原始输出

    # ═══ 步骤5产出：策略验证 ═══
    validation_passed: bool = True
    validation_score: float = 0.0
    validation_violations: List[Dict[str, Any]] = field(default_factory=list)
    validation_suggestions: List[str] = field(default_factory=list)
    validation_dimensions: Dict[str, float] = field(default_factory=dict)  # 各维度分数

    # ═══ 步骤6产出：章节保存 ═══
    chapter_saved: bool = False
    save_method: str = ""                        # ephemeral / queue / repository

    # ═══ 步骤7产出：文风审计 ═══
    drift_alert: bool = False
    similarity_score: Optional[float] = None
    voice_mode: str = "statistics"               # statistics / llm
    rewrite_applied: bool = False                # 是否触发了定向改写
    rewrite_attempts: int = 0                    # 定向改写尝试次数

    # ═══ 步骤8产出：章后管线 ═══
    narrative_sync_ok: bool = False
    vector_stored: bool = False
    foreshadow_stored: bool = False
    triples_extracted: bool = False
    causal_edges_stored: bool = False
    character_mutations_stored: bool = False
    debt_updated: bool = False

    # ═══ 步骤9产出：张力打分 ═══
    tension_composite: Optional[float] = None    # 多维张力 (0-100)
    tension_plot: Optional[float] = None         # 情节张力
    tension_emotional: Optional[float] = None    # 情感张力
    tension_pacing: Optional[float] = None       # 节奏张力

    # ═══ 步骤10产出：收尾 ═══
    novel_stage_advanced: bool = False           # 状态是否推进
    next_stage: str = ""                         # 推进到的下一阶段

    # ═══ 断点续写 ═══
    existing_content: str = ""                   # 已有内容（断点续写）
    start_beat_index: int = 0                    # 从哪个节拍开始

    # ═══ 依赖注入（通过 inject() 设置） ═══
    novel_repository: Any = None
    chapter_repository: Any = None
    llm_service: Any = None
    context_builder: Any = None                  # ContextBuilder
    aftermath_pipeline: Any = None               # ChapterAftermathPipeline
    voice_drift_service: Any = None
    knowledge_service: Any = None
    foreshadowing_repository: Any = None
    story_node_repo: Any = None
    planning_service: Any = None
    chapter_workflow: Any = None                 # AutoNovelGenerationWorkflow
    background_task_service: Any = None
    circuit_breaker: Any = None
    volume_summary_service: Any = None
    policy_validator: Any = None                 # PolicyValidator（新增）

    # ═══ 杂项 ═══
    metadata: Dict[str, Any] = field(default_factory=dict)
    _dependencies: Dict[str, Any] = field(default_factory=dict)

    def inject(self, **deps) -> "PipelineContext":
        """注入依赖（链式调用）

        Args:
            **deps: 任意依赖，键名对应上述字段名

        Returns:
            self（支持链式调用）

        Usage:
            ctx.inject(
                novel_repository=repo,
                llm_service=llm,
                context_builder=cb,
            )
        """
        for key, value in deps.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                self._dependencies[key] = value
        return self

    def get_dep(self, key: str, default: Any = None) -> Any:
        """获取注入的依赖"""
        if hasattr(self, key):
            val = getattr(self, key)
            return val if val is not None else default
        return self._dependencies.get(key, default)

    def is_fully_equipped(self) -> bool:
        """检查是否具备运行管线的最低依赖"""
        return all([
            self.novel_id,
            self.novel_repository is not None,
            self.llm_service is not None,
        ])


@dataclass
class PipelineResult:
    """管线最终输出 — 不可变记录"""
    success: bool = True
    chapter_number: int = 0
    content: str = ""
    word_count: int = 0
    tension: int = 0                            # 0-100
    drift_alert: bool = False
    similarity_score: Optional[float] = None
    validation_score: float = 0.0
    validation_passed: bool = True
    narrative_sync_ok: bool = False
    error: Optional[str] = None

    # 审计快照（供 _step_finalize 落库）
    audit_snapshot: Dict[str, Any] = field(default_factory=dict)

    # 各步骤的执行状态
    step_status: Dict[str, str] = field(default_factory=dict)  # step_name → "ok"/"skipped"/"failed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "chapter_number": self.chapter_number,
            "word_count": self.word_count,
            "tension": self.tension,
            "drift_alert": self.drift_alert,
            "similarity_score": self.similarity_score,
            "validation_score": round(self.validation_score, 3),
            "validation_passed": self.validation_passed,
            "narrative_sync_ok": self.narrative_sync_ok,
            "error": self.error,
            "step_status": self.step_status,
        }
