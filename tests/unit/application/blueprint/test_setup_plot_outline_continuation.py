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
        variable_plan=VariablePlan(aliases={"novel.target_chapters": 80}),
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


def test_setup_plot_outline_continuation_accepts_legacy_outline_shape():
    overview = (
        "主角带着前世覆灭的记忆重返弱小时刻，以隐藏能力在底层秩序中重新起势。"
        "他先通过解决眼前危机稳住生存空间，再一步步挖出旧势力对自身命运的操控痕迹，"
        "把个人复仇线逐渐扩展成对旧秩序的全面对抗。随着资源、盟友与真相不断累积，"
        "主角从被动求生转向主动破局，并在连续升级的高压冲突中完成成长，最终直面造成一切悲剧的核心敌人，"
        "以必须承担代价的决断打开新的世界格局。"
    )
    session = InvocationSession(
        id="session-legacy",
        operation="setup.plot_outline",
        node_key="planning-plot-outline",
        policy=InvocationPolicy.FULL_INTERACTIVE,
        context={
            "novel_id": "novel-legacy",
            "setup_context": {"target_chapters": 50},
        },
        continuation=ContinuationRef(handler_key="setup_plot_outline"),
        variable_plan=VariablePlan(aliases={"novel.target_chapters": 50}),
    )
    decision = AdoptionDecision(
        id="decision-legacy",
        session_id="session-legacy",
        attempt_id="attempt-legacy",
        accepted_content=(
            '{'
            f'"outline_main":"{overview}",'
            '"stage_plan":{'
            '"stage_opening_1_15":"建立处境并引出第一轮危机。",'
            '"stage_develop_15_40":"让局部冲突扩展成多方博弈。",'
            '"stage_deepen_40_70":"揭露深层真相并压缩退路。",'
            '"stage_climax_70_90":"集中兑现主线冲突与代价。",'
            '"stage_end_90_100":"收束后果并落地新秩序。"},'
            '"ending_expect":"主角以明确代价终结旧秩序并开启新阶段。",'
            '"core_conflict":"主角的逆袭意志与旧秩序的压制机制发生正面对撞。"}'
        ),
    )

    result = setup_plot_outline_handler(ContinuationContext(session=session, decision=decision))

    assert result["novel_id"] == "novel-legacy"
    assert result["plot_outline"]["main_story_overview"] == overview
    assert result["plot_outline"]["stage_plan"][0]["phase"] == "opening"
    assert result["plot_outline"]["stage_plan"][-1]["phase"] == "ending"
    assert result["expected_ending"] == "主角以明确代价终结旧秩序并开启新阶段。"


def test_setup_plot_outline_continuation_preserves_extra_outline_fields():
    overview = (
        "主角在一场失败的行动后被迫重回起点，为了追回失去的一切，他必须先穿过旧同盟的怀疑、"
        "新敌人的试探以及一条不断暴露真实代价的追查线。随着局势推进，原本只想自保的目标逐步升级成"
        "必须主动破局的长期对抗，并在一次次选择中把人际裂痕、资源短缺与更大秩序问题同时推到台前。"
        "中后段通过持续升级的事件把主角逼到无路可退的位置，最终让他以承担明确损失的方式换来主线推进与格局改写。"
    )
    session = InvocationSession(
        id="session-extra",
        operation="setup.plot_outline",
        node_key="planning-plot-outline",
        policy=InvocationPolicy.FULL_INTERACTIVE,
        context={"novel_id": "novel-extra", "setup_context": {"target_chapters": 40}},
        continuation=ContinuationRef(handler_key="setup_plot_outline"),
        variable_plan=VariablePlan(aliases={"novel.target_chapters": 40}),
    )
    decision = AdoptionDecision(
        id="decision-extra",
        session_id="session-extra",
        attempt_id="attempt-extra",
        accepted_content=(
            "```json\n"
            '{"plot_outline":{'
            f'"main_story_overview":"{overview}",'
            '"theme":"代价与重建",'
            '"stage_plan":['
            '{"phase":"opening","label":"开篇阶段","range_percent":"1-15%","summary":"建立失败后的新处境。","milestone":"失去关键筹码"},'
            '{"phase":"development","label":"发展阶段","range_percent":"15-40%","summary":"让追查线牵出更大的阻力。","milestone":"敌我边界模糊"},'
            '{"phase":"deepening","label":"深化阶段","range_percent":"40-70%","summary":"真相与代价同步加码。","milestone":"旧盟友倒戈"},'
            '{"phase":"climax","label":"高潮阶段","range_percent":"70-90%","summary":"集中兑现冲突并逼出决断。","milestone":"主动反击"},'
            '{"phase":"ending","label":"收尾阶段","range_percent":"90-100%","summary":"收束后果并重建新秩序。","milestone":"接受损失"}'
            '],'
            '"expected_ending":"主角接受关键损失后换来主线突破，并为后续秩序重建奠定基础。",'
            '"core_conflict":"主角想追回失去的一切，但每前进一步都必须牺牲关系、资源或自身底线。"}}\n'
            "```"
        ),
    )

    result = setup_plot_outline_handler(ContinuationContext(session=session, decision=decision))

    assert result["plot_outline"]["theme"] == "代价与重建"
    assert result["plot_outline"]["stage_plan"][0]["milestone"] == "失去关键筹码"
    assert result["plot_outline"]["stage_plan"][0]["chapter_start"] == 1
    assert result["plot_outline"]["stage_plan"][-1]["chapter_end"] == 40
