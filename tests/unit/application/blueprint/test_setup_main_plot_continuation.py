from application.ai_invocation.continuation import ContinuationContext
from application.ai_invocation.dtos import (
    AdoptionDecision,
    ContinuationRef,
    InvocationPolicy,
    InvocationSession,
    VariableBinding,
    VariablePlan,
)
from application.blueprint.services.setup_main_plot_continuation import setup_main_plot_options_handler


def test_setup_main_plot_continuation_uses_output_bindings_for_custom_paths(monkeypatch):
    session = InvocationSession(
        id="session-main-plot",
        operation="setup.main_plot_options",
        node_key="planning-main-plot-option",
        policy=InvocationPolicy.FULL_INTERACTIVE,
        context={
            "novel_id": "novel-main-plot",
            "setup_context": {
                "target_chapters": 100,
                "fusion_axis": {},
            },
        },
        continuation=ContinuationRef(handler_key="setup_main_plot_options"),
        variable_plan=VariablePlan(aliases={"novel.target_chapters": 100}),
    )
    decision = AdoptionDecision(
        id="decision-main-plot",
        session_id="session-main-plot",
        attempt_id="attempt-main-plot",
        accepted_content=(
            '{'
            '"用户主线候选":['
            '{"title":"方案一","logline":"L1","core_conflict":"C1","starting_hook":"H1"},'
            '{"title":"方案二","logline":"L2","core_conflict":"C2","starting_hook":"H2"},'
            '{"title":"方案三","logline":"L3","core_conflict":"C3","starting_hook":"H3"}]}'
        ),
    )

    monkeypatch.setattr(
        "application.blueprint.services.setup_main_plot_continuation.load_session_output_bindings",
        lambda _session: [
            VariableBinding(alias="plot_options", variable_key="plot.main_options", source_path="用户主线候选"),
        ],
    )

    result = setup_main_plot_options_handler(ContinuationContext(session=session, decision=decision))

    assert len(result["plot_options"]) == 3
    assert result["plot_options"][0]["title"] == "方案一"
    assert result["plot_options"][2]["core_conflict"] == "C3"

