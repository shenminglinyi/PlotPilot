"""BeatCardPromptRenderer — 确定性渲染 EmotionBeatCard 为自然语言块。

设计约束：
- 纯 Python 字符串格式化，不调 PromptRegistry，不走 LLM
- 渲染结果插入 build_beat_prompt 的「写前三问」之前
- 字段缺失时静默降级（空字符串），不抛异常
"""
from application.engine.dtos.emotion_beat_card import EmotionBeatCard

_CARD_TEMPLATE = """\
━━━ 节点卡（策划预填，内化后动笔，不输出到正文） ━━━
目标：{goal}
阻碍：{obstacle}
✅ 必须写出的行为：{active_action}
✅ 本拍改变了什么：{delta}
✅ 本拍结尾钩子：{hook_delta}
感官锚点（必须出现）：{sensory_anchor}
读者缺口：{emotion_gap}
🚫 本拍禁止写成：{forbidden_drift}
━━━━━━━━━━━━━━━━━━━━"""

_CARD_FIELDS = (
    "goal", "obstacle", "active_action", "delta",
    "emotion_gap", "hook_delta", "sensory_anchor", "forbidden_drift",
)


class BeatCardPromptRenderer:
    def render(self, card: EmotionBeatCard) -> str:
        return _CARD_TEMPLATE.format(
            **{f: getattr(card, f, "") or "" for f in _CARD_FIELDS}
        )
