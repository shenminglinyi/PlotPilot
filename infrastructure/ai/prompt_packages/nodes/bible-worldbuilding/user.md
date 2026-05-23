【故事创意】
{premise}

【目标章节数】
{target_chapters} 章

【已有设定】
{existing_settings}

请生成世界观。

请按照以下 json 格式输出，可被 Python json.loads 解析。只给出 JSON，不要解释，不要 markdown 说明。
每个字段值写成 80-160 字中文单段文本，不得换行，不得嵌套对象或数组；如果题材不涉及某项，也保留键名并写空字符串。

{{
  "worldbuilding": {{
{fields_desc}
  }}
}}
