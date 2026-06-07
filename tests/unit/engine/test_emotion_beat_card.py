"""EmotionBeatCard + BeatCardPromptRenderer 单元测试"""
import pytest

from application.engine.dtos.emotion_beat_card import EmotionBeatCard
from application.engine.services.beat_card_renderer import BeatCardPromptRenderer


def _sample_card(**overrides) -> EmotionBeatCard:
    defaults = dict(
        goal="主角夺回被没收的证据",
        obstacle="对手在门口守着，且手下两人",
        active_action="主角借火警拉响警报，趁乱推开对手冲出",
        delta="证据到手，但身份已暴露",
        emotion_gap="读者已感到憋屈，渴望看到主角反击成功",
        hook_delta="对手说出一句话让主角愣住——暗示有内鬼",
        sensory_anchor="走廊里消防铃声刺穿耳膜，白光频闪",
        forbidden_drift="禁止主角只靠一次对话化解；必须有肢体或物理行动",
        function="action",
        target_words=700,
    )
    defaults.update(overrides)
    return EmotionBeatCard(**defaults)


class TestBeatCardPromptRenderer:
    def setup_method(self):
        self.renderer = BeatCardPromptRenderer()

    def test_render_contains_all_fields(self):
        card = _sample_card()
        result = self.renderer.render(card)
        assert "主角夺回被没收的证据" in result
        assert "对手在门口守着" in result
        assert "主角借火警拉响警报" in result
        assert "证据到手，但身份已暴露" in result
        assert "读者已感到憋屈" in result
        assert "对手说出一句话" in result
        assert "消防铃声刺穿耳膜" in result
        assert "禁止主角只靠一次对话化解" in result

    def test_render_has_section_markers(self):
        card = _sample_card()
        result = self.renderer.render(card)
        assert "━━━ 节点卡" in result
        assert "必须写出的行为" in result
        assert "本拍禁止写成" in result

    def test_render_empty_fields_no_exception(self):
        card = _sample_card(goal="", forbidden_drift="")
        result = self.renderer.render(card)
        assert isinstance(result, str)

    def test_default_function_and_target_words(self):
        card = EmotionBeatCard(
            goal="g",
            obstacle="o",
            active_action="a",
            delta="d",
            emotion_gap="e",
            hook_delta="h",
            sensory_anchor="s",
            forbidden_drift="f",
        )
        assert card.function == "action"
        assert card.target_words == 600


class TestMakeMinimalCard:
    """context_builder._make_minimal_card 的烟雾测试"""

    def test_minimal_card_from_segment(self):
        from application.engine.services.context_builder import ContextBuilder

        # 只需要验证方法可调用，无需完整依赖注入
        # 使用 object.__new__ 绕过 __init__
        cb = object.__new__(ContextBuilder)
        card = cb._make_minimal_card("主角发现了藏在暗格里的密信", "suspense", 600)
        assert card.goal
        assert card.function == "suspense"
        assert card.target_words == 600
        assert card.forbidden_drift  # 应从 _forbidden_drifts 或 default 取值
