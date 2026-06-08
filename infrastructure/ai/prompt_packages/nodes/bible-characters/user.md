【小说设定】
故事创意/原始设定：
{{ novel.premise }}

大类：{{ novel.genre_major }}
主题：{{ novel.genre_theme }}
类型：{{ novel.genre_label }}
基调：{{ novel.world_preset }}
写作风格：{{ novel.writing_style }}
特殊要求：{{ novel.special_requirements }}

【文风内容】
{{ worldbuilding.style }}

【结构化世界观】
{{ worldbuilding.content }}

请基于以上世界观生成主要角色阵容。人物不是标签卡，而是写文引擎的角色锁：必须包含核心信念、禁忌、声线、创伤触发和 POV 防火墙信息。

先从【故事创意/原始设定】中抽取已经出现的人物、人名、关系、身份、创伤事件、季节节点和关键意象；这些内容是硬约束，必须保留，不得改名、换关系、换职业时代或改写为无关套路。世界观只用于补全空白和解释人物所处社会生态，不能覆盖原始设定。

直接输出 JSON（不要包在代码块里）：

{{
  "characters": [
    {{
      "name": "角色全名",
      "gender": "性别",
      "age": "年龄",
      "role": "主角/对立角色/盟友/次要角色",
      "description": "一句话功能定位与人物矛盾，单行",
      "appearance": "最容易辨认的外貌锚点，单行；没有则空字符串",
      "personality": "性格底色/处事风格，单行；没有则空字符串",
      "background": "最关键的背景经历或出身来历，单行；没有则空字符串",
      "public_profile": "其他角色可见的身份、阶层、外显行为，单行",
      "hidden_profile": "暂不可见的秘密/真实动机/身份雷区，单行；没有则空字符串",
      "reveal_chapter": null,
      "mental_state": "开局心理状态，2-8字",
      "mental_state_reason": "该心理状态的成因，单行",
      "core_belief": "一句可驱动选择的核心信念",
      "moral_taboos": ["绝不做的事1", "绝不做的事2"],
      "core_motivation": "核心驱动力/表层目标，单行；最好与 want 一致",
      "inner_lack": "内在缺口/深层需要，单行；最好与 need 一致",
      "ghost": "内心创伤或恐惧",
      "want": "表层目标",
      "need": "深层需要（角色自己可能不自知）",
      "flaw": "致命弱点",
      "verbal_tic": "口头禅或高频话语；没有则空字符串",
      "idle_behavior": "压力下的小动作/待机动作",
      "voice_profile": {{
        "style": "话多/克制/讥诮/温和等",
        "sentence_pattern": "短句/长句/反问/命令式/混合",
        "speech_tempo": "fast/normal/slow",
        "metaphors": ["常用隐喻意象"],
        "catchphrases": ["口头禅"]
      }},
      "active_wounds": [
        {{"description": "未愈合创伤", "trigger": "触发条件", "effect": "触发后的反应"}}
      ],
      "relationships": [
        {{"target": "其他角色名", "relation": "敌对/师徒/利用/保护等", "description": "张力说明"}}
      ]
    }}
  ]
}}
