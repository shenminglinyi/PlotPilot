/**
 * 人物关系图：合并 Knowledge facts 与 Bible.relationships，
 * 并过滤 LLM 写入的内部占位实体名（如 char 005）。
 */
import type { CharacterDTO } from '../api/bible'

/** 形如 char 005 / character_12 / CHAR-003 */
const INTERNAL_GRAPH_ENTITY_RE = /^(?:char|character)[\s_-]*\d+$/i

export function isInternalGraphEntityLabel(raw: string): boolean {
  return INTERNAL_GRAPH_ENTITY_RE.test((raw || '').trim())
}

/** 书中已有角色名，长按长度排序以便优先匹配全名 */
function rosterSorted(chars: CharacterDTO[]): string[] {
  const names = [
    ...new Set(
      (chars || [])
        .map(c => (c.name || '').trim())
        .filter(n => n.length > 0 && !isInternalGraphEntityLabel(n)),
    ),
  ]
  names.sort((a, b) => b.length - a.length)
  return names
}

function stripOuterWrappers(s: string): string {
  let t = s.trim()
  const pairs: Array<[string, string]> = [
    ['「', '」'],
    ['『', '』'],
    ['"', '"'],
    ["'", "'"],
    ['【', '】'],
    ['（', '）'],
    ['(', ')'],
  ]
  let changed = true
  while (changed && t.length >= 2) {
    changed = false
    for (const [a, b] of pairs) {
      if (t.startsWith(a) && t.endsWith(b)) {
        t = t.slice(a.length, -b.length).trim()
        changed = true
        break
      }
    }
  }
  return t
}

/**
 * 将 Bible 单条字符串关系解析为 (predicate, target)；解析失败返回 null。
 * 覆盖常见中文写法：「仇敌：张三」「与李四订婚」「对皇帝怀有敌意」「……「艾伦」……」等。
 */
export function parseBibleStringRelationship(
  subject: string,
  relStr: string,
  rosterSortedLongFirst: string[],
): { predicate: string; target: string } | null {
  const raw = (relStr || '').trim()
  if (!raw) return null

  const colon = raw.match(/^(.{1,48}?)[：:]\s*(.+)$/s)
  if (colon) {
    const pred = colon[1].trim()
    let obj = colon[2].trim().split(/[，,。；;\n]/)[0].trim()
    obj = stripOuterWrappers(obj)
    if (
      pred &&
      obj &&
      obj !== subject &&
      !isInternalGraphEntityLabel(obj) &&
      obj.length <= 80
    ) {
      return { predicate: pred.slice(0, 120), target: obj.slice(0, 80) }
    }
  }

  for (const name of rosterSortedLongFirst) {
    if (name === subject || name.length < 2) continue
    if (raw.includes(`「${name}」`) || raw.includes(`『${name}』`)) {
      const predicate =
        raw.replace(`「${name}」`, ' ').replace(`『${name}』`, ' ').replace(/\s+/g, ' ').trim().slice(0, 120) ||
        '关系'
      return { predicate, target: name }
    }
  }

  const starters = ['与', '同', '对', '向', '和']
  for (const name of rosterSortedLongFirst) {
    if (name === subject || name.length < 2) continue
    for (const st of starters) {
      const prefix = st + name
      if (raw.startsWith(prefix)) {
        const rest = raw.slice(prefix.length).trim()
        const predicate =
          rest.replace(/^[是为：，。\s]+/, '').trim().slice(0, 120) || '关系'
        return { predicate, target: name }
      }
    }
  }

  for (const name of rosterSortedLongFirst) {
    if (name === subject || name.length < 2) continue
    if (!raw.includes(name)) continue
    const idx = raw.indexOf(name)
    let predicate = `${raw.slice(0, idx)} ${raw.slice(idx + name.length)}`.replace(/\s+/g, ' ').trim()
    predicate = predicate.replace(/^[是为：，、。\s]+|[是为：，、。\s]+$/g, '').trim()
    if (!predicate) predicate = '提及'
    return { predicate: predicate.slice(0, 120), target: name }
  }

  return null
}

export function bibleRelationshipsToCharacterFacts(chars: CharacterDTO[]): Array<Record<string, unknown>> {
  const out: Array<Record<string, unknown>> = []
  let seq = 0
  const roster = rosterSorted(chars || [])

  for (const c of chars || []) {
    const subject = (c.name || '').trim()
    if (!subject || isInternalGraphEntityLabel(subject)) continue

    for (const rel of c.relationships || []) {
      if (typeof rel === 'string') {
        const parsed = parseBibleStringRelationship(subject, rel, roster)
        if (!parsed || isInternalGraphEntityLabel(parsed.target)) continue
        seq += 1
        out.push({
          id: `bible-rel-${seq}`,
          subject,
          predicate: parsed.predicate,
          object: parsed.target,
          entity_type: 'character',
          note: rel.trim().slice(0, 240),
        })
        continue
      }

      if (!rel || typeof rel !== 'object') continue

      const target = ((rel as { target?: string }).target || '').trim()
      const predicate = ((rel as { relation?: string }).relation || '关系').trim().slice(0, 120)
      const note = ((rel as { description?: string }).description || '').trim()

      if (!target) continue
      if (isInternalGraphEntityLabel(target)) continue

      seq += 1
      out.push({
        id: `bible-rel-${seq}`,
        subject,
        predicate,
        object: target,
        entity_type: 'character',
        ...(note ? { note } : {}),
      })
    }
  }
  return out
}

function factTripleKey(t: { subject?: string; predicate?: string; object?: string }): string {
  return `${(t.subject || '').trim()}|${(t.predicate || '').trim()}|${(t.object || '').trim()}`
}

/** 过滤内部占位实体；合并 Bible 关系（按三元组去重）。 */
export function mergeKnowledgeFactsWithBibleCharacters<
  T extends { subject?: string; predicate?: string; object?: string; entity_type?: string | null },
>(kbFacts: T[], bibleChars: CharacterDTO[]): T[] {
  const kb = kbFacts || []
  const bibleSynth = bibleRelationshipsToCharacterFacts(bibleChars || []) as unknown as T[]

  const kbChar = kb.filter(
    t =>
      t.entity_type === 'character' &&
      !isInternalGraphEntityLabel((t.subject || '').trim()) &&
      !isInternalGraphEntityLabel((t.object || '').trim()),
  )

  const seen = new Set(kbChar.map(factTripleKey))
  const merged: T[] = [...kbChar]

  for (const bf of bibleSynth) {
    const sub = String((bf as Record<string, unknown>).subject ?? '').trim()
    const obj = String((bf as Record<string, unknown>).object ?? '').trim()
    if (!sub || !obj) continue
    const k = factTripleKey(bf)
    if (seen.has(k)) continue
    seen.add(k)
    merged.push(bf)
  }

  return merged
}
