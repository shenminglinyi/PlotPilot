"""Mock LLM Provider for testing without API keys"""
import json
from typing import AsyncIterator
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService


class MockProvider(LLMService):
    """Mock LLM Provider for testing

    Returns predefined responses without calling any external API.
    """

    def __init__(self):
        """Initialize Mock Provider

        No settings or API key needed.
        """
        self.last_stream_stop_reason: str = ""

    async def generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> GenerationResult:
        """Generate mock response

        Args:
            prompt: The prompt
            config: Generation config

        Returns:
            Mock generation result
        """
        # Detect what kind of generation is requested based on prompt
        user_prompt = prompt.user.lower()

        if "宏观结构" in user_prompt or "结构框架" in user_prompt or "部-卷-幕" in user_prompt:
            # Macro planning generation
            content = json.dumps({
                "parts": [
                    {
                        "number": 1,
                        "title": "第一部：科学之眼",
                        "description": "主角以科学视角观察修仙世界，发现其中的规律",
                        "suggested_chapter_count": 10,
                        "themes": ["科学观察", "数据分析"],
                        "volumes": [
                            {
                                "number": 1,
                                "title": "第一卷：观测者",
                                "description": "主角初入修仙界，开始观察和记录",
                                "suggested_chapter_count": 3,
                                "acts": [
                                    {
                                        "number": 1,
                                        "title": "第一幕：凡人的困境",
                                        "description": "主角作为凡人，在修仙世界中艰难求生",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["穿越到修仙世界", "发现无法修炼"],
                                        "narrative_arc": "开局困境，引发主角思考",
                                        "conflicts": ["生存危机"]
                                    },
                                    {
                                        "number": 2,
                                        "title": "第二幕：数据的力量",
                                        "description": "主角用科学方法分析灵气",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["建立观测系统", "发现灵气规律"],
                                        "narrative_arc": "发现新方法，获得希望",
                                        "conflicts": ["知识壁垒"]
                                    },
                                    {
                                        "number": 3,
                                        "title": "第三幕：第一次冲突",
                                        "description": "主角的方法引起修仙者注意",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["被修仙者发现", "展示科学成果"],
                                        "narrative_arc": "初次对抗，建立地位",
                                        "conflicts": ["传统vs科学"]
                                    }
                                ]
                            },
                            {
                                "number": 2,
                                "title": "第二卷：数据师",
                                "description": "主角建立数据分析体系",
                                "suggested_chapter_count": 3,
                                "acts": [
                                    {
                                        "number": 1,
                                        "title": "第四幕：建立体系",
                                        "description": "主角完善科学修仙理论",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["建立理论框架", "招收学生"],
                                        "narrative_arc": "体系建立，影响扩大",
                                        "conflicts": ["理论争议"]
                                    },
                                    {
                                        "number": 2,
                                        "title": "第五幕：传播知识",
                                        "description": "科学修仙法开始传播",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["开设学院", "培养弟子"],
                                        "narrative_arc": "影响力增长，引发变革",
                                        "conflicts": ["保守派反对"]
                                    },
                                    {
                                        "number": 3,
                                        "title": "第六幕：第一次危机",
                                        "description": "传统势力的反扑",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["遭遇围攻", "化解危机"],
                                        "narrative_arc": "危机考验，证明实力",
                                        "conflicts": ["势力冲突"]
                                    }
                                ]
                            },
                            {
                                "number": 3,
                                "title": "第三卷：变革者",
                                "description": "主角推动修仙界变革",
                                "suggested_chapter_count": 4,
                                "acts": [
                                    {
                                        "number": 1,
                                        "title": "第七幕：理论突破",
                                        "description": "科学修仙理论重大突破",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["发现核心原理", "创造新功法"],
                                        "narrative_arc": "理论飞跃，开创新时代",
                                        "conflicts": ["认知突破"]
                                    },
                                    {
                                        "number": 2,
                                        "title": "第八幕：全面推广",
                                        "description": "科学修仙法全面推广",
                                        "suggested_chapter_count": 2,
                                        "key_events": ["建立联盟", "改革制度"],
                                        "narrative_arc": "变革深化，影响深远",
                                        "conflicts": ["利益冲突"]
                                    },
                                    {
                                        "number": 3,
                                        "title": "第九幕：新秩序",
                                        "description": "建立新的修仙秩序",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["制定新规则", "和平共处"],
                                        "narrative_arc": "秩序重建，和谐发展",
                                        "conflicts": ["秩序建立"]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "number": 2,
                        "title": "第二部：理论突破",
                        "description": "深入研究修仙本质，建立完整理论体系",
                        "suggested_chapter_count": 10,
                        "themes": ["理论创新", "技术突破"],
                        "volumes": [
                            {
                                "number": 1,
                                "title": "第一卷：实验室",
                                "description": "建立修仙研究实验室",
                                "suggested_chapter_count": 3,
                                "acts": [
                                    {
                                        "number": 1,
                                        "title": "第十幕：同道者",
                                        "description": "寻找志同道合的研究者",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["组建团队", "建立实验室"],
                                        "narrative_arc": "团队组建，研究起步",
                                        "conflicts": ["资源争夺"]
                                    },
                                    {
                                        "number": 2,
                                        "title": "第十一幕：灵气引擎",
                                        "description": "研发灵气转换装置",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["设计原型", "测试成功"],
                                        "narrative_arc": "技术突破，应用落地",
                                        "conflicts": ["技术难题"]
                                    },
                                    {
                                        "number": 3,
                                        "title": "第十二幕：初步成果",
                                        "description": "实验室取得初步成果",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["发表论文", "获得认可"],
                                        "narrative_arc": "成果展示，影响扩大",
                                        "conflicts": ["学术争议"]
                                    }
                                ]
                            },
                            {
                                "number": 2,
                                "title": "第二卷：技术革新",
                                "description": "开发革命性修仙技术",
                                "suggested_chapter_count": 3,
                                "acts": [
                                    {
                                        "number": 1,
                                        "title": "第十三幕：灵气网络",
                                        "description": "构建灵气传输网络",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["设计网络", "建设基站"],
                                        "narrative_arc": "基础设施建设，改变格局",
                                        "conflicts": ["技术垄断"]
                                    },
                                    {
                                        "number": 2,
                                        "title": "第十四幕：商业化",
                                        "description": "技术商业化推广",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["成立公司", "市场推广"],
                                        "narrative_arc": "商业成功，财富积累",
                                        "conflicts": ["商业竞争"]
                                    },
                                    {
                                        "number": 3,
                                        "title": "第十五幕：垄断危机",
                                        "description": "面临反垄断调查",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["遭遇调查", "化解危机"],
                                        "narrative_arc": "危机应对，巩固地位",
                                        "conflicts": ["政治压力"]
                                    }
                                ]
                            },
                            {
                                "number": 3,
                                "title": "第三卷：理论大成",
                                "description": "完善科学修仙理论体系",
                                "suggested_chapter_count": 4,
                                "acts": [
                                    {
                                        "number": 1,
                                        "title": "第十六幕：统一理论",
                                        "description": "提出统一修仙理论",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["发表理论", "震惊世界"],
                                        "narrative_arc": "理论突破，奠定基础",
                                        "conflicts": ["理论质疑"]
                                    },
                                    {
                                        "number": 2,
                                        "title": "第十七幕：实验验证",
                                        "description": "大规模实验验证理论",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["设计实验", "验证成功"],
                                        "narrative_arc": "实验成功，理论确立",
                                        "conflicts": ["实验风险"]
                                    },
                                    {
                                        "number": 3,
                                        "title": "第十八幕：清算",
                                        "description": "与传统势力的最终对决",
                                        "suggested_chapter_count": 2,
                                        "key_events": ["大战爆发", "科学胜利"],
                                        "narrative_arc": "决战时刻，奠定地位",
                                        "conflicts": ["终极对决"]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "number": 3,
                        "title": "第三部：新纪元",
                        "description": "科学修仙时代全面到来",
                        "suggested_chapter_count": 10,
                        "themes": ["新时代", "文明进步"],
                        "volumes": [
                            {
                                "number": 1,
                                "title": "第一卷：革命前夜",
                                "description": "科学修仙革命的准备阶段",
                                "suggested_chapter_count": 3,
                                "acts": [
                                    {
                                        "number": 1,
                                        "title": "第十九幕：联盟组建",
                                        "description": "组建科学修仙联盟",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["召集盟友", "制定计划"],
                                        "narrative_arc": "力量集结，准备变革",
                                        "conflicts": ["内部分歧"]
                                    },
                                    {
                                        "number": 2,
                                        "title": "第二十幕：舆论战",
                                        "description": "争夺话语权和民心",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["宣传造势", "赢得支持"],
                                        "narrative_arc": "舆论胜利，民心所向",
                                        "conflicts": ["信息战"]
                                    },
                                    {
                                        "number": 3,
                                        "title": "第二十一幕：第一枪",
                                        "description": "革命正式开始",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["起义爆发", "初战告捷"],
                                        "narrative_arc": "革命开启，势不可挡",
                                        "conflicts": ["武装冲突"]
                                    }
                                ]
                            },
                            {
                                "number": 2,
                                "title": "第二卷：革命进行时",
                                "description": "科学修仙革命全面展开",
                                "suggested_chapter_count": 3,
                                "acts": [
                                    {
                                        "number": 1,
                                        "title": "第二十二幕：星火燎原",
                                        "description": "科学修仙法遍地开花",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["全面普及", "文明跃迁"],
                                        "narrative_arc": "革命成功，新时代开启",
                                        "conflicts": ["旧势力残余"]
                                    },
                                    {
                                        "number": 2,
                                        "title": "第二十三幕：最后堡垒",
                                        "description": "攻克传统势力最后据点",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["围攻堡垒", "攻克成功"],
                                        "narrative_arc": "最后战役，胜利在望",
                                        "conflicts": ["殊死抵抗"]
                                    },
                                    {
                                        "number": 3,
                                        "title": "第二十四幕：终极对决",
                                        "description": "与最强传统势力的对决",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["终极之战", "彻底胜利"],
                                        "narrative_arc": "最终对决，确立霸权",
                                        "conflicts": ["最终之战"]
                                    }
                                ]
                            },
                            {
                                "number": 3,
                                "title": "第三卷：新世界",
                                "description": "建立科学修仙新秩序",
                                "suggested_chapter_count": 4,
                                "acts": [
                                    {
                                        "number": 1,
                                        "title": "第二十五幕：秩序重建",
                                        "description": "建立新的修仙秩序",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["制定宪法", "建立政府"],
                                        "narrative_arc": "秩序建立，和平降临",
                                        "conflicts": ["权力分配"]
                                    },
                                    {
                                        "number": 2,
                                        "title": "第二十六幕：文明跃迁",
                                        "description": "修仙文明进入新阶段",
                                        "suggested_chapter_count": 1,
                                        "key_events": ["科技爆发", "文明升级"],
                                        "narrative_arc": "文明进步，前所未有",
                                        "conflicts": ["发展问题"]
                                    },
                                    {
                                        "number": 3,
                                        "title": "第二十七幕：新篇章",
                                        "description": "开启修仙新纪元",
                                        "suggested_chapter_count": 2,
                                        "key_events": ["建立新秩序", "展望未来"],
                                        "narrative_arc": "圆满结局，开启新篇",
                                        "conflicts": ["未来挑战"]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }, ensure_ascii=False)
        elif "世界观" in user_prompt or "worldbuilding" in user_prompt:
            # Worldbuilding generation
            content = json.dumps({
                "style": "第三人称有限视角，以主角视角为主。基调轻松幽默，节奏明快。避免过度描写。营造轻松愉快的阅读氛围。",
                "worldbuilding": {
                    "core_rules": {
                        "power_system": "现代都市背景，无特殊力量体系",
                        "physics_rules": "遵循现实世界物理规律",
                        "magic_tech": "现代科技水平"
                    },
                    "geography": {
                        "terrain": "现代都市，高楼林立",
                        "climate": "温带季风气候，四季分明",
                        "resources": "现代城市资源丰富",
                        "ecology": "城市生态系统"
                    },
                    "society": {
                        "politics": "现代民主政体",
                        "economy": "市场经济",
                        "class_system": "现代社会阶层"
                    },
                    "culture": {
                        "history": "当代都市文化",
                        "religion": "多元信仰并存",
                        "taboos": "遵守现代社会规范"
                    },
                    "daily_life": {
                        "food_clothing": "现代都市生活方式",
                        "language_slang": "现代汉语，偶有网络用语",
                        "entertainment": "现代娱乐方式：电影、音乐、游戏等"
                    }
                }
            }, ensure_ascii=False)
        elif "人物" in user_prompt or "character" in user_prompt:
            # Character generation
            content = json.dumps({
                "characters": [
                    {
                        "name": "张三",
                        "role": "主角",
                        "description": "30岁，自由作家，性格开朗乐观，目标是写出畅销小说",
                        "relationships": [
                            {
                                "target": "李四",
                                "relation": "好友",
                                "description": "多年好友，互相支持"
                            }
                        ]
                    },
                    {
                        "name": "李四",
                        "role": "配角",
                        "description": "32岁，出版社编辑，性格严谨认真，帮助主角修改稿件",
                        "relationships": [
                            {
                                "target": "张三",
                                "relation": "好友",
                                "description": "多年好友，提供专业建议"
                            }
                        ]
                    },
                    {
                        "name": "王五",
                        "role": "对手",
                        "description": "28岁，畅销书作家，性格傲慢自负，与主角竞争",
                        "relationships": [
                            {
                                "target": "张三",
                                "relation": "竞争",
                                "description": "文学奖竞争对手"
                            }
                        ]
                    }
                ]
            }, ensure_ascii=False)
        elif "setup_main_plot_options_v1" in prompt.user:
            content = json.dumps(
                {
                    "plot_options": [
                        {
                            "id": "mock_option_a",
                            "type": "底层逆袭 / 生存狂飙",
                            "title": "暗巷里的第一票",
                            "logline": "主角为救至亲卷入黑市交易，却摸到上层不想让人看见的命脉。",
                            "core_conflict": "无名小卒 vs 掌控信息与暴力的结构之手",
                            "starting_hook": "货不对板：箱子里不是药，而是一枚会招来杀身之祸的证物。",
                        },
                        {
                            "id": "mock_option_b",
                            "type": "自上而下的阴谋",
                            "title": "干净的报表，脏掉的人",
                            "logline": "主角被指派“善后”一桩意外，却发现所有线索都指向自己信任的制度。",
                            "core_conflict": "个体的良知 vs 系统性的封口与甩锅",
                            "starting_hook": "上级的口头表扬与同时到达的匿名警告，只相隔十分钟。",
                        },
                        {
                            "id": "mock_option_c",
                            "type": "异类 / 变数觉醒",
                            "title": "规则写错了你的名字",
                            "logline": "主角的能力/体质无法被既有体系解释，于是成为被争夺的变量。",
                            "core_conflict": "不可归类之人 vs 必须维持分类的权力",
                            "starting_hook": "检测仪在主角面前死机，而围观者的眼神先一步变了。",
                        },
                    ]
                },
                ensure_ascii=False,
            )
        elif "地点" in user_prompt or "location" in user_prompt:
            # Location generation
            content = json.dumps({
                "locations": [
                    {
                        "name": "咖啡馆",
                        "type": "建筑",
                        "description": "主角常去的咖啡馆，安静舒适，适合写作",
                        "connections": ["图书馆"]
                    },
                    {
                        "name": "图书馆",
                        "type": "建筑",
                        "description": "市中心图书馆，藏书丰富，主角查资料的地方",
                        "connections": ["咖啡馆", "出版社"]
                    },
                    {
                        "name": "出版社",
                        "type": "建筑",
                        "description": "李四工作的出版社，现代化办公楼",
                        "connections": ["图书馆"]
                    }
                ]
            }, ensure_ascii=False)
        else:
            # Default response
            content = json.dumps({
                "characters": [],
                "locations": [],
                "style": "第三人称视角，轻松基调"
            }, ensure_ascii=False)

        # Create mock token usage
        token_usage = TokenUsage(
            input_tokens=len(prompt.user),
            output_tokens=len(content)
        )

        return GenerationResult(content=content, token_usage=token_usage, stop_reason="stop")

    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        """Stream mock response

        Args:
            prompt: The prompt
            config: Generation config

        Yields:
            Mock response chunks
        """
        result = await self.generate(prompt, config)
        self.last_stream_stop_reason = result.stop_reason
        # Simulate streaming by yielding the content in chunks
        chunk_size = 50
        for i in range(0, len(result.content), chunk_size):
            yield result.content[i:i+chunk_size]
