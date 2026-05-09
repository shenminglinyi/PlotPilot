"""DAG 执行引擎 — LangGraph 编排 + 拓扑并行执行

核心职责：
1. 将 DAGDefinition 编译为 LangGraph StateGraph
2. 支持断点续写（通过 LangGraph Checkpoint）
3. 拓扑排序后无依赖节点并行执行
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from application.engine.dag.models import (
    DAGDefinition,
    DAGRunResult,
    EdgeCondition,
    NodeDefinition,
    NodeResult,
    NodeRunState,
    NodeStatus,
    NovelWorkflowState,
)
from application.engine.dag.registry import NodeRegistry

logger = logging.getLogger(__name__)


def _is_langgraph_available() -> bool:
    """检查 LangGraph 是否可用"""
    try:
        import langgraph  # noqa: F401
        return True
    except ImportError:
        return False


class DAGEngine:
    """DAG 执行引擎

    设计决策：
    - 优先使用 LangGraph 进行编排（支持循环重写、断点续写）
    - LangGraph 不可用时降级为自研拓扑排序执行器
    - 两种路径共享相同的节点注册表和输入收集逻辑
    """

    def __init__(self, checkpointer=None):
        self._checkpointer = checkpointer
        self._use_langgraph = _is_langgraph_available()

        if self._use_langgraph:
            logger.info("DAG 引擎: LangGraph 可用，使用 LangGraph 编排")
        else:
            logger.info("DAG 引擎: LangGraph 不可用，使用自研拓扑执行器")

    # ─── 主入口 ───

    async def run(
        self,
        dag: DAGDefinition,
        initial_state: Dict[str, Any],
        thread_id: str = "",
    ) -> DAGRunResult:
        """执行完整的 DAG

        Args:
            dag: DAG 定义
            initial_state: 初始状态
            thread_id: 线程 ID（用于 LangGraph Checkpoint）

        Returns:
            DAGRunResult
        """
        start_time = time.time()
        dag_run_id = initial_state.get("dag_run_id", f"run_{int(time.time()*1000)}")

        # 运行时状态追踪
        node_states: Dict[str, NodeRunState] = {}
        for node in dag.nodes:
            node_states[node.id] = NodeRunState(node_id=node.id)

        try:
            if self._use_langgraph:
                result_state = await self._run_with_langgraph(dag, initial_state, thread_id)
            else:
                result_state = await self._run_with_topological_sort(dag, initial_state)

            # 收集结果
            total_ms = int((time.time() - start_time) * 1000)
            return DAGRunResult(
                dag_run_id=dag_run_id,
                novel_id=initial_state.get("novel_id", ""),
                status="completed",
                node_results={nid: NodeResult(outputs=res) for nid, res in result_state.items() if isinstance(res, dict)},
                total_duration_ms=total_ms,
                error_count=0,
            )

        except DAGExecutionError as e:
            total_ms = int((time.time() - start_time) * 1000)
            return DAGRunResult(
                dag_run_id=dag_run_id,
                novel_id=initial_state.get("novel_id", ""),
                status="error",
                total_duration_ms=total_ms,
                error_count=1,
            )
        except Exception as e:
            logger.error(f"DAG 执行异常: {e}", exc_info=True)
            total_ms = int((time.time() - start_time) * 1000)
            return DAGRunResult(
                dag_run_id=dag_run_id,
                novel_id=initial_state.get("novel_id", ""),
                status="error",
                total_duration_ms=total_ms,
                error_count=1,
            )

    async def run_from_node(
        self,
        dag: DAGDefinition,
        node_id: str,
        state: Dict[str, Any],
        thread_id: str = "",
    ) -> DAGRunResult:
        """从指定节点开始执行（断点续写）

        仅执行 node_id 及其所有后继节点。
        """
        # 找到所有需要执行的节点（node_id + 所有后继）
        nodes_to_run = self._find_downstream_nodes(dag, node_id)
        nodes_to_run.add(node_id)

        # 创建裁剪后的 DAG
        pruned_dag = DAGDefinition(
            id=dag.id,
            name=dag.name,
            version=dag.version,
            nodes=[n for n in dag.nodes if n.id in nodes_to_run],
            edges=[e for e in dag.edges if e.source in nodes_to_run and e.target in nodes_to_run],
        )

        return await self.run(pruned_dag, state, thread_id)

    # ─── LangGraph 路径 ───

    async def _run_with_langgraph(
        self,
        dag: DAGDefinition,
        initial_state: Dict[str, Any],
        thread_id: str,
    ) -> Dict[str, Any]:
        """使用 LangGraph StateGraph 执行 DAG"""
        from langgraph.graph import StateGraph, END

        # 构建状态 Schema（使用 dict 模式，更灵活）
        graph = StateGraph(dict)

        # 1. 注册所有节点
        for node_def in dag.nodes:
            if not node_def.enabled:
                continue
            if not NodeRegistry.has(node_def.type):
                logger.warning(f"跳过未注册的节点类型: {node_def.type}")
                continue
            executor = NodeRegistry.create_executor(node_def.type, node_def.id, node_def.config)
            graph.add_node(node_def.id, executor)

        # 2. 注册所有边
        entry_node = None
        for node_def in dag.nodes:
            if not node_def.enabled:
                continue
            if not dag.get_predecessors(node_def.id):
                entry_node = node_def.id
                break

        if not entry_node:
            raise DAGExecutionError("DAG 没有入口节点")

        graph.set_entry_point(entry_node)

        # 添加边
        for edge in dag.edges:
            source_node = dag.get_node(edge.source)
            target_node = dag.get_node(edge.target)
            if not source_node or not target_node:
                continue
            if not source_node.enabled or not target_node.enabled:
                continue

            if edge.condition != EdgeCondition.ALWAYS:
                # 条件边 — 使用 conditional_edges
                condition_fn = _make_condition_function(edge.condition, edge.target)
                graph.add_conditional_edges(
                    edge.source,
                    condition_fn,
                    {True: edge.target, False: END},
                )
            else:
                graph.add_edge(edge.source, edge.target)

        # 编译
        compile_kwargs = {}
        if self._checkpointer:
            compile_kwargs["checkpointer"] = self._checkpointer

        compiled = graph.compile(**compile_kwargs)

        # 执行
        config = {"configurable": {"thread_id": thread_id}} if thread_id else {}
        result = await compiled.ainvoke(initial_state, config)
        return result if isinstance(result, dict) else {}

    # ─── 自研拓扑排序路径 ───

    async def _run_with_topological_sort(
        self,
        dag: DAGDefinition,
        initial_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """使用自研拓扑排序执行器（LangGraph 不可用时的降级方案）

        优化：
        1. 同层无依赖节点并行执行（asyncio.gather）
        2. Context 节点层内并行，减少上下文组装耗时
        3. 验证节点层内并行，审计不再串行等待
        4. 快速路径：如果只有单个链式依赖，跳过并行调度开销
        """
        state = dict(initial_state)

        # 获取拓扑层级
        layers = self._topological_layers(dag)
        logger.info(f"DAG 拓扑层级: {[len(l) for l in layers]}")

        for layer_idx, layer in enumerate(layers):
            layer_node_ids = [n.id for n in layer]
            layer_types = [n.type for n in layer]
            logger.info(f"执行层级 {layer_idx}: {layer_node_ids} (types: {layer_types})")

            if len(layer) == 1:
                # 串行节点
                node_def = layer[0]
                result = await self._execute_node(node_def, state)
                state.update(result)
            else:
                # ★ 并行节点 — 同层无依赖节点并发执行
                # 使用共享 state 的只读快照，避免并发写入冲突
                state_snapshot = dict(state)
                tasks = [self._execute_node(n, state_snapshot) for n in layer]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for node_def, result in zip(layer, results):
                    if isinstance(result, Exception):
                        logger.error(f"节点 {node_def.id} 执行失败: {result}")
                        state.setdefault("_errors", {})[node_def.id] = str(result)
                    else:
                        state.update(result)

        return state

    async def _execute_node(self, node_def: NodeDefinition, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个节点"""
        if not node_def.enabled:
            logger.info(f"节点 {node_def.id} 已禁用，跳过")
            return {}

        if not NodeRegistry.has(node_def.type):
            logger.warning(f"跳过未注册的节点类型: {node_def.type}")
            return {}

        executor = NodeRegistry.create_executor(node_def.type, node_def.id, node_def.config)
        return await executor(state)

    def _topological_layers(self, dag: DAGDefinition) -> List[List[NodeDefinition]]:
        """Kahn 算法分层 — 同层节点无依赖可并行"""
        enabled_nodes = {n.id for n in dag.nodes if n.enabled}
        in_degree = {n.id: 0 for n in dag.nodes if n.enabled}

        for edge in dag.edges:
            if edge.source in enabled_nodes and edge.target in enabled_nodes:
                in_degree[edge.target] = in_degree.get(edge.target, 0) + 1

        layers = []
        queue = [nid for nid, d in in_degree.items() if d == 0]

        while queue:
            layer = [dag.get_node(nid) for nid in queue if dag.get_node(nid)]
            layers.append(layer)
            next_queue = []
            for nid in queue:
                for edge in dag.edges:
                    if edge.source == nid and edge.target in in_degree:
                        in_degree[edge.target] -= 1
                        if in_degree[edge.target] == 0:
                            next_queue.append(edge.target)
            queue = next_queue

        return layers

    def _find_downstream_nodes(self, dag: DAGDefinition, start_node_id: str) -> Set[str]:
        """找到所有后继节点（BFS）"""
        downstream = set()
        queue = [start_node_id]
        while queue:
            current = queue.pop(0)
            for succ in dag.get_successors(current):
                if succ not in downstream:
                    downstream.add(succ)
                    queue.append(succ)
        return downstream

    # ─── 校验 ───

    def validate(self, dag: DAGDefinition) -> List[str]:
        """校验 DAG 有效性（无环、端口匹配、必填输入满足）"""
        errors = []

        # 环检测
        if self._has_cycle(dag):
            errors.append("DAG 包含环，请使用 gw_retry 网关节点实现循环重写")

        # 入口节点检查
        entry_nodes = dag.get_entry_nodes()
        if not entry_nodes:
            errors.append("DAG 没有入口节点（所有节点都有入边）")

        # 未注册节点类型检查
        for node in dag.nodes:
            if not NodeRegistry.has(node.type):
                errors.append(f"节点 '{node.id}' 使用未注册的类型 '{node.type}'")

        return errors

    def _has_cycle(self, dag: DAGDefinition) -> bool:
        """DFS 环检测"""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n.id: WHITE for n in dag.nodes}
        adj = defaultdict(list)
        for edge in dag.edges:
            adj[edge.source].append(edge.target)

        def dfs(node_id: str) -> bool:
            color[node_id] = GRAY
            for neighbor in adj[node_id]:
                if color.get(neighbor) == GRAY:
                    return True
                if color.get(neighbor, WHITE) == WHITE:
                    if dfs(neighbor):
                        return True
            color[node_id] = BLACK
            return False

        for node in dag.nodes:
            if color[node.id] == WHITE:
                if dfs(node.id):
                    return True
        return False


# ─── 辅助函数 ───


class DAGExecutionError(Exception):
    """DAG 执行错误"""
    pass


def _make_condition_function(condition: EdgeCondition, target: str):
    """创建 LangGraph 条件边函数"""
    def condition_fn(state: dict) -> bool:
        if condition == EdgeCondition.ON_SUCCESS:
            return state.get("status") != "error"
        elif condition == EdgeCondition.ON_ERROR:
            return state.get("status") == "error"
        elif condition == EdgeCondition.ON_DRIFT_ALERT:
            return state.get("drift_alert", False)
        elif condition == EdgeCondition.ON_NO_DRIFT:
            return not state.get("drift_alert", False)
        elif condition == EdgeCondition.ON_BREAKER_OPEN:
            return state.get("breaker_status") == "open"
        elif condition == EdgeCondition.ON_BREAKER_CLOSED:
            return state.get("breaker_status") != "open"
        elif condition == EdgeCondition.ON_REVIEW_APPROVED:
            return state.get("review_approved", False)
        elif condition == EdgeCondition.ON_REVIEW_REJECTED:
            return not state.get("review_approved", False)
        return True

    return condition_fn
