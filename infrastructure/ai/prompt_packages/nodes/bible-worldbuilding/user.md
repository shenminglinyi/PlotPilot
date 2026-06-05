【故事创意】
{{ novel.premise }}

【小说设定】
名称：{{ novel.title }}
大类：{{ novel.genre_major }}
主题：{{ novel.genre_theme }}
类型：{{ novel.genre_label }}
基调：{{ novel.world_preset }}
剧情结构：{{ novel.story_structure }}
节奏把控：{{ novel.pacing_control }}
写作风格：{{ novel.writing_style }}
特殊要求：{{ novel.special_requirements }}
章节数量：{{ novel.target_chapters }}
每章字数：{{ novel.target_words_per_chapter }}

请生成世界观。

请按照以下 json 格式输出，可被 Python json.loads 解析。只给出 JSON，不要解释，不要 markdown 说明。
每个字段值写成 80-160 字中文单段文本，不得换行，不得嵌套对象或数组；如果题材不涉及某项，也保留键名并写空字符串。
注意：`style` 不是 `worldbuilding` 的子字段，必须保持为顶层字段；`worldbuilding` 里只允许五维世界观字段。

{
  "style": "文风公约文本",
  "worldbuilding": {
    "core_rules": "",
    "geography": "",
    "society": "",
    "culture": "",
    "daily_life": ""
  }
}
