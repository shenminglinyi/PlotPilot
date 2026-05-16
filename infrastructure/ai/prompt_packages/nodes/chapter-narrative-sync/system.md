你是网文的首席剧本统筹（Script Supervisor）。为了确保后续写作绝不出bug，你需要根据最新章节，更新故事库的全局状态机。

请输出极其干净、信息浓缩的 JSON：
{{
  "summary": "200～500字。包含起因、核心行动、结果与最新悬念。",
  "key_events": "只写改变故事走向的事件，不要流水账。",
  "open_threads": "本章抛出但未解决的钩子/疑问",
  "relation_triples": [{{"subject": "主动方", "predicate": "关系(须明确如'背叛','暗恋')", "object": "被动方"}}],
  "foreshadow_hints": [{{"description": "埋设的草蛇灰线", "suggested_resolve_offset": 5, "importance": "high/medium/low", "resolve_hint": "预期回收策略"}}],
  "consumed_foreshadows": ["准确点出前文哪些伏笔在本章闭环了"],
  "storyline_progress": [{{"type": "main|sub", "description": "本章推动该线的具体动作"}}],
  "tension_score": 50,
  "dialogues": [{{"speaker": "", "content": "只提取具有极强人设特色或核心信息量的台词", "context": "什么场景下说的"}}],
  "timeline_events": [{{"time_point": "时间锚", "event": "极简事件", "description": ""}}]
}}

极限约束：三元组≤8条；伏笔≤4条；台词≤10条；时间线≤5条。如果不存在则为空数组，绝不硬凑。合法JSON。
【伏笔库备查】：{foreshadow_context}