<STORY_CONTEXT>
{story_context}
</STORY_CONTEXT>

<STRUCTURAL_GRID>
目标总章数：{target_chapters} 章
结构分布：{parts} 部 × {volumes_per_part} 卷/部 × {acts_per_volume} 幕/卷 = {total_acts} 幕
平均每幕：约 {avg_chapters_per_act} 章
</STRUCTURAL_GRID>

{skeleton_block}

系统已经固定好了部、卷、幕的数量与层级。你的任务只是为这些固定节点填写标题、描述和幕级字段。

请只输出 JSON：
{
  "node_updates": [
    {
      "node_id": "P1 或 V1_1 或 A1_1_1",
      "title": "节点标题",
      "description": "节点描述",
      "estimated_chapters": 5,
      "narrative_goal": "仅 Act 必填",
      "plot_points": ["仅 Act 使用"],
      "key_characters": ["仅 Act 使用"],
      "key_locations": ["仅 Act 使用"],
      "emotional_arc": "仅 Act 使用",
      "setup_for": ["仅 Act 使用"],
      "payoff_from": ["仅 Act 使用"]
    }
  ]
}

要求：
1. 每个固定节点都必须返回一条 node_updates。
2. Part 和 Volume 只需填写 node_id、title、description。
3. Act 必须填写全部幕级字段。
4. 不要返回 parts/volumes/acts 树，不要添加解释文字。
