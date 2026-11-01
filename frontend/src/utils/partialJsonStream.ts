/**
 * 部分 JSON 增量提取（headless AI Invocation 轮询模式下的流式渲染支撑）。
 *
 * 背景：向导三个阶段（世界观/人物/地图）在 headless 模式走 AI Invocation，
 * 后端每 0.35s 把「生成中」的部分 attempt.content 落库，前端 1.2s 轮询拿到
 * 不断增长的原始 LLM 输出。本模块从这段「未闭合的 JSON 文本」里增量提取：
 * - 世界观：style 字符串（含未闭合尾巴→打字机效果）+ 各维度已完成字段
 * - 人物/地点数组：已闭合的完整对象（出一个渲染一个）
 *
 * 语义与后端 infrastructure/json_stream/incremental_extractor.py +
 * worldbuilding_stream_parser.py 保持一致（前端消费侧移植）。
 */

/** 维度 → 契约字段键（用于判定「维度已完整」与字段归一化过滤） */
const WB_FIELD_KEYS: Record<string, string[]> = {
  core_rules: ['power_system', 'physics_rules', 'magic_tech'],
  geography: ['terrain', 'climate', 'resources', 'ecology'],
  society: ['politics', 'economy', 'class_system'],
  culture: ['history', 'religion', 'taboos'],
  daily_life: ['food_clothing', 'language_slang', 'entertainment'],
}

const WB_DIM_ORDER = ['core_rules', 'geography', 'society', 'culture', 'daily_life']

export interface WorldbuildingPartial {
  /** 文风公约（可含未闭合尾巴，用于打字机效果）；空串表示尚未出现 */
  style: string
  /** style 是否已完整闭合 */
  styleComplete: boolean
  /** 维度 → 已完成的规范字段（不含未闭合字段值） */
  dims: Record<string, Record<string, string>>
}

function unescapeJsonString(s: string): string {
  return s.replace(/\\\\/g, '\\').replace(/\\n/g, '\n').replace(/\\t/g, '\t').replace(/\\"/g, '"')
}

/** 扫描从 braceStart 的 `{` 到匹配 `}` 的结束下标（+1）；未闭合返回 -1 */
function scanBalancedBraceEnd(buf: string, braceStart: number): number {
  if (braceStart < 0 || braceStart >= buf.length || buf[braceStart] !== '{') return -1
  let depth = 0
  let inString = false
  let escape = false
  for (let i = braceStart; i < buf.length; i++) {
    const ch = buf[i]
    if (escape) { escape = false; continue }
    if (inString) {
      if (ch === '\\') escape = true
      else if (ch === '"') inString = false
      continue
    }
    if (ch === '"') { inString = true; continue }
    if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth === 0) return i + 1
    }
  }
  return -1
}

/** 定位 `"key": {` 中 `{` 的下标；找不到返回 -1 */
function findKeyObjectBraceStart(buf: string, key: string): number {
  const m = buf.match(new RegExp(`"${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"\\s*:\\s*\\{`))
  return m ? (m.index ?? -1) + m[0].length - 1 : -1
}

/** 定位 `"key": [` 中 `[` 的下标；找不到返回 -1 */
function findKeyArrayBracketStart(buf: string, key: string): number {
  const m = buf.match(new RegExp(`"${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"\\s*:\\s*\\[`))
  return m ? (m.index ?? -1) + m[0].length - 1 : -1
}

/** 对象闭合后 JSON.parse；失败/非对象返回 null */
function tryParseJsonObject(buf: string, braceStart: number, braceEnd: number): Record<string, unknown> | null {
  const slice = buf.slice(braceStart, braceEnd)
  try {
    const parsed = JSON.parse(slice) as unknown
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch { /* 未闭合或语法错误都按 null 处理 */ }
  return null
}

/** 从未闭合的对象片段里提取已完成的 `"key": "value"` 字符串对 */
function extractCompleteStringFields(objectBody: string, allowedKeys: string[] | null): Record<string, string> {
  const out: Record<string, string> = {}
  const re = /"([\w]+)"\s*:\s*"((?:[^"\\]|\\.)*)"/g
  let m: RegExpExecArray | null
  while ((m = re.exec(objectBody))) {
    const key = m[1]
    if (allowedKeys && !allowedKeys.includes(key)) continue
    out[key] = unescapeJsonString(m[2])
  }
  return out
}

/** 提取 `"style": "..."`：闭合取全量，未闭合取已到达尾巴（打字机效果） */
function extractStyleString(buf: string): { value: string; complete: boolean } {
  const complete = buf.match(/"style"\s*:\s*"((?:[^"\\]|\\.)*)"/)
  if (complete) return { value: unescapeJsonString(complete[1]), complete: true }
  const tail = buf.match(/"style"\s*:\s*"((?:[^"\\]|\\.)*)$/)
  if (tail) return { value: unescapeJsonString(tail[1]), complete: false }
  return { value: '', complete: false }
}

/**
 * 从（可能是部分的）LLM 输出中增量提取世界观。
 *
 * 兼容两种输出形态：
 * 1. 直接输出五维根对象（`{"core_rules": {...}, ...}`——SSE 分维生成的形态）
 * 2. 包一层 `worldbuilding` 键（invocation 一次性模板输出形态，`{"style": "...", "worldbuilding": {...}}`）
 */
export function extractWorldbuildingPartial(raw: string): WorldbuildingPartial {
  const result: WorldbuildingPartial = { style: '', styleComplete: false, dims: {} }
  let buf = raw.trim()
  if (!buf) return result

  // 剥掉 markdown 代码栅栏
  const fenced = buf.match(/```(?:json)?\s*([\s\S]*?)(?:```|$)/i)
  if (fenced?.[1]) buf = fenced[1].trim()

  const style = extractStyleString(buf)
  result.style = style.value
  result.styleComplete = style.complete

  // 若存在 "worldbuilding": { 包装，则下钻其内部（未闭合也照用片段）
  const wrapper = findKeyObjectBraceStart(buf, 'worldbuilding')
  const body = wrapper >= 0 ? buf.slice(wrapper + 1) : buf

  for (const dimKey of WB_DIM_ORDER) {
    const fieldKeys = WB_FIELD_KEYS[dimKey]
    const brace = findKeyObjectBraceStart(body, dimKey)
    if (brace < 0) continue
    const end = scanBalancedBraceEnd(body, brace)
    if (end >= 0) {
      const obj = tryParseJsonObject(body, brace, end)
      if (obj) {
        const fields: Record<string, string> = {}
        for (const [k, v] of Object.entries(obj)) {
          if (fieldKeys.includes(k) && (typeof v === 'string') && v.trim()) fields[k] = v
        }
        if (Object.keys(fields).length) result.dims[dimKey] = fields
        continue
      }
    }
    // 未闭合：提取已完成的字符串字段（出一个渲染一个）
    const partial = extractCompleteStringFields(body.slice(brace + 1), fieldKeys)
    if (Object.keys(partial).length) result.dims[dimKey] = partial
  }
  return result
}

/** 维度契约字段是否已齐（用于把骨架点标成「已生成」） */
export function worldbuildingDimComplete(dimKey: string, fields: Record<string, string>): boolean {
  const required = WB_FIELD_KEYS[dimKey]
  if (!required?.length) return false
  return required.every(k => String(fields[k] || '').trim().length > 0)
}

/**
 * 从（可能是部分的）LLM 输出中提取数组里已闭合的完整对象。
 * 适用于 `"characters": [...]` / `"locations": [...]` 的逐个呈现。
 */
export function extractArrayObjectsPartial(
  raw: string,
  arrayKey: 'characters' | 'locations',
): Array<Record<string, unknown>> {
  let buf = raw.trim()
  if (!buf) return []
  const fenced = buf.match(/```(?:json)?\s*([\s\S]*?)(?:```|$)/i)
  if (fenced?.[1]) buf = fenced[1].trim()

  const bracket = findKeyArrayBracketStart(buf, arrayKey)
  if (bracket < 0) return []

  const items: Array<Record<string, unknown>> = []
  let i = bracket + 1
  const len = buf.length
  while (i < len) {
    const ch = buf[i]
    if (ch === '{') {
      const end = scanBalancedBraceEnd(buf, i)
      if (end < 0) break // 当前对象未闭合，后面的都不可用
      const obj = tryParseJsonObject(buf, i, end)
      if (obj && typeof obj.name !== 'undefined') items.push(obj)
      i = end
      continue
    }
    if (ch === ']') break // 数组闭合
    if (ch === '"') {
      // 跳过字符串字面量
      let j = i + 1
      while (j < len) {
        if (buf[j] === '\\') j += 2
        else if (buf[j] === '"') { j++; break }
        else j++
      }
      i = j
      continue
    }
    i++
  }
  return items
}
