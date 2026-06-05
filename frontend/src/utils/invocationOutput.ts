import type { InvocationVariableBinding } from '@/api/aiInvocation'

export function parseJsonLikeRecord(raw: string): Record<string, unknown> | null {
  const trimmed = raw.trim()
  if (!trimmed) return null
  const candidates = [
    trimmed,
    extractJsonFromMarkdown(trimmed),
    extractOuterJson(trimmed),
  ].filter(Boolean) as string[]
  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate) as unknown
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>
      }
    } catch {
      // Try the next candidate. LLM output often includes prose or code fences.
    }
  }
  return null
}

export function extractJsonFromMarkdown(raw: string): string {
  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i)
  return fenced?.[1]?.trim() || ''
}

export function extractOuterJson(raw: string): string {
  const start = raw.indexOf('{')
  const end = raw.lastIndexOf('}')
  if (start < 0 || end <= start) return ''
  return raw.slice(start, end + 1).trim()
}

export function pickPath(source: unknown, path: string): unknown {
  if (source == null || !path) return undefined
  const normalized = path.trim()
  if (!normalized || normalized === '$') return source
  const input = normalized.startsWith('$.')
    ? normalized.slice(2)
    : normalized.startsWith('$')
      ? normalized.slice(1).replace(/^\./, '')
      : normalized

  let current: unknown = source
  for (const segment of input.split('.').filter(Boolean)) {
    current = pickPathSegment(current, segment)
    if (current == null) return undefined
  }
  return current
}

function pickPathSegment(source: unknown, segment: string): unknown {
  const raw = segment.trim()
  if (!raw || raw === '$') return source
  if (raw === '[]' || raw === '[*]' || raw === '*') return Array.isArray(source) ? source : undefined

  if (Array.isArray(source)) {
    if (raw.startsWith('[') && raw.endsWith(']')) {
      return pickListIndex(source, raw.slice(1, -1))
    }
    const values = source
      .map(item => pickPathSegment(item, raw))
      .filter(item => item !== undefined)
    return values
  }

  let key = raw
  const selectors: string[] = []
  const bracketIndex = raw.indexOf('[')
  if (bracketIndex >= 0) {
    key = raw.slice(0, bracketIndex)
    let rest = raw.slice(bracketIndex)
    while (rest.startsWith('[')) {
      const close = rest.indexOf(']')
      if (close < 0) return undefined
      selectors.push(rest.slice(1, close))
      rest = rest.slice(close + 1)
    }
    if (rest) return undefined
  }

  let value: unknown = source
  if (key) {
    if (!value || typeof value !== 'object') return undefined
    value = (value as Record<string, unknown>)[key]
  }

  for (const selector of selectors) {
    if (selector === '' || selector === '*') {
      if (!Array.isArray(value)) return undefined
      continue
    }
    if (!Array.isArray(value)) return undefined
    value = pickListIndex(value, selector)
  }
  return value
}

function pickListIndex(values: unknown[], selector: string): unknown {
  const index = Number.parseInt(selector, 10)
  if (Number.isNaN(index)) return undefined
  const normalized = index < 0 ? values.length + index : index
  if (normalized < 0 || normalized >= values.length) return undefined
  return values[normalized]
}

export function pickExactOrDottedChildren(source: unknown, key: string): unknown {
  if (!source || typeof source !== 'object' || Array.isArray(source) || !key) return undefined
  const record = source as Record<string, unknown>
  if (key in record) return record[key]
  const prefix = `${key}.`
  const nestedEntries = Object.entries(record).filter(([entryKey]) => entryKey.startsWith(prefix))
  if (!nestedEntries.length) return undefined
  const root: Record<string, unknown> = {}
  for (const [entryKey, entryValue] of nestedEntries) {
    const remainder = entryKey.slice(prefix.length)
    if (!remainder) continue
    const parts = remainder.split('.').filter(Boolean)
    if (!parts.length) continue
    let cursor: Record<string, unknown> = root
    for (const part of parts.slice(0, -1)) {
      const next = cursor[part]
      if (!next || typeof next !== 'object' || Array.isArray(next)) {
        cursor[part] = {}
      }
      cursor = cursor[part] as Record<string, unknown>
    }
    cursor[parts[parts.length - 1]] = entryValue
  }
  return Object.keys(root).length ? root : undefined
}

export function resolveBoundOutputValue(
  source: unknown,
  binding: Pick<InvocationVariableBinding, 'source_path' | 'alias' | 'variable_key'>,
): unknown {
  const candidates = [binding.source_path, binding.alias, binding.variable_key]
  for (const candidate of candidates) {
    const normalized = String(candidate || '').trim()
    if (!normalized) continue
    const exact = pickExactOrDottedChildren(source, normalized)
    if (exact !== undefined) return exact
    const picked = pickPath(source, normalized)
    if (picked !== undefined) return picked
  }
  return undefined
}

export function extractBoundOutputMaps(
  source: unknown,
  bindings: InvocationVariableBinding[],
): { byAlias: Record<string, unknown>; byVariableKey: Record<string, unknown> } {
  const byAlias: Record<string, unknown> = {}
  const byVariableKey: Record<string, unknown> = {}
  for (const binding of bindings || []) {
    const value = resolveBoundOutputValue(source, binding)
    if (value === undefined) continue
    if (binding.alias) byAlias[binding.alias] = value
    if (binding.variable_key) byVariableKey[binding.variable_key] = value
  }
  return { byAlias, byVariableKey }
}

