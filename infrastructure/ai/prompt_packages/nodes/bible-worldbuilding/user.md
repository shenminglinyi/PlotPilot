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
特殊要求：{special_requirements}

【生成上下文】
{{ genre_opening_profile | tojson(indent=2) }}

请生成世界观。

请按照以下 json 格式输出，可被 Python json.loads 解析。只给出 JSON，不要解释，不要 markdown 说明。
每个字段值写成 80-160 字中文单段文本，不得换行，不得嵌套对象或数组；不得把一个维度写成字符串；不得省略任何 fields_desc 中列出的子字段。
注意：`style` 不是 `worldbuilding` 的子字段，必须保持为顶层字段；`worldbuilding` 里只允许五维世界观字段。

{
  "style": "文风公约文本",
  "worldbuilding": {
{fields_desc}
  }
}
