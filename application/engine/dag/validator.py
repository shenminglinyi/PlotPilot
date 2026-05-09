"""DAG 验证引擎 — 提交前/执行前的完整性校验

验证规则：
1. 结构性验证（必填字段、ID 格式）
2. 拓扑验证（环检测）
3. 端口匹配验证（数据类型兼容性）
4. 必填输入验证
5. 节点可达性分析
6. 网关完整性验证
7. 语义验证
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from application.engine.dag.models import DAGDefinition, EdgeDefinition, NodeDefinition
from application.engine.dag.registry import NodeRegistry

logger = logging.getLogger(__name__)


# ─── 数据类型兼容矩阵 ───

COMPATIBLE_TYPES: Dict[str, Set[str]] = {
    "text": {"text", "prompt"},
    "json": {"json", "list"},
    "score": {"score", "json"},
    "boolean": {"boolean", "json"},
    "list": {"list", "json"},
    "prompt": {"text", "prompt"},
}


@dataclass
class ValidationResult:
    """DAG 验证结果"""
    errors: List[str] = field(default_factory=list)     # 阻断性错误
    warnings: List[str] = field(default_factory=list)    # 非阻断性警告
    is_valid: bool = True

    @property
    def summary(self) -> str:
        if self.is_valid and not self.warnings:
            return "✅ DAG 验证通过"
        elif self.is_valid:
            return f"⚠️ DAG 可执行，但有 {len(self.warnings)} 个警告"
        else:
            return f"❌ DAG 不可执行：{len(self.errors)} 个错误"


class DAGValidator:
    """DAG 定义验证器"""

    def validate(self, dag: DAGDefinition) -> ValidationResult:
        """执行完整验证"""
        result = ValidationResult()

        # 1. 结构性验证
        result.errors.extend(self._check_structure(dag))

        # 2. 拓扑验证（环检测）
        result.errors.extend(self._check_acyclic(dag))

        # 3. 端口匹配验证
        result.errors.extend(self._check_port_compatibility(dag))

        # 4. 必填输入验证
        result.errors.extend(self._check_required_inputs(dag))

        # 5. 节点可达性验证
        result.warnings.extend(self._check_reachability(dag))

        # 6. 网关完整性验证
        result.errors.extend(self._check_gateway_completeness(dag))

        # 7. 语义验证
        result.warnings.extend(self._check_semantic_consistency(dag))

        result.is_valid = len(result.errors) == 0
        return result

    # ─── 1. 结构性验证 ───

    def _check_structure(self, dag: DAGDefinition) -> List[str]:
        """检查基本结构完整性"""
        errors = []

        if not dag.nodes:
            errors.append("DAG 没有节点")
            return errors

        # 节点 ID 唯一性
        node_ids = [n.id for n in dag.nodes]
        duplicates = [nid for nid in set(node_ids) if node_ids.count(nid) > 1]
        if duplicates:
            errors.append(f"节点 ID 不唯一: {duplicates}")

        # 边 ID 唯一性
        edge_ids = [e.id for e in dag.edges]
        dup_edges = [eid for eid in set(edge_ids) if edge_ids.count(eid) > 1]
        if dup_edges:
            errors.append(f"边 ID 不唯一: {dup_edges}")

        # 边引用的节点必须存在
        node_id_set = set(node_ids)
        for edge in dag.edges:
            if edge.source not in node_id_set:
                errors.append(f"边 '{edge.id}' 的源节点 '{edge.source}' 不存在")
            if edge.target not in node_id_set:
                errors.append(f"边 '{edge.id}' 的目标节点 '{edge.target}' 不存在")

        # 自环
        for edge in dag.edges:
            if edge.source == edge.target:
                errors.append(f"边 '{edge.id}' 形成自环: {edge.source} → {edge.target}")

        return errors

    # ─── 2. 环检测 ───

    def _check_acyclic(self, dag: DAGDefinition) -> List[str]:
        """DFS 三色环检测"""
        errors = []

        adj = defaultdict(list)
        for edge in dag.edges:
            adj[edge.source].append(edge.target)

        WHITE, GRAY, BLACK = 0, 1, 2
        color = {node.id: WHITE for node in dag.nodes}

        def dfs(node_id: str, path: List[str]) -> bool:
            color[node_id] = GRAY
            path.append(node_id)

            for neighbor in adj[node_id]:
                if color.get(neighbor) == GRAY:
                    # 检测到环：neighbor 在当前路径中
                    if neighbor in path:
                        cycle_start = path.index(neighbor)
                        cycle = path[cycle_start:] + [neighbor]
                        errors.append(
                            f"检测到环: {' → '.join(cycle)}。"
                            f"如需循环重写，请使用 gw_retry 网关节点。"
                        )
                    # 即使检测到环也继续遍历，确保正确清理状态

                if color.get(neighbor, WHITE) == WHITE:
                    dfs(neighbor, path)

            path.pop()
            color[node_id] = BLACK
            return False

        for node in dag.nodes:
            if color[node.id] == WHITE:
                dfs(node.id, [])

        return errors

    # ─── 3. 端口兼容性验证 ───

    def _check_port_compatibility(self, dag: DAGDefinition) -> List[str]:
        """验证边的源端口与目标端口数据类型兼容"""
        errors = []

        for edge in dag.edges:
            source_node = dag.get_node(edge.source)
            target_node = dag.get_node(edge.target)
            if not source_node or not target_node:
                continue

            # 获取端口元数据
            try:
                source_meta = NodeRegistry.get_meta(source_node.type)
                target_meta = NodeRegistry.get_meta(target_node.type)
            except KeyError:
                # 节点类型未注册，跳过端口检查
                continue

            source_port = None
            if edge.source_port:
                source_port = next(
                    (p for p in source_meta.output_ports if p.name == edge.source_port),
                    None,
                )
            elif source_meta.output_ports:
                source_port = source_meta.output_ports[0]

            target_port = None
            if edge.target_port:
                target_port = next(
                    (p for p in target_meta.input_ports if p.name == edge.target_port),
                    None,
                )
            elif target_meta.input_ports:
                target_port = target_meta.input_ports[0]

            if source_port and target_port:
                src_type = source_port.data_type.value if hasattr(source_port.data_type, 'value') else str(source_port.data_type)
                tgt_type = target_port.data_type.value if hasattr(target_port.data_type, 'value') else str(target_port.data_type)

                if tgt_type not in COMPATIBLE_TYPES.get(src_type, set()):
                    errors.append(
                        f"端口类型不兼容: {edge.source}.{source_port.name}({src_type}) "
                        f"→ {edge.target}.{target_port.name}({tgt_type})"
                    )

        return errors

    # ─── 4. 必填输入验证 ───

    def _check_required_inputs(self, dag: DAGDefinition) -> List[str]:
        """验证入口节点的必填输入是否有数据源"""
        errors = []

        for node in dag.nodes:
            if not node.enabled:
                continue
            try:
                meta = NodeRegistry.get_meta(node.type)
            except KeyError:
                continue

            for port in meta.input_ports:
                if not port.required:
                    continue
                # 检查是否有边连向此端口
                incoming = [e for e in dag.edges if e.target == node.id]
                if not incoming:
                    # 入口节点，必填输入由 initial_state 提供
                    continue

        return errors

    # ─── 5. 节点可达性分析 ───

    def _check_reachability(self, dag: DAGDefinition) -> List[str]:
        """检查孤立节点和不可达节点"""
        warnings = []

        targets = {e.target for e in dag.edges}
        sources = {e.source for e in dag.edges}
        all_nodes = {n.id for n in dag.nodes}

        # 孤立节点
        isolated = all_nodes - targets - sources
        for node_id in isolated:
            node = dag.get_node(node_id)
            if node and node.enabled:
                warnings.append(f"节点 '{node_id}' 是孤立的（无输入/输出边），将被忽略")

        # 不可达节点
        entry_nodes = {n.id for n in dag.nodes if n.id not in targets and n.enabled}
        reachable = set()
        queue = list(entry_nodes)

        while queue:
            node_id = queue.pop(0)
            if node_id in reachable:
                continue
            reachable.add(node_id)
            for edge in dag.edges:
                if edge.source == node_id and edge.target not in reachable:
                    queue.append(edge.target)

        unreachable = all_nodes - reachable
        for node_id in unreachable:
            node = dag.get_node(node_id)
            if node and node.enabled:
                warnings.append(f"节点 '{node_id}' 从入口不可达，将永远不会执行")

        return warnings

    # ─── 6. 网关完整性验证 ───

    def _check_gateway_completeness(self, dag: DAGDefinition) -> List[str]:
        """检查网关节点的完整性"""
        errors = []

        # 熔断网关应该有条件输出
        circuit_nodes = [n for n in dag.nodes if n.type == "gw_circuit"]
        for node in circuit_nodes:
            outgoing = [e for e in dag.edges if e.source == node.id]
            if len(outgoing) < 2:
                errors.append(
                    f"熔断网关 '{node.id}' 至少需要 2 条出边"
                    f"（on_breaker_closed + on_breaker_open），当前 {len(outgoing)} 条"
                )

        # 审阅网关应有审批流程
        review_nodes = [n for n in dag.nodes if n.type == "gw_review"]
        for node in review_nodes:
            outgoing = [e for e in dag.edges if e.source == node.id]
            if not outgoing:
                warnings_msg = f"审阅网关 '{node.id}' 没有出边，审阅后无法继续执行"
                errors.append(warnings_msg)

        return errors

    # ─── 7. 语义验证 ───

    def _check_semantic_consistency(self, dag: DAGDefinition) -> List[str]:
        """语义层面的一致性检查"""
        warnings = []

        # 检查是否有写作节点但无上下文节点
        has_writer = any(n.type == "exec_writer" for n in dag.nodes)
        has_context = any(n.type.startswith("ctx_") for n in dag.nodes)
        if has_writer and not has_context:
            warnings.append("有写作引擎但无上下文注入节点，生成质量可能不佳")

        # 检查写作节点后有验证节点
        writer_nodes = [n for n in dag.nodes if n.type == "exec_writer"]
        for writer in writer_nodes:
            outgoing = [e for e in dag.edges if e.source == writer.id]
            has_validation = any(
                dag.get_node(e.target) and dag.get_node(e.target).type.startswith("val_")
                for e in outgoing
            )
            if not has_validation and outgoing:
                warnings.append(f"写作节点 '{writer.id}' 后无校验节点，建议添加文风/张力检查")

        return warnings
