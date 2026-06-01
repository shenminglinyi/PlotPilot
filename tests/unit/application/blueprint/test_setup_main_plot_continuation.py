from application.ai_invocation.continuation import ContinuationContext
from application.ai_invocation.dtos import (
    AdoptionDecision,
    InvocationPolicy,
    InvocationSession,
    ContinuationRef,
    VariablePlan,
)
from application.blueprint.services.setup_main_plot_continuation import setup_main_plot_options_handler


def test_setup_main_plot_continuation_returns_normalized_options():
    session = InvocationSession(
        id="session-1",
        operation="setup.main_plot_options",
        node_key="planning-main-plot-option",
        policy=InvocationPolicy.FULL_INTERACTIVE,
        context={
            "novel_id": "novel-1",
            "setup_context": {
                "target_chapters": 60,
                "fusion_axis": {
                    "core_promise": "核心承诺",
                    "central_conflict": "中心冲突",
                    "false_mystery": "表层谜团",
                    "true_mystery": "真实谜团",
                    "forbidden_mainline_competitors": ["竞品A"],
                    "taboos": ["禁忌A"],
                },
            },
        },
        continuation=ContinuationRef(handler_key="setup_main_plot_options"),
        variable_plan=VariablePlan(
            aliases={
                "novel_title": "变量中心之书",
                "premise": "变量中心先行",
                "target_chapters": 80,
                "fusion_contract": "融合合同",
                "protagonist": {"name": "阿澄"},
                "locations": [{"name": "天枢城"}],
                "worldbuilding_full": "全文",
            },
        ),
    )
    decision = AdoptionDecision(
        id="decision-1",
        session_id="session-1",
        attempt_id="attempt-1",
        accepted_content=(
            '{"plot_options":['
            '{"id":"option_a_survival","type":"生存求证","title":"绝境中的第一枪","logline":"log","core_conflict":"conflict","starting_hook":"hook"},'
            '{"id":"option_b_conspiracy","type":"阴谋求真","title":"表象之下的齿轮","logline":"log2","core_conflict":"conflict2","starting_hook":"hook2"},'
            '{"id":"option_c_anomaly","type":"异类觉醒","title":"规则的裂缝","logline":"log3","core_conflict":"conflict3","starting_hook":"hook3"}'
            ']}'
        ),
    )

    result = setup_main_plot_options_handler(ContinuationContext(session=session, decision=decision))

    assert result["session_id"] == "session-1"
    assert result["novel_id"] == "novel-1"
    assert result["worldbuilding_full"] == "全文"
    assert result["protagonist"]["name"] == "阿澄"
    assert result["locations"][0]["name"] == "天枢城"
    assert result["fusion_contract"] == "融合合同"
    assert result["plot_options"]
    assert result["plot_options"][0]["main_axis"]
