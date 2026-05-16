"""IPC 适配器测试"""
import pytest
from unittest.mock import MagicMock
from application.engine.dag.ipc_adapter import IPCAdapter
from application.engine.dag.models import NodeEvent, NodeResult, NodeStatus


class TestIPCAdapter:
    """IPC 适配器测试"""

    def test_on_node_start_publishes_event(self):
        aggregator = MagicMock()
        adapter = IPCAdapter(event_aggregator=aggregator)
        adapter.on_node_start("novel_001", "ctx_blueprint", "ctx_blueprint")

        # 验证聚合器收到了事件
        aggregator.push.assert_called_once()
        event = aggregator.push.call_args[0][0]
        assert isinstance(event, NodeEvent)
        assert event.type == "node_status_change"
        assert event.status == NodeStatus.RUNNING
        assert event.node_id == "ctx_blueprint"

    def test_on_node_complete_publishes_event(self):
        aggregator = MagicMock()
        adapter = IPCAdapter(event_aggregator=aggregator)

        result = NodeResult(
            outputs={"content": "test"},
            status=NodeStatus.SUCCESS,
            duration_ms=100,
        )
        adapter.on_node_complete("novel_001", "exec_writer", result)

        aggregator.push.assert_called_once()
        event = aggregator.push.call_args[0][0]
        assert event.type == "node_output"
        assert event.status == NodeStatus.SUCCESS

    def test_on_node_error_publishes_event(self):
        aggregator = MagicMock()
        adapter = IPCAdapter(event_aggregator=aggregator)
        adapter.on_node_error("novel_001", "val_style", RuntimeError("检查失败"))

        aggregator.push.assert_called_once()
        event = aggregator.push.call_args[0][0]
        assert event.type == "node_status_change"
        assert event.status == NodeStatus.ERROR

    def test_on_edge_flow_publishes_event(self):
        aggregator = MagicMock()
        adapter = IPCAdapter(event_aggregator=aggregator)
        adapter.on_edge_flow("novel_001", "ctx_blueprint", "exec_writer", "world_rules")

        aggregator.push.assert_called_once()
        event = aggregator.push.call_args[0][0]
        assert event.type == "edge_data_flow"
        assert event.source_node == "ctx_blueprint"
        assert event.target_node == "exec_writer"

    def test_on_node_bypassed_publishes_event(self):
        aggregator = MagicMock()
        adapter = IPCAdapter(event_aggregator=aggregator)
        adapter.on_node_bypassed("novel_001", "ctx_memory")

        aggregator.push.assert_called_once()
        event = aggregator.push.call_args[0][0]
        assert event.status == NodeStatus.BYPASSED

    def test_without_aggregator_uses_bus(self):
        bus = MagicMock()
        adapter = IPCAdapter(streaming_bus=bus)
        adapter.on_node_start("novel_001", "ctx_blueprint", "ctx_blueprint")

        bus.publish_node_event.assert_called_once()

    def test_without_aggregator_and_bus_no_error(self):
        adapter = IPCAdapter()
        # 应该不抛异常
        adapter.on_node_start("novel_001", "ctx_blueprint", "ctx_blueprint")
        adapter.on_node_complete("novel_001", "exec_writer", NodeResult())
        adapter.on_node_error("novel_001", "val_style", RuntimeError("error"))

    def test_state_publisher_on_start(self):
        publisher = MagicMock()
        adapter = IPCAdapter(state_publisher=publisher)
        adapter.on_node_start("novel_001", "ctx_blueprint", "ctx_blueprint")

        publisher.update_novel_state.assert_called_once()
        call_kwargs = publisher.update_novel_state.call_args[1]
        assert call_kwargs["current_node"] == "ctx_blueprint"

    def test_state_publisher_error_handling(self):
        publisher = MagicMock()
        publisher.update_novel_state.side_effect = Exception("IPC 错误")
        adapter = IPCAdapter(state_publisher=publisher)

        # 应该不抛异常
        adapter.on_node_start("novel_001", "ctx_blueprint", "ctx_blueprint")
