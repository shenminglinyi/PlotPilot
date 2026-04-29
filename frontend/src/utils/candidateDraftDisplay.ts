import type { ChapterCandidateDraftDTO } from '@/api/chapter'

export type CandidateDraftTagType = 'default' | 'info' | 'success' | 'warning' | 'error'

export interface CandidateDraftMemoryImpactItem {
  label: string
  detail: string
  type: CandidateDraftTagType
}

const SOURCE_LABELS: Record<string, string> = {
  'workbench-generate': '工作台生成',
  'chapter-editor': '章节页保存',
  'continuity-voice': '文风改稿',
  'continuity-outline': '大纲改稿',
  'continuity-dropout': '角色掉线',
  'continuity-relationship': '关系推进',
  'precision-rewrite': '精细改稿',
  'partial-accept': '部分采纳',
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
  'partial-accept': 'success',
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

export function candidateDraftMemoryImpactPreview(draft: ChapterCandidateDraftDTO): CandidateDraftMemoryImpactItem[] {
  const metadata = draft.metadata || {}
  const focus = stringFromMetadata(metadata.rewrite_focus)
  const externalModel = stringFromMetadata(metadata.external_model)
  const partialSourceDraftId = stringFromMetadata(metadata.partial_source_draft_id)
  const warningReasons = Array.isArray(metadata.warning_reasons)
    ? metadata.warning_reasons.filter((item): item is string => typeof item === 'string')
    : []

  const items: CandidateDraftMemoryImpactItem[] = [
    {
      label: '正文事实',
      detail: '采纳后章后记忆会重新抽取本章事实、事件和实体证据。',
      type: 'info',
    },
  ]

  if (focus === 'character-continuity' || draft.source === 'continuity-relationship') {
    items.push({
      label: '角色关系',
      detail: '可能更新角色共现、关系推进、掉线修复或冲突状态。',
      type: 'warning',
    })
  }

  if (focus === 'outline-deviation' || warningReasons.length > 0) {
    items.push({
      label: '大纲节点',
      detail: warningReasons.length ? warningReasons.join('；') : '可能改变本章对大纲节点的完成状态。',
      type: 'warning',
    })
  }

  if (draft.source === 'continuity-dropout') {
    items.push({
      label: '出场记录',
      detail: '可能修复角色长时间未出场造成的连续性缺口。',
      type: 'warning',
    })
  }

  if (externalModel) {
    items.push({
      label: '外部模型回稿',
      detail: `来自 ${externalModel}，采纳前建议重点核对设定、事实和语气是否越权。`,
      type: 'info',
    })
  }

  if (partialSourceDraftId) {
    items.push({
      label: '部分采纳',
      detail: '只会把所选候选段落混入主稿，其余段落保持当前主稿版本。',
      type: 'success',
    })
  }

  return items
}
