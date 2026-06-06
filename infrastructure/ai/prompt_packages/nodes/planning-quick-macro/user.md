<STORY_CONTEXT>
【作者原始梗概】
{premise}

【世界观、地点与时间线】
{worldview}

【角色与关系】
{characters}
</STORY_CONTEXT>

<GENRE_PROFILE>
【类型开篇画像】
{{ genre_opening_profile }}

【读者留存契约】
{{ genre_reader_contract }}

【类型节奏约束】
{{ genre_rhythm_constraints }}
</GENRE_PROFILE>

<TARGET_SCOPE>
目标总篇幅：精确 {target_chapters} 章
强制约束：所有卷或幕的 estimated_chapters 之和必须等于 {target_chapters}
</TARGET_SCOPE>

请生成叙事骨架，严格按以下 JSON 结构输出：
{% if planning_depth == "framework" %}
{
  "parts": [
    {
      "title": "部标题",
      "theme": "部主题",
      "estimated_chapters": 0,
      "volumes": [
        {
          "title": "卷标题",
          "theme": "卷主题",
          "estimated_chapters": 0
        }
      ]
    }
  ]
}
{% elif planning_depth == "partial" %}
{
  "parts": [
    {
      "title": "部标题",
      "theme": "部主题",
      "estimated_chapters": 0,
      "volumes": [
        {
          "title": "开篇前导卷标题",
          "theme": "卷主题",
          "estimated_chapters": 0,
          "acts": [
            {
              "title": "幕标题",
              "estimated_chapters": 0,
              "core_conflict": "谁与谁对抗，赌注是什么",
              "emotional_turn": "情绪从什么变化到什么",
              "description": "情节摘要",
              "key_characters": ["角色ID或角色名"],
              "key_locations": ["地点ID或地点名"]
            }
          ]
        },
        {
          "title": "后续卷标题",
          "theme": "卷主题",
          "estimated_chapters": 0,
          "acts": []
        }
      ]
    }
  ]
}
{% else %}
{
  "parts": [
    {
      "title": "部标题",
      "theme": "部主题",
      "estimated_chapters": 0,
      "volumes": [
        {
          "title": "卷标题",
          "theme": "卷主题",
          "estimated_chapters": 0,
          "acts": [
            {
              "title": "幕标题",
              "estimated_chapters": 0,
              "core_conflict": "谁与谁对抗，赌注是什么",
              "emotional_turn": "情绪从什么变化到什么",
              "description": "情节摘要",
              "key_characters": ["角色ID或角色名"],
              "key_locations": ["地点ID或地点名"]
            }
          ]
        }
      ]
    }
  ]
}
{% endif %}
