from application.ai_invocation.autopilot.review_gate import review_gate_from_status
from application.blueprint.services.chapter_plan_renderer import (
    render_lightweight_act_chapter_outline,
)
from application.blueprint.services.chapter_planning_policy import (
    has_rendered_chapter_execution_plan,
    validate_lightweight_act_plan,
)


def _chapter(number: int) -> dict:
    return {
        "number": number,
        "title": f"第{number}章",
        "main_event": "推进主事件",
        "handoff_from_previous": "承接前章后果",
        "handoff_to_next": "留下下一章钩子",
        "required_threads": ["主线"],
    }


def test_lightweight_act_plan_rejects_truncated_chapter_list():
    errors = validate_lightweight_act_plan([_chapter(i) for i in range(1, 6)], expected_count=10)

    assert any("expected 10 chapters, got 5" in error for error in errors)


def test_lightweight_act_plan_requires_sequential_numbers_and_core_fields():
    bad = _chapter(2)
    bad["main_event"] = ""

    errors = validate_lightweight_act_plan([bad], expected_count=1)

    assert "chapter 1 number must be 1" in errors
    assert "chapter 1 missing required field: main_event" in errors


def test_detects_existing_seven_section_execution_script():
    outline = "\n".join(
        [
            "一、开篇切入点：",
            "二、场景转换列表：",
            "三、关键对话（4组）：",
            "四、剧情事件链（6个事件）：",
            "五、角色关键决策：",
            "六、爽点/反转设计：",
            "七、主角状态变化：",
        ]
    )

    assert has_rendered_chapter_execution_plan(outline)


def test_rejects_analysis_sections_mixed_into_execution_script():
    outline = "\n".join(
        [
            "一、开篇切入点：",
            "二、故事单元检查：",
            "三、场景转换列表：",
            "四、情绪变化节点（5组）：",
            "五、关键对话（4组）：",
            "六、剧情事件链（6个事件）：",
            "七、角色关键决策：",
            "八、爽点/反转设计：",
            "九、主角状态变化：",
        ]
    )

    assert not has_rendered_chapter_execution_plan(outline)


def test_rejects_incomplete_execution_script_even_with_five_markers():
    outline = "\n".join(
        [
            "一、开篇切入点：",
            "二、场景转换列表：",
            "三、关键对话（4组）：",
            "四、剧情事件链（6个事件）：",
            "五、角色关键决策：",
        ]
    )

    assert not has_rendered_chapter_execution_plan(outline)


def test_lightweight_outline_labels_first_chapter_as_opening_entry():
    outline = render_lightweight_act_chapter_outline(_chapter(1))

    assert "开篇入口：承接前章后果" in outline
    assert "承接上一章：承接前章后果" not in outline


def test_review_gate_prefers_act_plan_over_macro_ready_flag():
    gate = review_gate_from_status(
        {
            "autopilot_status": "running",
            "current_stage": "paused_for_review",
            "requires_ai_review": False,
            "writing_substep": "act_planning",
            "macro_structure_ready": False,
            "current_auto_chapters": 0,
            "autopilot_pending_act_chapters": [_chapter(1)],
        }
    )

    assert gate["type"] == "act_plan"
    assert gate["action_label"] == "确认章节规划，继续"
