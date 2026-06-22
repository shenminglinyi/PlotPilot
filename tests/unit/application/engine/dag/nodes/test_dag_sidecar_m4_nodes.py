from application.engine.dag.models import NodeCategory, NodeMeta
from application.engine.dag.registry import BaseNode
from domain.ai.value_objects.prompt import Prompt


class _WriterNodeForSidecarTest(BaseNode):
    meta = NodeMeta(
        node_type="exec_writer",
        display_name="Writer",
        category=NodeCategory.EXECUTION,
    )

    def get_effective_prompt(self):
        return {
            "system": "writer system {{outline}}",
            "user_template": "writer user {{outline}}",
            "source": "test",
        }

    async def execute(self, inputs, context):
        raise NotImplementedError

    def validate_inputs(self, inputs):
        return True


class _ValidationNodeForSidecarTest(BaseNode):
    meta = NodeMeta(
        node_type="val_style",
        display_name="Style",
        category=NodeCategory.VALIDATION,
    )

    def get_effective_prompt(self):
        return {
            "system": "validation system {{content}}",
            "user_template": "validation user {{content}}",
            "source": "test",
        }

    async def execute(self, inputs, context):
        raise NotImplementedError

    def validate_inputs(self, inputs):
        return True


def test_dag_exec_writer_resolve_prompt_applies_m4_adapter(monkeypatch):
    import application.engine.dag.registry as registry_module

    def fake_enhance(prompt, **kwargs):
        return (
            Prompt(
                system=prompt.system + "\n\n【Sidecar M4 pre-generation】\nnode_type: dag_exec_writer",
                user=prompt.user,
            ),
            {
                "enhancement_mode": "pre_generation",
                "node_type": kwargs["node_type"],
                "enhancement_applied": True,
                "sidecar_added_regeneration_count": 0,
                "native_call_boundary": kwargs["native_call_boundary"],
            },
        )

    monkeypatch.setattr(registry_module, "enhance_prompt_for_plotpilot_m4", fake_enhance, raising=False)

    node = _WriterNodeForSidecarTest()
    resolved = node.resolve_prompt({"outline": "章节大纲"})

    assert "【Sidecar M4 pre-generation】" in resolved["system"]
    assert resolved["sidecar_trace"]["node_type"] == "dag_exec_writer"
    assert node._sidecar_traces[-1]["native_call_boundary"]["source_function"] == (
        "BaseNode.resolve_prompt"
    )


def test_non_creative_dag_node_is_not_sidecar_enhanced(monkeypatch):
    import application.engine.dag.registry as registry_module

    calls = []

    def fake_enhance(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return prompt, {"enhancement_applied": True}

    monkeypatch.setattr(registry_module, "enhance_prompt_for_plotpilot_m4", fake_enhance, raising=False)

    node = _ValidationNodeForSidecarTest()
    resolved = node.resolve_prompt({"content": "正文"})

    assert calls == []
    assert "【Sidecar M4 pre-generation】" not in resolved["system"]
