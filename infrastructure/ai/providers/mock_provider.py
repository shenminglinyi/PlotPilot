"""Neutral mock LLM provider used when no runtime API key is configured.

The provider is intentionally schema-oriented: it returns valid, minimal JSON for
known generation intents, but it must not invent a reusable plot, genre, or fixed
story trope. This keeps no-key/local-dev paths from polluting production data with
hidden fallback narratives.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Callable, Dict

from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage


JsonObject = Dict[str, Any]


class MockResponseFactory:
    """Build contract-shaped, genre-neutral mock responses.

    The factory deliberately describes structure rather than story content. If a
    caller needs real creative material, it must use a configured LLM provider.
    """

    def build(self, prompt: Prompt) -> str:
        intent = self._detect_intent(prompt)
        builders: Dict[str, Callable[[], str]] = {
            "macro_plan": self._macro_plan,
            "worldbuilding": self._worldbuilding,
            "characters": self._characters,
            "locations": self._locations,
            "main_plot_options": self._main_plot_options,
            "chapter_review": self._chapter_review,
            "style": self._style,
        }
        return builders.get(intent, self._default)()

    def _detect_intent(self, prompt: Prompt) -> str:
        text = f"{prompt.system}\n{prompt.user}".lower()

        if "setup_main_plot_options_v1" in text or "plot_options" in text or "主线候选" in text:
            return "main_plot_options"
        if "宏观结构" in text or "结构框架" in text or "部-卷-幕" in text or '"parts"' in text:
            return "macro_plan"
        if "worldbuilding" in text or "世界观" in text or "核心法则" in text:
            return "worldbuilding"
        if "characters" in text or "人物" in text or "角色" in text:
            return "characters"
        if "locations" in text or "地点" in text or "地图" in text:
            return "locations"
        if "章节 ai 审阅" in text or "严格但务实的小说责任编辑" in text or '"score"' in text and '"issues"' in text:
            return "chapter_review"
        if "文风公约" in text or "style convention" in text or "style" in text:
            return "style"
        return "default"

    def _json(self, payload: JsonObject) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _macro_plan(self) -> str:
        return self._json(
            {
                "parts": [
                    {
                        "number": 1,
                        "title": "第一部：目标建立",
                        "description": "围绕用户设定建立核心目标、主要阻力与阶段性代价。",
                        "suggested_chapter_count": 3,
                        "themes": ["目标", "阻力", "选择"],
                        "volumes": [
                            {
                                "number": 1,
                                "title": "第一卷：起始压力",
                                "description": "让关键人物在明确压力下做出第一轮选择。",
                                "suggested_chapter_count": 3,
                                "acts": [
                                    {
                                        "number": 1,
                                        "title": "第一幕：问题出现",
                                        "description": "呈现用户设定中的核心问题与即时后果。",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["核心问题显性化", "人物目标被迫明确"],
                                        "narrative_arc": "从稳定状态进入需要行动的局面。",
                                        "conflicts": ["个人目标与外部压力"],
                                        "plot_points": ["建立起点", "触发选择"],
                                        "key_characters": [],
                                        "key_locations": [],
                                    },
                                    {
                                        "number": 2,
                                        "title": "第二幕：代价确认",
                                        "description": "通过一次受阻确认目标并非轻易可得。",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["第一次尝试受阻", "代价被具体化"],
                                        "narrative_arc": "行动带来代价，人物开始调整策略。",
                                        "conflicts": ["短期收益与长期风险"],
                                        "plot_points": ["尝试", "受阻"],
                                        "key_characters": [],
                                        "key_locations": [],
                                    },
                                    {
                                        "number": 3,
                                        "title": "第三幕：方向锁定",
                                        "description": "用一个不可逆选择锁定后续推进方向。",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["关键选择发生", "阶段目标升级"],
                                        "narrative_arc": "从被动应对转为主动推进。",
                                        "conflicts": ["安全退路与主动承担"],
                                        "plot_points": ["选择", "升级"],
                                        "key_characters": [],
                                        "key_locations": [],
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        )

    def _worldbuilding(self) -> str:
        return self._json(
            {
                "style": self._style_text(),
                "worldbuilding": {
                    "core_rules": {
                        "power_system": "依据用户设定建立核心能力、资源或规则体系，明确获得门槛、使用边界与失败代价。",
                        "physics_rules": "世界运行遵循用户设定的基础逻辑，特殊规则必须前后一致并能影响人物选择。",
                        "magic_tech": "关键工具、能力或技术只服务冲突推进，不替人物自动解决核心问题。",
                    },
                    "geography": {
                        "terrain": "地点层级围绕行动路线、信息差与冲突压力组织，避免只做背景陈列。",
                        "climate": "环境条件应能影响行动难度、节奏变化或人物判断。",
                        "resources": "关键资源按照稀缺性、获取成本和使用风险分布。",
                        "ecology": "人与环境的互动形成可复用约束，并在重要场景中产生后果。",
                    },
                    "society": {
                        "politics": "组织规则与权力关系应解释谁能决策、谁承担代价、谁会阻止改变。",
                        "economy": "交换关系围绕资源、机会与风险展开，推动人物做取舍。",
                        "class_system": "身份差异必须转化为行动权限、信息可得性或冲突压力。",
                    },
                    "culture": {
                        "history": "过去事件为当下冲突提供成因，但不替代当前行动。",
                        "religion": "信念、传统或公共叙事应影响人物判断与群体反应。",
                        "taboos": "禁忌用于制造边界和代价，触碰后必须产生可见后果。",
                    },
                    "daily_life": {
                        "food_clothing": "日常细节体现身份、资源状况和压力，不做无效铺陈。",
                        "language_slang": "语言风格服务角色区分、阵营差异和场景真实感。",
                        "entertainment": "休闲与传播方式可承载舆论、关系变化或信息流动。",
                    },
                },
            }
        )

    def _characters(self) -> str:
        return self._json(
            {
                "characters": [
                    {
                        "name": "核心人物甲",
                        "gender": "未指定",
                        "age": "未指定",
                        "role": "主角",
                        "description": "围绕用户设定承担主要目标的人物，必须通过选择推动剧情。",
                        "public_profile": "外界可见身份由用户设定决定，当前仅保留结构占位。",
                        "hidden_profile": "",
                        "reveal_chapter": None,
                        "mental_state": "承压",
                        "mental_state_reason": "核心问题出现后需要在有限信息下行动。",
                        "core_belief": "行动必须承担后果。",
                        "moral_taboos": ["不把无关者当作代价", "不伪造关键事实"],
                        "ghost": "曾因判断不足付出代价。",
                        "want": "解决当前核心问题。",
                        "need": "学会在代价明确时仍然做出有效选择。",
                        "flaw": "容易把问题独自扛下。",
                        "verbal_tic": "",
                        "idle_behavior": "压力升高时会反复确认关键细节。",
                        "voice_profile": {
                            "style": "克制",
                            "sentence_pattern": "短句",
                            "speech_tempo": "normal",
                            "metaphors": [],
                            "catchphrases": [],
                        },
                        "active_wounds": [
                            {"description": "旧选择留下的压力", "trigger": "类似代价再次出现", "effect": "先控制信息再行动"}
                        ],
                        "relationships": [],
                    },
                    {
                        "name": "关键关系乙",
                        "gender": "未指定",
                        "age": "未指定",
                        "role": "盟友",
                        "description": "提供不同判断标准，与核心人物形成互补或分歧。",
                        "public_profile": "与核心问题存在明确关联。",
                        "hidden_profile": "",
                        "reveal_chapter": None,
                        "mental_state": "观望",
                        "mental_state_reason": "尚未确认核心人物是否值得合作。",
                        "core_belief": "合作必须建立在可验证事实上。",
                        "moral_taboos": ["不无条件服从", "不隐瞒致命风险"],
                        "ghost": "曾因轻信付出代价。",
                        "want": "确认局势真相。",
                        "need": "建立可持续的信任关系。",
                        "flaw": "过度防御。",
                        "verbal_tic": "",
                        "idle_behavior": "先观察出口和风险点。",
                        "voice_profile": {
                            "style": "谨慎",
                            "sentence_pattern": "反问",
                            "speech_tempo": "normal",
                            "metaphors": [],
                            "catchphrases": [],
                        },
                        "active_wounds": [],
                        "relationships": [
                            {"target": "核心人物甲", "relation": "合作", "description": "信任需要通过行动逐步建立。"}
                        ],
                    },
                    {
                        "name": "阻力人物丙",
                        "gender": "未指定",
                        "age": "未指定",
                        "role": "对立角色",
                        "description": "代表阻止目标达成的现实力量或价值立场。",
                        "public_profile": "拥有制造障碍的资源、权限或信息优势。",
                        "hidden_profile": "真实动机需由后续剧情确认。",
                        "reveal_chapter": None,
                        "mental_state": "施压",
                        "mental_state_reason": "核心人物的行动影响其既有利益或秩序。",
                        "core_belief": "秩序比个体选择更重要。",
                        "moral_taboos": ["不公开承认失控", "不轻易交出主动权"],
                        "ghost": "失去控制感。",
                        "want": "维持现有优势。",
                        "need": "面对变化并重新定义秩序。",
                        "flaw": "低估个体行动的连锁反应。",
                        "verbal_tic": "",
                        "idle_behavior": "用沉默迫使对方先暴露需求。",
                        "voice_profile": {
                            "style": "压迫",
                            "sentence_pattern": "命令式",
                            "speech_tempo": "slow",
                            "metaphors": [],
                            "catchphrases": [],
                        },
                        "active_wounds": [],
                        "relationships": [
                            {"target": "核心人物甲", "relation": "阻力", "description": "围绕目标、代价和规则解释权形成对抗。"}
                        ],
                    },
                ]
            }
        )

    def _locations(self) -> str:
        return self._json(
            {
                "locations": [
                    {
                        "id": "location_starting_point",
                        "name": "起始地点",
                        "type": "区域",
                        "description": "核心问题第一次显性化的地点，承担开局压力与信息投放功能。",
                        "parent_id": None,
                        "connections": [
                            {"target": "关键转折地点", "relation": "通往", "description": "行动从发现问题转向验证问题。"}
                        ],
                    },
                    {
                        "id": "location_turning_point",
                        "name": "关键转折地点",
                        "type": "场所",
                        "description": "人物必须付出代价或做出选择的地点，推动目标升级。",
                        "parent_id": None,
                        "connections": [
                            {"target": "结果承压地点", "relation": "通往", "description": "选择产生后果并扩散到更大范围。"}
                        ],
                    },
                    {
                        "id": "location_consequence_point",
                        "name": "结果承压地点",
                        "type": "区域",
                        "description": "集中呈现阶段后果、关系变化和下一轮冲突入口。",
                        "parent_id": None,
                        "connections": [],
                    },
                ]
            }
        )

    def _main_plot_options(self) -> str:
        return self._json(
            {
                "plot_options": [
                    {
                        "id": "mock_option_goal_pressure",
                        "type": "目标压力型",
                        "title": "目标被迫提前",
                        "logline": "核心人物为了处理用户设定中的关键问题，必须在准备不足时提前行动。",
                        "core_conflict": "个人目标与外部压力之间的冲突。",
                        "starting_hook": "一个无法延后的后果迫使核心人物立刻做选择。",
                    },
                    {
                        "id": "mock_option_relationship_tension",
                        "type": "关系张力型",
                        "title": "信任需要代价",
                        "logline": "核心人物需要争取关键关系的协助，却必须先证明自己愿意承担代价。",
                        "core_conflict": "合作需求与信任缺口之间的冲突。",
                        "starting_hook": "最需要合作的时刻，对方提出了一个必须当场回应的条件。",
                    },
                    {
                        "id": "mock_option_rule_boundary",
                        "type": "规则边界型",
                        "title": "规则露出裂缝",
                        "logline": "既有规则无法解释新出现的问题，核心人物因此进入更大的冲突结构。",
                        "core_conflict": "旧规则的稳定性与新问题的破坏性之间的冲突。",
                        "starting_hook": "一次按规则执行的行动产生了反常结果。",
                    },
                ]
            }
        )

    def _chapter_review(self) -> str:
        return self._json(
            {
                "status": "reviewed",
                "score": 75,
                "summary": "本地模拟审阅只验证结构契约，真实质量判断需要配置 LLM。",
                "issues": [
                    {
                        "severity": "suggestion",
                        "location": "全文",
                        "description": "当前为无密钥环境的结构化模拟结果。",
                        "suggestion": "配置真实模型后重新执行 AI 审阅。",
                    }
                ],
                "suggestions": ["配置真实模型后重新执行 AI 审阅。"],
            }
        )

    def _style(self) -> str:
        return self._style_text()

    def _style_text(self) -> str:
        return "第三人称有限视角，叙事聚焦人物选择、信息差和代价反馈；节奏清晰，避免无效铺陈。"

    def _default(self) -> str:
        return self._json(
            {
                "characters": [],
                "locations": [],
                "style": self._style_text(),
                "worldbuilding": {},
                "parts": [],
                "plot_options": [],
            }
        )


class MockProvider(LLMService):
    """Mock LLM provider for tests and local no-key runs."""

    def __init__(self, response_factory: MockResponseFactory | None = None):
        self._response_factory = response_factory or MockResponseFactory()

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        content = self._response_factory.build(prompt)
        token_usage = TokenUsage(
            input_tokens=len(prompt.system) + len(prompt.user),
            output_tokens=len(content),
        )
        return GenerationResult(content=content, token_usage=token_usage)

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig) -> AsyncIterator[str]:
        result = await self.generate(prompt, config)
        chunk_size = 50
        for index in range(0, len(result.content), chunk_size):
            yield result.content[index : index + chunk_size]
