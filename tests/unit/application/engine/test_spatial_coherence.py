"""spatial_coherence / ATG 运行时单元测试"""
from application.engine.dtos.scene_director_dto import ActionTransitionGraphPayload, SceneNodePayload, TransitionEdgePayload
from application.engine.services.beat_coherence_enhancer import BeatCoherenceEnhancer
from application.engine.services.context_builder import Beat
from application.engine.services.spatial_coherence import (
    DraftTopologyCommitGate,
    EscalatingBeatRetryDirector,
    StreamingSceneLeakGuard,
    assign_visit_locations_to_beats,
    initialize_micro_scene_context,
    refresh_micro_scene_context_after_beat,
    transition_anchor_satisfied,
)
from domain.novel.value_objects.action_transition_graph import ActionTransitionGraph, SceneNode, TransitionEdge


def test_assign_visit_locations_distributes_sequence():
    beats = [
        Beat(description="a", target_words=100, focus="action"),
        Beat(description="b", target_words=100, focus="action"),
        Beat(description="c", target_words=100, focus="action"),
    ]
    assign_visit_locations_to_beats(beats, ["L1", "L2", "L3"])
    assert beats[0].location_id == "L1"
    assert beats[1].location_id == "L2"
    assert beats[2].location_id == "L3"


def test_transition_anchor_prefix_match():
    edge = TransitionEdge("A", "B", "艾伦推开沉重的木门", ("艾伦",))
    assert transition_anchor_satisfied("艾伦推开沉重的木门，跨入房间。", edge)
    assert not transition_anchor_satisfied("他直接坐在桌前。", edge)


def test_commit_gate_same_location_blocks_roster_stranger():
    gate = DraftTopologyCommitGate()
    roster = {"艾伦", "老威廉"}
    active = {"艾伦"}
    res = gate.evaluate(
        "老威廉站起身。",
        transitioning=False,
        edge=None,
        roster=roster,
        active_characters=active,
    )
    assert not res.ok
    assert res.failure_kind == "illegal_characters"


def test_commit_gate_transition_requires_anchor():
    gate = DraftTopologyCommitGate()
    edge = TransitionEdge("走廊", "房间", "推开木门", ("艾伦",))
    res = gate.evaluate(
        "房间里很安静。",
        transitioning=True,
        edge=edge,
        roster={"艾伦"},
        active_characters={"艾伦"},
    )
    assert not res.ok
    assert res.failure_kind == "missing_transition"


def test_escalating_retry_levels():
    director = EscalatingBeatRetryDirector()
    edge = TransitionEdge("走廊", "房间", "推开木门", ("艾伦",))
    p1 = director.build_patch(
        1, failure_kind="missing_transition", edge=edge, prev_loc="走廊", curr_loc="房间"
    )
    assert "状态流转失败" in p1
    p2 = director.build_patch(
        2, failure_kind="missing_transition", edge=edge, prev_loc="走廊", curr_loc="房间"
    )
    assert "强制锚定" in p2


def test_streaming_guard_skips_during_transition():
    guard = StreamingSceneLeakGuard(
        roster={"艾伦", "老威廉"},
        allowed_characters={"艾伦"},
        transitioning=True,
    )
    assert guard.check("老威廉说话了") is None


def test_payload_to_domain_roundtrip():
    payload = ActionTransitionGraphPayload(
        nodes=[
            SceneNodePayload(location_id="府邸_走廊", initial_props=["火把"], is_entry_point=True),
            SceneNodePayload(location_id="府邸_房间", initial_props=["木桌"]),
        ],
        transitions=[
            TransitionEdgePayload(
                source_location="府邸_走廊",
                target_location="府邸_房间",
                required_action="推开木门",
                trigger_characters=["艾伦"],
            )
        ],
        visit_sequence=["府邸_走廊", "府邸_房间"],
    )
    dom = payload.to_domain()
    assert isinstance(dom, ActionTransitionGraph)
    assert dom.get_transition_path("府邸_走廊", "府邸_房间") is not None


def test_beat_coherence_atg_directive():
    enh = BeatCoherenceEnhancer()
    dom = ActionTransitionGraph(
        nodes={
            "府邸_走廊": SceneNode("府邸_走廊", ("火把",)),
            "府邸_房间": SceneNode("府邸_房间", ("木桌",)),
        },
        transitions=(
            TransitionEdge("府邸_走廊", "府邸_房间", "推开木门", ("艾伦",)),
        ),
    )
    s = enh.build_atg_transition_directive("府邸_走廊", "府邸_房间", dom)
    assert "强制物理过渡" in s
    assert "推开木门" in s


def test_initialize_and_refresh_micro_ctx():
    dom = ActionTransitionGraph(
        nodes={"L1": SceneNode("L1", ("桌",))},
        transitions=(),
        visit_sequence=("L1",),
    )
    ctx = initialize_micro_scene_context(
        graph=dom, first_location_id="L1", roster=["艾伦", "老威廉"], pov="艾伦"
    )
    assert ctx.location_id == "L1"
    assert "艾伦" in ctx.active_characters

    enh = BeatCoherenceEnhancer()

    def _extract(t: str):
        return enh.extract_character_names(t)

    refresh_micro_scene_context_after_beat(
        ctx,
        beat_location_id="L1",
        beat_text="艾伦点了点头。",
        graph=dom,
        roster=["艾伦", "老威廉"],
        character_extractor=_extract,
    )
    assert "艾伦" in ctx.active_characters
