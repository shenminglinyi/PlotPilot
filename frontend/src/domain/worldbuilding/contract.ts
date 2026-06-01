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

export function getDimensionFieldOrder(dimKey: string): string[] {
  return Object.keys(contract.dimensions?.[dimKey]?.fields || {})
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
