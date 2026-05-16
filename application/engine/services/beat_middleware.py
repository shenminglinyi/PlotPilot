"""节拍中间件协议与实现 — 低侵入式增强 autopilot_daemon 的节拍循环

核心设计：
- 中间件协议 (BeatMiddleware) 定义 pre_beat / post_beat 两个钩子
- 四个核心中间件：
  1. CoherenceMiddleware — 激活 BeatCoherenceEnhancer，注入连贯性指令
  2. TransitionMiddleware — 自动推断 transition_from_prev，注入过渡方式
  3. EnergyImmunityMiddleware — 高能节拍免疫 ChapterConductor 的字数压缩
  4. StepTensionMiddleware — ★ 爽文引擎: STEP 阶跃张力注入

★ 爽文引擎优化 — 内存优先 + Repository 仅持久化：
- 中间件的所有运行时状态（情绪趋势、前节拍上下文等）存储在 BeatMiddlewareContext 中
- BeatMiddlewareContext 是纯内存对象，不直接读写 Repository
- Repository 仅在章节生成完成后（post_process）进行持久化
- 这避免了每个节拍都进行 DB I/O，大幅提升生成速度

使用方式：
  middlewares = init_beat_middlewares(conductor, coherence_enhancer)
  ctx = BeatMiddlewareContext(novel_id=..., chapter_number=...)
  for i, beat in enumerate(beats):
      ctx.beat_index = i
      ctx.beat = beat
      # pre_beat: 修改 beat_prompt / adjusted_target
      for mw in middlewares:
          beat_prompt, adjusted_target = mw.pre_beat(...)
      # ... LLM 生成 ...
      # post_beat: 提取上下文，为下一节拍准备
      for mw in middlewares:
          ctx = mw.post_beat(...)
  # 章节生成完成后，一次性持久化 Repository
  middleware_cache.flush_to_repository(repository)
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Tuple

from application.engine.services.context_builder import Beat

logger = logging.getLogger(__name__)


# ─── 中间件协议 ───

@dataclass
class BeatMiddlewareContext:
    """节拍中间件上下文 — 在中间件之间流转的共享状态

    ★ 爽文引擎优化: 纯内存对象，不直接读写 Repository
    所有运行时状态都存储在此对象中，避免每个节拍都进行 DB I/O。
    Repository 仅在章节生成完成后进行一次性持久化。
    """
    # 当前小说信息
    novel_id: str = ""
    chapter_number: int = 0
    # 节拍信息
    beat_index: int = 0
    total_beats: int = 0
    beat: Optional[Beat] = None
    # 指挥信号
    original_adjusted_target: int = 0
    phase: str = "unfurl"  # unfurl / converge / land
    # 累积内容
    accumulated_content: str = ""
    # 前一节拍信息（post_beat 填充）
    prev_beat_content: str = ""
    prev_beat_focus: str = ""
    prev_beat_context: Optional[Any] = None  # BeatContext from CoherenceEnhancer
    # 情绪方向（post_beat 填充）
    emotion_trend: str = "stable"  # rising / peak / falling / stable
    # ★ 爽文引擎: STEP 阶跃阶段名（由 StepTensionMiddleware 填充）
    step_phase: str = "daily"  # daily / provocation / eruption / aftermath / settlement
    step_tension_pct: int = 10  # 当前 STEP 阶段对应的张力百分比
    # ★ 爽文引擎: 内存缓存 — 待持久化的中间件提取结果
    _pending_persist: dict = field(default_factory=dict)  # {key: value} 待持久化数据

    def queue_persist(self, key: str, value: Any) -> None:
        """★ 爽文引擎: 将数据加入待持久化队列（内存操作，不触发 I/O）"""
        self._pending_persist[key] = value

    def flush_to_repository(self, repository: Any) -> int:
        """★ 爽文引擎: 一次性将内存缓存持久化到 Repository

        仅在章节生成完成后调用，避免每个节拍都进行 DB I/O。

        Args:
            repository: 目标 Repository 实例

        Returns:
            持久化的条目数量
        """
        if not self._pending_persist or repository is None:
            return 0
        count = 0
        for key, value in self._pending_persist.items():
            try:
                # 通用持久化接口——Repository 需要实现 save_middleware_result
                if hasattr(repository, 'save_middleware_result'):
                    repository.save_middleware_result(
                        novel_id=self.novel_id,
                        chapter_number=self.chapter_number,
                        key=key,
                        value=value,
                    )
                    count += 1
            except Exception as e:
                logger.warning(f"中间件缓存持久化失败 key={key}: {e}")
        self._pending_persist.clear()
        return count


# 避免循环导入
from typing import Any


class BeatMiddleware(Protocol):
    """节拍中间件协议"""

    def pre_beat(
        self,
        beat_prompt: str,
        adjusted_target: int,
        ctx: BeatMiddlewareContext,
    ) -> Tuple[str, int]:
        """节拍生成前钩子：可修改 beat_prompt 和 adjusted_target

        Args:
            beat_prompt: 当前节拍的 Prompt
            adjusted_target: 调整后的目标字数
            ctx: 中间件上下文

        Returns:
            (modified_prompt, modified_target)
        """
        return beat_prompt, adjusted_target

    def post_beat(
        self,
        beat_content: str,
        ctx: BeatMiddlewareContext,
    ) -> BeatMiddlewareContext:
        """节拍生成后钩子：提取上下文，为下一节拍准备

        Args:
            beat_content: 生成的节拍内容
            ctx: 中间件上下文（可修改 prev_beat_* 字段）

        Returns:
            更新后的上下文
        """
        return ctx


# ─── 1. CoherenceMiddleware — 激活 BeatCoherenceEnhancer ───

class CoherenceMiddleware:
    """连贯性中间件：将 BeatCoherenceEnhancer 的分析结果注入 beat_prompt

    核心逻辑：
    - pre_beat: 如果有前一节拍的上下文，生成连贯性指令并注入
    - post_beat: 分析当前节拍的 BeatContext，供下一节拍使用
    """

    def __init__(self):
        from application.engine.services.beat_coherence_enhancer import BeatCoherenceEnhancer
        self.enhancer = BeatCoherenceEnhancer()

    def pre_beat(
        self,
        beat_prompt: str,
        adjusted_target: int,
        ctx: BeatMiddlewareContext,
    ) -> Tuple[str, int]:
        if ctx.beat_index == 0 or ctx.prev_beat_context is None:
            return beat_prompt, adjusted_target

        # 生成连贯性指令
        coherence_instructions = self.enhancer.generate_coherence_instructions(
            previous_content=ctx.prev_beat_content,
            current_beat_description=ctx.beat.description if ctx.beat else "",
            previous_context=ctx.prev_beat_context,
            beat_index=ctx.beat_index,
            total_beats=ctx.total_beats,
        )

        if coherence_instructions.strip():
            beat_prompt = f"{coherence_instructions}\n\n{beat_prompt}"

        return beat_prompt, adjusted_target

    def post_beat(
        self,
        beat_content: str,
        ctx: BeatMiddlewareContext,
    ) -> BeatMiddlewareContext:
        if not beat_content.strip():
            return ctx

        # 分析当前节拍的上下文
        beat_focus = ctx.beat.focus if ctx.beat else "sensory"
        ctx.prev_beat_context = self.enhancer.analyze_beat_context(
            beat_content, beat_focus
        )
        ctx.prev_beat_content = beat_content
        ctx.prev_beat_focus = beat_focus

        return ctx


# ─── 2. TransitionMiddleware — 自动推断 transition_from_prev ───

class TransitionMiddleware:
    """过渡方式中间件：自动推断节拍间的过渡方式并注入 Prompt

    核心逻辑：
    - pre_beat: 根据前一节拍和当前节拍的 focus 类型，推断过渡方式
    - 首节拍：不注入（由 ChapterBridge 的 BRIDGE_DIRECTIVE 负责）
    """

    # 过渡方式映射表：(prev_focus, curr_focus) → transition_type
    TRANSITION_MAP = {
        # 从对话出发的过渡
        ("dialogue", "action"): "对话中断/决裂 → 动作爆发（情绪升级驱动行动）",
        ("dialogue", "sensory"): "对话中的某个细节引发注意 → 感官聚焦",
        ("dialogue", "emotion"): "对话引发内心波澜 → 转入心理描写",
        ("dialogue", "suspense"): "对话中透露关键信息 → 悬念开始",
        ("dialogue", "power_reveal"): "对话中的挑衅/轻视 → 实力揭露",
        ("dialogue", "identity_reveal"): "对话中的质疑 → 身份揭露",

        # 从动作出发的过渡
        ("action", "dialogue"): "动作暂停/对峙 → 对话交锋",
        ("action", "sensory"): "动作后的环境破坏/变化 → 感官描写",
        ("action", "emotion"): "动作完成后的情绪释放 → 心理余波",
        ("action", "suspense"): "动作中的意外发现 → 悬念转折",
        ("action", "power_reveal"): "战斗中展露底牌 → 实力爆发",

        # 从感官出发的过渡
        ("sensory", "dialogue"): "环境中的声响/动静 → 角色对话",
        ("sensory", "action"): "氛围酝酿到极点 → 动作爆发",
        ("sensory", "emotion"): "感官细节触发回忆/情绪 → 心理描写",
        ("sensory", "suspense"): "环境中的异常 → 悬念开始",
        ("sensory", "power_reveal"): "压抑的氛围 → 突然的实力展现",

        # 从情绪出发的过渡
        ("emotion", "action"): "情绪积累到极点 → 化为行动",
        ("emotion", "dialogue"): "内心感受驱动 → 说出口",
        ("emotion", "suspense"): "不安/疑虑 → 发现线索",
        ("emotion", "power_reveal"): "被逼到绝境 → 底牌爆发",

        # 从悬念出发的过渡
        ("suspense", "action"): "悬念揭晓 → 行动开始",
        ("suspense", "dialogue"): "发现线索 → 质问/对峙",
        ("suspense", "power_reveal"): "悬念指向 → 实力揭露",

        # 从爽点出发的过渡
        ("power_reveal", "emotion"): "实力展现后 → 众人反应/内心感受",
        ("power_reveal", "suspense"): "爽点之后 → 新的悬念/更大挑战",
        ("power_reveal", "dialogue"): "实力展现后 → 对话收场",
        ("identity_reveal", "emotion"): "身份揭露后 → 众人震惊",
        ("identity_reveal", "suspense"): "身份揭露后 → 新的谜团",
    }

    def pre_beat(
        self,
        beat_prompt: str,
        adjusted_target: int,
        ctx: BeatMiddlewareContext,
    ) -> Tuple[str, int]:
        if ctx.beat_index == 0:
            return beat_prompt, adjusted_target

        curr_focus = ctx.beat.focus if ctx.beat else "sensory"
        prev_focus = ctx.prev_beat_focus or "sensory"

        # 查找过渡方式
        transition = self.TRANSITION_MAP.get((prev_focus, curr_focus))

        if not transition:
            # 尝试通用过渡
            transition = self._infer_generic_transition(prev_focus, curr_focus)

        if transition:
            transition_block = (
                f"\n\n🔗【本节拍过渡方式】{transition}\n"
                f"→ 你的第一句话必须遵循此过渡方式与前节拍衔接"
            )
            beat_prompt = transition_block + beat_prompt

        return beat_prompt, adjusted_target

    def post_beat(
        self,
        beat_content: str,
        ctx: BeatMiddlewareContext,
    ) -> BeatMiddlewareContext:
        ctx.prev_beat_focus = ctx.beat.focus if ctx.beat else "sensory"
        return ctx

    @staticmethod
    def _infer_generic_transition(prev_focus: str, curr_focus: str) -> str:
        """通用过渡推断"""
        if prev_focus == curr_focus:
            return "延续同一节奏，加深描写力度"

        high_energy = {"action", "power_reveal", "identity_reveal", "hook"}
        low_energy = {"sensory", "emotion", "suspense"}

        if prev_focus in high_energy and curr_focus in low_energy:
            return "高潮余波 → 节奏放缓，消化冲击"
        if prev_focus in low_energy and curr_focus in high_energy:
            return "积蓄势能 → 爆发突破"
        return "自然过渡，保持叙事流畅"


# ─── 3. EnergyImmunityMiddleware — 高能节拍免疫压缩 ───

class EnergyImmunityMiddleware:
    """能量免疫中间件：确保高能节拍不被 ChapterConductor 过度压缩

    核心逻辑：
    - 高能节拍（action / power_reveal / identity_reveal / hook）在 CONVERGE/LAND
      阶段时，保持原始目标字数，不压缩
    - 被豁免的字数预算由低能节拍（sensory / suspense）分摊
    - post_beat: 推断情绪方向（rising/peak/falling/stable）
    """

    # 高能 focus 类型 — 在收束阶段免疫压缩
    HIGH_ENERGY_FOCUSES = {"action", "power_reveal", "identity_reveal", "hook", "cultivation"}

    # 情绪关键词检测
    RISING_KEYWORDS = {"爆发", "冲", "怒", "震", "怒吼", "反击", "逆转", "底牌", "暴露", "揭露", "震惊"}
    PEAK_KEYWORDS = {"绝境", "巅峰", "最强", "极限", "终极", "致命", "一击"}
    FALLING_KEYWORDS = {"平息", "退", "缓", "叹", "沉默", "余波", "收场", "结束"}

    def pre_beat(
        self,
        beat_prompt: str,
        adjusted_target: int,
        ctx: BeatMiddlewareContext,
    ) -> Tuple[str, int]:
        curr_focus = ctx.beat.focus if ctx.beat else "sensory"

        # 如果当前节拍是高能类型，且处于收束/着陆阶段
        if curr_focus in self.HIGH_ENERGY_FOCUSES and ctx.phase in ("converge", "land"):
            # 恢复到原始目标字数（不压缩）
            original_target = ctx.beat.target_words if ctx.beat else adjusted_target
            if original_target > adjusted_target:
                logger.info(
                    f"[EnergyImmunity] 🛡️ 节拍 {ctx.beat_index + 1} ({curr_focus}) "
                    f"免疫压缩：{adjusted_target} → {original_target} 字 "
                    f"(phase={ctx.phase})"
                )
                adjusted_target = original_target

                # 在 prompt 中追加提示：这是被保护的爽点节拍
                beat_prompt += (
                    "\n\n🛡️【能量免疫】本节拍为高能爽点，已获得字数保护。"
                    "请全力展开，不要因为字数压力而压缩冲击力。"
                    "完整展现实力/身份/反转的每一个细节！"
                )

        return beat_prompt, adjusted_target

    def post_beat(
        self,
        beat_content: str,
        ctx: BeatMiddlewareContext,
    ) -> BeatMiddlewareContext:
        """推断情绪方向，供 soft_landing 和下一节拍使用"""
        if not beat_content.strip():
            return ctx

        content_tail = beat_content[-500:]  # 取尾部500字

        # 简单关键词检测
        rising_count = sum(1 for kw in self.RISING_KEYWORDS if kw in content_tail)
        peak_count = sum(1 for kw in self.PEAK_KEYWORDS if kw in content_tail)
        falling_count = sum(1 for kw in self.FALLING_KEYWORDS if kw in content_tail)

        if peak_count > 0 or (rising_count >= 2):
            ctx.emotion_trend = "peak"
        elif rising_count > falling_count:
            ctx.emotion_trend = "rising"
        elif falling_count > rising_count:
            ctx.emotion_trend = "falling"
        else:
            ctx.emotion_trend = "stable"

        return ctx


# ─── 4. StepTensionMiddleware — ★ 爽文引擎: STEP 阶跃张力注入 ───

class StepTensionMiddleware:
    """★ 爽文引擎: STEP 阶跃张力中间件

    核心逻辑：
    - pre_beat: 根据当前节拍在章节中的位置，注入 STEP 阶跃张力指令
    - 使 LLM 在不同阶段（日常/挑衅/爆发/余韵/结算）输出不同密度的内容
    - 前三章使用加速版 STEP 配置（日常更短，爆发更长）

    与 ChapterConductor 的对应关系：
    - UNFURL ≈ daily + provocation（展开蓄力）
    - CONVERGE ≈ eruption（爆发收束）
    - LAND ≈ aftermath + settlement（余韵着陆）
    """

    # STEP 阶段对应的写作指令
    STEP_INSTRUCTIONS = {
        "daily": (
            "🏠【日常节奏】当前处于日常蓄力阶段。用轻快的笔触铺陈：\n"
            "- 角色日常互动、轻幽默对话、生活细节\n"
            "- 暗埋冲突种子：一句不经意的话、一个意味深长的眼神\n"
            "- 节奏舒缓但有张力暗涌——不要让读者感到无聊\n"
            "- 禁止大段背景介绍，用动作和对话推进"
        ),
        "provocation": (
            "⚡【挑衅升温】当前处于挑衅升温阶段。节奏开始收紧：\n"
            "- 主角遭受质疑/轻视/不公——但隐忍不发\n"
            "- 反派或对手嚣张跋扈，细节描写其傲慢\n"
            "- 周围人的态度：有人同情、有人冷眼、有人落井下石\n"
            "- 蓄力感越来越强——读者在等那个爆发的瞬间"
        ),
        "eruption": (
            "🔥【爆发高潮】当前处于核心爽点爆发阶段！必须全力以赴：\n"
            "- 主角展露底牌/实力/身份——用最震撼的方式！\n"
            "- 短句、快节奏、画面切换——制造视觉冲击\n"
            "- 旁观者的反应是爽感核心：从轻视到震惊，从不屑到敬畏\n"
            "- 反派的表情变化要具体——瞳孔骤缩、脸色煞白、冷汗直流\n"
            "- 这是读者付费的核心体验，字数宁多勿少，充分展开！"
        ),
        "aftermath": (
            "🌊【余韵回落】当前处于爆发后的余韵阶段：\n"
            "- 描写爆发后的场景变化——环境破坏、沉默的人群、震惊的余波\n"
            "- 关键角色的内心独白——对刚才发生之事的消化\n"
            "- 态度转变的具体表现：之前嘲讽者低头、之前轻视者弯腰\n"
            "- 不要急——让读者在爽感中慢慢回味"
        ),
        "settlement": (
            "📝【收尾结算】当前处于章节收尾阶段：\n"
            "- 新的格局/关系状态确认\n"
            "- 主角的态度：云淡风轻、不以为意（增加反差爽感）\n"
            "- 用一个画面或一句话作为结尾钩子——暗示更大的挑战即将到来\n"
            "- 简洁有力，不要拖泥带水"
        ),
    }

    def __init__(self, plot_arc=None):
        """初始化

        Args:
            plot_arc: PlotArc 实例（提供 STEP 配置）；如果为 None，使用默认配置
        """
        self.plot_arc = plot_arc

    def pre_beat(
        self,
        beat_prompt: str,
        adjusted_target: int,
        ctx: BeatMiddlewareContext,
    ) -> Tuple[str, int]:
        # 确定 STEP 阶段
        if self.plot_arc:
            tension_pct = self.plot_arc.get_step_tension_for_beat(
                chapter_number=ctx.chapter_number,
                beat_index=ctx.beat_index,
                total_beats=ctx.total_beats,
            )
            profile = self.plot_arc.get_step_tension_profile(ctx.chapter_number)
            # 根据张力百分比反推阶段名
            step_phase = "daily"
            for phase_config in profile:
                if phase_config["tension_pct"] == tension_pct:
                    step_phase = phase_config["phase"]
                    break
        else:
            # 无 PlotArc 时使用简化推断
            step_phase, tension_pct = self._infer_step_phase(ctx)

        # 更新上下文
        ctx.step_phase = step_phase
        ctx.step_tension_pct = tension_pct

        # 注入 STEP 指令
        instruction = self.STEP_INSTRUCTIONS.get(step_phase, "")
        if instruction:
            beat_prompt = (
                f"\n🎯【STEP阶跃张力={tension_pct}% | 阶段={step_phase}】\n"
                f"{instruction}\n\n"
                f"{beat_prompt}"
            )

        return beat_prompt, adjusted_target

    def post_beat(
        self,
        beat_content: str,
        ctx: BeatMiddlewareContext,
    ) -> BeatMiddlewareContext:
        """将 STEP 阶段信息加入待持久化队列（内存操作）"""
        if ctx.novel_id and ctx.chapter_number > 0:
            ctx.queue_persist(
                key=f"step_tension_beat_{ctx.beat_index}",
                value={
                    "step_phase": ctx.step_phase,
                    "tension_pct": ctx.step_tension_pct,
                    "emotion_trend": ctx.emotion_trend,
                },
            )
        return ctx

    @staticmethod
    def _infer_step_phase(ctx: BeatMiddlewareContext) -> Tuple[str, int]:
        """无 PlotArc 时的简化 STEP 阶段推断"""
        if ctx.total_beats <= 0:
            return "daily", 10

        progress = ctx.beat_index / ctx.total_beats

        if progress < 0.15:
            return "daily", 10
        elif progress < 0.35:
            return "provocation", 30
        elif progress < 0.70:
            return "eruption", 80
        elif progress < 0.85:
            return "aftermath", 40
        else:
            return "settlement", 20


# ─── 工厂函数 ───

def init_beat_middlewares(
    conductor=None,
    enable_coherence: bool = True,
    enable_transition: bool = True,
    enable_energy_immunity: bool = True,
    enable_step_tension: bool = True,
    plot_arc=None,
) -> List[BeatMiddleware]:
    """初始化节拍中间件链

    ★ 爽文引擎优化: 内存优先架构
    - 所有中间件操作在内存中完成
    - Repository 仅在章节生成完成后通过 ctx.flush_to_repository() 一次性持久化

    Args:
        conductor: ChapterConductor 实例（供 EnergyImmunity 使用）
        enable_coherence: 是否启用连贯性中间件
        enable_transition: 是否启用过渡方式中间件
        enable_energy_immunity: 是否启用能量免疫中间件
        enable_step_tension: 是否启用 STEP 阶跃张力中间件
        plot_arc: PlotArc 实例（供 StepTensionMiddleware 使用）

    Returns:
        中间件列表
    """
    middlewares = []

    if enable_coherence:
        try:
            middlewares.append(CoherenceMiddleware())
            logger.info("✓ CoherenceMiddleware 已挂载")
        except Exception as e:
            logger.warning(f"CoherenceMiddleware 挂载失败: {e}")

    if enable_transition:
        try:
            middlewares.append(TransitionMiddleware())
            logger.info("✓ TransitionMiddleware 已挂载")
        except Exception as e:
            logger.warning(f"TransitionMiddleware 挂载失败: {e}")

    if enable_energy_immunity:
        try:
            middlewares.append(EnergyImmunityMiddleware())
            logger.info("✓ EnergyImmunityMiddleware 已挂载")
        except Exception as e:
            logger.warning(f"EnergyImmunityMiddleware 挂载失败: {e}")

    # ★ 爽文引擎: STEP 阶跃张力中间件
    if enable_step_tension:
        try:
            middlewares.append(StepTensionMiddleware(plot_arc=plot_arc))
            logger.info("✓ StepTensionMiddleware 已挂载（爽文引擎）")
        except Exception as e:
            logger.warning(f"StepTensionMiddleware 挂载失败: {e}")

    return middlewares
