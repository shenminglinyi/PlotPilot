当前 ACTIVE 道具列表：
{props_summary}

章节正文（节选，前 1500 字）：
{chapter_excerpt}

输出格式（JSON 数组）：
[
  {
    "prop_id": "...",
    "event_type": "TRANSFERRED|DAMAGED|REPAIRED|UPGRADED|RESOLVED",
    "actor_character": "角色名（可选）",
    "from_holder": "转出方角色名（TRANSFERRED 时填）",
    "to_holder": "转入方角色名（TRANSFERRED 时填）",
    "description": "一句话描述"
  }
]

无相关事件时输出空数组 []。
