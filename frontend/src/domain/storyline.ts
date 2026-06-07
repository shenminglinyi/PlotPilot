export type NaiveTagType = 'default' | 'primary' | 'info' | 'success' | 'warning' | 'error'

export type StorylineType =
  | 'main_plot'
  | 'romance'
  | 'revenge'
  | 'mystery'
  | 'growth'
  | 'political'
  | 'adventure'
  | 'family'
  | 'friendship'
  | 'general'

export type StorylineRole = 'main' | 'sub' | 'dark'
export type StorylineStatus = 'active' | 'completed' | 'abandoned'
export type StoryPhase = 'opening' | 'development' | 'convergence' | 'finale'
export type ConfluenceMergeType = 'intersect' | 'absorb' | 'reveal'

export interface StorylineIdentity {
  storyline_type?: string | null
  role?: string | null
}

export interface SelectOption<T extends string = string> {
  label: string
  value: T
}

const STORYLINE_TYPE_META: Record<StorylineType, {
  label: string
  shortLabel?: string
  graphColor: string
  tagType: NaiveTagType
}> = {
  main_plot: { label: '主线', graphColor: '#6366f1', tagType: 'primary' },
  romance: { label: '爱情线', shortLabel: '情感', graphColor: '#ec4899', tagType: 'error' },
  revenge: { label: '复仇线', shortLabel: '复仇', graphColor: '#ef4444', tagType: 'warning' },
  mystery: { label: '悬疑线', shortLabel: '悬疑', graphColor: '#8b5cf6', tagType: 'info' },
  growth: { label: '成长线', shortLabel: '成长', graphColor: '#10b981', tagType: 'success' },
  political: { label: '政治线', shortLabel: '政治', graphColor: '#f59e0b', tagType: 'default' },
  adventure: { label: '冒险线', shortLabel: '冒险', graphColor: '#06b6d4', tagType: 'default' },
  family: { label: '家庭线', shortLabel: '家族', graphColor: '#f97316', tagType: 'default' },
  friendship: { label: '友情线', shortLabel: '友情', graphColor: '#84cc16', tagType: 'default' },
  general: { label: '通用', graphColor: '#94a3b8', tagType: 'default' },
}

const STORYLINE_TYPE_ORDER: StorylineType[] = [
  'main_plot',
  'romance',
  'revenge',
  'mystery',
  'growth',
  'political',
  'adventure',
  'family',
  'friendship',
]

export const DEFAULT_STORYLINE_TYPE: StorylineType = 'main_plot'
export const DEFAULT_STORYLINE_THEME: StorylineType = 'general'
export const DEFAULT_CONFLUENCE_MERGE_TYPE: ConfluenceMergeType = 'absorb'

export const STORYLINE_TYPE_OPTIONS: SelectOption<StorylineType>[] = STORYLINE_TYPE_ORDER.map(value => ({
  value,
  label: STORYLINE_TYPE_META[value].label,
}))

export const STORYLINE_THEME_OPTIONS: SelectOption<StorylineType>[] = [
  { value: 'general', label: STORYLINE_TYPE_META.general.label },
  ...STORYLINE_TYPE_ORDER.filter(value => value !== 'main_plot').map(value => ({
    value,
    label: STORYLINE_TYPE_META[value].shortLabel ?? STORYLINE_TYPE_META[value].label,
  })),
]

export const CONFLUENCE_MERGE_TYPE_OPTIONS: SelectOption<ConfluenceMergeType>[] = [
  { label: '吸收（支线完结并入主线）', value: 'absorb' },
  { label: '交叉（两线继续并行）', value: 'intersect' },
  { label: '揭露（暗线首次显现）', value: 'reveal' },
]

const ROLE_META: Record<StorylineRole, {
  label: string
  compactLabel: string
  tagType: NaiveTagType
  cssKey: string
}> = {
  main: { label: '主线', compactLabel: '主', tagType: 'success', cssKey: 'main' },
  sub: { label: '支线', compactLabel: '支', tagType: 'warning', cssKey: 'sub' },
  dark: { label: '暗线', compactLabel: '暗', tagType: 'default', cssKey: 'dark' },
}

const STATUS_META: Record<StorylineStatus, { label: string; tagType: NaiveTagType }> = {
  active: { label: '进行中', tagType: 'success' },
  completed: { label: '已完成', tagType: 'info' },
  abandoned: { label: '已废弃', tagType: 'default' },
}

export const STORY_PHASE_STAGES: SelectOption<StoryPhase>[] = [
  { key: 'opening', label: '开局' },
  { key: 'development', label: '发展' },
  { key: 'convergence', label: '收敛' },
  { key: 'finale', label: '终局' },
].map(({ key, label }) => ({ value: key as StoryPhase, label }))

export const STORY_PHASE_ORDER = STORY_PHASE_STAGES.map(stage => stage.value)

const STORY_PHASE_LABELS: Record<string, string> = {
  opening: '开局期',
  development: '发展期',
  convergence: '收敛期',
  finale: '终局期',
  setup: '设定阶段',
  rising_action: '冲突升级',
  crisis: '危机阶段',
  climax: '高潮阶段',
  resolution: '收束阶段',
}

const STORY_PHASE_HINTS: Record<StoryPhase, string> = {
  opening: '铺陈悬念，埋设伏笔，建立世界观',
  development: '激化矛盾，引入支线，角色成长',
  convergence: '禁止开新坑，强制填坑，收敛线索',
  finale: '终极对决，切断日常，揭晓谜底',
}

const STORY_PHASE_COLORS: Record<StoryPhase, string> = {
  opening: 'var(--color-info)',
  development: 'var(--color-brand)',
  convergence: 'var(--color-warning)',
  finale: 'var(--color-gold)',
}

const LEGACY_PHASE_MAP: Record<string, StoryPhase> = {
  setup: 'opening',
  rising_action: 'development',
  crisis: 'development',
  climax: 'convergence',
  resolution: 'finale',
}

export function normalizeStorylineType(type?: string | null): string {
  const normalized = String(type || '').trim().toLowerCase()
  if (normalized === 'main_plot' || normalized === 'main' || normalized === 'mainplot') return 'main_plot'
  if (normalized === 'sub_plot') return 'general'
  if (normalized === 'dark_line') return 'mystery'
  return normalized
}

export function normalizeStorylineRole(role?: string | null): string {
  const normalized = String(role || '').trim().toLowerCase()
  if (normalized === 'main_plot') return 'main'
  if (normalized === 'sub_plot') return 'sub'
  if (normalized === 'dark_line') return 'dark'
  return normalized
}

export function normalizeStorylineStatus(status?: string | null): string {
  return String(status || '').trim().toLowerCase()
}

export function isMainStoryline(storyline: StorylineIdentity): boolean {
  return normalizeStorylineRole(storyline.role) === 'main'
    || normalizeStorylineType(storyline.storyline_type) === 'main_plot'
}

export function getStorylineTypeLabel(type?: string | null, compact = false): string {
  const key = normalizeStorylineType(type) as StorylineType
  const meta = STORYLINE_TYPE_META[key]
  if (!meta) return String(type || '')
  return compact ? (meta.shortLabel ?? meta.label) : meta.label
}

export function getStorylineTypeTagType(type?: string | null): NaiveTagType {
  const key = normalizeStorylineType(type) as StorylineType
  return STORYLINE_TYPE_META[key]?.tagType ?? 'default'
}

export function getStorylineGraphColor(type?: string | null): string {
  const key = normalizeStorylineType(type) as StorylineType
  return STORYLINE_TYPE_META[key]?.graphColor ?? STORYLINE_TYPE_META.general.graphColor
}

export function getStorylineRoleLabel(role?: string | null): string {
  const key = normalizeStorylineRole(role) as StorylineRole
  return ROLE_META[key]?.label ?? role ?? '未知'
}

export function getStorylineRoleCompactLabel(role?: string | null): string {
  const key = normalizeStorylineRole(role) as StorylineRole
  return ROLE_META[key]?.compactLabel ?? role ?? ''
}

export function getStorylineRoleTagType(role?: string | null): NaiveTagType {
  const key = normalizeStorylineRole(role) as StorylineRole
  return ROLE_META[key]?.tagType ?? 'default'
}

export function getStorylineRoleCssKey(role?: string | null): string {
  const key = normalizeStorylineRole(role) as StorylineRole
  return ROLE_META[key]?.cssKey ?? 'default'
}

export function getStorylineStatusLabel(status?: string | null): string {
  const key = normalizeStorylineStatus(status) as StorylineStatus
  return STATUS_META[key]?.label ?? status ?? ''
}

export function getStorylineStatusTagType(status?: string | null): NaiveTagType {
  const key = normalizeStorylineStatus(status) as StorylineStatus
  return STATUS_META[key]?.tagType ?? 'default'
}

export function normalizeStoryPhase(phase?: string | null): StoryPhase | string {
  const key = String(phase || '').trim().toLowerCase()
  return LEGACY_PHASE_MAP[key] ?? key
}

export function getStoryPhaseLabel(phase?: string | null): string {
  const key = String(phase || '').trim().toLowerCase()
  return STORY_PHASE_LABELS[key] ?? key
}

export function getStoryPhaseHint(phase?: string | null): string {
  const normalized = normalizeStoryPhase(phase) as StoryPhase
  return STORY_PHASE_HINTS[normalized] ?? ''
}

export function getStoryPhaseColor(phase?: string | null): string {
  const normalized = normalizeStoryPhase(phase) as StoryPhase
  return STORY_PHASE_COLORS[normalized] ?? 'var(--color-brand)'
}

export function getStoryPhaseTagType(phase?: string | null): NaiveTagType {
  const normalized = normalizeStoryPhase(phase)
  const index = STORY_PHASE_ORDER.indexOf(normalized as StoryPhase)
  if (index <= 0) return 'info'
  if (index === 1) return 'warning'
  if (index === 2) return 'error'
  return 'success'
}

export function isStoryPhasePast(stage: string, current?: string | null): boolean {
  return STORY_PHASE_ORDER.indexOf(stage as StoryPhase)
    < STORY_PHASE_ORDER.indexOf(normalizeStoryPhase(current) as StoryPhase)
}

export function getConfluenceLabel(type?: string | null): string {
  const labels: Record<string, string> = {
    intersect: '交叉',
    absorb: '并入',
    reveal: '显影',
  }
  return labels[String(type || '').trim()] ?? String(type || '')
}

export function getConfluenceMarker(type?: string | null): string {
  return type === 'reveal' ? '◎' : '▶'
}

export function getConfluenceTooltipLabel(type?: string | null): string {
  return type === 'reveal' ? '揭露点' : '汇流至主线'
}
