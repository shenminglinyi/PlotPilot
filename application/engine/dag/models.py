"""DAG 核心数据模型 — Pydantic V2 定义

前后端共享 Schema，所有 DAG 相关的数据结构定义在此。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field, field_validator, model_validator


# ─── 枚举 ───


class NodeCategory(str, Enum):
    """节点分类"""
    CONTEXT = "context"        # 📦 上下文注入
    EXECUTION = "execution"    # ⚙️ 执行与生成
    VALIDATION = "validation"  # 🔍 校验与监控
    GATEWAY = "gateway"        # 🚦 网关与熔断
    WORLD = "world"            # 🏰 世界设定
    REVIEW = "review"          # 🔬 审稿质检
    ANTI_AI = "anti-ai"        # 🛡️ Anti-AI 防御
    PLANNING = "planning"      # 📐 规划设计
    PROP = "prop"              # 🎒 道具上下文


class NodeStatus(str, Enum):
    """节点运行时状态"""
    IDLE = "idle"
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    BYPASSED = "bypassed"
    DISABLED = "disabled"
    COMPLETED = "completed"


class EdgeCondition(str, Enum):
    """边条件表达式"""
    ON_SUCCESS = "on_success"
    ON_ERROR = "on_error"
    ON_DRIFT_ALERT = "on_drift_alert"
    ON_NO_DRIFT = "on_no_drift"
    ON_BREAKER_OPEN = "on_breaker_open"
    ON_BREAKER_CLOSED = "on_breaker_closed"
    ON_REVIEW_APPROVED = "on_review_approved"
    ON_REVIEW_REJECTED = "on_review_rejected"
    ALWAYS = "always"


class PortDataType(str, Enum):
    """端口数据类型"""
    TEXT = "text"
    JSON = "json"
    SCORE = "score"
    BOOLEAN = "boolean"
    LIST = "list"
    PROMPT = "prompt"
    OBJECT = "object"


# ─── 端口 ───


class NodePort(BaseModel):
    """节点的输入/输出端口"""
    name: str
    data_type: PortDataType = PortDataType.TEXT
    required: bool = True
    default: Any = None
    description: str = ""


# ─── 节点元数据（注册表用，类级别常量）───


class PromptMode(str, Enum):
    """提示词使用模式

    - CPMS_ONLY: 完全依赖提示词广场，无硬编码回退
    - CPMS_FIRST: 优先从提示词广场拉取，降级到节点内模板
    - TEMPLATE_ONLY: 仅使用节点内硬编码模板（不查广场）
    - INJECT: 从广场拉取片段注入到父节点的变量槽（子提示词）
    """
    CPMS_ONLY = "cpms_only"
    CPMS_FIRST = "cpms_first"
    TEMPLATE_ONLY = "template_only"
    INJECT = "inject"


class CPMSInjectionPoint(BaseModel):
    """CPMS 子提示词注入点定义 — 将广场提示词注入到父节点的指定变量槽"""
    cpms_node_key: str              # 广场提示词 node_key
    target_variable: str            # 注入到哪个模板变量
    description: str = ""           # 注入说明
    required: bool = False          # 是否必须


class NodeMeta(BaseModel):
    """节点元数据 — 注册表中的类型描述

    CPMS 联动设计（三级）：
    1. cpms_node_key: 主提示词关联（核心生成/提取/审稿节点）
    2. cpms_sub_keys: 子提示词注入列表（Anti-AI 层、行为协议等注入到生成节点变量槽）
    3. prompt_mode: 提示词使用模式（CPMS_FIRST / CPMS_ONLY / TEMPLATE_ONLY / INJECT）

    数据流转：
    - CPMS_FIRST 节点：execute() 内调用 self.resolve_prompt() → 自动走 CPMS → Config → Meta 三级降级
    - INJECT 节点：execute() 返回子提示词文本，由 DAG runtime 注入到下游节点变量
    - 广场编辑提示词 → 缓存失效 → 下次 DAG 运行自动拉取最新版
    """
    node_type: str
    display_name: str
    category: NodeCategory
    icon: str = "📦"
    color: str = "#6366f1"
    input_ports: List[NodePort] = Field(default_factory=list)
    output_ports: List[NodePort] = Field(default_factory=list)
    prompt_template: str = ""
    prompt_variables: List[str] = Field(default_factory=list)
    is_configurable: bool = True
    can_disable: bool = True
    default_timeout_seconds: int = 60
    default_max_retries: int = 1
    # ★ CPMS 主关联字段
    cpms_node_key: str = ""           # 对应提示词广场的 node_key
    # ★ CPMS 子提示词注入（Anti-AI 层、行为协议等注入到生成节点变量槽）
    cpms_sub_keys: List[CPMSInjectionPoint] = Field(default_factory=list)
    # ★ 提示词使用模式
    prompt_mode: PromptMode = PromptMode.CPMS_FIRST
    description: str = ""             # 节点功能描述（展示用）
    default_edges: List[str] = Field(default_factory=list)  # 默认下游节点类型


# ─── 节点配置 ───


class NodeConfig(BaseModel):
    """节点运行时配置（可被用户覆盖）"""
    prompt_template: Optional[str] = None
    prompt_variables: Dict[str, str] = Field(default_factory=dict)
    thresholds: Dict[str, float] = Field(default_factory=dict)
    model_override: Optional[str] = None
    max_retries: int = Field(default=1, ge=0, le=5)
    timeout_seconds: int = Field(default=60, ge=10, le=600)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=100, le=16000)


# ─── DAG 定义模型 ───


class NodeDefinition(BaseModel):
    """DAG 中的节点实例定义"""
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: str
    label: str = ""
    position: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    enabled: bool = True
    config: NodeConfig = Field(default_factory=NodeConfig)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        # ★ 动态校验：从注册表获取合法类型，消除硬编码白名单
        try:
            from application.engine.dag.registry import NodeRegistry
            registered = NodeRegistry.all_types()
            if registered and v not in registered:
                raise ValueError(f"未知节点类型: {v}，已注册: {sorted(registered)}")
        except ImportError:
            pass  # 注册表未加载时跳过校验（测试/迁移场景）
        return v


class EdgeDefinition(BaseModel):
    """DAG 中的边定义"""
    id: str = Field(pattern=r"^edge_[a-z0-9_]+$")
    source: str
    source_port: str = ""
    target: str
    target_port: str = ""
    condition: EdgeCondition = EdgeCondition.ALWAYS
    animated: bool = False


class DAGMetadata(BaseModel):
    """DAG 元数据"""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = "system"


class DAGDefinition(BaseModel):
    """DAG 完整定义 — 前后端共享核心模型"""
    id: str
    name: str
    version: int = Field(default=1, ge=1)
    description: str = ""
    nodes: List[NodeDefinition] = Field(default_factory=list)
    edges: List[EdgeDefinition] = Field(default_factory=list)
    metadata: DAGMetadata = Field(default_factory=DAGMetadata)

    def fingerprint(self) -> str:
        """计算 DAG 结构指纹（用于缓存编译结果）"""
        data = {
            "nodes": [{"id": n.id, "type": n.type, "enabled": n.enabled} for n in sorted(self.nodes, key=lambda n: n.id)],
            "edges": [{"id": e.id, "source": e.source, "target": e.target, "condition": e.condition.value}
                      for e in sorted(self.edges, key=lambda e: e.id)],
        }
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get_node(self, node_id: str) -> Optional[NodeDefinition]:
        """按 ID 查找节点"""
        return next((n for n in self.nodes if n.id == node_id), None)

    def get_entry_nodes(self) -> List[NodeDefinition]:
        """获取入口节点（无入边的节点）"""
        targets = {e.target for e in self.edges}
        return [n for n in self.nodes if n.id not in targets and n.enabled]

    def get_successors(self, node_id: str) -> List[str]:
        """获取直接后继节点 ID"""
        return [e.target for e in self.edges if e.source == node_id]

    def get_predecessors(self, node_id: str) -> List[str]:
        """获取直接前驱节点 ID"""
        return [e.source for e in self.edges if e.target == node_id]


# ─── 节点执行结果 ───


class NodeResult(BaseModel):
    """节点执行结果"""
    outputs: Dict[str, Any] = Field(default_factory=dict)
    status: NodeStatus = NodeStatus.SUCCESS
    metrics: Dict[str, float] = Field(default_factory=dict)
    duration_ms: int = 0
    error: Optional[str] = None


# ─── 节点运行时状态 ───


class NodeRunState(BaseModel):
    """节点运行时状态（前端 SSE 更新用）"""
    node_id: str
    status: NodeStatus = NodeStatus.IDLE
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: int = 0
    outputs: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, float] = Field(default_factory=dict)
    error: Optional[str] = None
    progress: float = 0.0  # 0.0 ~ 1.0


# ─── DAG 运行结果 ───


class DAGRunResult(BaseModel):
    """DAG 一次运行的结果"""
    dag_run_id: str
    novel_id: str
    status: str = "completed"  # completed / error / interrupted
    node_results: Dict[str, NodeResult] = Field(default_factory=dict)
    total_duration_ms: int = 0
    error_count: int = 0
    started_at: str = ""
    completed_at: str = ""


# ─── LangGraph 全局状态 ───


class NovelWorkflowState(BaseModel):
    """整个 DAG 运行期间的全局状态 — 映射到 LangGraph StateGraph"""
    novel_id: str = ""
    chapter_number: int = 0
    dag_run_id: str = ""

    # Context 节点输出
    world_rules: str = ""
    fact_lock: str = ""
    foreshadowing_block: str = ""
    voice_block: str = ""
    debt_due_block: str = ""

    # Execution 节点输出
    outline: str = ""
    beats: List[Dict[str, Any]] = Field(default_factory=list)
    content: str = ""
    word_count: int = 0

    # Validation 节点输出
    drift_score: float = 0.0
    drift_alert: bool = False
    tension_composite: float = 0.0
    tension_dimensions: Dict[str, float] = Field(default_factory=dict)
    anti_ai_severity: float = 0.0
    anti_ai_hits: List[Dict[str, Any]] = Field(default_factory=list)
    narrative_summary: str = ""
    narrative_events: List[Dict[str, Any]] = Field(default_factory=list)
    narrative_triples: List[Dict[str, Any]] = Field(default_factory=list)
    foreshadow_recovered: int = 0
    foreshadow_pending: int = 0
    inferred_triples: List[Dict[str, Any]] = Field(default_factory=list)

    # Gateway 输出
    breaker_status: str = "closed"
    review_approved: bool = False
    retry_count: int = 0

    # DAG 配置（用户覆盖）
    node_configs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    disabled_nodes: List[str] = Field(default_factory=list)

    # 内部状态
    current_node: str = ""
    current_stage: str = ""
    completed_nodes: Set[str] = Field(default_factory=set, exclude=True)

    model_config = {"arbitrary_types_allowed": True}


# ─── SSE 事件模型 ───


class NodeEvent(BaseModel):
    """SSE 节点事件"""
    type: str  # node_status_change / node_output / edge_data_flow
    novel_id: str
    node_id: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: Optional[NodeStatus] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0
    error: Optional[str] = None
    source_node: str = ""
    target_node: str = ""
    port: str = ""
    data_type: str = ""
    data_size: int = 0


# ─── 默认 DAG 实例 ───


def get_default_dag() -> DAGDefinition:
    """获取默认 DAG 实例（单幕全流程）"""
    return DAGDefinition(
        id="dag_default_single_act",
        name="单幕全流程（默认）",
        version=1,
        nodes=[
            NodeDefinition(id="ctx_blueprint", type="ctx_blueprint", label="📋 剧本基建", position={"x": 100, "y": 100}),
            NodeDefinition(id="ctx_memory", type="ctx_memory", label="🧠 记忆引擎", position={"x": 100, "y": 250}),
            NodeDefinition(id="ctx_foreshadow", type="ctx_foreshadow", label="🪝 伏笔注入器", position={"x": 100, "y": 400}),
            NodeDefinition(id="ctx_voice", type="ctx_voice", label="🎭 角色声线注入", position={"x": 100, "y": 550}),
            NodeDefinition(id="ctx_debt", type="ctx_debt", label="💰 叙事债务", position={"x": 100, "y": 700}),
            NodeDefinition(id="exec_beat", type="exec_beat", label="🥁 节拍放大器", position={"x": 500, "y": 200}),
            NodeDefinition(
                id="exec_writer", type="exec_writer", label="✍️ 剧情引擎", position={"x": 800, "y": 300},
                config=NodeConfig(
                    prompt_template="写作姿态：回忆并讲述这段事；避免写成交差用的说明文。\n\n{{context}}\n{{outline}}\n{{voice_block}}",
                    prompt_variables={"context": "", "outline": "", "voice_block": ""},
                ),
            ),
            NodeDefinition(
                id="val_style", type="val_style", label="🎭 文风警报器", position={"x": 1200, "y": 100},
                config=NodeConfig(
                    thresholds={"drift_warning": 0.5, "drift_critical": 0.75},
                    prompt_template="评估以下文本是否符合角色声线...",
                ),
            ),
            NodeDefinition(
                id="val_tension", type="val_tension", label="📈 张力评估器", position={"x": 1200, "y": 300},
                config=NodeConfig(thresholds={"tension_floor": 30, "tension_ceiling": 85}),
            ),
            NodeDefinition(id="val_anti_ai", type="val_anti_ai", label="🛡️ Anti-AI 审计", position={"x": 1200, "y": 500}),
            NodeDefinition(
                id="gw_circuit", type="gw_circuit", label="🔌 熔断保护", position={"x": 1500, "y": 300},
                config=NodeConfig(thresholds={"max_errors": 3}),
            ),
            NodeDefinition(id="val_narrative", type="val_narrative", label="🧬 叙事同步", position={"x": 1800, "y": 200}),
            NodeDefinition(id="val_foreshadow", type="val_foreshadow", label="📖 伏笔雷达", position={"x": 1800, "y": 400}),
            NodeDefinition(id="val_kg_infer", type="val_kg_infer", label="🕸️ KG推断", position={"x": 1800, "y": 600}),
            NodeDefinition(id="gw_review", type="gw_review", label="⏸️ 审阅网关", position={"x": 2100, "y": 400}),
            NodeDefinition(
                id="gw_retry", type="gw_retry", label="🔄 重写网关", position={"x": 1500, "y": 100},
                config=NodeConfig(
                    max_retries=2,
                    prompt_template="以下章节文风偏离角色声线，请重写...",
                ),
            ),
        ],
        edges=[
            EdgeDefinition(id="edge_01", source="ctx_blueprint", target="exec_beat", source_port="world_rules"),
            EdgeDefinition(id="edge_02", source="ctx_memory", target="exec_beat", source_port="fact_lock"),
            EdgeDefinition(id="edge_03", source="ctx_foreshadow", target="exec_writer", source_port="foreshadowing_block"),
            EdgeDefinition(id="edge_04", source="ctx_voice", target="exec_writer", source_port="voice_block"),
            EdgeDefinition(id="edge_05", source="ctx_debt", target="exec_writer", source_port="debt_due_block"),
            EdgeDefinition(id="edge_06", source="exec_beat", target="exec_writer", source_port="beats"),
            EdgeDefinition(id="edge_07", source="exec_writer", target="val_style", source_port="content"),
            EdgeDefinition(id="edge_08", source="exec_writer", target="val_tension", source_port="content"),
            EdgeDefinition(id="edge_09", source="exec_writer", target="val_anti_ai", source_port="content"),
            EdgeDefinition(id="edge_10", source="val_style", target="gw_circuit", condition=EdgeCondition.ON_NO_DRIFT),
            EdgeDefinition(id="edge_11", source="val_style", target="gw_retry", condition=EdgeCondition.ON_DRIFT_ALERT, animated=True),
            EdgeDefinition(id="edge_12", source="val_tension", target="gw_circuit"),
            EdgeDefinition(id="edge_13", source="val_anti_ai", target="gw_circuit"),
            EdgeDefinition(id="edge_14", source="gw_circuit", target="val_narrative", condition=EdgeCondition.ON_BREAKER_CLOSED),
            EdgeDefinition(id="edge_15", source="gw_retry", target="exec_writer", animated=True),
            EdgeDefinition(id="edge_16", source="val_narrative", target="val_foreshadow"),
            EdgeDefinition(id="edge_17", source="val_foreshadow", target="val_kg_infer"),
            EdgeDefinition(id="edge_18", source="val_kg_infer", target="gw_review"),
        ],
    )
