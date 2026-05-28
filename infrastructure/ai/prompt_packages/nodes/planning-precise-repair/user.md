<STORY_CONTEXT>
{story_context}
</STORY_CONTEXT>

【全书约束】
- 总章数：{target_chapters} 章
- 结构：{parts} 部 × {volumes_per_part} 卷/部 × {acts_per_volume} 幕/卷
- 平均每幕：约 {avg_chapters_per_act} 章

【待补全幕】
{incomplete_acts_block}

请只输出 JSON：
{
  "node_updates": [
    {
      "node_id": "A1_1_1",
      "narrative_goal": "不能为空",
      "plot_points": ["至少 2 条"],
      "key_characters": ["至少 1 条"],
      "key_locations": ["至少 1 条"],
      "emotional_arc": "不能为空"
    }
  ]
}

要求：
1. 每个待补全幕都必须返回一条 node_updates。
2. 只返回缺失字段，不要输出 title、description、estimated_chapters，除非该幕这些字段也为空。
3. plot_points 至少 2 条，key_characters 和 key_locations 至少各 1 条。
