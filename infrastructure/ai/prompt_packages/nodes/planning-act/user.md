{context}

叙事契约：
- 锁定题材：{genre_label}
- 世界观基调：{world_preset}
- 结构承诺：{story_structure}
- 节奏承诺：{pacing_control}
- 文风承诺：{writing_style}
- 特殊要求：{special_requirements}

请为这一幕规划 {chapter_count} 个章节。这里只输出幕级轻量主事件链，用来保证相邻章节连续；不要输出单章七段“章节执行剧本”。

回报类型 thrill_type 必选其一；所有回报类型都必须服从叙事契约和作者原设：
- power_reveal：实力或能力验证，只在大纲和设定需要时使用。
- identity_reveal：身份或地位揭露，只在已有铺垫和因果允许时使用。
- action：战斗或对峙高潮，强调冲突和胜负翻转。
- suspense：悬念爆发，揭示重大真相或造成认知颠覆；悬念的来源必须从叙事契约、人物关系、既有事实和当前因果中推导。
- emotion：情感爆发，形成催泪、燃点或关系冲击。
- hook：钩子开场，以强冲突立刻抓住读者；钩子形态必须来自叙事契约中的核心期待。
- relation_shift：信任、背叛、试探、结盟或决裂。
- world_rule：世界规则落地，让读者看见叙事契约中已授权的规则如何改变行动；不得借此新增未被契约授权的外部类型机制。

题材一致性要求：
1. 作者原始输入、锁定题材、世界观基调和特殊要求是最高优先级。
2. 把意象、物件、梦境、闪回、异常感或氛围描写视为“待判定素材”；只有叙事契约或既有因果明确授权时，才能把它升级为新的规则、势力、能力、危机或主线机制。
3. 当素材存在多种解释时，优先选择能兑现锁定题材读者期待的解释，而不是引入外部类型机制。
4. 如果需要补全空白，只补因果、动机、关系压力、选择代价和阶段回报，不补成另一种故事赛道。

伏笔操作 foreshadow_action 必选其一：plant、resolve、plant_and_resolve、none。none 仅限纯动作或过渡章节，每幕不超过 2 章。

前三章原则：
1. 第 1 章必须有 hook，并清楚落地主角处境、阻力和题材承诺。
2. 第 2 章必须承接第 1 章后果，推进一个实质选择或关系变化。
3. 第 3 章必须有一次实质高潮，可为 action、power_reveal、suspense 或 relation_shift，按题材和原设选择。

伏笔节奏：本幕内种下的伏笔，至少 1 条需要在本幕或下一幕回收；不能连续 2 章都是 none；最后一章必须 resolve 或 plant_and_resolve。

轻量链条要求：
1. 必须严格输出 {chapter_count} 章，number 从 1 连续递增，不可缺章、跳章或多章。
2. main_event 写本章唯一主事件，不写七段执行细节。
3. handoff_from_previous 写本章如何承接上一章的后果、地点、角色状态或未完问题；第 1 章承接本幕入口。
4. handoff_to_next 写本章末尾交给下一章的明确承诺、钩子或未解决因果；最后一章交给下一幕。
5. required_threads 只列本章必须推进或回收的线索，不要堆全书设定。
6. location_hint 和 cast_hint 只保留本章核心地点、核心出场人物。
7. 不要输出 opening_entry、scene_transitions、key_dialogues、event_chain、character_decisions、payoff_reversals、protagonist_state_change，也不要输出 chapter_plan。

请输出 JSON：
{
  "chapters": [
    {
      "number": 1,
      "title": "章节标题",
      "main_event": "本章唯一主事件",
      "handoff_from_previous": "承接上一章的具体因果；第1章写本幕入口，不要伪造前章",
      "handoff_to_next": "本章末尾交给下一章的明确钩子或承诺",
      "required_threads": ["必须推进或回收的线索"],
      "location_hint": "核心地点",
      "cast_hint": ["核心出场人物ID或姓名"],
      "characters": ["人物ID"],
      "locations": ["地点ID"],
      "thrill_type": "power_reveal",
      "thrill_description": "本章通过什么冲突、反击、突破、揭示或关系变化给读者正反馈",
      "foreshadow_action": "plant",
      "foreshadow_detail": "种下或回收了什么伏笔"
    }
  ]
}
