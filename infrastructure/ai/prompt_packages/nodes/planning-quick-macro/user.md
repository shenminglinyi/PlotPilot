<STORY_CONTEXT>
【作者原始梗概】
{{premise}}

【世界观】
{{worldbuilding.content}}

【地点】
{{locations.list}}

【角色与关系】
{{characters}}
</STORY_CONTEXT>

<TARGET_SCOPE>
目标总篇幅：精确 {target_chapters} 章
强制约束：所有卷或幕的 estimated_chapters 之和必须等于 {target_chapters}
</TARGET_SCOPE>

<PLANNING_REQUIREMENTS>
1. 标题要贴合原始设定，不要使用「第一部」「成长卷」「决战卷」这类占位标题。
2. theme 写该结构单元的叙事功能，不写抽象口号。
3. reading_hook 写该结构单元让读者继续追读的阶段问题或期待。
4. payoff 写该结构单元结束时给读者的阶段性回报。
5. escalation 写该结构单元结束后抬高的新压力、新诱因或新问题。
6. description 必须整合本单元的阶段目标、主要阻力、关键选择、代价、回报和后续钩子，避免只复述 theme。
7. 角色和地点只能优先使用 STORY_CONTEXT 中已有内容；资料不足时可以用功能性称谓，但不要创造与原设无关的固定模板名词。
8. estimated_chapters 必须使用正整数；总和必须严格满足 TARGET_SCOPE。
</PLANNING_REQUIREMENTS>

请生成叙事骨架，严格按以下 JSON 结构输出：
{% if planning_depth == "framework" %}
{
  "parts": [
    {
      "title": "部标题",
      "theme": "部主题",
      "reading_hook": "本部持续牵引读者的核心问题",
      "payoff": "本部结束时兑现的阶段性回报",
      "escalation": "本部结束后抬高的长期压力或诱因",
      "description": "本部的阶段目标、主要阻力、关键选择、代价、回报与后续钩子",
      "estimated_chapters": 0,
      "volumes": [
        {
          "title": "卷标题",
          "theme": "卷主题",
          "reading_hook": "本卷持续牵引读者的阶段问题",
          "payoff": "本卷结束时兑现的阶段性回报",
          "escalation": "本卷结束后引出的新压力或新诱因",
          "description": "本卷的阶段目标、主要阻力、关键选择、代价、回报与后续钩子",
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
      "reading_hook": "本部持续牵引读者的核心问题",
      "payoff": "本部结束时兑现的阶段性回报",
      "escalation": "本部结束后抬高的长期压力或诱因",
      "description": "本部的阶段目标、主要阻力、关键选择、代价、回报与后续钩子",
      "estimated_chapters": 0,
      "volumes": [
        {
          "title": "开篇前导卷标题",
          "theme": "卷主题",
          "reading_hook": "本卷持续牵引读者的阶段问题",
          "payoff": "本卷结束时兑现的阶段性回报",
          "escalation": "本卷结束后引出的新压力或新诱因",
          "description": "本卷的阶段目标、主要阻力、关键选择、代价、回报与后续钩子",
          "estimated_chapters": 0,
          "acts": [
            {
              "title": "幕标题",
              "estimated_chapters": 0,
              "core_conflict": "谁与谁对抗，赌注是什么",
              "emotional_turn": "情绪从什么变化到什么",
              "reading_hook": "本幕末尾保留的追读问题或期待",
              "payoff": "本幕兑现的阶段性回报",
              "description": "情节摘要",
              "key_characters": ["角色ID或角色名"],
              "key_locations": ["地点ID或地点名"]
            }
          ]
        },
        {
          "title": "后续卷标题",
          "theme": "卷主题",
          "reading_hook": "本卷持续牵引读者的阶段问题",
          "payoff": "本卷结束时兑现的阶段性回报",
          "escalation": "本卷结束后引出的新压力或新诱因",
          "description": "本卷的阶段目标、主要阻力、关键选择、代价、回报与后续钩子",
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
      "reading_hook": "本部持续牵引读者的核心问题",
      "payoff": "本部结束时兑现的阶段性回报",
      "escalation": "本部结束后抬高的长期压力或诱因",
      "description": "本部的阶段目标、主要阻力、关键选择、代价、回报与后续钩子",
      "estimated_chapters": 0,
      "volumes": [
        {
          "title": "卷标题",
          "theme": "卷主题",
          "reading_hook": "本卷持续牵引读者的阶段问题",
          "payoff": "本卷结束时兑现的阶段性回报",
          "escalation": "本卷结束后引出的新压力或新诱因",
          "description": "本卷的阶段目标、主要阻力、关键选择、代价、回报与后续钩子",
          "estimated_chapters": 0,
          "acts": [
            {
              "title": "幕标题",
              "estimated_chapters": 0,
              "core_conflict": "谁与谁对抗，赌注是什么",
              "emotional_turn": "情绪从什么变化到什么",
              "reading_hook": "本幕末尾保留的追读问题或期待",
              "payoff": "本幕兑现的阶段性回报",
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
