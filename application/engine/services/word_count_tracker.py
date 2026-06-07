"""章节指挥（ChapterConductor）—— 专业小说家的字数控制哲学

核心思想：
    真正的小说家从不"截断"——他们"收束"。

    想象你在写一个场景，编辑告诉你"还剩 800 字"。
    你不会写到 799 字然后一刀切掉，而是：
    1. 还剩很多 → 放开写，细节铺陈、对话展开
    2. 用掉大半 → 开始加速，场景变紧凑，对话变短促
    3. 快到上限 → 用一个有画面感的短句收住，干净利落
    4. 超了 → 不截断正文；交给完成判定拦截，下一轮重新生成或继续

三个阶段：
    UNFURL  (铺陈): 0% ~ 75% 预算 — 尽情展开，冲突、对话、感官细节
    CONVERGE (收束): 75% ~ 92% 预算 — 场景加速，对话短促，线头开始回收
    LAND    (着陆): 92% ~ 100%+ 预算 — 必须收住，干净结尾，悬念钩子

使用方式：
    conductor = ChapterConductor(total_budget=2500, total_beats=4)

    for i, beat in enumerate(beats):
        # 1. 获取当前阶段信号
        signal = conductor.get_signal(i)

        # 2. 根据信号调整 Prompt（铺陈/收束/着陆指令）
        beat_instruction = signal.beat_instruction  # 注入节拍 Prompt

        # 3. 获取调整后的目标字数
        adjusted_target = conductor.allocate_beat(beat.target_words)

        # 4. 生成内容
        content = await generate_beat(adjusted_target)

        # 5. 报告实际字数
        deviation = conductor.report_actual(len(content))
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class ConductorPhase(Enum):
    """章节指挥阶段"""
    UNFURL = "unfurl"       # 铺陈：尽情展开
    CONVERGE = "converge"   # 收束：开始回收
    LAND = "land"           # 着陆：必须收住


@dataclass
class ConductorSignal:
    """指挥信号——告诉当前节拍应该怎么写"""
    phase: ConductorPhase
    budget_used_ratio: float      # 预算消耗比 0~1+
    remaining_budget: int         # 剩余字数
    beats_remaining: int          # 剩余节拍数
    is_final_beat: bool           # 是否是最后一个节拍

    # ── 创作指令（注入 Prompt） ──
    beat_instruction: str = ""    # 节拍级创作指令
    chapter_ending_hint: str = "" # 章节收尾提示（仅最后节拍）

    # ── 字数约束 ──
    max_words_hint: int = 0       # 建议字数上限（Prompt 中提示 LLM）
    hard_cap: int = 0             # 已废弃：不再对正文做硬截断


@dataclass
class BeatRecord:
    """节拍记录"""
    index: int
    original_target: int  # 原始目标
    adjusted_target: int  # 调整后目标
    actual: int = 0       # 实际字数
    deviation: int = 0    # 偏差（actual - adjusted_target）
    phase: ConductorPhase = ConductorPhase.UNFURL  # 该节拍所处的阶段
    focus: str = ""       # Phase 2: 节拍 focus 类型
    is_immune: bool = False  # Phase 2: 是否免疫了压缩


class ChapterConductor:
    """章节指挥——像专业小说家一样控制节奏

    核心原则：
    1. 不做事后精简（毁灭文本质量）
    2. 不做粗暴截断（读者感到割裂）
    3. 通过 Prompt 指令引导 LLM 自然收束
    4. 不做截断后补写；宁可不放行，也不制造胶水段
    5. 收束是渐进的——不是突然刹车，而是逐步减速
    6. Phase 2: 高能节拍免疫压缩——爽点不容妥协
    7. 爽文引擎: 高能节拍锁定 UNFURL，绝对不在打脸高潮处触发 CONVERGE
    8. 爽文引擎: 高能节拍超支的字数缺口，转嫁到后续 sensory/dialogue 节拍中压缩
    """

    # ── 阶段切换阈值 ──
    CONVERGE_THRESHOLD = 0.75   # 75% 预算消耗后开始收束
    LAND_THRESHOLD = 0.92       # 92% 预算消耗后进入着陆

    # ── 字数保护 ──
    MIN_BEAT_WORDS = 200        # 单节拍最小字数（不能无限压缩）

    # Phase 2: 高能 focus 集合 — 在 CONVERGE/LAND 阶段免疫压缩
    HIGH_ENERGY_FOCUSES = {"action", "power_reveal", "identity_reveal", "hook", "cultivation"}

    # ── 收束指令模板 ──
    _UNFURL_INSTRUCTION = (
        "【铺陈阶段】本章还有充足的篇幅空间。"
        "尽情展开：冲突要充分碰撞，对话要你来我往，感官细节要细腻。"
        "不要急于推进下一个情节点——让当前场景充分发酵。"
    )

    _CONVERGE_INSTRUCTION = (
        "【收束阶段】本章字数池已消耗过半。开始收紧节奏：\n"
        "• 场景转换加速——一个眼神、一句话就能交代清楚的，不要铺陈整段\n"
        "• 对话变精炼——删掉寒暄和同义反复，只留有信息增量的对白\n"
        "• 叙述变紧凑——环境描写点到即止，用一两个精准细节代替全景扫描\n"
        "• 情节主线优先——支线细节如果不在本章闭合，一笔带过\n"
        "• 保持连贯性——即使节奏收紧，也要确保与上一节拍的情节衔接自然\n"
        "• 收紧节奏≠碎片化——同一动作链和视觉焦点的句子仍须合并为有机段落，只是每段信息密度更高、句数更少（2-3句），不要退化为一句一行的分镜脚本"
    )

    _LAND_INSTRUCTION = (
        "【着陆阶段】本章即将结束，必须立即收住！\n"
        "• 用最后一个完整的场景画面收束——一个动作、一个表情、一句有分量的话\n"
        "• 绝不开启新的场景或新的对话回合\n"
        "• 如果有下一章的钩子，用一句暗示性的短句点一下即可，不要展开\n"
        "• 结尾必须是完整的句子（以句号等结束），绝不留下半句话\n"
        "• 确保与上一节拍形成完整的叙事弧线，给读者满足感\n"
        "• 着陆收束仍须保持段落完整性——同一个画面的动作、感官、心理合并在同一段，不要因收尾急促而退化为一句一行的碎片"
    )

    _FINAL_BEAT_HINT = (
        "这是本章最后一个节拍！章节必须在此结束：\n"
        "1. 给出完整的段落收尾——故事告一段落，读者能感知到「这一章讲完了」\n"
        "2. 留一个悬念钩子——让读者想翻下一页，但不要强行总结\n"
        "3. 用有画面感的方式结束——最后一个画面留在读者脑海中\n"
        "4. 绝对不能留下悬而未决的对话或行动"
    )

    def __init__(
        self,
        total_budget: int,
        total_beats: int = 0,
        *,
        converge_threshold: Optional[float] = None,
        land_threshold: Optional[float] = None,
    ):
        """
        Args:
            total_budget: 章节总字数预算
            total_beats: 总节拍数（用于计算剩余节拍）
            converge_threshold: 铺陈→收束切换点（消耗预算占比，0–1）；None 用类默认
            land_threshold: 收束→着陆切换点（消耗预算占比，0–1]）；None 用类默认
        """
        c_def = float(self.CONVERGE_THRESHOLD)
        l_def = float(self.LAND_THRESHOLD)
        ct = float(converge_threshold) if converge_threshold is not None else c_def
        lt = float(land_threshold) if land_threshold is not None else l_def
        if not (0.0 < ct < 1.0 and 0.0 < lt <= 1.0 and ct < lt):
            logger.warning(
                "[章节指挥] 相位阈值无效（%.4f, %.4f），回退内置 %.2f / %.2f",
                ct,
                lt,
                c_def,
                l_def,
            )
            ct, lt = c_def, l_def
        self.converge_threshold = ct
        self.land_threshold = lt
        self.total_budget = total_budget
        self.total_beats = total_beats
        self.used = 0
        self.beats: List[BeatRecord] = []
        self.current_index = 0

    # 爽文引擎: 可压缩的 focus 集合 — 用于收束转嫁
    COMPRESSIBLE_FOCUSES = {"sensory", "dialogue", "emotion", "inner_monologue"}

    @property
    def phase(self) -> ConductorPhase:
        """当前所处的指挥阶段

        爽文引擎增强：
        如果当前最近一个节拍是高能 focus，强制锁定 UNFURL，
        无视 60% 或 85% 的预算消耗比——绝不在打脸高潮处触发收束。
        """
        if self.total_budget <= 0:
            return ConductorPhase.LAND
        ratio = self.used / self.total_budget

        # 爽文引擎: 高能节拍锁定 UNFURL
        if self._is_in_high_energy():
            return ConductorPhase.UNFURL

        if ratio < self.converge_threshold:
            return ConductorPhase.UNFURL
        elif ratio < self.land_threshold:
            return ConductorPhase.CONVERGE
        else:
            return ConductorPhase.LAND

    def get_signal(self, beat_index: int) -> ConductorSignal:
        """获取当前节拍的指挥信号

        Args:
            beat_index: 当前节拍索引（0-based）

        Returns:
            ConductorSignal 对象，包含阶段、指令、字数约束等
        """
        current_phase = self.phase
        remaining_budget = self.total_budget - self.used
        beats_remaining = max(0, self.total_beats - beat_index) if self.total_beats > 0 else self._estimate_remaining_beats()
        is_final_beat = (beat_index == self.total_beats - 1) if self.total_beats > 0 else (beats_remaining <= 1)

        # 选择创作指令
        instruction = {
            ConductorPhase.UNFURL: self._UNFURL_INSTRUCTION,
            ConductorPhase.CONVERGE: self._CONVERGE_INSTRUCTION,
            ConductorPhase.LAND: self._LAND_INSTRUCTION,
        }[current_phase]

        # 最后一个节拍：追加章节收尾提示
        chapter_ending_hint = ""
        if is_final_beat:
            chapter_ending_hint = self._FINAL_BEAT_HINT
            # 最后节拍强制进入着陆
            current_phase = ConductorPhase.LAND
            instruction = self._LAND_INSTRUCTION

        # 建议字数上限（Prompt 中告诉 LLM）
        if beats_remaining > 0:
            suggested_max = remaining_budget // beats_remaining
        else:
            suggested_max = max(self.MIN_BEAT_WORDS, remaining_budget)

        # 不再提供物理硬上限。字数控制只作为提示，正文不做事后切割。
        hard_cap = 0

        return ConductorSignal(
            phase=current_phase,
            budget_used_ratio=self.used / self.total_budget if self.total_budget > 0 else 1.0,
            remaining_budget=remaining_budget,
            beats_remaining=beats_remaining,
            is_final_beat=is_final_beat,
            beat_instruction=instruction,
            chapter_ending_hint=chapter_ending_hint,
            max_words_hint=suggested_max,
            hard_cap=hard_cap,
        )

    def allocate_beat(self, original_target: int, focus: str = "") -> int:
        """分配节拍预算，返回调整后的目标字数

        根据当前阶段和剩余预算动态调整，优先保证连贯性：
        - UNFURL 阶段：保持原始目标甚至略微放宽
        - CONVERGE 阶段：适度压缩（85%），确保情节连贯
          Phase 2: 高能节拍免疫压缩
        - LAND 阶段：谨慎压缩（70%），保证结尾完整性
          Phase 2: 高能节拍免疫压缩

        Args:
            original_target: 原始目标字数
            focus: 节拍 focus 类型（Phase 2: 用于判断是否免疫压缩）

        Returns:
            调整后的目标字数
        """
        remaining_budget = self.total_budget - self.used
        remaining_beats = self._estimate_remaining_beats()
        current_phase = self.phase
        is_high_energy = focus in self.HIGH_ENERGY_FOCUSES
        is_immune = False  # Phase 2: 标记是否触发了免疫

        # 爽文引擎: 收束转嫁 — 可压缩节拍分摊高能节拍超支的缺口
        high_energy_debt = self._calc_debt_from_high_energy()
        if focus in self.COMPRESSIBLE_FOCUSES and high_energy_debt > 0:
            # 将超支缺口平摊到后续所有可压缩节拍
            remaining_compressible = self._estimate_remaining_compressible_beats()
            if remaining_compressible > 0:
                debt_share = high_energy_debt // remaining_compressible
                original_target = max(self.MIN_BEAT_WORDS, original_target - debt_share)
                logger.info(
                    f"[章节指挥] 收束转嫁：可压缩节拍({focus})承担 {debt_share} 字缺口 "
                    f"(总债务={high_energy_debt}, 剩余可压缩节拍={remaining_compressible})"
                )

        if remaining_beats <= 0 or remaining_budget <= 0:
            # 没有剩余预算或节拍，给一个最小值
            adjusted = max(self.MIN_BEAT_WORDS, min(original_target // 3, remaining_budget))
        elif current_phase == ConductorPhase.UNFURL:
            # 铺陈阶段：保持原始目标
            avg_per_beat = remaining_budget // remaining_beats
            if avg_per_beat >= original_target:
                adjusted = original_target  # 预算充足，不压缩
            elif avg_per_beat >= original_target * 0.85:
                adjusted = int(avg_per_beat)  # 轻微调整
            else:
                adjusted = max(self.MIN_BEAT_WORDS, int(original_target * 0.85))
        elif current_phase == ConductorPhase.CONVERGE:
            # Phase 2: 高能节拍免疫压缩
            if is_high_energy:
                adjusted = original_target  # 免疫：不压缩
                is_immune = True
                logger.info(
                    f"[章节指挥] 高能节拍({focus})免疫压缩：保持 {original_target} 字 "
                    f"(CONVERGE 阶段)"
                )
            else:
                # 收束阶段：适度压缩，优先保证连贯性
                avg_per_beat = remaining_budget // remaining_beats
                beat_minimum = max(self.MIN_BEAT_WORDS, original_target // 2)
                adjusted = max(beat_minimum, int(min(original_target * 0.85, avg_per_beat * 1.1)))
        else:
            # Phase 2: 高能节拍免疫压缩（即使是 LAND 阶段）
            if is_high_energy:
                adjusted = max(original_target, int(original_target * 0.9))  # LAND 阶段最多压 10%
                is_immune = True
                logger.info(
                    f"[章节指挥] 高能节拍({focus})免疫压缩：保持 {adjusted} 字 "
                    f"(LAND 阶段，最多压缩10%)"
                )
            else:
                # 着陆阶段：谨慎压缩，保证结尾完整性
                avg_per_beat = remaining_budget // remaining_beats
                beat_minimum = max(self.MIN_BEAT_WORDS, original_target // 2)
                adjusted = max(beat_minimum, int(min(original_target * 0.7, avg_per_beat * 1.05)))

        # 记录
        record = BeatRecord(
            index=self.current_index,
            original_target=original_target,
            adjusted_target=adjusted,
            phase=current_phase,
            focus=focus,
            is_immune=is_immune,  # Phase 2
        )
        self.beats.append(record)

        immune_mark = "免疫" if is_immune else ""
        logger.debug(
            f"[章节指挥] 节拍 {self.current_index + 1}: "
            f"阶段={current_phase.value}, 目标 {original_target} → {adjusted} 字 "
            f"(剩余预算 {remaining_budget} 字){immune_mark}"
        )

        return adjusted

    def report_actual(self, actual_words: int) -> int:
        """报告实际字数

        Args:
            actual_words: 实际生成的字数

        Returns:
            偏差值（正数表示超出，负数表示不足）
        """
        if not self.beats:
            return 0

        record = self.beats[-1]
        record.actual = actual_words
        record.deviation = actual_words - record.adjusted_target

        self.used += actual_words
        self.current_index += 1

        if record.deviation > 0:
            logger.info(
                f"[章节指挥] 节拍 {record.index + 1} 超额 {record.deviation} 字 "
                f"(目标 {record.adjusted_target}，实际 {actual_words})"
            )

        return record.deviation

    def get_adjusted_target(self, original_target: int, focus: str = "") -> int:
        """获取调整后的目标字数（allocate_beat 的别名，兼容旧接口）"""
        return self.allocate_beat(original_target, focus=focus)

    def get_urgency_hint(self) -> Optional[str]:
        """获取紧急约束提示（兼容旧接口）

        Returns:
            紧急约束文本，或 None（如果不需要）
        """
        if not self.beats:
            return None

        current_phase = self.phase
        if current_phase == ConductorPhase.LAND:
            remaining_budget = self.total_budget - self.used
            return (
                f"【着陆指令】：本章即将结束！剩余预算仅 {remaining_budget} 字。"
                f"必须立即收束场景，用一个完整的句子结束本节拍，绝不开启新场景！"
            )
        elif current_phase == ConductorPhase.CONVERGE:
            return (
                f"【收束提示】：本章字数池已消耗较多，当前节拍请适度控制篇幅，"
                f"场景转换加快，对话简洁有力。"
            )

        return None

    def get_status(self) -> dict:
        """获取当前状态"""
        total_deviation = sum(b.deviation for b in self.beats)
        return {
            "total_budget": self.total_budget,
            "used": self.used,
            "remaining": self.total_budget - self.used,
            "phase": self.phase.value,
            "budget_used_ratio": round(self.used / self.total_budget, 2) if self.total_budget > 0 else 1.0,
            "beats_completed": len(self.beats),
            "total_deviation": total_deviation,
            "on_track": abs(total_deviation) < self.total_budget * 0.15,
        }

    def _is_in_high_energy(self) -> bool:
        """爽文引擎: 判断是否正处于高能节拍中

        检查最近一个已完成的节拍是否为高能 focus，
        如果是，则整个当前阶段锁定为 UNFURL。
        """
        if not self.beats:
            return False
        # 检查最后一个节拍的 focus
        last_beat = self.beats[-1]
        return last_beat.focus in self.HIGH_ENERGY_FOCUSES and last_beat.is_immune

    def _calc_debt_from_high_energy(self) -> int:
        """爽文引擎: 计算因高能节拍免疫而超支的字数缺口

        遍历所有已完成的节拍，累计因免疫而超支的字数。
        这些缺口需要从后续可压缩节拍中回收。
        """
        debt = 0
        for b in self.beats:
            if b.is_immune and b.actual > b.adjusted_target:
                debt += (b.actual - b.adjusted_target)
        return debt

    def _estimate_remaining_beats(self) -> int:
        """估算剩余节拍数"""
        if self.total_beats > 0:
            return max(0, self.total_beats - self.current_index)

        if not self.beats:
            return 4  # 默认假设还有 4 个节拍

        avg_target = sum(b.original_target for b in self.beats) / len(self.beats)
        remaining_budget = self.total_budget - self.used

        if avg_target > 0:
            return max(1, int(remaining_budget / avg_target))
        return 2

    def _estimate_remaining_compressible_beats(self) -> int:
        """爽文引擎: 估算剩余可压缩节拍数

        可压缩节拍是 focus 属于 COMPRESSIBLE_FOCUSES 的节拍。
        用于收束转嫁时计算每个可压缩节拍应承担的债务份额。
        """
        if self.total_beats <= 0:
            return 2  # 保守估计
        # 从当前索引往后，假设一半节拍是可压缩的
        remaining = max(0, self.total_beats - self.current_index)
        return max(1, remaining // 2)


# ═══════════════════════════════════════════════════════════════
# 向后兼容：WordCountTracker 是 ChapterConductor 的别名
# ═══════════════════════════════════════════════════════════════

WordCountTracker = ChapterConductor
