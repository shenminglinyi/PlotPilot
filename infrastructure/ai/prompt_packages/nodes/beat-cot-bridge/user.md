[上一节拍结尾]
{prev_beat_tail}

[下一节拍任务]
{next_beat_intent}

分析上述节拍结束时的叙事状态，给出精确的过渡指令。

{
  "active_scene": {
    "location": "场景地点（10字以内）",
    "characters_present": ["人物1及状态", "人物2及状态"],
    "atmosphere": "氛围关键词（8字以内）"
  },
  "narrative_momentum": "读者注意力此刻聚焦于什么（15字以内）",
  "transition": {
    "type": "emotion_continue|action_continue|dialogue_continue|scene_cut|internal_shift",
    "opening_line": "下一节拍的第一句话（可直接写入正文，15-30字）",
    "carry_forward": "必须延续的叙事要素（15字以内）"
  },
  "risk": "最容易出现的叙事断层（12字以内）"
}
