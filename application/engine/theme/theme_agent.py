"""ThemeAgent 抽象接口 — 专项题材写作能力的统一契约

每个题材 Agent 实现此接口，向写作管线注入题材专项知识：
1. 人设/角色设定指导（system persona）
2. 题材专项写作规则（writing rules）
3. 世界观/氛围约束上下文（context directives）
4. 题材专项节拍模板（beat templates）
5. 缓冲章模板（buffer chapter template）
6. 题材专项审计规则（audit criteria）

使用方式：
    通过 ThemeAgentRegistry 注册，管线根据 Novel 的 genre 字段自动加载对应 Agent。

设计原则：
    - 所有方法返回纯文本/数据结构，不依赖 LLM 调用
    - 每个方法都有合理的默认空值，题材 Agent 按需覆盖
    - 接口面向「注入」而非「替换」— 输出会附加到现有管线上下文中
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BeatTemplate:
    """题材专项节拍模板

    对应 context_builder.py 中的 Beat 数据结构，
    但作为题材 Agent 的输出，包含额外的匹配规则。

    Attributes:
        keywords: 触发此模板的大纲关键词列表（任一命中即匹配）
        beats: 节拍定义列表，每个元素为 (description, target_words, focus)
        priority: 优先级（高优先级的模板先匹配），默认 50
    """
    keywords: List[str]
    beats: List[tuple]  # [(description, target_words, focus), ...]
    priority: int = 50


@dataclass
class ThemeDirectives:
    """题材上下文指令 — 注入到 ContextBudgetAllocator 的 T0 槽位

    Attributes:
        world_rules: 世界观规则（如「修仙体系分九境」）
        atmosphere: 氛围描写指令（如「保持压抑悬疑的基调」）
        taboos: 禁忌清单（如「不要出现科技元素」）
        tropes_to_use: 推荐使用的叙事套路
        tropes_to_avoid: 应避免的叙事套路
    """
    world_rules: str = ""
    atmosphere: str = ""
    taboos: str = ""
    tropes_to_use: str = ""
    tropes_to_avoid: str = ""

    def to_context_text(self) -> str:
        """格式化为可注入上下文的文本块"""
        parts = []
        if self.world_rules:
            parts.append(f"【世界观规则】\n{self.world_rules}")
        if self.atmosphere:
            parts.append(f"【氛围基调】\n{self.atmosphere}")
        if self.taboos:
            parts.append(f"【题材禁忌】\n{self.taboos}")
        if self.tropes_to_use:
            parts.append(f"【推荐叙事手法】\n{self.tropes_to_use}")
        if self.tropes_to_avoid:
            parts.append(f"【应避免的套路】\n{self.tropes_to_avoid}")
        return "\n\n".join(parts) if parts else ""


@dataclass
class ThemeAuditCriteria:
    """题材专项审计标准 — 用于章后审计阶段

    Attributes:
        required_elements: 本章必须包含的元素描述
        quality_checks: 质量检查项列表
        tension_guidance: 张力评分的题材修正说明
    """
    required_elements: List[str] = field(default_factory=list)
    quality_checks: List[str] = field(default_factory=list)
    tension_guidance: str = ""


class ThemeAgent(ABC):
    """专项题材 Agent 抽象接口

    所有题材 Agent 必须实现此接口。管线在以下节点调用对应方法：

    1. _build_prompt()    → get_system_persona() + get_writing_rules()
    2. _collect_all_slots()→ get_context_directives()
    3. magnify_outline_to_beats() → get_beat_templates()
    4. _handle_writing() buffer → get_buffer_chapter_template()

    实现者只需覆盖想要定制的方法，其余使用基类默认值。
    """

    @property
    @abstractmethod
    def genre_key(self) -> str:
        """题材唯一标识（如 'xuanhuan', 'suspense', 'romance'）

        此 key 将用于 ThemeAgentRegistry 的查找，
        与 Novel.genre 字段对应。
        """
        ...

    @property
    @abstractmethod
    def genre_name(self) -> str:
        """题材显示名称（如 '玄幻', '悬疑', '言情'）"""
        ...

    @property
    def description(self) -> str:
        """题材描述（可选）"""
        return ""

    # ─── 1. 人设注入（_build_prompt 系统消息开头） ───

    def get_system_persona(self) -> str:
        """题材专项人设

        替换默认的「你是一位专业的网络小说作家」，
        注入题材专项的写作身份和核心写作理念。

        Returns:
            人设描述文本。返回空字符串则使用默认人设。

        Example:
            "你是一位精通东方仙侠体系的玄幻小说大师，擅长..."
        """
        return ""

    # ─── 2. 写作规则注入（_build_prompt 写作要求部分） ───

    def get_writing_rules(self) -> List[str]:
        """题材专项写作规则

        追加到默认 8 条写作规则之后。每条规则为一个字符串，
        会自动编号（从 9 开始，或紧跟现有规则）。

        Returns:
            规则列表。空列表则不追加。

        Example:
            [
                "战斗场景必须有具体的招式/功法描写，不能只写'一拳打去'",
                "修炼突破时必须描写身体变化和境界感悟",
            ]
        """
        return []

    # ─── 3. 上下文指令注入（_collect_all_slots T0 槽位） ───

    def get_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        """题材上下文指令

        根据当前章节信息，返回题材专项的上下文约束。
        输出会注入到 ContextBudgetAllocator 的 T0 槽位。

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            outline: 当前章节大纲

        Returns:
            ThemeDirectives 对象
        """
        return ThemeDirectives()

    # ─── 4. 节拍模板注入（magnify_outline_to_beats） ───

    def get_beat_templates(self) -> List[BeatTemplate]:
        """题材专项节拍模板

        返回一组基于关键词匹配的节拍模板。
        管线会按 priority 降序尝试匹配，命中后覆盖默认模板。

        Returns:
            BeatTemplate 列表。空列表则使用默认节拍。

        Note:
            每个 BeatTemplate 的 beats 元素格式为:
            (description: str, target_words: int, focus: str)
            focus 可用值: sensory, dialogue, action, emotion, hook,
                         character_intro, suspense + 题材自定义值
        """
        return []

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        """题材自定义聚焦点说明

        为题材特有的 beat focus 类型提供描述指令，
        会合并到 build_beat_prompt() 的 focus_instructions 字典中。

        Returns:
            {focus_key: instruction_text} 字典

        Example:
            {
                "cultivation": "描写修炼突破：灵气涌入、经脉打通、境界提升的具体感受...",
                "power_reveal": "展现实力揭露：以弱胜强的反转、旁观者的震惊反应...",
            }
        """
        return {}

    # ─── 5. 缓冲章模板（_handle_writing 缓冲章） ───

    def get_buffer_chapter_template(self, outline: str) -> str:
        """题材专项缓冲章模板

        当上章张力 ≥ 8 时自动触发缓冲章。此方法返回
        缓冲章的大纲修饰前缀，替换默认的「日常过渡」模板。

        Args:
            outline: 原始章节大纲

        Returns:
            修饰后的缓冲章大纲。返回空字符串则使用默认模板。

        Example:
            "【缓冲章：战后疗伤悟道】{outline}。主角闭关恢复，感悟战斗中的招式，境界有所松动。"
        """
        return ""

    # ─── 6. 审计标准（_handle_auditing 章后审计） ───

    def get_audit_criteria(
        self,
        chapter_number: int,
        outline: str,
    ) -> ThemeAuditCriteria:
        """题材专项审计标准（预留接口）

        为章后审计阶段提供题材专项的质量检查标准。
        当前版本为预留接口，后续可接入 ChapterAftermathPipeline。

        Args:
            chapter_number: 章节号
            outline: 章节大纲

        Returns:
            ThemeAuditCriteria 对象
        """
        return ThemeAuditCriteria()

    # ─── 7. 开篇黄金法则定制（前 3 章特殊节拍） ───

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        """题材专项开篇节拍（前 3 章）

        覆盖 magnify_outline_to_beats() 中对第 1/2/3 章的硬编码模板。
        返回 None 表示使用默认模板。

        Args:
            chapter_number: 章节号（1, 2, 或 3）

        Returns:
            节拍列表 [(description, target_words, focus), ...] 或 None

        Example (玄幻第 1 章):
            [
                ("开篇：废柴觉醒 / 意外获得传承...", 500, "hook"),
                ("展现修炼体系基础设定...", 1000, "character_intro"),
                ...
            ]
        """
        return None

    # ─── 工具方法 ───

    def __repr__(self) -> str:
        return f"<ThemeAgent:{self.genre_key}({self.genre_name})>"
