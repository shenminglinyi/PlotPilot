【待分析的章节】第 {chapter_number} 章

大纲：{outline}

正文如下：
{chapter_content}

{% if fact_lock_text %}
━━━ 当前事实锁（FACT_LOCK）━━━
{fact_lock_text}

请逐条检查正文是否违反上述事实。
{% endif %}
{% if existing_beats_summary %}
━━━ 已完成的节拍（COMPLETED_BEATS，不要重复提取）━━━
{existing_beats_summary}
{% endif %}
{% if existing_clues_summary %}
━━━ 已揭露的线索（REVEALED_CLUES，不要重复提取）━━━
{existing_clues_summary}
{% endif %}

请按以下 JSON 结构返回：
{
  "completed_beats": [
    {
      "beat_id": "ch5-confrontation-gaming-hall",
      "summary": "谁做了什么，并导致什么变化",
      "chapter": {chapter_number},
      "characters_involved": ["角色名"]
    }
  ],
  "revealed_clues": [
    {
      "clue_id": "clue-ch4-fake-driver",
      "content": "本章首次揭露的信息或真相",
      "revealed_at_chapter": {chapter_number},
      "category": "truth",
      "is_still_valid": true
    }
  ],
  "fact_violations": [
    {
      "violation_type": "timeline_contradiction",
      "description": "具体违反了哪条事实锁",
      "severity": "warning",
      "location_hint": "大致位置"
    }
  ]
}
