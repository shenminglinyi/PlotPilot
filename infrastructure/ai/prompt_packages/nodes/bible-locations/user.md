【故事创意】
{premise}

【小说设定】
名称：{novel_title}
大类：{genre_major}
主题：{genre_theme}
类型：{genre_label}
基调：{world_preset}
章节数量：{target_chapters}
每章字数：{target_words_per_chapter}

【类型开篇画像】
{{ genre_opening_profile | tojson }}

【读者留存契约】
{{ genre_reader_contract | tojson }}

【类型节奏约束】
{{ genre_rhythm_constraints | tojson }}

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

【已点亮锚点】
{existing_locations}

【上一阶段人物设定】
{{ characters_brief }}

【主角】
{{ protagonist_card }}

【当前人物活动热区】
{character_context}

---

请基于以上世界观和人物生成完整地图（5-10 个地点）。直接输出 JSON（不要包在代码块里）：

{{
  "locations": [
    {{
      "id": "唯一ID，小写英文+下划线+数字",
      "name": "地点名",
      "type": "城市/建筑/区域/特殊场所/秘境",
      "description": "地点功能与叙事价值，单行",
      "parent_id": null,
      "connections": [
        {{
          "target": "目标地点name",
          "relation": "包含/相邻/通往/封锁/隐藏通道",
          "description": "连接的叙事意义，单行"
        }}
      ]
    }}
  ]
}}
