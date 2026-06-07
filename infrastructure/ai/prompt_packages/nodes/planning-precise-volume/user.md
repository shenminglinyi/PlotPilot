<STORY_CONTEXT>
{story_context}
</STORY_CONTEXT>

【全书网格】
- 总章数：{target_chapters} 章
- 结构：{parts} 部 × {volumes_per_part} 卷/部 × {acts_per_volume} 幕/卷
- 平均每幕：约 {avg_chapters_per_act} 章

{scope_block}

请仅返回当前卷相关节点的 JSON：
{
  "node_updates": [
    {
      "node_id": "{example_node_id}",
      "title": "节点标题",
      "description": "节点描述",
      "estimated_chapters": 5,
      "narrative_goal": "仅 Act 必填，不能为空",
      "plot_points": ["仅 Act 使用，至少 2 条"],
      "key_characters": ["仅 Act 使用，至少 1 条"],
      "key_locations": ["仅 Act 使用，至少 1 条"],
      "emotional_arc": "仅 Act 使用，不能为空",
      "setup_for": ["仅 Act 使用"],
      "payoff_from": ["仅 Act 使用"]
    }
  ]
}

要求：
1. 只返回当前卷涉及的 node_updates。
2. 当前卷内每个 Act 都必须返回一条更新。
3. 每个 Act 的 narrative_goal、plot_points、key_characters、key_locations、emotional_arc 都不能为空。
4. 不要新增或删除节点。
