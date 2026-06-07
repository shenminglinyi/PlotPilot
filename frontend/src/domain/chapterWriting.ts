export type ChapterTagType = 'error' | 'warning' | 'info' | 'success' | 'default'
export type GuardrailSeverityTagType = Exclude<ChapterTagType, 'success'>
export type BeatFocusTone = 'info' | 'success' | 'warning' | 'danger' | 'neutral'
export type GuardrailMode = 'advise' | 'enforce'

export interface ChapterOption<T extends string = string> {
  label: string
  value: T
}

const BEAT_FOCUS_META: Record<string, { label: string; tone: BeatFocusTone }> = {
  sensory: { label: '感官', tone: 'info' },
  dialogue: { label: '对话', tone: 'success' },
  action: { label: '动作', tone: 'warning' },
  emotion: { label: '情绪', tone: 'danger' },
  pacing: { label: '节奏', tone: 'neutral' },
  mixed: { label: '混合', tone: 'neutral' },
  outline_ref: { label: '大纲参考', tone: 'neutral' },
  narrative_ref: { label: '叙事节拍', tone: 'info' },
  transition: { label: '过渡', tone: 'info' },
}

const BEAT_FUNCTION_LABELS: Record<string, string> = {
  setup: '铺设',
  pressure: '加压',
  payoff: '兑现',
  reveal: '揭示',
  transition: '转场',
  aftermath: '余波',
  hook: '钩子',
}

const CHAPTER_PACING_LABELS: Record<string, string> = {
  slow: '慢',
  medium: '中',
  fast: '快',
}

const CHAPTER_QUALITY_LABELS: Record<string, string> = {
  coherence: '连贯性',
  pacing: '节奏感',
  dialogue: '对话质量',
  description: '描写质量',
  emotion: '情感表达',
  consistency: '一致性',
}

const CAST_IMPORTANCE_META: Record<string, { tierLabel: string }> = {
  major: { tierLabel: 'T0' },
  normal: { tierLabel: 'T1' },
  minor: { tierLabel: 'T2' },
}

const SCENE_FUNCTION_LABELS: Record<string, string> = {
  pov: '视角位',
  conflict: '冲突位',
  informant: '信息位',
  mirror: '镜像位',
  foreshadow_carrier: '伏笔位',
  support: '支撑位',
  explicit_scene_cast: '明确出场',
  walk_on: '过场人物',
}

const CAST_RECOMMENDATION_META: Record<string, { label: string; cssKey: string }> = {
  create_bible_character: { label: '建档', cssKey: 'create' },
  ephemeral: { label: '本章路人', cssKey: 'ephemeral' },
  ignore: { label: '忽略', cssKey: 'ignore' },
}

const GUARDRAIL_SEVERITY_META: Record<string, { label: string; tagType: GuardrailSeverityTagType }> = {
  critical: { label: '严重', tagType: 'error' },
  error: { label: '严重', tagType: 'error' },
  important: { label: '重要', tagType: 'warning' },
  warning: { label: '重要', tagType: 'warning' },
  minor: { label: '轻微', tagType: 'info' },
  info: { label: '轻微', tagType: 'info' },
}

const GUARDRAIL_DIMENSION_LABELS: Record<string, string> = {
  language_style: '语言风格',
  character_consistency: '角色一致性',
  plot_density: '情节密度',
  naming: '命名',
  viewpoint: '视角',
  rhythm: '节奏',
}

export const GUARDRAIL_MODE_OPTIONS: ChapterOption<GuardrailMode>[] = [
  { label: '建议模式', value: 'advise' },
  { label: '强制模式', value: 'enforce' },
]

export function getBeatFocusLabel(focus?: string | null): string {
  const key = String(focus || '').trim()
  return BEAT_FOCUS_META[key]?.label ?? (key || '节拍')
}

export function getBeatFocusTone(focus?: string | null): BeatFocusTone {
  const key = String(focus || '').trim()
  return BEAT_FOCUS_META[key]?.tone ?? 'neutral'
}

export function getBeatFunctionLabel(value?: string | null): string {
  const key = String(value || '').trim()
  return BEAT_FUNCTION_LABELS[key] ?? key
}

export function getChapterPacingLabel(pacing?: string | null): string {
  const key = String(pacing || '').trim()
  return CHAPTER_PACING_LABELS[key] ?? (key || '—')
}

export function getChapterQualityLabel(key?: string | null): string {
  const value = String(key || '').trim()
  return CHAPTER_QUALITY_LABELS[value] ?? value
}

export function getCastImportanceTierLabel(importance?: string | null): string {
  const key = String(importance || '').trim()
  return CAST_IMPORTANCE_META[key]?.tierLabel ?? 'T2'
}

export function getSceneFunctionLabel(value?: string | null): string {
  const key = String(value || '').trim()
  return SCENE_FUNCTION_LABELS[key] ?? '支撑位'
}

export function getCastRecommendationLabel(value?: unknown): string {
  const key = String(value || '').trim()
  return CAST_RECOMMENDATION_META[key]?.label ?? '无动作'
}

export function getCastRecommendationCssKey(value?: unknown): string {
  const key = String(value || '').trim()
  return CAST_RECOMMENDATION_META[key]?.cssKey ?? 'ignore'
}

export function getGuardrailScoreColor(score: number): string {
  if (score >= 0.75) return '#10b981'
  if (score >= 0.5) return '#f59e0b'
  return '#ef4444'
}

export function getGuardrailSeverityTagType(severity?: string | null): GuardrailSeverityTagType {
  const key = String(severity || '').trim().toLowerCase()
  return GUARDRAIL_SEVERITY_META[key]?.tagType ?? 'default'
}

export function getGuardrailSeverityLabel(severity?: string | null): string {
  const key = String(severity || '').trim().toLowerCase()
  return GUARDRAIL_SEVERITY_META[key]?.label ?? (String(severity || '').trim() || '—')
}

export function getGuardrailDimensionLabel(key?: string | null): string {
  const value = String(key || '').trim()
  return GUARDRAIL_DIMENSION_LABELS[value] ?? value
}
