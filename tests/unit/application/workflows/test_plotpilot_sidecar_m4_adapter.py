from domain.ai.value_objects.prompt import Prompt


def test_m4_adapter_appends_pre_generation_block_and_trace_with_active_assets():
    from application.workflows.plotpilot_sidecar_m4_adapter import (
        enhance_prompt_for_plotpilot_m4,
    )

    registry = {
        "research_assets": [
            {
                "asset_type": "capability",
                "asset_id": "CAP-ACTIVE",
                "status": "active",
                "version": "1.0",
                "source": "cap.md",
                "node_scope": ["beat_prose"],
            },
            {
                "asset_type": "method_card",
                "asset_id": "METHOD-ACTIVE",
                "status": "active",
                "version": "1.0",
                "source": "method.md",
                "node_scope": ["beat_scene"],
            },
            {
                "asset_type": "failure_case",
                "asset_id": "FAIL-ACTIVE",
                "status": "active",
                "version": "1.0",
                "source": "fail.md",
                "node_scope": ["chapter_prose"],
            },
            {
                "asset_type": "capability",
                "asset_id": "CAP-DRAFT",
                "status": "draft",
                "version": "1.0",
                "source": "draft.md",
                "node_scope": ["beat_prose"],
            },
        ]
    }
    prompt = Prompt(system="base system", user="base user")

    enhanced, trace = enhance_prompt_for_plotpilot_m4(
        prompt,
        beat_prompt="beat focus",
        beat_mode=True,
        registry=registry,
    )

    assert enhanced.user == "base user"
    assert "【Sidecar M4 pre-generation】" in enhanced.system
    assert "node_type: beat_prose" in enhanced.system
    assert "CAP-ACTIVE" in enhanced.system
    assert "CAP-DRAFT" not in enhanced.system
    assert trace["enhancement_mode"] == "pre_generation"
    assert trace["node_type"] == "beat_prose"
    assert trace["enhancement_applied"] is True
    assert trace["sidecar_added_regeneration_count"] == 0
    assert trace["no_post_generation_rewrite"] is True
    assert trace["active_registry_writeback"] is False
    assert [asset["asset_id"] for asset in trace["selected_assets"]] == [
        "CAP-ACTIVE",
        "METHOD-ACTIVE",
        "FAIL-ACTIVE",
    ]
    assert trace["injected_blocks"][0]["target"] == "system"
    assert trace["injected_blocks"][0]["asset_ids"] == [
        "CAP-ACTIVE",
        "METHOD-ACTIVE",
        "FAIL-ACTIVE",
    ]


def test_m4_adapter_falls_back_with_trace_when_no_active_assets():
    from application.workflows.plotpilot_sidecar_m4_adapter import (
        enhance_prompt_for_plotpilot_m4,
    )

    prompt = Prompt(system="base system", user="base user")

    enhanced, trace = enhance_prompt_for_plotpilot_m4(
        prompt,
        node_type="chapter_prose",
        registry={"research_assets": []},
    )

    assert enhanced is prompt
    assert trace["node_type"] == "chapter_prose"
    assert trace["enhancement_applied"] is False
    assert trace["sidecar_added_regeneration_count"] == 0
    assert "NO_SELECTABLE_RESEARCH_ASSETS" in trace["failure_reason"]


def test_m4_adapter_trace_exposes_audit_consumable_source_trace():
    from application.workflows.plotpilot_sidecar_m4_adapter import (
        enhance_prompt_for_plotpilot_m4,
    )

    registry = {
        "research_assets": [
            {
                "asset_type": "method_card",
                "asset_id": "METHOD-MAIN",
                "status": "active",
                "version": "2.1",
                "source": "method.md",
                "source_anchor": "主线候选方法",
                "source_line": 12,
                "node_scope": ["main_plot"],
                "usage": "method_orchestration",
            }
        ]
    }

    _enhanced, trace = enhance_prompt_for_plotpilot_m4(
        Prompt(system="base system", user="base user"),
        node_type="main_plot",
        registry=registry,
    )

    assert trace["selected_asset_ids"] == ["METHOD-MAIN"]
    assert trace["selected_assets"][0]["source_anchor"] == "主线候选方法"
    assert trace["selected_assets"][0]["source_line"] == 12
    assert trace["source_trace"]["selected_asset_ids"] == ["METHOD-MAIN"]
    assert trace["source_trace"]["asset_versions"] == {"METHOD-MAIN": "2.1"}
    assert trace["source_trace"]["asset_sources"]["METHOD-MAIN"]["source_anchor"] == "主线候选方法"
