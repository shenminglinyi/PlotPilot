{context}

请为这一幕规划 {chapter_count} 个章节。每章必须包含回报类型标注、伏笔操作，以及可直接交给正文模型执行的“章节执行剧本”。

回报类型 thrill_type 必选其一：
- power_reveal：实力或能力验证，只在大纲和设定需要时使用。
- identity_reveal：身份或地位揭露，只在已有铺垫和因果允许时使用。
- action：战斗或对峙高潮，强调冲突和胜负翻转。
- suspense：悬念爆发，揭示重大真相或造成认知颠覆。
- emotion：情感爆发，形成催泪、燃点或关系冲击。
- hook：钩子开场，以强冲突立刻抓住读者。
- relation_shift：信任、背叛、试探、结盟或决裂。
- world_rule：世界规则落地，让读者看见本题材规则如何改变行动。

伏笔操作 foreshadow_action 必选其一：plant、resolve、plant_and_resolve、none。none 仅限纯动作或过渡章节，每幕不超过 2 章。

前三章原则：
1. 第 1 章必须有 hook，并清楚落地主角处境、阻力和题材承诺。
2. 第 2 章必须承接第 1 章后果，推进一个实质选择或关系变化。
3. 第 3 章必须有一次实质高潮，可为 action、power_reveal、suspense 或 relation_shift，按题材和原设选择。

伏笔节奏：本幕内种下的伏笔，至少 1 条需要在本幕或下一幕回收；不能连续 2 章都是 none；最后一章必须 resolve 或 plant_and_resolve。

章节执行剧本要求：
1. 不要再输出 100-200 字短大纲作为主要写作依据。
2. 每章必须输出 chapter_plan 对象，并覆盖以下七段：
   - opening_entry：开篇切入点，一句话说明从哪个动作/冲突/信息差切入。
   - scene_transitions：场景转换列表，每项包含 scene、location、cast、purpose。
   - key_dialogues：关键对话 4-8 组，每项包含 speaker、line、reply、purpose；必须说明这组对白推进了什么线索、关系或冲突。
   - event_chain：剧情事件链 6-10 个事件，每项包含 phase 和 content；phase 只能用 触发、升级、爆发、收束。
   - character_decisions：角色关键决策，至少包含主角的主动选择、目的和后果。
   - payoff_reversals：爽点/反转设计，说明预期、反转、读者获得的正反馈。
   - protagonist_state_change：主角状态变化，包含位置、实力、新获得、身体状况、重大变化。
3. outline 字段必须是 chapter_plan 的中文七段渲染文本，格式使用“一、开篇切入点：”“二、场景转换列表：”直到“七、主角状态变化：”。
4. chapter_plan 与 outline 必须内容一致；正文生成会优先使用 outline 作为章节执行剧本。

请输出 JSON：
{
  "chapters": [
    {
      "number": 1,
      "title": "章节标题",
      "outline": "按七段格式渲染的章节执行剧本，不是短大纲",
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
      },
      "characters": ["人物ID"],
      "locations": ["地点ID"],
      "thrill_type": "power_reveal",
      "thrill_description": "本章通过什么冲突、反击、突破、揭示或关系变化给读者正反馈",
      "foreshadow_action": "plant",
      "foreshadow_detail": "种下或回收了什么伏笔"
    }
  ]
}
