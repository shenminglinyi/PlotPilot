【故事创意】
{premise}

【小说设定】
名称：{novel_title}
大类：{genre_major}
主题：{genre_theme}
类型：{genre_label}
基调：{world_preset}
章节数量：{target_chapters}
每章字数：{target_words_per_chapter}

【目标章节数】
{target_chapters} 章

【类型开篇画像】
{{ genre_opening_profile | tojson }}

【读者留存契约】
{{ genre_reader_contract | tojson }}

【类型节奏约束】
{{ genre_rhythm_constraints | tojson }}

请生成世界观。

请按照以下 json 格式输出，可被 Python json.loads 解析。只给出 JSON，不要解释，不要 markdown 说明。
每个字段值写成 80-160 字中文单段文本，不得换行，不得嵌套对象或数组；如果题材不涉及某项，也保留键名并写空字符串。
注意：`style` 不是 `worldbuilding` 的子字段，必须保持为顶层字段；`worldbuilding` 里只允许五维世界观字段。

{{
  "worldbuilding": {{
{fields_desc}
  }}
}}
