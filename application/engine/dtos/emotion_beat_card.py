from dataclasses import dataclass


@dataclass
class EmotionBeatCard:
    """小说家视角的节拍规格卡——结构化真源，供渲染器和验收器消费。

    八个字段覆盖专业创作的"场景-续篇"闭环：
      goal/obstacle        → 场景驱动力
      active_action/delta  → 可见行为与结果变化
      emotion_gap          → 读者缺口（已感到X，渴望看到Y）
      hook_delta           → 钩子推进
      sensory_anchor       → 感官锚点
      forbidden_drift      → 本拍特有反模式（区别于通用水文雷达）
    """

    goal: str            # 主角本拍目标（一句话，主语为主角）
    obstacle: str        # 阻碍 / 对手行为 / 主角误判
    active_action: str   # 必写可见行为（不能是内心活动）
    delta: str           # 本拍结束后改变的事实（情节/关系/信息差 三选一）
    emotion_gap: str     # 读者已感到X，渴望看到Y（两个半句）
    hook_delta: str      # 本拍结尾推进的钩子（悬念/欲望/疑问）
    sensory_anchor: str  # 必须出现的感官细节（一句具体物象）
    forbidden_drift: str # 本拍禁止写成这样

    function: str = "action"  # 对应 Beat.focus
    target_words: int = 600
