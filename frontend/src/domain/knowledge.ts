export type KnowledgeTagType = 'success' | 'warning' | 'default'

export interface KnowledgeOption {
  label: string
  value: string
}

const ENTITY_TYPE_META: Record<string, { label: string }> = {
  character: { label: '人物' },
  location: { label: '地点' },
}

const CHARACTER_IMPORTANCE_META: Record<string, { label: string; compactLabel: string }> = {
  primary: { label: '主角', compactLabel: '主角' },
  secondary: { label: '重要配角', compactLabel: '重要配角' },
  minor: { label: '次要人物', compactLabel: '次要人物' },
}

const LOCATION_IMPORTANCE_META: Record<string, {
  label: string
  compactLabel: string
  tagType: KnowledgeTagType
}> = {
  core: { label: '核心地点', compactLabel: '核心', tagType: 'success' },
  important: { label: '重要地点', compactLabel: '重要', tagType: 'warning' },
  normal: { label: '一般地点', compactLabel: '一般', tagType: 'default' },
}

const LOCATION_TYPE_META: Record<string, { label: string; detailLabel: string; previewLabel: string }> = {
  city: { label: '城市', detailLabel: '城市', previewLabel: '城市' },
  region: { label: '区域', detailLabel: '区域', previewLabel: '区域' },
  building: { label: '建筑', detailLabel: '建筑', previewLabel: '建筑' },
  faction: { label: '势力', detailLabel: '势力', previewLabel: '势力' },
  realm: { label: '领域', detailLabel: '境界/领域', previewLabel: '秘境' },
}

export const KNOWLEDGE_ENTITY_TYPE_OPTIONS: KnowledgeOption[] = Object.entries(ENTITY_TYPE_META)
  .map(([value, meta]) => ({ value, label: meta.label }))

export const CHARACTER_IMPORTANCE_OPTIONS: KnowledgeOption[] = Object.entries(CHARACTER_IMPORTANCE_META)
  .map(([value, meta]) => ({ value, label: meta.label }))

export const LOCATION_IMPORTANCE_OPTIONS: KnowledgeOption[] = Object.entries(LOCATION_IMPORTANCE_META)
  .map(([value, meta]) => ({ value, label: meta.label }))

export const LOCATION_TYPE_OPTIONS: KnowledgeOption[] = Object.entries(LOCATION_TYPE_META)
  .map(([value, meta]) => ({ value, label: meta.previewLabel === '秘境' ? '领域' : meta.label }))

export const LOCATION_PREVIEW_TYPE_ORDER = ['城市', '区域', '建筑', '势力', '秘境', '其他']

export function getKnowledgeEntityTypeLabel(type?: string | null): string {
  const key = String(type || '').trim()
  return ENTITY_TYPE_META[key]?.label ?? key
}

export function getCharacterImportanceLabel(importance?: string | null): string {
  const key = String(importance || '').trim()
  return CHARACTER_IMPORTANCE_META[key]?.label ?? ''
}

export function getLocationImportanceLabel(importance?: string | null, compact = false): string {
  const key = String(importance || '').trim()
  const meta = LOCATION_IMPORTANCE_META[key]
  if (!meta) return compact ? '' : key
  return compact ? meta.compactLabel : meta.label
}

export function getLocationImportanceTagType(importance?: string | null): KnowledgeTagType {
  const key = String(importance || '').trim()
  return LOCATION_IMPORTANCE_META[key]?.tagType ?? 'default'
}

export function getLocationTypeLabel(type?: string | null): string {
  const key = String(type || '').trim()
  return LOCATION_TYPE_META[key]?.label ?? key
}

export function getLocationTypeDetailLabel(type?: string | null): string {
  const key = String(type || '').trim()
  return LOCATION_TYPE_META[key]?.detailLabel ?? key
}

export function getLocationPreviewTypeLabel(type?: string | null): string {
  const key = String(type || '').trim()
  if (!key) return '其他'
  return LOCATION_TYPE_META[key]?.previewLabel ?? key
}

export function getKnowledgeImportanceOptions(entityType?: string | null): KnowledgeOption[] {
  if (entityType === 'character') return CHARACTER_IMPORTANCE_OPTIONS
  if (entityType === 'location') return LOCATION_IMPORTANCE_OPTIONS
  return []
}
