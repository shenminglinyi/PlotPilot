"""快速验证所有核心模块的导入和基本功能"""
import sys
import os

# 添加项目根目录
# __file__ = D:\CODE\Plotpilot\scripts\evaluation\quick_verify.py
# 我们需要 D:\CODE\Plotpilot 在 sys.path 中
PLOTPILOT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PLOTPILOT_ROOT not in sys.path:
    sys.path.insert(0, PLOTPILOT_ROOT)

def test_story():
    from engine.core.entities.story import Story, StoryId, StoryPhase
    s = Story.create("测试小说", "武侠世界", 10)
    assert s.title == "测试小说"
    assert s.story_phase == StoryPhase.OPENING
    s.current_chapter = 8
    s.update_phase()
    assert s.story_phase == StoryPhase.CONVERGENCE
    print("✅ Story OK")

def test_character():
    from engine.core.entities.character import Character, CharacterId, VoiceStyle, Wound, CharacterPatch
    c = Character.create("林羽", core_belief="信任是致命软肋")
    assert c.name == "林羽"
    c.apply_trauma(
        trigger_chapter=10,
        trigger_event="导师背叛",
        new_belief="只有力量能保护自己",
        new_wound=Wound(description="左肩被恩师刺伤", trigger="有人靠近左后方", effect="肌肉紧绷"),
    )
    assert len(c.evolution_patches) == 1
    mask = c.compute_mask()
    assert mask["core_belief"] == "只有力量能保护自己"
    t0 = c.to_t0_fact_lock(10)
    assert "林羽" in t0
    print("✅ Character OK")

def test_chapter():
    from engine.core.entities.chapter import Chapter, Paragraph, ChapterStatus
    ch = Chapter(chapter_number=1, title="初入江湖")
    ch.add_paragraph(Paragraph(content="他推开门，发现了那封信。", paragraph_type="action"))
    assert len(ch.paragraphs) == 1
    assert ch.word_count > 0
    print("✅ Chapter OK")

def test_foreshadow():
    from engine.core.entities.foreshadow import Foreshadow, ForeshadowStatus, ForeshadowBinding
    fs = Foreshadow.create(
        description="师父留下的剑谱暗藏玄机",
        planted_in_chapter=1,
        emotional_weight=0.9,
        binding_level=ForeshadowBinding.EVENT,
        planting_atmosphere="雨夜，烛光摇曳",
    )
    assert fs.status == ForeshadowStatus.PLANTED
    fs.reference(5)
    assert fs.status == ForeshadowStatus.REFERENCED
    fs.awaken()
    assert fs.status == ForeshadowStatus.AWAKENING
    instruction = fs.to_t0_awakening_instruction()
    assert "伏笔苏醒" in instruction
    fs.resolve(10)
    assert fs.status == ForeshadowStatus.RESOLVED
    assert fs.validate_binding() == True  # 0.9 weight + event binding
    print("✅ Foreshadow OK")

def test_checkpoint():
    from engine.core.value_objects.checkpoint import Checkpoint, CheckpointId, CheckpointType
    cp = Checkpoint.create(
        story_id="test",
        trigger_type=CheckpointType.CHAPTER,
        trigger_reason="第1章完成",
        story_state={"chapter": 1},
        character_masks={},
        emotion_ledger={},
        active_foreshadows=["fs1"],
    )
    assert cp.trigger_type == CheckpointType.CHAPTER
    d = cp.to_dict()
    cp2 = Checkpoint.from_dict(d)
    assert cp2.checkpoint_id.value == cp.checkpoint_id.value
    print("✅ Checkpoint OK")

def test_emotion_ledger():
    from engine.core.value_objects.emotion_ledger import (
        EmotionLedger, EmotionalWound, EmotionalBoon, PowerShift, OpenLoop,
    )
    ledger = EmotionLedger.create_empty()
    ledger = ledger.add_wound(EmotionalWound(description="失去师父", impact="多疑"))
    ledger = ledger.add_boon(EmotionalBoon(description="获得剑谱", value="实力提升"))
    ledger = ledger.add_power_shift(PowerShift(from_state="被动", to_state="主动"))
    ledger = ledger.add_open_loop(OpenLoop(description="赵虎眼神", hint="幕后黑手"))
    summary = ledger.to_chapter_summary()
    assert "失去师父" in summary
    t0 = ledger.to_t0_section()
    assert "情绪账本" in t0
    print("✅ EmotionLedger OK")

def test_character_mask():
    from engine.core.value_objects.character_mask import CharacterMask
    mask = CharacterMask(
        character_id="lin_yu",
        name="林羽",
        core_belief="信任是致命软肋",
        moral_taboos=["不杀手无寸铁之人"],
        voice_style="惜字如金",
        active_wounds=[{"description": "左肩被刺", "trigger": "左后方", "effect": "紧绷"}],
        chapter_number=50,
    )
    t0 = mask.to_t0_fact_lock()
    assert "林羽" in t0
    result = mask.validate_behavior("林羽信任了陌生人")
    assert isinstance(result, dict)
    print("✅ CharacterMask OK")

def test_quality_guardrail():
    from engine.application.quality_guardrails.quality_guardrail import QualityGuardrail
    guardrail = QualityGuardrail()
    report = guardrail.advise(
        text="他愣了半晌，攥紧的拳头慢慢松开。她笑了，眼底有光。",
        character_names=["林羽"],
        era="ancient",
    )
    assert 0 <= report.overall_score <= 1
    print(f"✅ QualityGuardrail OK (score: {report.overall_score:.2f})")

def test_plot_state_machine():
    from engine.application.plot_state_machine.state_machine import PlotStateMachine
    from engine.core.entities.story import StoryPhase
    sm = PlotStateMachine()
    assert sm.current_phase == StoryPhase.OPENING
    assert sm.is_new_foreshadow_allowed() == True
    sm.transition(StoryPhase.DEVELOPMENT, "开局完成")
    sm.transition(StoryPhase.CONVERGENCE, "进入收敛")
    assert sm.is_new_foreshadow_allowed() == False
    instruction = sm.get_phase_instruction()
    assert "禁止开新坑" in instruction
    print("✅ PlotStateMachine OK")

def test_event_bus():
    from engine.infrastructure.events.event_bus import EventBus, ChapterCompletedEvent
    bus = EventBus()
    received = []
    bus.subscribe("chapter_completed", lambda e: received.append(e))
    event = ChapterCompletedEvent(story_id="test", chapter_number=1)
    bus.publish_sync(event)
    assert len(received) == 1
    print("✅ EventBus OK")

def test_naming_guardrail():
    from engine.application.quality_guardrails.naming_guardrail import NamingGuardrail
    g = NamingGuardrail()
    score, violations = g.check(["李天", "王刚", "苏沉渊"], era="ancient")
    assert score < 1.0  # 李天和王刚应该有问题
    print(f"✅ NamingGuardrail OK (score: {score:.2f}, violations: {len(violations)})")

def test_prompt_runtime():
    from infrastructure.ai.prompt_runtime import PromptRuntimeService
    service = PromptRuntimeService()
    variables = service.scan_variables("你好{name}，欢迎来到{place}")
    assert "name" in variables and "place" in variables
    print("✅ PromptRuntime OK")

def test_autopilot_state():
    from domain.novel.entities.novel_refactored import AutopilotState, AutopilotStatus, NovelStage
    state = AutopilotState(autopilot_status=AutopilotStatus.RUNNING)
    assert state.is_running()
    assert state.can_continue()
    new_state = state.with_update(consecutive_error_count=3)
    assert not new_state.can_continue()
    print("✅ AutopilotState OK")


if __name__ == "__main__":
    tests = [
        test_story,
        test_character,
        test_chapter,
        test_foreshadow,
        test_checkpoint,
        test_emotion_ledger,
        test_character_mask,
        test_quality_guardrail,
        test_plot_state_machine,
        test_event_bus,
        test_naming_guardrail,
        test_prompt_runtime,
        test_autopilot_state,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"测试结果: {passed} 通过, {failed} 失败, 共 {passed+failed} 个")
    print(f"{'='*60}")
