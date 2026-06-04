from application.ai_invocation.continuation import ContinuationContext
from application.ai_invocation.dtos import (
    AdoptionDecision,
    ContinuationRef,
    InvocationPolicy,
    InvocationSession,
    VariablePlan,
)
from application.blueprint.services.setup_plot_outline_continuation import setup_plot_outline_handler


def test_setup_plot_outline_continuation_returns_normalized_outline():
    overview = (
        "主角在旧秩序里原本还能拖延核心问题，但一次外部冲击把隐患提前推到台前。"
        "为了守住眼前最重要的人与资源，他必须先处理一个看似局部的危机，"
        "却在追查与应对过程中逐步发现这背后连接着更大的权力结构和世界规则漏洞。"
        "随着局势升级，主角会被迫在短期安全、长期目标和关系信任之间不断做选择，"
        "每次选择都会带来新的代价与更深的卷入。中段开始，人物关系和关键地点共同把表层问题导向更深层真相，"
        "让主角从被动应对转为主动突破。后段则集中兑现前文积累的冲突与筹码，"
        "把主角推向必须承担后果的最终决断，并让结局阶段完成主要线索收束与新秩序落地。"
    )
    session = InvocationSession(
        id="session-1",
        operation="setup.plot_outline",
        node_key="planning-plot-outline",
        policy=InvocationPolicy.FULL_INTERACTIVE,
        context={
            "novel_id": "novel-1",
            "setup_context": {"target_chapters": 60},
        },
        continuation=ContinuationRef(handler_key="setup_plot_outline"),
        variable_plan=VariablePlan(aliases={"target_chapters": 80}),
    )
    decision = AdoptionDecision(
        id="decision-1",
        session_id="session-1",
        attempt_id="attempt-1",
        accepted_content=(
            '{"plot_outline":{'
            f'"main_story_overview":"{overview}",'
            '"stage_plan":['
            '{"phase":"opening","label":"开篇阶段","range_percent":"1-15%","summary":"建立主角的初始处境与第一轮外部压力。","key_goals":["建立目标","引入冲突"]},'
            '{"phase":"development","label":"发展阶段","range_percent":"15-40%","summary":"让局部危机扩大成更广的对抗结构。","key_goals":["升级压力","扩大冲突"]},'
            '{"phase":"deepening","label":"深化阶段","range_percent":"40-70%","summary":"推进真相揭示与人物成长，让主线进入深水区。","key_goals":["揭示真相","压缩退路"]},'
            '{"phase":"climax","label":"高潮阶段","range_percent":"70-90%","summary":"集中兑现冲突与代价，逼出最终决断。","key_goals":["集中对抗","支付代价"]},'
            '{"phase":"ending","label":"收尾阶段","range_percent":"90-100%","summary":"收束后果与人物去向，完成结局闭环。","key_goals":["回收线索","落地结局"]}'
            '],'
            '"expected_ending":"主角在付出明确代价后完成阶段性目标，并让世界秩序进入新的稳定状态。",'
            '"core_conflict":"主角试图守住重要关系与核心目标，但更大的结构性压力不断逼他支付超出预期的代价。"}}'
        ),
    )

    result = setup_plot_outline_handler(ContinuationContext(session=session, decision=decision))

    assert result["session_id"] == "session-1"
    assert result["novel_id"] == "novel-1"
    assert result["plot_outline"]["main_story_overview"] == overview
    assert result["plot_outline"]["stage_plan"][0]["chapter_start"] == 1
    assert result["plot_outline"]["stage_plan"][0]["chapter_end"] == 12
    assert result["plot_outline"]["stage_plan"][-1]["chapter_start"] == 73
    assert result["plot_outline"]["stage_plan"][-1]["chapter_end"] == 80
    assert result["expected_ending"]
    assert result["core_conflict"]
