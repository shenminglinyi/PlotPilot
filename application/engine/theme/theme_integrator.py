"""Theme/Skill 系统集成器 - 将题材能力注入写作管线

核心设计：
1. SkillOrchestrator: 编排多个 Skill 的调用
2. ThemeAwareContextBuilder: Theme 感知的上下文构建
3. BattleTrigger: 战斗场景检测和增强注入

解决问题：
- BattleChoreographySkill 已实现但从未被调用
- ThemeAgent 未集成到工作流
- 战斗触发关键词太少
"""
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from application.engine.theme.theme_agent import ThemeAgent, ThemeSkill
    from application.engine.services.context_builder import ContextBuilder, Beat

logger = logging.getLogger(__name__)


class SkillOrchestrator:
    """Skill 编排器 - 管理多个 Skill 的生命周期和调用

    负责在写作管线的各个阶段调用所有注册的 Skill，
    收集增强内容并组装到最终结果中。
    """

    def __init__(self, skills: List["ThemeSkill"] = None):
        self._skills: Dict[str, "ThemeSkill"] = {}
        if skills:
            for skill in skills:
                self.register(skill)

    def register(self, skill: "ThemeSkill") -> None:
        """注册 Skill"""
        self._skills[skill.skill_key] = skill
        logger.debug(f"[SkillOrchestrator] 已注册 Skill: {skill.skill_name}")

    def get_skill(self, skill_key: str) -> Optional["ThemeSkill"]:
        """获取 Skill"""
        return self._skills.get(skill_key)

    def invoke_context_build(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        existing_context: str,
    ) -> str:
        """调用所有 Skill 的上下文构建增强

        Returns:
            增强的上下文文本
        """
        parts = []
        for skill in self._skills.values():
            try:
                text = skill.on_context_build(
                    novel_id, chapter_number, outline, existing_context
                )
                if text and text.strip():
                    parts.append(f"【{skill.skill_name}】\n{text}")
            except Exception as e:
                logger.warning(
                    f"[SkillOrchestrator] Skill {skill.skill_key} 上下文增强失败: {e}"
                )
        return "\n\n".join(parts) if parts else ""

    def invoke_beat_enhance(
        self,
        beat_description: str,
        beat_focus: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        """调用所有 Skill 的节拍增强

        Returns:
            增强的节拍提示
        """
        parts = []
        for skill in self._skills.values():
            try:
                text = skill.on_beat_enhance(
                    beat_description, beat_focus, chapter_number, outline
                )
                if text and text.strip():
                    parts.append(text)
            except Exception as e:
                logger.debug(
                    f"[SkillOrchestrator] Skill {skill.skill_key} 节拍增强失败: {e}"
                )
        return "\n".join(parts) if parts else ""

    def invoke_prompt_build(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        """调用所有 Skill 的提示词构建增强

        Returns:
            增强的提示词文本
        """
        parts = []
        for skill in self._skills.values():
            try:
                if hasattr(skill, "on_prompt_build"):
                    text = skill.on_prompt_build(novel_id, chapter_number, outline)
                    if text and text.strip():
                        parts.append(text)
            except Exception as e:
                logger.debug(
                    f"[SkillOrchestrator] Skill {skill.skill_key} 提示词增强失败: {e}"
                )
        return "\n".join(parts) if parts else ""

    def invoke_audit_enhance(
        self,
        chapter_number: int,
        chapter_content: str,
        outline: str,
    ) -> List[str]:
        """调用所有 Skill 的审计增强

        Returns:
            审计检查项列表
        """
        checks = []
        for skill in self._skills.values():
            try:
                items = skill.on_audit_enhance(chapter_number, chapter_content, outline)
                if items:
                    checks.extend(items)
            except Exception as e:
                logger.debug(
                    f"[SkillOrchestrator] Skill {skill.skill_key} 审计增强失败: {e}"
                )
        return checks


class BattleTrigger:
    """战斗触发器 - 检测并注入战斗增强

    扩展战斗触发关键词，解决"没有打斗场面"的问题。
    """

    # 扩展的战斗触发关键词（覆盖常见战斗场景）
    BATTLE_KEYWORDS = [
        # 直接战斗词
        "战斗", "对决", "交锋", "过招", "比武", "擂台", "决斗",
        "厮杀", "激战", "搏斗", "火拼", "对峙", "混战", "乱战",
        # 动作词
        "攻击", "防守", "反击", "突袭", "围攻", "强攻", "猛攻",
        "杀", "斩", "刺", "砍", "劈", "轰", "打", "击",
        # 武器/招式词
        "招式", "功法", "武技", "必杀技", "绝招", "秘技",
        "剑法", "刀法", "拳法", "掌法", "腿法",
        # 修炼词
        "修为压制", "境界碾压", "以弱胜强", "逆袭", "越级挑战",
        # 情绪/状态词
        "爆发", "觉醒", "突破", "拼命", "绝境", "生死",
        "怒", "愤", "杀气", "战意",
        # 结果词
        "胜负", "输赢", "败", "胜", "死战", "不死不休",
    ]

    # 冲突升级关键词（情绪推到高潮，需要接战斗）
    CONFLICT_ESCALATION_KEYWORDS = [
        "冲突升级", "矛盾激化", "剑拔弩张", "一触即发",
        "针锋相对", "势不两立", "水火不容", "仇恨",
        "报仇", "复仇", "雪恨", "清算", "算账",
        "忍无可忍", "不再退让", "最后通牒",
    ]

    @classmethod
    def detect_battle_scene(cls, outline: str, beat_description: str = "") -> bool:
        """检测是否为战斗场景

        Args:
            outline: 章节大纲
            beat_description: 节拍描述

        Returns:
            True 表示检测到战斗场景
        """
        combined = f"{outline} {beat_description}".lower()
        return any(kw in combined for kw in cls.BATTLE_KEYWORDS)

    @classmethod
    def detect_conflict_escalation(cls, outline: str, beat_description: str = "") -> bool:
        """检测是否为冲突升级场景（需要接战斗）

        Args:
            outline: 章节大纲
            beat_description: 节拍描述

        Returns:
            True 表示检测到冲突升级
        """
        combined = f"{outline} {beat_description}".lower()
        return any(kw in combined for kw in cls.CONFLICT_ESCALATION_KEYWORDS)

    @classmethod
    def get_battle_enhancement_prompt(cls, beat_focus: str = "") -> str:
        """获取战斗增强提示词

        Args:
            beat_focus: 节拍聚焦点

        Returns:
            战斗增强提示文本
        """
        return """【战斗场景增强指导】
1. 动作分解：将一个回合拆成「起手→出招→碰撞→结果」四拍
2. 感官层次：视觉（招式形态/光影效果）+ 听觉（破空声/撞击声）+ 触觉（力量反馈/震动）
3. 节奏控制：快慢交替——密集对攻后穿插喘息/对话/心理活动
4. 避免流水账：不要逐招列举，抓住2-3个关键招式重点描写
5. 旁观者视角：穿插围观者的反应来侧面烘托战斗激烈程度
6. 环境互动：招式对周围环境的影响（地面崩裂/空气震动/物品损坏）
7. 心理博弈：战斗中的思考、判断、试探、虚招"""

    @classmethod
    def should_inject_battle_skill(
        cls,
        outline: str,
        beat_description: str = "",
        beat_focus: str = "",
    ) -> bool:
        """判断是否需要注入战斗 Skill

        条件：
        1. 直接检测到战斗关键词
        2. 或检测到冲突升级 + beat_focus 是 action/emotion
        """
        if cls.detect_battle_scene(outline, beat_description):
            return True

        # 冲突升级场景，如果聚焦点是动作或情绪，则注入战斗
        if cls.detect_conflict_escalation(outline, beat_description):
            if beat_focus in ("action", "emotion", "suspense"):
                return True

        return False


class ThemeAwarePromptBuilder:
    """Theme 感知的提示词构建器

    将 ThemeAgent 的能力注入到提示词构建过程中。
    """

    def __init__(self, theme_agent: Optional["ThemeAgent"] = None):
        self._theme_agent = theme_agent
        self._orchestrator: Optional[SkillOrchestrator] = None

        if theme_agent:
            self._orchestrator = SkillOrchestrator(theme_agent.get_skills())

    def set_theme_agent(self, agent: "ThemeAgent") -> None:
        """设置 Theme Agent"""
        self._theme_agent = agent
        self._orchestrator = SkillOrchestrator(agent.get_skills())

    def build_system_persona(self, genre: str = None) -> str:
        """构建系统人设

        Args:
            genre: 题材类型

        Returns:
            系统人设文本
        """
        if not self._theme_agent:
            return ""

        try:
            persona = self._theme_agent.get_effective_system_persona()
            if persona and persona.strip():
                return f"\n【作家风格】\n{persona}\n"
        except Exception as e:
            logger.debug(f"[ThemeIntegrator] 获取系统人设失败: {e}")

        return ""

    def build_writing_rules(self, genre: str = None) -> str:
        """构建写作规则

        Args:
            genre: 题材类型

        Returns:
            写作规则文本
        """
        if not self._theme_agent:
            return ""

        try:
            rules = self._theme_agent.get_effective_writing_rules()
            if rules:
                rules_text = "\n".join(f"- {r}" for r in rules)
                if rules_text.strip():
                    return f"\n【题材专项规则】\n{rules_text}\n"
        except Exception as e:
            logger.debug(f"[ThemeIntegrator] 获取写作规则失败: {e}")

        return ""

    def build_beat_enhancement(
        self,
        beat_description: str,
        beat_focus: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        """构建节拍增强提示

        Args:
            beat_description: 节拍描述
            beat_focus: 节拍聚焦点
            chapter_number: 章节号
            outline: 章节大纲

        Returns:
            增强提示文本
        """
        parts = []

        # 1. 检测是否需要战斗增强
        if BattleTrigger.should_inject_battle_skill(outline, beat_description, beat_focus):
            parts.append(BattleTrigger.get_battle_enhancement_prompt(beat_focus))

        # 2. 调用 Skill 编排器
        if self._orchestrator:
            skill_enhance = self._orchestrator.invoke_beat_enhance(
                beat_description, beat_focus, chapter_number, outline
            )
            if skill_enhance:
                parts.append(skill_enhance)

        return "\n\n".join(parts) if parts else ""

    def build_format_rules(self) -> str:
        """构建格式规则（分段、对话等）

        Returns:
            格式规则文本
        """
        return """【分段与格式要求（必须遵守）】
1. 句号结束必须另起一行（每段最多5句，保持段落简洁）
2. 对话双引号内通常只有一个句号，简短有力
3. 场景转换时空一行分隔
4. 对话和叙述自然交错，避免大段对话或大段叙述
5. 适配手机阅读：段落不宜过长，留白适当
6. 重要对话独立成段，增强画面感"""


class ThemeIntegrator:
    """Theme 集成器 - 统一管理 Theme 相关的集成逻辑

    使用方式：
        integrator = ThemeIntegrator()
        integrator.initialize(genre="xuanhuan")

        # 构建提示词时
        system_persona = integrator.build_system_persona()
        writing_rules = integrator.build_writing_rules()
        beat_enhance = integrator.build_beat_enhancement(...)
    """

    def __init__(self):
        self._theme_agent: Optional["ThemeAgent"] = None
        self._prompt_builder: ThemeAwarePromptBuilder = ThemeAwarePromptBuilder()
        self._initialized = False

    def initialize(self, genre: str = None) -> bool:
        """初始化 Theme Agent

        Args:
            genre: 题材类型

        Returns:
            True 表示初始化成功
        """
        if self._initialized:
            return True

        try:
            from application.engine.theme.theme_registry import ThemeAgentRegistry

            registry = ThemeAgentRegistry()
            registry.auto_discover()

            self._theme_agent = registry.get_or_default(genre)
            if self._theme_agent:
                self._prompt_builder.set_theme_agent(self._theme_agent)
                logger.info(
                    f"[ThemeIntegrator] 已初始化 Theme Agent: "
                    f"{self._theme_agent.__class__.__name__}"
                )

            self._initialized = True
            return True

        except Exception as e:
            logger.warning(f"[ThemeIntegrator] 初始化失败: {e}")
            return False

    def get_theme_agent(self) -> Optional["ThemeAgent"]:
        """获取 Theme Agent"""
        return self._theme_agent

    def get_prompt_builder(self) -> ThemeAwarePromptBuilder:
        """获取提示词构建器"""
        return self._prompt_builder

    def build_system_persona(self) -> str:
        """构建系统人设"""
        return self._prompt_builder.build_system_persona()

    def build_writing_rules(self) -> str:
        """构建写作规则"""
        return self._prompt_builder.build_writing_rules()

    def build_beat_enhancement(
        self,
        beat_description: str,
        beat_focus: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        """构建节拍增强"""
        return self._prompt_builder.build_beat_enhancement(
            beat_description, beat_focus, chapter_number, outline
        )

    def build_format_rules(self) -> str:
        """构建格式规则"""
        return self._prompt_builder.build_format_rules()

    def get_beat_templates(self, chapter_number: int, outline: str) -> List[Dict]:
        """获取节拍模板

        Args:
            chapter_number: 章节号
            outline: 章节大纲

        Returns:
            节拍模板列表
        """
        if not self._theme_agent:
            return []

        try:
            templates = self._theme_agent.get_beat_templates(chapter_number, outline)
            if templates:
                # 转换为字典列表
                return [
                    {
                        "description": t.description,
                        "target_words": t.target_words,
                        "focus": t.focus,
                        "expansion_hints": t.expansion_hints or [],
                    }
                    for t in templates.beats
                ]
        except Exception as e:
            logger.debug(f"[ThemeIntegrator] 获取节拍模板失败: {e}")

        return []


# 全局 Theme 集成器实例
_theme_integrator: Optional[ThemeIntegrator] = None


def get_theme_integrator() -> ThemeIntegrator:
    """获取全局 Theme 集成器"""
    global _theme_integrator
    if _theme_integrator is None:
        _theme_integrator = ThemeIntegrator()
    return _theme_integrator


def initialize_theme(genre: str = None) -> ThemeIntegrator:
    """初始化全局 Theme 集成器

    Args:
        genre: 题材类型

    Returns:
        ThemeIntegrator 实例
    """
    integrator = get_theme_integrator()
    integrator.initialize(genre)
    return integrator
