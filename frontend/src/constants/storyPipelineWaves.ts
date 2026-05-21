/** 与 engine/pipeline/telemetry.py STORY_PIPELINE_WAVES 顺序一致（仅展示用） */
export const STORY_PIPELINE_WAVE_TOTAL = 10

export const STORY_PIPELINE_WAVES: ReadonlyArray<{
  index: number
  id: string
  label: string
}> = [
  { index: 1, id: 'find_chapter', label: '章节定位' },
  { index: 2, id: 'build_context', label: '组装上下文' },
  { index: 3, id: 'magnify_beats', label: '节拍拆分' },
  { index: 4, id: 'generate', label: '正文生成' },
  { index: 5, id: 'validate_policy', label: '策略校验' },
  { index: 6, id: 'persist_chapter', label: '章节落盘' },
  { index: 7, id: 'voice_audit', label: '文风审计' },
  { index: 8, id: 'aftermath', label: '章后管线' },
  { index: 9, id: 'score_tension', label: '张力打分' },
  { index: 10, id: 'finalize', label: '收尾' },
]
