import { STAGE_BY_KEY } from '@/constants/aiCallStages'

export type TraceTagType = 'default' | 'info' | 'success' | 'warning' | 'error'

export interface TraceSelectOption {
  label: string
  value: string
}

const TRACE_NODE_TYPE_META: Record<string, { label: string; tagType: TraceTagType }> = {
  dag_node: { label: 'DAG', tagType: 'info' },
  guardrail: { label: '护栏', tagType: 'warning' },
  checkpoint: { label: '快照', tagType: 'success' },
  character_psyche: { label: '心理画像', tagType: 'error' },
}

export const TRACE_NODE_TYPE_OPTIONS: TraceSelectOption[] = [
  { label: 'DAG 节点', value: 'dag_node' },
  { label: '质量护栏', value: 'guardrail' },
  { label: 'Checkpoint', value: 'checkpoint' },
  { label: '角色心理', value: 'character_psyche' },
]

const AI_STAGE_SEMANTIC_TAG_TYPES: Record<string, TraceTagType> = {
  plan: 'info',
  write: 'success',
  audit: 'warning',
  sync: 'default',
  review: 'error',
  generate: 'info',
}

export function getTraceNodeTypeLabel(type?: string | null): string {
  const key = String(type || '')
  return TRACE_NODE_TYPE_META[key]?.label ?? key
}

export function getTraceNodeTypeTagType(type?: string | null): TraceTagType {
  const key = String(type || '')
  return TRACE_NODE_TYPE_META[key]?.tagType ?? 'default'
}

export function getAiStageTagType(stage?: string | null): TraceTagType {
  const key = String(stage || '')
  const semantic = STAGE_BY_KEY[key]?.semantic
  return semantic ? AI_STAGE_SEMANTIC_TAG_TYPES[semantic] ?? 'default' : 'default'
}

export function getScoreColor(score: number | null | undefined): string {
  if (score == null) return 'inherit'
  if (score >= 0.75) return '#10b981'
  if (score >= 0.5) return '#f59e0b'
  return '#ef4444'
}
