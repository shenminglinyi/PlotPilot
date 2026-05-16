"""IPC 适配器 -- LangGraph 节点与现有 IPC 通道的适配器

核心职责：
1. 节点状态变更 → 更新共享内存 + 推送 SSE
2. 节点输出 → SSE 推送 + 关键数据持久化
3. 边数据流 → SSE 动画事件
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from application.engine.dag.models import NodeEvent, NodeResult, NodeStatus

logger = logging.getLogger(__name__)


class IPCAdapter:
    """LangGraph 节点与现有 IPC 通道的适配器

    设计原则：
    - 复用现有 IPC 通道（StreamingBus、SharedState、PersistenceQueue）
    - 接口与现有 AutopilotDaemon 一致
    - 可在无 IPC 通道的测试环境下降级运行
    """

    def __init__(
        self,
        streaming_bus=None,
        state_publisher=None,
        persistence_queue=None,
        event_aggregator=None,
    ):
        self._bus = streaming_bus
        self._publisher = state_publisher
        self._pq = persistence_queue
        self._aggregator = event_aggregator

    def on_node_start(self, novel_id: str, node_id: str, node_type: str):
        """节点开始执行"""
        # 更新共享内存
        if self._publisher:
            try:
                self._publisher.update_novel_state(
                    novel_id,
                    current_node=node_id,
                    writing_substep=node_id,
                    writing_substep_label=f"执行 {node_type}",
                )
            except Exception as e:
                logger.warning(f"IPC 更新共享内存失败: {e}")

        # 推送 SSE 事件
        event = NodeEvent(
            type="node_status_change",
            novel_id=novel_id,
            node_id=node_id,
            status=NodeStatus.RUNNING,
        )
        self._publish_event(event)

    def on_node_complete(self, novel_id: str, node_id: str, result: NodeResult):
        """节点执行完成"""
        # SSE 推送节点输出
        event = NodeEvent(
            type="node_output",
            novel_id=novel_id,
            node_id=node_id,
            status=result.status,
            outputs=result.outputs,
            duration_ms=result.duration_ms,
            metrics=result.metrics,
        )
        self._publish_event(event)

        # 关键节点指标写入共享内存
        if self._publisher and result.metrics:
            try:
                self._publisher.update_novel_state(novel_id, **result.metrics)
            except Exception as e:
                logger.warning(f"IPC 写入共享内存失败: {e}")

    def on_node_error(self, novel_id: str, node_id: str, error: Exception):
        """节点执行失败"""
        event = NodeEvent(
            type="node_status_change",
            novel_id=novel_id,
            node_id=node_id,
            status=NodeStatus.ERROR,
            error=str(error),
        )
        self._publish_event(event)

    def on_edge_flow(self, novel_id: str, source: str, target: str, port: str, data: Any = None):
        """边数据流动"""
        event = NodeEvent(
            type="edge_data_flow",
            novel_id=novel_id,
            source_node=source,
            target_node=target,
            port=port,
            data_type=type(data).__name__ if data else "",
            data_size=len(str(data)) if data else 0,
        )
        self._publish_event(event)

    def on_node_bypassed(self, novel_id: str, node_id: str):
        """节点被旁路"""
        event = NodeEvent(
            type="node_status_change",
            novel_id=novel_id,
            node_id=node_id,
            status=NodeStatus.BYPASSED,
        )
        self._publish_event(event)

    def _publish_event(self, event: NodeEvent):
        """发布事件（通过聚合器或直接推送）"""
        if self._aggregator:
            self._aggregator.push(event)
        elif self._bus:
            try:
                self._bus.publish_node_event(event.novel_id, event.model_dump(mode="json"))
            except Exception as e:
                logger.warning(f"SSE 推送失败: {e}")
