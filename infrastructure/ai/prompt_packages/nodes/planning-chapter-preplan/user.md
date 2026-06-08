请为第 {chapter_number} 章《{chapter_title}》生成正文写作前的“章节执行剧本”。

幕级本章主事件链：
{act_chapter_plan}

连续性上下文（前3章规划大纲）：
{continuity_context}

输出要求：

1. 输出一个 JSON 对象，包含 detail_title、key_plot_points、chapter_characters 与 chapter_plan。
2. chapter_plan 会由系统渲染成七段细纲；禁止输出“故事单元检查”“情绪变化节点”等分析型额外段落。
3. key_plot_points 从剧情事件链中抽取 5-10 个本章正文绝不能遗漏的关键情节点，必须是具体事件，不要写抽象主题。
4. chapter_characters 只列本章实际出场或群体围观角色，名称优先用中文名；没有中文名时使用人物ID。
5. chapter_plan 必须且只能覆盖七段字段：
   - opening_entry：开篇切入点，一句话说明从哪个场景的哪个动作、冲突或信息差切入。
   - scene_transitions：场景转换列表，每项包含 scene、location、cast、purpose。
   - key_dialogues：关键对话 4-8 组，每项包含 speaker、line、reply、purpose。
   - event_chain：剧情事件链 6-10 个事件，每项包含 phase 和 content；phase 只能用 触发、升级、爆发、收束。
   - character_decisions：角色关键决策，至少包含主角主动选择、目的和后果。
   - payoff_reversals：爽点/反转设计，说明预期、反转、读者正反馈。
   - protagonist_state_change：主角状态变化，包含位置、实力、新获得、身体状况、重大变化。
6. 正文模型会按 event_chain 顺序扩写，所以上下文交接、人物位置、关键动作、对话作用必须具体可执行。

请输出 JSON：
{
  "detail_title": "细纲标题",
  "key_plot_points": [
    "本章必须落地的关键情节点"
  ],
  "chapter_characters": [
    "本章角色"
  ],
  "chapter_plan": {
    "opening_entry": "开篇切入点",
    "scene_transitions": [
      {"scene": "场景1", "location": "地点", "cast": ["人物ID或姓名"], "purpose": "本场景推进的剧情"}
    ],
    "key_dialogues": [
      {"speaker": "人物A", "line": "A要说/试探/告知的重点", "reply": "人物B的回应重点", "purpose": "对白作用"}
    ],
    "event_chain": [
      {"phase": "触发", "content": "事件1具体内容"}
    ],
    "character_decisions": [
      {"actor": "主角", "decision": "主动决策", "purpose": "目的与后果"}
    ],
    "payoff_reversals": [
      "爽点1：预期→反转→正反馈"
    ],
    "protagonist_state_change": {
      "位置": "起点→终点",
      "实力": "变化或无变化",
      "新获得": "信息、资源、资格或关系",
      "身体状况": "状态",
      "重大变化": "本章对后续行动的实质改变"
    }
  }
}
