【双轨上下文】
{context_block}

【当前幕信息】
幕标题：{current_act_title}
幕描述：{current_act_description}
幕号：第 {current_act_number} 幕

【任务】
请生成第 {next_act_number} 幕的详细规划。

【输出要求】
请输出 JSON：
{
  "title": "幕标题，动词加名词，暗示冲突",
  "description": "幕简介，100-200 字，包含核心事件、冲突、转折",
  "suggested_chapter_count": 5,
  "key_events": ["事件1", "事件2"],
  "narrative_arc": "叙事弧线，如：紧张→爆发→暂缓",
  "foreshadow_to_resolve": ["需要回收的伏笔"],
  "foreshadow_to_plant": ["需要埋下的新伏笔"]
}
