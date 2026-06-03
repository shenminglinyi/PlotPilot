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
