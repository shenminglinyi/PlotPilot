export type CharacterRole = 'PROTAGONIST' | 'SUPPORTING' | 'MINOR'
export type CharacterMentalSeverity = 'normal' | 'active' | 'warning' | 'danger'

const CHARACTER_ROLE_META: Record<CharacterRole, {
  label: string
  cssKey: string
  color: string
  sortOrder: number
  icon: string
}> = {
  PROTAGONIST: {
    label: '主角',
    cssKey: 'protagonist',
    color: 'var(--color-brand, #2563eb)',
    sortOrder: 0,
    icon: '主',
  },
  SUPPORTING: {
    label: '配角',
    cssKey: 'supporting',
    color: 'var(--color-warning, #f59e0b)',
    sortOrder: 1,
    icon: '配',
  },
  MINOR: {
    label: '龙套',
    cssKey: 'minor',
    color: 'var(--app-text-muted)',
    sortOrder: 2,
    icon: '群',
  },
}

const ROLE_ALIASES: Record<string, CharacterRole> = {
  protagonist: 'PROTAGONIST',
  main: 'PROTAGONIST',
  lead: 'PROTAGONIST',
  hero: 'PROTAGONIST',
  supporting: 'SUPPORTING',
  support: 'SUPPORTING',
  secondary: 'SUPPORTING',
  minor: 'MINOR',
  cameo: 'MINOR',
  extra: 'MINOR',
}

const SPEECH_TEMPO_LABELS: Record<string, string> = {
  fast: '急促',
  normal: '平稳',
  slow: '舒缓',
}

const CHARACTER_FIELD_NARRATIVE_LABELS: Record<string, string> = {
  core_belief: '信念转变',
  moral_taboos: '底线调整',
  voice_profile: '声线改变',
  active_wounds: '新增创伤',
}

const MEMORY_TYPE_LABELS: Record<string, string> = {
  state: '状态',
  scar: '创伤',
  motivation: '执念',
  emotion: '情绪',
  voice: '对白',
  relationship: '关系',
  debt: '债务',
  fact: '事实',
}

export function normalizeCharacterRole(role?: string | null): CharacterRole {
  const raw = String(role || '').trim()
  if (!raw) return 'MINOR'
  const upper = raw.toUpperCase()
  if (upper === 'PROTAGONIST' || upper === 'SUPPORTING' || upper === 'MINOR') {
    return upper as CharacterRole
  }
  return ROLE_ALIASES[raw.toLowerCase()] ?? 'MINOR'
}

export function getCharacterRoleLabel(role?: string | null): string {
  return CHARACTER_ROLE_META[normalizeCharacterRole(role)].label
}

export function getCharacterRoleCssKey(role?: string | null): string {
  return CHARACTER_ROLE_META[normalizeCharacterRole(role)].cssKey
}

export function getCharacterRoleColor(role?: string | null, minorColor?: string): string {
  const normalized = normalizeCharacterRole(role)
  if (normalized === 'MINOR' && minorColor) return minorColor
  return CHARACTER_ROLE_META[normalized].color
}

export function getCharacterRoleSortOrder(role?: string | null): number {
  return CHARACTER_ROLE_META[normalizeCharacterRole(role)].sortOrder
}

export function getCharacterRoleIcon(role?: string | null): string {
  return CHARACTER_ROLE_META[normalizeCharacterRole(role)].icon
}

export function getSpeechTempoLabel(tempo?: string | null): string {
  const key = String(tempo || '').trim()
  return SPEECH_TEMPO_LABELS[key] ?? key
}

export function getCharacterFieldNarrativeLabel(field?: string | null): string {
  const key = String(field || '').trim()
  return CHARACTER_FIELD_NARRATIVE_LABELS[key] ?? key
}

export function getMemoryTypeLabel(type?: string | null): string {
  const key = String(type || '').trim()
  return MEMORY_TYPE_LABELS[key] ?? key
}

export function classifyCharacterMentalState(mental?: string | null): CharacterMentalSeverity {
  const value = String(mental || '').trim()
  if (!value || value.toUpperCase() === 'NORMAL') return 'normal'
  if (/焦虑|恐惧|崩溃|危机|绝望/.test(value)) return 'danger'
  if (/愤怒|悲伤|痛苦|压抑/.test(value)) return 'warning'
  return 'active'
}
