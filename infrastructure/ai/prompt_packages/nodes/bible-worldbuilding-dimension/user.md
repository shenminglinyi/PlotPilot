故事创意：{premise}

目标章节数：{target_chapters}章

请生成世界观的「{dim_label}」维度。{context_block}

请严格按照以下JSON格式输出，字段名不要修改，可以被Python json.loads函数解析。只给出JSON，不作解释，不作答：
```json
{{
{fields_desc}
}}
```
