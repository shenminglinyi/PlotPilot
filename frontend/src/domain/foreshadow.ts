export type ForeshadowImportance = 'low' | 'medium' | 'high' | 'critical'
export type ForeshadowTagType = 'default' | 'info' | 'warning' | 'error'

export interface ForeshadowImportanceOption {
  label: string
  value: ForeshadowImportance
}

const FORESHADOW_IMPORTANCE_META: Record<ForeshadowImportance, {
  label: string
  order: number
  chipClass: string
  accentColor: string
  tagType: ForeshadowTagType
}> = {
  critical: {
    label: '危急',
    order: 4,
    chipClass: 'pp-chip--danger',
    accentColor: 'var(--color-danger)',
    tagType: 'error',
  },
  high: {
    label: '重要',
    order: 3,
    chipClass: 'pp-chip--warning',
    accentColor: 'var(--color-warning)',
    tagType: 'warning',
  },
  medium: {
    label: '一般',
    order: 2,
    chipClass: 'pp-chip--brand',
    accentColor: 'var(--color-brand)',
    tagType: 'info',
  },
  low: {
    label: '次要',
    order: 1,
    chipClass: 'pp-chip--muted',
    accentColor: 'var(--app-border)',
    tagType: 'default',
  },
}

export const FORESHADOW_IMPORTANCE_OPTIONS: ForeshadowImportanceOption[] = [
  { label: FORESHADOW_IMPORTANCE_META.critical.label, value: 'critical' },
  { label: FORESHADOW_IMPORTANCE_META.high.label, value: 'high' },
  { label: FORESHADOW_IMPORTANCE_META.medium.label, value: 'medium' },
  { label: FORESHADOW_IMPORTANCE_META.low.label, value: 'low' },
]

export function normalizeForeshadowImportance(importance?: string | null): ForeshadowImportance {
  const key = String(importance || '').trim().toLowerCase()
  if (key === 'critical' || key === 'high' || key === 'medium' || key === 'low') {
    return key
  }
  return 'medium'
}

export function getForeshadowImportanceLabel(importance?: string | null): string {
  return FORESHADOW_IMPORTANCE_META[normalizeForeshadowImportance(importance)].label
}

export function getForeshadowImportanceOrder(importance?: string | null): number {
  return FORESHADOW_IMPORTANCE_META[normalizeForeshadowImportance(importance)].order
}

export function getForeshadowImportanceChipClass(importance?: string | null): string {
  return FORESHADOW_IMPORTANCE_META[normalizeForeshadowImportance(importance)].chipClass
}

export function getForeshadowImportanceAccentColor(importance?: string | null): string {
  return FORESHADOW_IMPORTANCE_META[normalizeForeshadowImportance(importance)].accentColor
}

export function getForeshadowImportanceTagType(importance?: string | null): ForeshadowTagType {
  return FORESHADOW_IMPORTANCE_META[normalizeForeshadowImportance(importance)].tagType
}

export function compareForeshadowImportanceDesc(
  left?: string | null,
  right?: string | null,
): number {
  return getForeshadowImportanceOrder(right) - getForeshadowImportanceOrder(left)
}
