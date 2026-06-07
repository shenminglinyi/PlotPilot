export type GenerateStreamLogTag = 'SSE' | '规划' | '节拍' | '正文' | string
export type NaiveTagType = 'default' | 'primary' | 'success' | 'info' | 'warning' | 'error'

export interface GenerateStreamLogLine {
  tag: GenerateStreamLogTag
  msg: string
}

export const GENERATE_STREAM_LOG_LIMIT = 7

const STREAM_PHASE_PROGRESS: Record<string, number> = {
  planning: 14,
  context: 28,
  script: 52,
  prose: 78,
  outline_planning: 48,
  chapter_plan_ready: 50,
  llm: 72,
  post: 92,
}

const STREAM_PHASE_LABELS: Record<string, string> = {
  planning: '宏观 planning…',
  context: '组装上下文…',
  script: '生成六模块剧本…',
  outline_planning: '章节执行剧本准备…',
  chapter_plan_ready: '章节执行剧本已就绪…',
  prose: '正文撰写…',
  llm: '撰写正文…',
  post: '质检与收尾…',
}

const STREAM_PHASE_LOG_LABELS: Record<string, string> = {
  planning: '宏观 planning',
  context: '上下文 context',
  script: '剧本生成 script',
  outline_planning: '执行剧本准备',
  chapter_plan_ready: '执行剧本已就绪',
  prose: '正文撰写 prose',
  llm: '正文撰写 llm（兼容）',
  post: '质检 post',
}

const STREAM_LOG_TAG_TYPES: Record<string, NaiveTagType> = {
  SSE: 'info',
  规划: 'warning',
  节拍: 'success',
  正文: 'primary',
}

export function streamPhaseToProgress(phase: string): number {
  return STREAM_PHASE_PROGRESS[phase] ?? 12
}

export function streamPhaseToLabel(phase: string): string {
  return STREAM_PHASE_LABELS[phase] ?? phase
}

export function streamPhaseToLogLabel(phase: string): string {
  return STREAM_PHASE_LOG_LABELS[phase] ?? phase
}

export function generateStreamTagType(tag: string): NaiveTagType {
  return STREAM_LOG_TAG_TYPES[tag] ?? 'default'
}

export function planningSkeletonWidthPct(rowIndex: number): string {
  return `${Math.min(94, 36 + rowIndex * 10)}%`
}

export function appendGenerateStreamLog(
  lines: GenerateStreamLogLine[],
  line: GenerateStreamLogLine,
  limit = GENERATE_STREAM_LOG_LIMIT,
): GenerateStreamLogLine[] {
  return [...lines, line].slice(-limit)
}
