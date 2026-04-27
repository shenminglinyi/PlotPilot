import type { ChapterCandidateDraftDTO } from '@/api/chapter'

export type CandidateDraftTagType = 'default' | 'info' | 'success' | 'warning' | 'error'

const SOURCE_LABELS: Record<string, string> = {
  'workbench-generate': '工作台生成',
  'chapter-editor': '章节页保存',
  'continuity-voice': '文风改稿',
  'continuity-outline': '大纲改稿',
  'continuity-dropout': '角色掉线',
  'continuity-relationship': '关系推进',
}

const SOURCE_TYPES: Record<string, CandidateDraftTagType> = {
  'workbench-generate': 'info',
  'chapter-editor': 'default',
  'continuity-voice': 'warning',
  'continuity-outline': 'warning',
  'continuity-dropout': 'warning',
  'continuity-relationship': 'warning',
}

const FOCUS_LABELS: Record<string, string> = {
  'voice-drift': '文风漂移',
  'outline-deviation': '大纲偏离',
  'character-continuity': '角色连续性',
}

function stringFromMetadata(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
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
