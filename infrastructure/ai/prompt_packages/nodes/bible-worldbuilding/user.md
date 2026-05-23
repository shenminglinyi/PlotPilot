【故事创意】
{premise}

【目标章节数】
{target_chapters} 章

【已有设定】
{existing_settings}

---

按以下格式直接输出 JSON（不要包在 markdown 代码块里）。每个字段值只能是中文段落字符串，禁止嵌套对象/数组，禁止出现英文键名（name、tier、description 等）。层次结构用【小标题】写进一段正文里。

请严格按照模板顺序逐字段输出。先写完 `core_rules.power_system`，再写 `core_rules.physics_rules`，依次完成 `core_rules` 的所有子项；每个字段写完并关闭字符串后再进入下一个字段。这样系统可以在后端解析到一个子项时立即推送给前端。

{{
  "worldbuilding": {{
{fields_desc}
  }}
}}
