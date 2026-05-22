"""BeatCardPromptRenderer — 确定性渲染 EmotionBeatCard 为自然语言块。

设计约束：
- 纯 Python 字符串格式化，不调 PromptRegistry，不走 LLM
- 渲染结果插入 build_beat_prompt 的「写前三问」之前
- 字段缺失时静默降级（空字符串），不抛异常
"""
from application.engine.dtos.emotion_beat_card import EmotionBeatCard

_CARD_TEMPLATE = """\
【本拍写作锚点】
主角这一拍必须完成的事：{active_action}
这一拍之后，局面变了什么：{delta}
结尾要留下的悬钩：{hook_delta}
感官细节必须落地（至少选一个写进去）：{sensory_anchor}
读者此刻的期待缺口：{emotion_gap}
绝对禁止：{forbidden_drift}"""

_CARD_FIELDS = (
    "active_action", "delta", "hook_delta",
    "sensory_anchor", "emotion_gap", "forbidden_drift",
)


class BeatCardPromptRenderer:
    def render(self, card: EmotionBeatCard) -> str:
        return _CARD_TEMPLATE.format(
            **{f: getattr(card, f, "") or "" for f in _CARD_FIELDS}
        )
