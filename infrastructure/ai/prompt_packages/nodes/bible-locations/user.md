【故事创意】
{{ novel.premise }}

【小说设定】
名称：{{ novel.title }}
大类：{{ novel.genre_major }}
主题：{{ novel.genre_theme }}
类型：{{ novel.genre_label }}
基调：{{ novel.world_preset }}
剧情结构：{{ novel.story_structure }}
节奏把控：{{ novel.pacing_control }}
写作风格：{{ novel.writing_style }}
特殊要求：{{ novel.special_requirements }}
章节数量：{{ novel.target_chapters }}
每章字数：{{ novel.target_words_per_chapter }}

【结构化世界观】
{{ worldbuilding.content }}

【已点亮锚点】
{{ locations.list }}

【上一阶段人物设定】
{{ characters.list }}

【主角】
{{ characters.protagonist }}

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
