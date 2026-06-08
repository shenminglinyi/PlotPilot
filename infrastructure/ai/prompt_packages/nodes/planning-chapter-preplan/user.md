请为第 {chapter_number} 章《{chapter_title}》生成正文写作前的“章节执行剧本”。

幕级本章主事件链：
{act_chapter_plan}

近章连续性台账：
{continuity_ledger}

上一章结尾：
{previous_ending}

最近章节：
{recent_chapters}

角色状态：
{character_state}

未完成线索：
{unresolved_threads}

旧数据参考（如果有，只能参考，不得覆盖幕级主事件链）：
{legacy_chapter_plan}

输出要求：
1. 输出一个 JSON 对象，包含 outline 与 chapter_plan。
2. chapter_plan 必须覆盖九段：
   - opening_entry：开篇切入点，一句话说明从哪个动作、冲突或信息差切入。
   - story_unit：故事单元检查，包含 dilemma、chapter_goal、core_obstacle、action_path、reader_expectation、chapter_payoff、ending_hook。
   - scene_transitions：场景转换列表，每项包含 scene、location、cast、purpose。
   - emotional_beats：情绪变化节点 4-7 组，每项包含 beat、trigger、emotion_shift、reader_effect、text_anchor。
   - key_dialogues：关键对话 4-8 组，每项包含 speaker、line、reply、purpose。
   - event_chain：剧情事件链 6-10 个事件，每项包含 phase 和 content；phase 只能用 触发、升级、爆发、收束。
   - character_decisions：角色关键决策，至少包含主角主动选择、目的和后果。
   - payoff_reversals：爽点/反转设计，说明预期、反转、读者正反馈。
   - protagonist_state_change：主角状态变化，包含位置、实力、新获得、身体状况、重大变化。
3. story_unit 必须明确本章的目标、阻碍和读者期待；如果主角无法主动行动，chapter_goal 可以写成“外部行动者试图达成的目标 + 主角最低限度变化”，但不得为空。
4. emotional_beats 必须呈现递进链条，不得全部写成同一种情绪或同一种生理反应。
5. scene_transitions 和 event_chain 中，连续两个场景/事件不得只重复同一状态；每个核心场景必须带来动作、信息、关系、目标、风险或情绪的实际变化。
6. outline 是 chapter_plan 的中文九段渲染文本，格式从“一、开篇切入点：”到“九、主角状态变化：”。

请输出 JSON：
{
  "outline": "按九段格式渲染的章节执行剧本",
  "chapter_plan": {
    "opening_entry": "开篇切入点",
    "story_unit": {
      "dilemma": "本章当前困境",
      "chapter_goal": "本章要达成的明确目标",
      "core_obstacle": "阻碍目标达成的核心压力",
      "action_path": "角色将通过什么行动推进",
      "reader_expectation": "希望读者期待什么被满足",
      "chapter_payoff": "本章给出的阶段性回报",
      "ending_hook": "章尾留下的下一步牵引"
    },
    "scene_transitions": [
      {"scene": "场景1", "location": "地点", "cast": ["人物ID或姓名"], "purpose": "本场景推进的剧情"}
    ],
    "emotional_beats": [
      {"beat": "情绪节点1", "trigger": "触发动作/信息", "emotion_shift": "情绪从A到B", "reader_effect": "读者获得的情绪需求或期待", "text_anchor": "正文中应落地的具体动作/物件/对白"}
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
