/** 知识三元组在图表中的中文展示（与后端 importance / location_type 枚举对齐） */

import {
  getCharacterImportanceLabel,
  getLocationImportanceLabel,
  getLocationTypeLabel,
} from '@/domain/knowledge'

export function tripleStringAttrs(t: { attributes?: Record<string, unknown> }): Record<string, string> {
  const a = t.attributes
  if (!a || typeof a !== 'object') return {}
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(a)) {
    if (v !== undefined && v !== null) out[k] = String(v)
  }
  return out
}

export function characterImportanceZh(v?: string): string {
  return getCharacterImportanceLabel(v)
}

export function locationImportanceZh(v?: string): string {
  return getLocationImportanceLabel(v, true)
}

export function locationTypeZh(v?: string): string {
  return getLocationTypeLabel(v)
}
