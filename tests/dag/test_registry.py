"""节点注册表测试"""
import pytest
from application.engine.dag.models import NodeCategory, NodeConfig, NodeMeta, NodePort, PortDataType
from application.engine.dag.registry import BaseNode, NodeRegistry


class TestNodeRegistry:
    """节点注册表测试"""

    def setup_method(self):
        """每个测试前清理注册表"""
        NodeRegistry._registry.clear()
        NodeRegistry._meta_registry.clear()

    def test_register_node(self):
        @NodeRegistry.register("test_node_a")
        class TestNodeA(BaseNode):
            meta = NodeMeta(
                node_type="test_node_a",
                display_name="测试节点A",
                category=NodeCategory.CONTEXT,
            )
            async def execute(self, inputs, context):
                from application.engine.dag.models import NodeResult
                return NodeResult(outputs={"result": "ok"})
            def validate_inputs(self, inputs):
                return True

        assert NodeRegistry.has("test_node_a")
        assert "test_node_a" in NodeRegistry.all_types()

    def test_get_meta(self):
        @NodeRegistry.register("test_node_b")
        class TestNodeB(BaseNode):
            meta = NodeMeta(
                node_type="test_node_b",
                display_name="测试节点B",
                category=NodeCategory.EXECUTION,
            )
            async def execute(self, inputs, context):
                from application.engine.dag.models import NodeResult
                return NodeResult(outputs={})
            def validate_inputs(self, inputs):
                return True

        meta = NodeRegistry.get_meta("test_node_b")
        assert meta.display_name == "测试节点B"
        assert meta.category == NodeCategory.EXECUTION

    def test_get_unregistered_raises(self):
        with pytest.raises(KeyError, match="未注册"):
            NodeRegistry.get("nonexistent")

    def test_create_instance(self):
        @NodeRegistry.register("test_node_c")
        class TestNodeC(BaseNode):
            meta = NodeMeta(
                node_type="test_node_c",
                display_name="测试节点C",
                category=NodeCategory.VALIDATION,
            )
            async def execute(self, inputs, context):
                from application.engine.dag.models import NodeResult
                return NodeResult(outputs={})
            def validate_inputs(self, inputs):
                return True

        instance = NodeRegistry.create_instance("test_node_c")
        assert isinstance(instance, TestNodeC)

    def test_create_instance_with_config(self):
        @NodeRegistry.register("test_node_d")
        class TestNodeD(BaseNode):
            meta = NodeMeta(
                node_type="test_node_d",
                display_name="测试节点D",
                category=NodeCategory.GATEWAY,
            )
            async def execute(self, inputs, context):
                from application.engine.dag.models import NodeResult
                return NodeResult(outputs={})
            def validate_inputs(self, inputs):
                return True

        config = NodeConfig(temperature=0.3, max_retries=2)
        instance = NodeRegistry.create_instance("test_node_d", config=config)
        assert instance._config.temperature == 0.3

    def test_all_meta(self):
        @NodeRegistry.register("test_node_e")
        class TestNodeE(BaseNode):
            meta = NodeMeta(
                node_type="test_node_e",
                display_name="测试节点E",
                category=NodeCategory.CONTEXT,
            )
            async def execute(self, inputs, context):
                from application.engine.dag.models import NodeResult
                return NodeResult(outputs={})
            def validate_inputs(self, inputs):
                return True

        all_meta = NodeRegistry.all_meta()
        assert "test_node_e" in all_meta
