import type { ChapterCandidateDraftDTO } from '@/api/chapter'

export type CandidateDraftTagType = 'default' | 'info' | 'success' | 'warning' | 'error'

const SOURCE_LABELS: Record<string, string> = {
  'workbench-generate': '工作台生成',
  'chapter-editor': '章节页保存',
  'continuity-voice': '文风改稿',
  'continuity-outline': '大纲改稿',
  'continuity-dropout': '角色掉线',
  'continuity-relationship': '关系推进',
  'precision-rewrite': '精细改稿',
  'external-model': '外部模型稿',
}

const SOURCE_TYPES: Record<string, CandidateDraftTagType> = {
  'workbench-generate': 'info',
  'chapter-editor': 'default',
  'continuity-voice': 'warning',
  'continuity-outline': 'warning',
  'continuity-dropout': 'warning',
  'continuity-relationship': 'warning',
  'precision-rewrite': 'warning',
  'external-model': 'info',
}

const FOCUS_LABELS: Record<string, string> = {
  'voice-drift': '文风漂移',
  'outline-deviation': '大纲偏离',
  'character-continuity': '角色连续性',
  'precision-rewrite': '精细改稿',
}

const REWRITE_TASK_SOURCES = new Set([
  'continuity-voice',
  'continuity-outline',
  'continuity-dropout',
  'continuity-relationship',
  'precision-rewrite',
])

function stringFromMetadata(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function hasRewriteTaskParent(draft: ChapterCandidateDraftDTO): boolean {
  return Boolean(stringFromMetadata(draft.metadata?.rewrite_task_id))
}

export function candidateDraftSourceLabel(source: string): string {
  return SOURCE_LABELS[source] || source || '未知来源'
}

export function candidateDraftSourceType(source: string): CandidateDraftTagType {
  return SOURCE_TYPES[source] || 'default'
}

export function candidateDraftFocusTags(draft: ChapterCandidateDraftDTO): string[] {
  const metadata = draft.metadata || {}
  const tags: string[] = []
  const focus = stringFromMetadata(metadata.rewrite_focus)
  const characterName = stringFromMetadata(metadata.character_name)
  const outlineStatus = stringFromMetadata(metadata.outline_status)

  if (focus) {
    tags.push(FOCUS_LABELS[focus] || focus)
  }
  if (characterName) {
    tags.push(`角色：${characterName}`)
  }
  if (outlineStatus) {
    tags.push(`大纲：${outlineStatus}`)
  }

  return tags
}

export function candidateDraftLineageTags(draft: ChapterCandidateDraftDTO): string[] {
  if (hasRewriteTaskParent(draft)) {
    return ['任务生成']
  }
  return []
}

export function isCandidateRewriteTask(draft: ChapterCandidateDraftDTO): boolean {
  return REWRITE_TASK_SOURCES.has(draft.source) && !hasRewriteTaskParent(draft)
}

export function candidateDraftRewritePrompt(draft: ChapterCandidateDraftDTO): string {
  const tags = candidateDraftFocusTags(draft)
  const tagLine = tags.length ? `处理目标：${tags.join('、')}` : ''
  const rationale = draft.rationale?.trim() || '根据候选改稿任务修订当前章节。'

  return [
    `第${draft.chapter_number}章候选改稿任务`,
    tagLine,
    rationale,
    '请在保留现有主线事实和关键事件的前提下，生成一版可直接进入候选稿区的修订正文。',
  ].filter(Boolean).join('\n\n')
}

export function candidateDraftMemoryImpactHints(draft: ChapterCandidateDraftDTO): string[] {
  const hints = [
    '写入主稿正文',
    `创建 ${draft.branch_name || 'main'} 分支快照`,
    '触发章后记忆更新',
  ]
  const focus = stringFromMetadata(draft.metadata?.rewrite_focus)
  const externalModel = stringFromMetadata(draft.metadata?.external_model)
  const rewriteTaskId = stringFromMetadata(draft.metadata?.rewrite_task_id)

  if (focus) {
    hints.push(`改稿焦点：${FOCUS_LABELS[focus] || focus}`)
  }
  if (externalModel) {
    hints.push(`外部模型稿：${externalModel}`)
  }
  if (rewriteTaskId) {
    hints.push('关联候选改稿任务')
  }

  return hints
}
