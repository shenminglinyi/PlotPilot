{context}

请为这一幕规划 {chapter_count} 个章节。每章必须包含回报类型标注和伏笔操作。

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

请输出 JSON：
{
  "chapters": [
    {
      "number": 1,
      "title": "章节标题",
      "outline": "章节大纲，100-200 字，描述回报的具体内容",
      "characters": ["人物ID"],
      "locations": ["地点ID"],
      "thrill_type": "power_reveal",
      "thrill_description": "本章通过什么冲突、反击、突破、揭示或关系变化给读者正反馈",
      "foreshadow_action": "plant",
      "foreshadow_detail": "种下或回收了什么伏笔"
    }
  ]
}
