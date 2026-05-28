当前小说ID: {novel_id}
卡文章节: 第{chapter_number}章

作者自述的卡文原因:
{stuck_reason_text}

事件列表:
{events_text}

{% if repository_context %}
补充上下文（仓储）:
{repository_context}
{% endif %}

{stats_text}

请以 JSON 格式返回结果：
{
  "diagnosis": "诊断结果，2-3句话",
  "tension_level": "low/medium/high",
  "missing_elements": ["缺失元素1", "缺失元素2"],
  "suggestions": ["具体建议1", "具体建议2", "具体建议3"]
}
