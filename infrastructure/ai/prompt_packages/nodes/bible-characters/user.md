【核心法则】
{core_rules}

【地理生态】
{geography}

【社会结构】
{society}

【历史文化】
{culture}

【沉浸感细节】
{daily_life}

【剧本语态基调】
{style_guide}

【剧组已有卡司】
{existing_characters}

【命名种子】
{surname_seed}

---

请基于以上世界观生成主要角色阵容。人物不是标签卡，而是写文引擎的角色锁：必须包含核心信念、禁忌、声线、创伤触发和 POV 防火墙信息。

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
