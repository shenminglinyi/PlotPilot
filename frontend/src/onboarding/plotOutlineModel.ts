import type { PlotOutlineDTO } from '@/api/workflow'
import type { InvocationVariableBinding } from '@/api/aiInvocation'
import { extractBoundOutputMaps, parseJsonLikeRecord } from '@/utils/invocationOutput'

export type PlotOutlineStatus = 'idle' | 'creating' | 'reviewing' | 'generating' | 'committing' | 'done' | 'error'
export type PlotOutlineProgressState = 'pending' | 'active' | 'done'

export interface PlotOutlineProgressItem {
  key: string
  label: string
  desc: string
  state: PlotOutlineProgressState
}

export const PLOT_OUTLINE_META_KEYS = new Set(['stage_plan'])
export const PLOT_STAGE_META_KEYS = new Set(['phase', 'label', 'range_percent', 'chapter_start', 'chapter_end', 'key_goals'])

export const PLOT_FIELD_LABELS: Record<string, string> = {
  main_story_overview: '故事主线概述',
  core_conflict: '核心冲突',
  expected_ending: '预期结局',
  summary: '阶段任务',
}

const PLOT_OVERVIEW_KEYS = ['main_story_overview', 'outline_main', 'main_axis', 'overview', 'story_overview', '故事主线概述', '主线概述', '故事概述']
const PLOT_ENDING_KEYS = ['expected_ending', 'ending_expect', 'ending_expectation', 'expectedEnding', 'ending', 'finale', '预期结局', '预期结尾', '结局预期', '故事最终走向']
const PLOT_CONFLICT_KEYS = ['core_conflict', 'coreConflict', 'conflict', 'main_conflict', '核心冲突', '核心矛盾', '核心对抗']
const PLOT_STAGE_KEYS = ['stage_plan', 'stages', '阶段规划']

const LEGACY_STAGE_KEY_ALIASES = [
  ['stage_opening_1_15', 'stage_opening', 'opening'],
  ['stage_develop_15_40', 'stage_develop', 'development'],
  ['stage_deepen_40_70', 'stage_deepen', 'deepening'],
  ['stage_climax_70_90', 'stage_climax', 'climax'],
  ['stage_end_90_100', 'stage_end', 'stage_ending', 'ending'],
] as const

const STAGE_PHASE_META = [
  { phase: 'opening', label: '开篇阶段', range_percent: '1-15%' },
  { phase: 'development', label: '发展阶段', range_percent: '15-40%' },
  { phase: 'deepening', label: '深化阶段', range_percent: '40-70%' },
  { phase: 'climax', label: '高潮阶段', range_percent: '70-90%' },
  { phase: 'ending', label: '收尾阶段', range_percent: '90-100%' },
] as const

export function createEmptyPlotOutline(): PlotOutlineDTO {
  return {
    main_story_overview: '',
    core_conflict: '',
    expected_ending: '',
    stage_plan: [],
  }
}

export function parsePlotLabeledSections(text: string): Record<string, string> {
  const source = String(text || '').trim()
  if (!source) return {}
  const labels = ['阶段任务', '冲突变化', '角色成长', '关键剧情节点', '关键剧情', '核心冲突', '预期结局']
  const pattern = new RegExp(`(${labels.join('|')})\\s*[：:]`, 'g')
  const matches = [...source.matchAll(pattern)]
  if (matches.length < 2) return {}
  const fields: Record<string, string> = {}
  for (let i = 0; i < matches.length; i++) {
    const match = matches[i]
    const key = match[1]
    const start = (match.index || 0) + match[0].length
    const end = i + 1 < matches.length ? matches[i + 1].index || source.length : source.length
    const value = source.slice(start, end).trim()
    if (!value) continue
    fields[key === '阶段任务' ? 'summary' : key] = value
  }
  return fields
}

export function clonePlotOutline(outline: PlotOutlineDTO | null | undefined): PlotOutlineDTO {
  if (!outline) return createEmptyPlotOutline()
  return {
    ...outline,
    main_story_overview: outline.main_story_overview || '',
    core_conflict: outline.core_conflict || '',
    expected_ending: outline.expected_ending || '',
    stage_plan: (outline.stage_plan || []).map(stage => ({
      ...stage,
      ...parsePlotLabeledSections(stage.summary || ''),
      label: stage.label || '',
      range_percent: stage.range_percent || '',
      summary: parsePlotLabeledSections(stage.summary || '').summary || stage.summary || '',
      key_goals: Array.isArray(stage.key_goals) ? [...stage.key_goals] : [],
    })),
  }
}

export function getPlotOutlineTopFieldKeys(outline: PlotOutlineDTO): string[] {
  const record = outline as unknown as Record<string, unknown>
  const keys = Object.keys(record).filter(key => !PLOT_OUTLINE_META_KEYS.has(key))
  const preferred = ['main_story_overview', 'core_conflict', 'expected_ending']
  return [
    ...preferred.filter(key => keys.includes(key)),
    ...keys.filter(key => !preferred.includes(key)),
  ]
}

export function plotFieldLabel(key: string): string {
  return PLOT_FIELD_LABELS[key] || key
}

export function plotFieldText(
  target: Record<string, unknown> | PlotOutlineDTO | PlotOutlineDTO['stage_plan'][number],
  key: string,
): string {
  const value = (target as Record<string, unknown>)[key]
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export function updatePlotField(
  target: Record<string, unknown> | PlotOutlineDTO | PlotOutlineDTO['stage_plan'][number],
  key: string,
  value: string,
) {
  ;(target as Record<string, unknown>)[key] = value
}

export function stageContentFieldKeys(stage: PlotOutlineDTO['stage_plan'][number]): string[] {
  const record = stage as unknown as Record<string, unknown>
  const keys = Object.keys(record).filter(key => !PLOT_STAGE_META_KEYS.has(key))
  return [
    ...(['summary', '冲突变化', '角色成长', '关键剧情节点'] as string[]).filter(key => keys.includes(key)),
    ...keys.filter(key => !['summary', '冲突变化', '角色成长', '关键剧情节点'].includes(key)),
  ]
}

export function buildStageRangePercentLabel(
  stage: { chapter_start?: number; chapter_end?: number; range_percent?: string },
  totalChapters: number,
): string {
  const total = Math.max(1, totalChapters)
  const start = typeof stage.chapter_start === 'number' ? stage.chapter_start : 0
  const end = typeof stage.chapter_end === 'number' ? stage.chapter_end : 0
  if (start <= 0 || end <= 0) return stage.range_percent || ''
  const startPercent = Math.max(1, Math.min(100, Math.floor(((start - 1) / total) * 100)))
  const endPercent = Math.max(startPercent, Math.min(100, Math.floor((end / total) * 100)))
  return `${startPercent}-${endPercent}%`
}

export function buildEditablePlotOutlinePayload(
  editableOutline: PlotOutlineDTO,
  totalChapters: number,
): PlotOutlineDTO {
  return {
    ...editableOutline,
    main_story_overview: editableOutline.main_story_overview.trim(),
    core_conflict: editableOutline.core_conflict.trim(),
    expected_ending: editableOutline.expected_ending.trim(),
    stage_plan: editableOutline.stage_plan.map(stage => ({
      ...stage,
      chapter_start: typeof stage.chapter_start === 'number' ? stage.chapter_start : undefined,
      chapter_end: typeof stage.chapter_end === 'number' ? stage.chapter_end : undefined,
      range_percent: buildStageRangePercentLabel(stage, totalChapters) || stage.range_percent,
      summary: String(stage.summary || '').trim(),
      key_goals: (stage.key_goals || []).map(item => String(item || '').trim()).filter(Boolean),
    })),
  }
}

export function validateEditablePlotOutline(outline: PlotOutlineDTO): string {
  const topRecord = outline as unknown as Record<string, unknown>
  const hasTopContent = Object.entries(topRecord).some(([key, value]) =>
    !PLOT_OUTLINE_META_KEYS.has(key) && String(value ?? '').trim().length > 0,
  )
  if (!hasTopContent) return '请至少保留一项总纲内容'
  if (!outline.stage_plan.length) return '请保留并填写阶段规划'
  const invalidStageRange = outline.stage_plan.find((stage) => {
    const start = stage.chapter_start
    const end = stage.chapter_end
    return typeof start !== 'number' || typeof end !== 'number' || start < 1 || end < 1 || start > end
  })
  if (invalidStageRange) return `请检查${invalidStageRange.label || '阶段'}的起止章节`
  const emptyStage = outline.stage_plan.find(stage => stageContentFieldKeys(stage).every(key => !plotFieldText(stage, key).trim()))
  if (emptyStage) return `请填写${emptyStage.label || '阶段'}的规划内容`
  return ''
}

function pickPlotString(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = record[key]
    if (value !== undefined && value !== null && String(value).trim()) {
      return String(value).trim()
    }
  }
  return ''
}

function pickPlotValue(record: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    const value = record[key]
    if (value !== undefined && value !== null && value !== '') return value
  }
  return undefined
}

function normalizeLegacyStagePlan(stagePlan: unknown): PlotOutlineDTO['stage_plan'] {
  if (!stagePlan || typeof stagePlan !== 'object' || Array.isArray(stagePlan)) return []
  const record = stagePlan as Record<string, unknown>
  return LEGACY_STAGE_KEY_ALIASES.map((aliases, index) => {
    const meta = STAGE_PHASE_META[index]
    const value = aliases.map(key => record[key]).find(item => item !== undefined && item !== null && item !== '')
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return {
        ...(value as PlotOutlineDTO['stage_plan'][number]),
        phase: meta.phase,
        label: String((value as Record<string, unknown>).label || meta.label),
        range_percent: String((value as Record<string, unknown>).range_percent || meta.range_percent),
      }
    }
    return {
      phase: meta.phase,
      label: meta.label,
      range_percent: meta.range_percent,
      summary: value ? String(value).trim() : '',
      key_goals: [],
    }
  }).filter(stage => String(stage.summary || '').trim())
}

export function normalizePlotOutlineShape(value: unknown): PlotOutlineDTO | null {
  if (!value || typeof value !== 'object') return null
  const record = value as Record<string, unknown>
  const stagePlan = pickPlotValue(record, PLOT_STAGE_KEYS)
  return {
    ...(record as Partial<PlotOutlineDTO>),
    main_story_overview: pickPlotString(record, PLOT_OVERVIEW_KEYS),
    expected_ending: pickPlotString(record, PLOT_ENDING_KEYS),
    core_conflict: pickPlotString(record, PLOT_CONFLICT_KEYS),
    stage_plan: Array.isArray(stagePlan)
      ? stagePlan as PlotOutlineDTO['stage_plan']
      : normalizeLegacyStagePlan(stagePlan),
  }
}

export function normalizePlotOutlineFromBindings(
  source: Record<string, unknown>,
  bindings: InvocationVariableBinding[],
): PlotOutlineDTO | null {
  const { byVariableKey } = extractBoundOutputMaps(source, bindings)
  const direct = byVariableKey['plot.outline']
  if (direct && typeof direct === 'object') return normalizePlotOutlineShape(direct)
  const stagePlan = byVariableKey['plot.stage_plan']
  const overview = byVariableKey['plot.main_story_overview']
  const ending = byVariableKey['plot.expected_ending']
  const conflict = byVariableKey['plot.core_conflict']
  if (!stagePlan && !overview && !ending && !conflict) return null
  return normalizePlotOutlineShape({
    main_story_overview: overview,
    expected_ending: ending,
    core_conflict: conflict,
    stage_plan: stagePlan,
  })
}

export function extractPlotOutlineFromResult(
  result: Record<string, unknown>,
  outputBindings: InvocationVariableBinding[] = [],
): PlotOutlineDTO | null {
  const direct = result.plot_outline
  if (direct && typeof direct === 'object') return normalizePlotOutlineShape(direct)
  if (outputBindings.length) {
    const boundDirect = normalizePlotOutlineFromBindings(result, outputBindings)
    if (boundDirect?.stage_plan?.length) return boundDirect
  }
  const continuation = result.continuation
  if (continuation && typeof continuation === 'object') {
    const continuationRecord = continuation as Record<string, unknown>
    const fromContinuation = continuationRecord.plot_outline
    if (fromContinuation && typeof fromContinuation === 'object') return normalizePlotOutlineShape(fromContinuation)
    if (outputBindings.length) {
      const boundContinuation = normalizePlotOutlineFromBindings(continuationRecord, outputBindings)
      if (boundContinuation?.stage_plan?.length) return boundContinuation
    }
    const normalizedContinuation = normalizePlotOutlineShape(continuationRecord)
    if (normalizedContinuation?.main_story_overview && normalizedContinuation.stage_plan?.length) return normalizedContinuation
  }
  const acceptedContent = result.accepted_content
  if (typeof acceptedContent === 'string' && acceptedContent.trim()) {
    const parsedRecord = parseJsonLikeRecord(acceptedContent)
    if (parsedRecord) {
      if (outputBindings.length) {
        const boundAccepted = normalizePlotOutlineFromBindings(parsedRecord, outputBindings)
        if (boundAccepted?.stage_plan?.length) return boundAccepted
      }
      if (parsedRecord.plot_outline) {
        return normalizePlotOutlineShape(parsedRecord.plot_outline)
      }
      const normalizedAccepted = normalizePlotOutlineShape(parsedRecord)
      if (normalizedAccepted?.main_story_overview && normalizedAccepted.stage_plan?.length) return normalizedAccepted
    }
  }
  return null
}
