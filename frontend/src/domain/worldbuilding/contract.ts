import contractBundle from './contract.bundle.json'

type WorldbuildingDimensionConfig = {
  label?: string
  fields?: Record<string, string>
  scope_hints?: Record<string, string>
}

type WorldbuildingContractBundle = {
  dimensions?: Record<string, WorldbuildingDimensionConfig>
  json_key_labels?: Record<string, string>
}

const contract = contractBundle as WorldbuildingContractBundle

const FIELD_SHORT_LABELS: Record<string, string> = {
  power_system: '力量体系',
  physics_rules: '底层规律',
  magic_tech: '技术机制',
  terrain: '地理版图',
  climate: '气候环境',
  resources: '资源分布',
  ecology: '生态危险',
  politics: '权力结构',
  economy: '经济流通',
  class_system: '阶层秩序',
  history: '历史旧案',
  religion: '信仰体系',
  taboos: '禁忌后果',
  food_clothing: '日常生活',
  language_slang: '语言俚语',
  entertainment: '娱乐消遣',
}

export function getDimensionFieldOrder(dimKey: string): string[] {
  return Object.keys(contract.dimensions?.[dimKey]?.fields || {})
}

export function getWorldbuildingDimensionLabel(dimKey: string): string {
  return contract.dimensions?.[dimKey]?.label || getWorldbuildingLabel(dimKey)
}

export function getWorldbuildingFieldLabel(fieldKey: string): string {
  return FIELD_SHORT_LABELS[fieldKey] || getWorldbuildingLabel(fieldKey)
}

export function getWorldbuildingLabel(key: string): string {
  const direct = contract.json_key_labels?.[key]
  if (direct) return direct

  for (const dimension of Object.values(contract.dimensions || {})) {
    const fieldLabel = dimension.fields?.[key]
    if (fieldLabel) return fieldLabel
  }

  return key
}
