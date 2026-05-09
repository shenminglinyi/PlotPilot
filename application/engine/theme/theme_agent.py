"""ThemeAgent 抽象接口 — 专项题材写作能力的统一契约

每个题材 Agent 实现此接口，向写作管线注入题材专项知识：
1. 人设/角色设定指导（system persona）
2. 题材专项写作规则（writing rules）
3. 世界观/氛围约束上下文（context directives）
4. 题材专项节拍模板（beat templates）
5. 缓冲章模板（buffer chapter template）
6. 题材专项审计规则（audit criteria）
7. Skills 增强插槽（可选的能力扩展点）

使用方式：
    通过 ThemeAgentRegistry 注册，管线根据 Novel 的 genre 字段自动加载对应 Agent。

设计原则：
    - 所有方法返回纯文本/数据结构，不依赖 LLM 调用
    - 每个方法都有合理的默认空值，题材 Agent 按需覆盖
    - 接口面向「注入」而非「替换」— 输出会附加到现有管线上下文中
    - Skills 为可选增强，每个 Skill 独立实现、可跨题材复用
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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


class ThemeSkill(ABC):
    """题材增强技能插槽 — 可选的能力扩展点

    每个 Skill 是一个独立的增强模块，可以被多个题材 Agent 共享。
    Skill 在管线的特定阶段被调用，为写作过程注入额外的能力。

    设计原则：
        - 一个 Skill 只做一件事（单一职责）
        - Skill 之间互相独立，不依赖其他 Skill
        - 输入输出均为纯文本/数据结构
        - 所有 Skill 方法都有安全的默认空值

    生命周期：
        1. Agent 在 __init__ 或 get_skills() 中声明所用的 Skills
        2. 管线在对应阶段查找并调用匹配的 Skills
        3. Skill 输出追加到该阶段的上下文/指令中

    Example:
        class CultivationSystemSkill(ThemeSkill):
            skill_key = "cultivation_system"
            skill_name = "修炼体系生成器"

            def on_context_build(self, ...):
                return "【修炼境界参考】\\n练气 → 筑基 → 金丹 → ..."

            def on_beat_enhance(self, ...):
                return "确保突破场景描写包含: 灵气涌动、经脉拓宽、丹田变化"
    """

    @property
    @abstractmethod
    def skill_key(self) -> str:
        """技能唯一标识（如 'cultivation_system', 'battle_choreography'）"""
        ...

    @property
    @abstractmethod
    def skill_name(self) -> str:
        """技能显示名称（如 '修炼体系生成器', '战斗编排器'）"""
        ...

    @property
    def skill_description(self) -> str:
        """技能描述（可选）"""
        return ""

    @property
    def compatible_genres(self) -> List[str]:
        """声明此 Skill 适用的题材 genre_key 列表

        返回空列表表示适用于所有题材（通用 Skill）。
        子类覆盖此属性来声明适用范围。

        Returns:
            genre_key 列表，如 ["xuanhuan", "xianxia"]
        """
        return []

    # ─── 管线注入点 ───

    def on_context_build(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        existing_context: str,
    ) -> str:
        """上下文构建阶段增强

        在 ContextBudgetAllocator 收集完所有槽位后调用。
        返回的文本会追加到题材上下文指令之后。

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            outline: 当前章节大纲
            existing_context: 已构建的上下文文本（只读参考）

        Returns:
            增强文本，空字符串则不追加
        """
        return ""

    def on_beat_enhance(
        self,
        beat_description: str,
        beat_focus: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        """节拍增强阶段

        在每个节拍的 prompt 构建时调用。
        返回的文本会追加到该节拍的指令中。

        Args:
            beat_description: 节拍描述
            beat_focus: 节拍焦点类型
            chapter_number: 章节号
            outline: 章节大纲

        Returns:
            增强指令文本，空字符串则不追加
        """
        return ""

    def on_audit_enhance(
        self,
        chapter_number: int,
        chapter_content: str,
        outline: str,
    ) -> List[str]:
        """审计阶段增强

        在章后审计时调用，返回额外的审计检查项。

        Args:
            chapter_number: 章节号
            chapter_content: 章节正文
            outline: 章节大纲

        Returns:
            额外的审计检查项列表，空列表则不追加
        """
        return []

    def on_prompt_build(
        self,
        phase: str,
        current_prompt: str,
        **kwargs: Any,
    ) -> str:
        """通用 prompt 构建增强（万能插槽）

        在各个 prompt 构建的末尾调用，提供最大灵活性。
        phase 标识当前是哪个阶段的 prompt。

        Args:
            phase: 阶段标识，可选值:
                   'system' — 系统消息构建
                   'writing' — 写作 prompt
                   'auditing' — 审计 prompt
                   'planning' — 规划 prompt
            current_prompt: 当前已构建的 prompt（只读参考）
            **kwargs: 阶段特定的额外参数

        Returns:
            增强文本，空字符串则不追加
        """
        return ""

    def __repr__(self) -> str:
        return f"<ThemeSkill:{self.skill_key}({self.skill_name})>"


class ThemeAgent(ABC):
    """专项题材 Agent 抽象接口

    所有题材 Agent 必须实现此接口。管线在以下节点调用对应方法：

    1. _build_prompt()    → get_system_persona() + get_writing_rules()
    2. _collect_all_slots()→ get_context_directives()
    3. magnify_outline_to_beats() → get_beat_templates()
    4. _handle_writing() buffer → get_buffer_chapter_template()

    CPMS 改造：所有方法优先从 PromptRegistry 获取（广场可编辑），
    子类的硬编码返回值作为回退。

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

    # ─── CPMS 数据驱动支持 ───

    def _get_from_registry(self, method: str, fallback: str = "") -> str:
        """从 PromptRegistry 获取题材提示词（CPMS 数据驱动）。

        命名规则：theme-{genre_key}-{method}
        如：theme-romance-system_persona

        Args:
            method: 方法名（如 "system_persona", "writing_rules"）
            fallback: 回退文本

        Returns:
            从 Registry 获取的文本，或回退值
        """
        try:
            from infrastructure.ai.prompt_registry import get_prompt_registry
            registry = get_prompt_registry()
            node_key = f"theme-{self.genre_key}-{method}"
            system = registry.get_system(node_key)
            if system:
                return system
            # 也尝试 user_template
            user = registry.get_user_template(node_key)
            if user:
                return user
        except Exception:
            pass
        return fallback

    # ─── 1. 人设注入（_build_prompt 系统消息开头） ───

    def get_system_persona(self) -> str:
        """题材专项人设

        替换默认的「你是一位专业的网络小说作家」，
        注入题材专项的写作身份和核心写作理念。

        CPMS: 优先从 PromptRegistry 获取（广场可编辑），
        子类硬编码返回值作为回退。

        Returns:
            人设描述文本。返回空字符串则使用默认人设。
        """
        return ""

    def get_effective_system_persona(self) -> str:
        """获取生效的人设文本（CPMS 统一入口）。

        优先级：PromptRegistry > 子类硬编码 > 默认空值
        """
        hardcoded = self.get_system_persona()
        return self._get_from_registry("system_persona", fallback=hardcoded)

    # ─── 2. 写作规则注入（_build_prompt 写作要求部分） ───

    def get_writing_rules(self) -> List[str]:
        """题材专项写作规则

        追加到默认 8 条写作规则之后。每条规则为一个字符串，
        会自动编号（从 9 开始，或紧跟现有规则）。

        CPMS: 优先从 PromptRegistry 获取（支持换行分隔的多条规则），
        子类硬编码返回值作为回退。

        Returns:
            规则列表。空列表则不追加。
        """
        return []

    def get_effective_writing_rules(self) -> List[str]:
        """获取生效的写作规则列表（CPMS 统一入口）。"""
        registry_text = self._get_from_registry("writing_rules")
        if registry_text:
            # 从文本解析规则列表（按换行分隔，过滤空行）
            rules = [line.strip() for line in registry_text.split("\n") if line.strip()]
            if rules:
                return rules
        return self.get_writing_rules()

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

    def get_effective_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        """获取生效的上下文指令（CPMS 统一入口）。

        优先从 PromptRegistry 获取各维度文本，
        子类硬编码返回值作为回退。
        """
        base = self.get_context_directives(novel_id, chapter_number, outline)

        # 逐维度尝试从 Registry 获取
        for field_name in ["world_rules", "atmosphere", "taboos",
                           "tropes_to_use", "tropes_to_avoid"]:
            registry_text = self._get_from_registry(f"ctx_{field_name}")
            if registry_text:
                setattr(base, field_name, registry_text)

        return base

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

    # ─── 8. Skills 增强插槽 ───

    def get_skills(self) -> List[ThemeSkill]:
        """返回该题材 Agent 挂载的增强技能列表

        子类覆盖此方法来声明所使用的 Skills。
        管线会在对应阶段自动调用每个 Skill 的注入方法。

        Returns:
            ThemeSkill 实例列表。空列表表示不使用任何增强技能。

        Example:
            def get_skills(self):
                return [
                    CultivationSystemSkill(),
                    BattleChoreographySkill(),
                ]
        """
        return []

    def get_skill(self, skill_key: str) -> Optional[ThemeSkill]:
        """按 key 查找已挂载的 Skill

        Args:
            skill_key: 技能标识

        Returns:
            对应的 ThemeSkill 实例，未找到则返回 None
        """
        for skill in self.get_skills():
            if skill.skill_key == skill_key:
                return skill
        return None

    def invoke_skills_context(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        existing_context: str,
    ) -> str:
        """批量调用所有 Skill 的上下文增强

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            outline: 章节大纲
            existing_context: 已有上下文

        Returns:
            所有 Skill 的上下文增强文本拼接结果
        """
        parts = []
        for skill in self.get_skills():
            try:
                text = skill.on_context_build(
                    novel_id, chapter_number, outline, existing_context
                )
                if text:
                    parts.append(f"【{skill.skill_name}】\n{text}")
            except Exception:
                pass  # Skill 失败不影响主流程
        return "\n\n".join(parts) if parts else ""

    def invoke_skills_beat(
        self,
        beat_description: str,
        beat_focus: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        """批量调用所有 Skill 的节拍增强

        Returns:
            所有 Skill 的节拍增强文本拼接结果
        """
        parts = []
        for skill in self.get_skills():
            try:
                text = skill.on_beat_enhance(
                    beat_description, beat_focus, chapter_number, outline
                )
                if text:
                    parts.append(text)
            except Exception:
                pass
        return "\n".join(parts) if parts else ""

    def invoke_skills_audit(
        self,
        chapter_number: int,
        chapter_content: str,
        outline: str,
    ) -> List[str]:
        """批量调用所有 Skill 的审计增强

        Returns:
            所有 Skill 的额外审计检查项合并列表
        """
        checks: List[str] = []
        for skill in self.get_skills():
            try:
                items = skill.on_audit_enhance(
                    chapter_number, chapter_content, outline
                )
                checks.extend(items)
            except Exception:
                pass
        return checks

    def invoke_skills_prompt(
        self,
        phase: str,
        current_prompt: str,
        **kwargs: Any,
    ) -> str:
        """批量调用所有 Skill 的通用 prompt 增强

        Returns:
            所有 Skill 的 prompt 增强文本拼接结果
        """
        parts = []
        for skill in self.get_skills():
            try:
                text = skill.on_prompt_build(phase, current_prompt, **kwargs)
                if text:
                    parts.append(text)
            except Exception:
                pass
        return "\n".join(parts) if parts else ""

    # ─── 工具方法 ───

    def __repr__(self) -> str:
        return f"<ThemeAgent:{self.genre_key}({self.genre_name})>"
