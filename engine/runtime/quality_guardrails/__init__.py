"""质量守门人系统 — 六维度质量检查

维度：
1. language_style — 语言风格（八股文/数字比喻/过度理性/拐弯描写）
2. character_consistency — 角色一致性（OOC检测/语言指纹/创伤反应）
3. plot_density — 情节密度（形容词功能性/段落目标推进/信息密度）
4. naming — 命名规范（俗套姓氏/时代适配/复姓推荐）
5. viewpoint — 视角控制（信息差/弱势方/核心当事人）
6. rhythm — 叙事节奏（打斗简洁/揭秘对话/大事件精准）
"""
from engine.runtime.quality_guardrails.language_style_guardrail import LanguageStyleGuardrail
from engine.runtime.quality_guardrails.character_consistency_guardrail import CharacterConsistencyGuardrail
from engine.runtime.quality_guardrails.plot_density_guardrail import PlotDensityGuardrail
from engine.runtime.quality_guardrails.naming_guardrail import NamingGuardrail
from engine.runtime.quality_guardrails.viewpoint_guardrail import ViewpointGuardrail
from engine.runtime.quality_guardrails.rhythm_guardrail import RhythmGuardrail
from engine.runtime.quality_guardrails.quality_guardrail import QualityGuardrail, QualityViolationError

__all__ = [
    "LanguageStyleGuardrail",
    "CharacterConsistencyGuardrail",
    "PlotDensityGuardrail",
    "NamingGuardrail",
    "ViewpointGuardrail",
    "RhythmGuardrail",
    "QualityGuardrail",
    "QualityViolationError",
]
