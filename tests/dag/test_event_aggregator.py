"""SSE 节点事件聚合器测试"""
import time
import pytest
from application.engine.dag.event_aggregator import NodeEventAggregator
from application.engine.dag.models import NodeEvent, NodeStatus


class TestNodeEventAggregator:
    """节点事件聚合器测试"""

    def test_push_and_flush(self):
        agg = NodeEventAggregator()
        event = NodeEvent(
            type="node_status_change",
            novel_id="novel_001",
            node_id="ctx_blueprint",
            status=NodeStatus.RUNNING,
        )
        agg.push(event)
        events = agg.flush()
        assert len(events) == 1
        assert events[0].node_id == "ctx_blueprint"

    def test_same_node_takes_latest(self):
        agg = NodeEventAggregator()
        event1 = NodeEvent(
            type="node_status_change",
            novel_id="novel_001",
            node_id="ctx_blueprint",
            status=NodeStatus.RUNNING,
        )
        event2 = NodeEvent(
            type="node_status_change",
            novel_id="novel_001",
            node_id="ctx_blueprint",
            status=NodeStatus.SUCCESS,
        )
        agg.push(event1)
        agg.push(event2)
        events = agg.flush()
        assert len(events) == 1
        assert events[0].status == NodeStatus.SUCCESS

    def test_different_nodes_both_kept(self):
        agg = NodeEventAggregator()
        event1 = NodeEvent(
            type="node_status_change",
            novel_id="novel_001",
            node_id="ctx_blueprint",
            status=NodeStatus.RUNNING,
        )
        event2 = NodeEvent(
            type="node_status_change",
            novel_id="novel_001",
            node_id="exec_writer",
            status=NodeStatus.RUNNING,
        )
        agg.push(event1)
        agg.push(event2)
        events = agg.flush()
        assert len(events) == 2

    def test_flush_clears_buffer(self):
        agg = NodeEventAggregator()
        agg.push(NodeEvent(type="node_status_change", novel_id="n1", node_id="n1"))
        agg.flush()
        events = agg.flush()
        assert len(events) == 0

    def test_flush_callback(self):
        collected = []
        agg = NodeEventAggregator(flush_interval=0.1)
        agg.set_flush_callback(lambda events: collected.extend(events))
        agg.push(NodeEvent(type="node_status_change", novel_id="n1", node_id="n1"))

        agg.start()
        time.sleep(0.3)
        agg.stop()

        assert len(collected) > 0
