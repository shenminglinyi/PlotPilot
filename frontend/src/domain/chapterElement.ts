export type ChapterElementTagType = 'error' | 'warning' | 'info' | 'success' | 'default'

export interface ChapterElementOption {
  label: string
  value: string
}

const ELEMENT_TYPE_META: Record<string, { label: string; tagType: ChapterElementTagType }> = {
  character: { label: '人物', tagType: 'error' },
  location: { label: '地点', tagType: 'success' },
  item: { label: '道具', tagType: 'warning' },
  organization: { label: '组织', tagType: 'info' },
  event: { label: '事件', tagType: 'default' },
}

const RELATION_TYPE_META: Record<string, { label: string }> = {
  appears: { label: '出场' },
  mentioned: { label: '提及' },
  scene: { label: '场景' },
  uses: { label: '使用' },
  involved: { label: '参与' },
  occurs: { label: '发生' },
}

const IMPORTANCE_META: Record<string, { label: string; tagType: ChapterElementTagType }> = {
  major: { label: '主要', tagType: 'error' },
  normal: { label: '一般', tagType: 'info' },
  minor: { label: '次要', tagType: 'default' },
}

export const CHAPTER_ELEMENT_TYPE_OPTIONS: ChapterElementOption[] = Object.entries(ELEMENT_TYPE_META)
  .map(([value, meta]) => ({ value, label: meta.label }))

export const CHAPTER_ELEMENT_RELATION_TYPE_OPTIONS: ChapterElementOption[] = Object.entries(RELATION_TYPE_META)
  .map(([value, meta]) => ({ value, label: meta.label }))

export const CHAPTER_ELEMENT_IMPORTANCE_OPTIONS: ChapterElementOption[] = Object.entries(IMPORTANCE_META)
  .map(([value, meta]) => ({ value, label: meta.label }))

export function getChapterElementTypeLabel(type?: string | null): string {
  const key = String(type || '')
  return ELEMENT_TYPE_META[key]?.label ?? key
}

export function getChapterElementTypeTagType(type?: string | null): ChapterElementTagType {
  const key = String(type || '')
  return ELEMENT_TYPE_META[key]?.tagType ?? 'default'
}

export function getChapterElementRelationLabel(relation?: string | null): string {
  const key = String(relation || '')
  return RELATION_TYPE_META[key]?.label ?? key
}

export function getChapterElementImportanceLabel(importance?: string | null): string {
  const key = String(importance || '')
  return IMPORTANCE_META[key]?.label ?? key
}

export function getChapterElementImportanceTagType(importance?: string | null): ChapterElementTagType {
  const key = String(importance || '')
  return IMPORTANCE_META[key]?.tagType ?? 'default'
}
