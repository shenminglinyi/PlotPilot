"""DAG 工作流引擎 — 节点化 DAG 编排系统

核心模块：
- models: DAG 定义、节点/边模型、执行结果
- registry: 节点类型注册表（工厂模式）
- engine: DAG 执行引擎（LangGraph 编排 + 拓扑并行）
- validator: DAG 校验引擎（环检测、端口兼容性、可达性分析）
- version_manager: DAG 版本管理（保存/回滚/对比）
- daemon_runner: DAG 守护进程运行器（替代 AutopilotDaemon 隐式状态机）
- ipc_adapter: LangGraph 节点与现有 IPC 通道的适配器
- event_aggregator: SSE 节点事件聚合器（节流 + 批量推送）
- error_classifier: 节点错误分类器
- prompt_validator: Prompt 模板安全校验器
- nodes: V1 首批 19 个节点实现
"""

# 核心模型
from application.engine.dag.models import (
    DAGDefinition,
    DAGMetadata,
    DAGRunResult,
    EdgeCondition,
    EdgeDefinition,
    NodeCategory,
    NodeConfig,
    NodeDefinition,
    NodeEvent,
    NodeMeta,
    NodePort,
    NodeResult,
    NodeRunState,
    NodeStatus,
    NovelWorkflowState,
    PortDataType,
    get_default_dag,
)

# 核心组件
from application.engine.dag.registry import BaseNode, NodeRegistry
from application.engine.dag.engine import DAGEngine, DAGExecutionError
from application.engine.dag.validator import DAGValidator, ValidationResult
from application.engine.dag.version_manager import DAGVersionManager
from application.engine.dag.event_aggregator import NodeEventAggregator
from application.engine.dag.error_classifier import NodeErrorClassifier, ErrorClassification, ErrorLevel, RetryStrategy
from application.engine.dag.ipc_adapter import IPCAdapter
from application.engine.dag.daemon_runner import DAGDaemonRunner, EngineSelector
from application.engine.dag.prompt_validator import PromptTemplateValidator

__all__ = [
    # 模型
    "DAGDefinition",
    "DAGMetadata",
    "DAGRunResult",
    "EdgeCondition",
    "EdgeDefinition",
    "NodeCategory",
    "NodeConfig",
    "NodeDefinition",
    "NodeEvent",
    "NodeMeta",
    "NodePort",
    "NodeResult",
    "NodeRunState",
    "NodeStatus",
    "NovelWorkflowState",
    "PortDataType",
    "get_default_dag",
    # 核心组件
    "BaseNode",
    "NodeRegistry",
    "DAGEngine",
    "DAGExecutionError",
    "DAGValidator",
    "ValidationResult",
    "DAGVersionManager",
    "NodeEventAggregator",
    "NodeErrorClassifier",
    "ErrorClassification",
    "ErrorLevel",
    "RetryStrategy",
    "IPCAdapter",
    "DAGDaemonRunner",
    "EngineSelector",
    "PromptTemplateValidator",
]
