import type {
  ModNodeOverride,
  ModRoleCategory,
  ModTrustLevel,
  NarrativeModPack,
} from '@/domain/modPack/types'

export const MOD_MANIFEST_MAX_BYTES = 1_048_576
const LEGACY_FALLBACK_TIMEOUT_MS = 10_000
const DEFAULT_MANIFEST_FILENAMES = ['plotpilot-mod.json', 'mod.json', 'manifest.json'] as const
const TRUSTED_BROWSER_FALLBACK_HOSTS = new Set(['raw.githubusercontent.com'])

export const SAFE_MOD_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$/
export const SAFE_NODE_KEY_RE = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/
const SAFE_REPO_ATOM_RE = /^[A-Za-z0-9_.-]+$/
const SAFE_ORIGIN_TOKEN_RE = /^[0-9a-f]{32}$/
const RESERVED_MARKER_RE = /PlotPilot-Mod:/i
const ASCII_CONTROL_CHAR_RE = /[\u0000-\u001f\u007f]/

export type ModBlockMode = 'standalone' | 'appended' | 'replaced'

function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 生成 128-bit（16 字节 / 32 位小写十六进制）加密随机归属凭证；
 * 若运行环境缺少 CSPRNG（crypto.getRandomValues）则直接拒绝并失败关闭（F1）。
 */
export function generateOriginToken(): string {
  if (typeof globalThis.crypto?.getRandomValues !== 'function') {
    throw new Error(
      '当前运行环境缺少加密安全随机数生成器（crypto.getRandomValues），无法安全生成独立节点归属凭证',
    )
  }
  const bytes = new Uint8Array(16)
  globalThis.crypto.getRandomValues(bytes)
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
}

export function assertValidModId(packId: string): string {
  const trimmed = (packId || '').trim()
  if (!SAFE_MOD_ID_RE.test(trimmed)) {
    throw new Error(
      `模组标识（id: "${packId}"）格式非法：仅允许字母、数字、点、下划线与连字符（最长 96 字符）`,
    )
  }
  return trimmed
}

export function assertValidNodeKey(nodeKey: string): string {
  const trimmed = (nodeKey || '').trim()
  if (!SAFE_NODE_KEY_RE.test(trimmed) || trimmed.includes('..')) {
    throw new Error(
      `节点键（nodeKey: "${nodeKey}"）格式非法：仅允许字母、数字、点、下划线与连字符`,
    )
  }
  return trimmed
}

export function assertSafeProtocolBody(body: string, label = '模组提示词'): void {
  if (RESERVED_MARKER_RE.test(body)) {
    throw new Error(
      `${label}包含受保护的协议边界标记（PlotPilot-Mod），已拒绝写入以防破坏其他模组`,
    )
  }
}

export function sanitizeModIdAtom(raw: string, fallback = 'item'): string {
  const cleaned = String(raw || '')
    .trim()
    .replace(/[^A-Za-z0-9_.-]+/g, '-')
    .replace(/^[^A-Za-z0-9]+/, '')
    .slice(0, 72)
  return cleaned || fallback
}

export function stripModDelimiterComments(text: string): string {
  if (!text) return ''
  return text.replace(
    /^\s*<!--\s*\[PlotPilot-Mod:[A-Za-z0-9][A-Za-z0-9_.-]{0,95}:(?:START(?::[a-z]+(?::[0-9a-f]{16,64})?)?|END)\]\s*-->\r?\n?/gm,
    () => '',
  )
}

export function buildModStartMarker(
  packId: string,
  mode: ModBlockMode = 'appended',
): string {
  const safeId = assertValidModId(packId)
  return `<!-- [PlotPilot-Mod:${safeId}:START:${mode}] -->`
}

export function buildModEndMarker(packId: string): string {
  const safeId = assertValidModId(packId)
  return `<!-- [PlotPilot-Mod:${safeId}:END] -->`
}

export function buildOwnedCustomBlock(
  packId: string,
  originToken: string,
  body: string,
): string {
  const safeId = assertValidModId(packId)
  if (!SAFE_ORIGIN_TOKEN_RE.test(originToken)) {
    throw new Error('独立节点归属凭证格式非法')
  }
  assertSafeProtocolBody(body)
  return `<!-- [PlotPilot-Mod:${safeId}:START:custom:${originToken}] -->\n${body}\n${buildModEndMarker(safeId)}`
}

interface ParsedTopLevelModBlock {
  packId: string
  mode: 'standalone' | 'appended' | 'replaced' | 'custom' | 'legacy'
  customToken?: string
  startIndex: number
  endIndex: number
  innerBody: string
}

interface ParsedModTopology {
  blocks: ParsedTopLevelModBlock[]
}

const WELL_FORMED_MOD_COMMENT_RE =
  /<!-- \[PlotPilot-Mod:([A-Za-z0-9][A-Za-z0-9_.-]{0,95}):(?:(START)(?::(?:(standalone|appended|replaced)|custom:([0-9a-f]{32})))?|(END))\] -->/g

/**
 * 全局单遍协议拓扑解析器（深度固定为 1，严禁任何嵌套、交叉、未闭合、重复或残缺标记）：
 * 1. 全文每一处大小写不敏感的 `PlotPilot-Mod:` 引用必须精确对应一条语法合法的顶层 START 或 END 注释标记；
 * 2. 任何 START 出现时若已有未闭合的外层 START（如外层模组 B 包裹内层模组 A），立即判定为嵌套冲突并失败关闭；
 * 3. 每个 END 必须与当前打开的顶层 START 精确同模组配对（含大小写一致），且同一模组在全文最多只能出现一个顶层块；
 * 4. 起始标记与结束标记之间必须满足合法换行边界（custom/replaced 要求 `\n...\n`，追加/独立块允许 `\n...\n` 或空体 `\n`）。
 */
function parseTopLevelModTopology(
  text: string,
): { ok: true; topology: ParsedModTopology } | { ok: false; reason: string } {
  if (!text) {
    return { ok: true, topology: { blocks: [] } }
  }

  const rawMentions = Array.from(text.matchAll(/PlotPilot-Mod:/gi))
  if (rawMentions.length === 0) {
    return { ok: true, topology: { blocks: [] } }
  }

  const wellFormedMatches = Array.from(text.matchAll(WELL_FORMED_MOD_COMMENT_RE))
  if (wellFormedMatches.length !== rawMentions.length) {
    return {
      ok: false,
      reason: '目标节点包含残缺或未闭合的模组协议边界标记，为防止覆盖丢失您的内容已中止改写',
    }
  }

  for (let i = 0; i < wellFormedMatches.length; i += 1) {
    const wfIdx = wellFormedMatches[i].index
    const rawIdx = rawMentions[i].index
    if (wfIdx === undefined || rawIdx === undefined || rawIdx !== wfIdx + 6) {
      return {
        ok: false,
        reason: '目标节点包含格式损坏或伪造的模组协议边界标记，为保护块外内容已拒绝自动改写',
      }
    }
  }

  const blocks: ParsedTopLevelModBlock[] = []
  const seenLowerIds = new Set<string>()
  let openStart: {
    packId: string
    mode: 'standalone' | 'appended' | 'replaced' | 'custom' | 'legacy'
    customToken?: string
    markerStart: number
    markerEnd: number
  } | null = null

  for (const m of wellFormedMatches) {
    const markerStart = m.index!
    const markerEnd = markerStart + m[0].length
    const packId = m[1]
    const isStart = m[2] === 'START'
    const stdMode = m[3] as 'standalone' | 'appended' | 'replaced' | undefined
    const customToken = m[4]
    const isEnd = m[5] === 'END'

    if (isStart) {
      if (openStart !== null) {
        return {
          ok: false,
          reason:
            '节点中模组协议边界标记残缺或存在嵌套冲突，为保护块外与外层模组内容已中止自动改写',
        }
      }
      const lowerId = packId.toLowerCase()
      if (seenLowerIds.has(lowerId)) {
        return {
          ok: false,
          reason: `节点中模组「${packId}」存在重复的协议边界标记块，为保护块外内容已拒绝自动改写`,
        }
      }
      const mode: 'standalone' | 'appended' | 'replaced' | 'custom' | 'legacy' =
        customToken !== undefined ? 'custom' : (stdMode ?? 'legacy')
      openStart = {
        packId,
        mode,
        customToken,
        markerStart,
        markerEnd,
      }
    } else if (isEnd) {
      if (openStart === null) {
        return {
          ok: false,
          reason: '节点中存在孤立未配对的模组协议边界标记（END），为保护块外内容已拒绝自动改写',
        }
      }
      if (openStart.packId !== packId) {
        return {
          ok: false,
          reason:
            '节点中模组协议边界标记交叉或存在嵌套冲突，为保护块外与外层模组内容已中止自动改写',
        }
      }

      const between = text.slice(openStart.markerEnd, markerStart)
      let innerBody: string
      if (openStart.mode === 'custom' || openStart.mode === 'replaced') {
        if (between.length < 2 || !between.startsWith('\n') || !between.endsWith('\n')) {
          return {
            ok: false,
            reason: `节点中模组「${packId}」的协议边界标记换行分隔已损坏，已拒绝自动改写`,
          }
        }
        innerBody = between.slice(1, -1)
      } else if (between === '\n') {
        innerBody = ''
      } else if (between.length >= 2 && between.startsWith('\n') && between.endsWith('\n')) {
        innerBody = between.slice(1, -1)
      } else {
        return {
          ok: false,
          reason: `节点中模组「${packId}」的协议边界标记换行分隔已损坏，已拒绝自动改写`,
        }
      }

      if (RESERVED_MARKER_RE.test(innerBody)) {
        return {
          ok: false,
          reason: `节点中模组「${packId}」的协议块内部嵌套了其他模组标记，已中止自动改写`,
        }
      }

      blocks.push({
        packId: openStart.packId,
        mode: openStart.mode,
        customToken: openStart.customToken,
        startIndex: openStart.markerStart,
        endIndex: markerEnd,
        innerBody,
      })
      seenLowerIds.add(packId.toLowerCase())
      openStart = null
    }
  }

  if (openStart !== null) {
    return {
      ok: false,
      reason: '目标节点包含残缺或未闭合的模组协议边界标记，为防止覆盖丢失您的内容已中止改写',
    }
  }

  return { ok: true, topology: { blocks } }
}

function tryParseTopLevelModTopology(text: string): ParsedModTopology | null {
  const parsed = parseTopLevelModTopology(text)
  return parsed.ok ? parsed.topology : null
}

function assertValidModTopology(text: string): ParsedModTopology {
  const parsed = parseTopLevelModTopology(text)
  if (!parsed.ok) {
    throw new Error(parsed.reason)
  }
  return parsed.topology
}

interface VerifiedCustomBlockSpan {
  startIndex: number
  endIndex: number
  token: string
  innerBody: string
}

/**
 * 严格定位唯一、顶层无外层包裹且边界完整的自定义归属块：
 * 1. 先执行全局单遍拓扑校验，确保目标块既未包裹其他标记，也未被任何外层模组块（standalone/appended/replaced/custom）包裹；
 * 2. 目标模组在顶层块列表中必须唯一且为 `:START:custom:<32hex>` 模式；
 * 3. 若传入 expectedOriginToken，必须为合法 32 位十六进制且完全一致。
 */
function locateVerifiedCustomBlockSpan(
  text: string,
  packId: string,
  expectedOriginToken?: string,
): VerifiedCustomBlockSpan | null {
  if (!text) return null
  const safeId = assertValidModId(packId)
  if (expectedOriginToken !== undefined && !SAFE_ORIGIN_TOKEN_RE.test(expectedOriginToken)) {
    return null
  }

  const topology = tryParseTopLevelModTopology(text)
  if (!topology) {
    return null
  }

  const block = topology.blocks.find(b => b.packId.toLowerCase() === safeId.toLowerCase())
  if (!block || block.packId !== safeId || block.mode !== 'custom' || !block.customToken) {
    return null
  }
  if (expectedOriginToken !== undefined && block.customToken !== expectedOriginToken) {
    return null
  }

  return {
    startIndex: block.startIndex,
    endIndex: block.endIndex,
    token: block.customToken,
    innerBody: block.innerBody,
  }
}

interface VerifiedReplacedBlockSpan {
  startIndex: number
  endIndex: number
  innerBody: string
}

function locateVerifiedReplacedBlockSpan(
  text: string,
  packId: string,
): VerifiedReplacedBlockSpan | null {
  if (!text) return null
  const safeId = assertValidModId(packId)
  const topology = tryParseTopLevelModTopology(text)
  if (!topology) {
    return null
  }

  const block = topology.blocks.find(b => b.packId.toLowerCase() === safeId.toLowerCase())
  if (!block || block.packId !== safeId || block.mode !== 'replaced') {
    return null
  }

  return {
    startIndex: block.startIndex,
    endIndex: block.endIndex,
    innerBody: block.innerBody,
  }
}

export function extractCustomOriginToken(text: string, packId: string): string | null {
  const span = locateVerifiedCustomBlockSpan(text, packId)
  return span ? span.token : null
}

export function hasMatchingCustomOriginToken(
  text: string,
  packId: string,
  expectedToken: string,
): boolean {
  if (!SAFE_ORIGIN_TOKEN_RE.test(expectedToken)) return false
  return locateVerifiedCustomBlockSpan(text, packId, expectedToken) !== null
}

export function hasAnyModBlock(text: string, packId: string): boolean {
  if (!text) return false
  const safeId = assertValidModId(packId)
  const escaped = escapeRegExp(safeId)
  const re = new RegExp(
    `<!-- \\[PlotPilot-Mod:${escaped}:START(?::(?:standalone|appended|replaced|custom:[0-9a-f]{32}))?\\] -->`,
  )
  return re.test(text)
}

export function hasPackModMention(text: string, packId: string): boolean {
  if (!text) return false
  const safeId = assertValidModId(packId)
  const escaped = escapeRegExp(safeId)
  const re = new RegExp(`PlotPilot-Mod:${escaped}(?![A-Za-z0-9_.-])`, 'i')
  return re.test(text)
}

export function hasReplacedModBlock(text: string, packId: string): boolean {
  if (!text) return false
  const safeId = assertValidModId(packId)
  const escaped = escapeRegExp(safeId)
  const re = new RegExp(`<!-- \\[PlotPilot-Mod:${escaped}:START:replaced\\] -->`)
  return re.test(text)
}

export function hasForeignReplacedBlock(text: string, excludePackId: string): boolean {
  if (!text) return false
  const re = /<!-- \[PlotPilot-Mod:([A-Za-z0-9][A-Za-z0-9_.-]{0,95}):START:replaced\] -->/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m[1] !== excludePackId) return true
  }
  return false
}

export function hasForeignModMention(text: string, excludePackId: string): boolean {
  if (!text) return false
  const safeExclude = assertValidModId(excludePackId).toLowerCase()
  const re = /PlotPilot-Mod:([A-Za-z0-9][A-Za-z0-9_.-]{0,95})(?![A-Za-z0-9_.-])/gi
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m[1].toLowerCase() !== safeExclude) return true
  }
  return false
}

/**
 * 字节级无损剥离指定模组的顶层挂载块（append_protocol / standalone）：
 * 先执行全文顶层拓扑校验（杜绝目标块被外层模组块包裹、内部嵌套、未闭合或重复块），异常立即抛错拒绝改写。
 */
export function stripModProtocolBlock(text: string, packId: string): string {
  const safeId = assertValidModId(packId)
  if (!text) return text

  const topology = assertValidModTopology(text)
  const block = topology.blocks.find(b => b.packId.toLowerCase() === safeId.toLowerCase())
  if (!block) {
    return text
  }
  if (block.packId !== safeId) {
    throw new Error(
      `节点中模组「${safeId}」的协议边界标记大小写不一致，为保护块外内容已拒绝自动改写`,
    )
  }
  if (block.mode === 'replaced' || block.mode === 'custom') {
    throw new Error(`节点中模组「${safeId}」处于完整替换或独立归属模式，不能按普通追加协议块剥离`)
  }

  const startIdx = block.startIndex
  const endIdx = block.endIndex

  if (block.mode === 'standalone') {
    const prefix = text.slice(0, startIdx)
    const suffix = text.slice(endIdx)
    if (prefix === '') {
      const leadingNextRe =
        /^\n\n<!-- \[PlotPilot-Mod:([A-Za-z0-9][A-Za-z0-9_.-]{0,95}):START:appended\] -->/
      if (leadingNextRe.test(suffix)) {
        return suffix.replace(
          leadingNextRe,
          (_m: string, nextModId: string) =>
            `<!-- [PlotPilot-Mod:${nextModId}:START:standalone] -->`,
        )
      }
    }
    return `${prefix}${suffix}`
  }

  if (startIdx >= 2 && text.slice(startIdx - 2, startIdx) === '\n\n') {
    return `${text.slice(0, startIdx - 2)}${text.slice(endIdx)}`
  }
  return `${text.slice(0, startIdx)}${text.slice(endIdx)}`
}

/**
 * 字节级无损挂载模组协议块：不改动原提示词任何首尾或内部空白，并校验保留标记防注入
 */
export function injectModProtocolBlock(
  text: string,
  packId: string,
  protocolBody: string,
): string {
  const safeId = assertValidModId(packId)
  assertSafeProtocolBody(protocolBody)

  const base = stripModProtocolBlock(text, safeId)
  if (base === '') {
    return `${buildModStartMarker(safeId, 'standalone')}\n${protocolBody}\n${buildModEndMarker(safeId)}`
  }
  return `${base}\n\n${buildModStartMarker(safeId, 'appended')}\n${protocolBody}\n${buildModEndMarker(safeId)}`
}

export interface ExtractedModLayer {
  modId: string
  body: string
}

export function extractOtherAppendedLayers(
  text: string,
  excludePackId: string,
): ExtractedModLayer[] {
  if (!text) return []
  const topology = assertValidModTopology(text)
  const layers: ExtractedModLayer[] = []
  for (const block of topology.blocks) {
    if (block.packId === excludePackId) continue
    if (block.mode === 'replaced' || block.mode === 'custom') continue
    layers.push({ modId: block.packId, body: block.innerBody })
  }
  return layers
}

/**
 * 构造或原地更新 replace_system 的 System 文本：
 * - 先对全文执行顶层协议拓扑校验，杜绝先剥离内层目标块再掩盖外层包裹损坏的往返绕过
 * - 升级重装已含 :replaced 块的同模组时，校验唯一顶层边界后仅替换所属块正文，保留块外用户编辑与其他模组层
 * - 首次切换为 replace_system 时，验证全部现有顶层块可无损往返后提取纯净基线并保留其他挂载层
 */
export function prepareSystemReplacement(
  existingSystem: string,
  packId: string,
  replacementBody: string,
  carriedBaseline?: string,
): { baselineSystem: string; nextSystem: string } {
  const safeId = assertValidModId(packId)
  assertSafeProtocolBody(replacementBody)
  assertValidModTopology(existingSystem)

  if (hasForeignReplacedBlock(existingSystem, safeId)) {
    throw new Error('目标节点已存在其他模组的完整替换块，请先停用冲突模组')
  }

  const newReplacedBlock = `${buildModStartMarker(safeId, 'replaced')}\n${replacementBody}\n${buildModEndMarker(safeId)}`

  if (hasReplacedModBlock(existingSystem, safeId)) {
    if (carriedBaseline === undefined) {
      throw new Error(
        `节点已包含模组「${safeId}」的替换块但本地缺少原始基线快照，已拒绝覆盖以防丢失原始提示词`,
      )
    }
    const span = locateVerifiedReplacedBlockSpan(existingSystem, safeId)
    if (!span) {
      throw new Error(
        `节点中模组「${safeId}」的替换边界标记残缺或存在嵌套冲突，为防止吞噬其他内容已中止更新`,
      )
    }
    const nextSystem =
      existingSystem.slice(0, span.startIndex) +
      newReplacedBlock +
      existingSystem.slice(span.endIndex)
    return {
      baselineSystem: carriedBaseline,
      nextSystem,
    }
  }

  const withoutSelf = stripModProtocolBlock(existingSystem, safeId)
  const otherLayers = extractOtherAppendedLayers(withoutSelf, safeId)

  let pureBaseline = withoutSelf
  for (const layer of otherLayers) {
    pureBaseline = stripModProtocolBlock(pureBaseline, layer.modId)
  }
  if (RESERVED_MARKER_RE.test(pureBaseline)) {
    throw new Error(
      '目标节点包含残缺或未闭合的模组协议标记，为防止覆盖丢失您的内容已中止替换',
    )
  }

  let canonicalCheck = pureBaseline
  for (const layer of otherLayers) {
    canonicalCheck = injectModProtocolBlock(canonicalCheck, layer.modId, layer.body)
  }
  if (canonicalCheck !== withoutSelf) {
    throw new Error(
      '目标节点在其他模组协议块之后包含交错的手动编辑内容，为防止覆盖丢失，请先整理节点文本或改用协议追加模式',
    )
  }

  let nextSystem = newReplacedBlock
  for (const layer of otherLayers) {
    assertSafeProtocolBody(layer.body)
    nextSystem = injectModProtocolBlock(nextSystem, layer.modId, layer.body)
  }

  return {
    baselineSystem: pureBaseline,
    nextSystem,
  }
}

/**
 * 更新由本模组创建的独立自定义节点时，仅原地替换经严格唯一无嵌套校验的 :custom:<token> 区间，
 * 字节级保留块外用户前后缀与其他模组挂载层（F4）
 */
export function prepareOwnedCustomSystemUpdate(
  existingSystem: string,
  ownerPackId: string,
  newBaseContent: string,
  expectedOriginToken?: string,
): { nextSystem: string; verifiedToken: string } {
  const safeOwnerId = assertValidModId(ownerPackId)
  assertSafeProtocolBody(newBaseContent)

  if (hasForeignReplacedBlock(existingSystem, safeOwnerId)) {
    throw new Error('该自定义节点正被其他模组完整替换接管，请先停用接管模组后再更新')
  }

  const anyCustomSpan = locateVerifiedCustomBlockSpan(existingSystem, safeOwnerId)
  if (!anyCustomSpan) {
    throw new Error(
      '独立节点缺少唯一且边界完整的模组归属标记（可能已被手动损坏或存在嵌套标记），为防止覆盖丢失您的自定义修改已中止更新',
    )
  }

  if (expectedOriginToken !== undefined && anyCustomSpan.token !== expectedOriginToken) {
    throw new Error('独立节点归属凭证校验不匹配，已拒绝覆盖非本模组创建的自定义节点')
  }

  const updatedBlock = buildOwnedCustomBlock(safeOwnerId, anyCustomSpan.token, newBaseContent)
  const nextSystem =
    existingSystem.slice(0, anyCustomSpan.startIndex) +
    updatedBlock +
    existingSystem.slice(anyCustomSpan.endIndex)
  return {
    nextSystem,
    verifiedToken: anyCustomSpan.token,
  }
}

/**
 * 卸载自建独立节点时剥离经严格无嵌套校验的 :custom:<token> 块；若边界已损坏则拒绝修改并保留原文本（F4）
 */
export function stripOwnedCustomBlock(
  existingSystem: string,
  ownerPackId: string,
  expectedOriginToken?: string,
): { strippedSystem: string; hadValidBlock: boolean } {
  const safeOwnerId = assertValidModId(ownerPackId)
  const span = locateVerifiedCustomBlockSpan(existingSystem, safeOwnerId, expectedOriginToken)
  if (!span) {
    return { strippedSystem: existingSystem, hadValidBlock: false }
  }

  const strippedSystem =
    existingSystem.slice(0, span.startIndex) + existingSystem.slice(span.endIndex)
  return { strippedSystem, hadValidBlock: true }
}

/**
 * 卸载 replace_system 模组时精确将本模组的 :replaced 块还原为安装前基线，保留块外前后缀与追加模组层
 */
export function restoreReplacedModBlock(
  currentSystem: string,
  packId: string,
  baselineSystem: string,
): string {
  const safeId = assertValidModId(packId)
  if (!currentSystem) return currentSystem

  if (!hasReplacedModBlock(currentSystem, safeId)) {
    return stripModProtocolBlock(currentSystem, safeId)
  }

  const span = locateVerifiedReplacedBlockSpan(currentSystem, safeId)
  if (!span) {
    throw new Error(
      `节点中模组「${safeId}」的替换边界标记残缺或存在嵌套冲突，已拒绝自动剥离以防误删块外内容`,
    )
  }

  const prefix = currentSystem.slice(0, span.startIndex)
  const suffix = currentSystem.slice(span.endIndex)
  if (baselineSystem === '') {
    if (prefix === '') {
      const leadingAppendedRe =
        /^\n\n<!-- \[PlotPilot-Mod:([A-Za-z0-9][A-Za-z0-9_.-]{0,95}):START:appended\] -->/
      if (leadingAppendedRe.test(suffix)) {
        return suffix.replace(
          leadingAppendedRe,
          (_m: string, nextModId: string) =>
            `<!-- [PlotPilot-Mod:${nextModId}:START:standalone] -->`,
        )
      }
    }
    return `${prefix}${suffix}`
  }

  return `${prefix}${baselineSystem}${suffix}`
}

function safeDecodeURIComponent(raw: string, label: string): string {
  try {
    return decodeURIComponent(raw)
  } catch {
    throw new Error(`${label} 包含非法的百分号编码`)
  }
}

function assertNoControlChars(value: string, label: string): void {
  if (ASCII_CONTROL_CHAR_RE.test(value)) {
    throw new Error(`${label}包含非法的控制字符`)
  }
}

function validateRepoAtom(value: string, label: string): string {
  assertNoControlChars(value, `GitHub ${label}`)
  const decodedRaw = safeDecodeURIComponent(value, `GitHub ${label}`)
  assertNoControlChars(decodedRaw, `GitHub ${label}`)
  const decoded = decodedRaw.replace(/^ +| +$/g, '')
  if (
    !decoded ||
    decoded !== value ||
    decoded === '.' ||
    decoded === '..' ||
    decoded.includes('..') ||
    decoded.includes('/') ||
    decoded.includes('\\') ||
    !SAFE_REPO_ATOM_RE.test(decoded)
  ) {
    throw new Error(`GitHub ${label} 字段格式非法`)
  }
  return decoded
}

function validateCleanSegments(rawValue: string, label: string, allowSlash = true): string {
  if (!rawValue) {
    throw new Error(`GitHub ${label} 不能为空`)
  }
  assertNoControlChars(rawValue, `GitHub ${label}`)
  const decoded = safeDecodeURIComponent(rawValue, `GitHub ${label}`)
  assertNoControlChars(decoded, `GitHub ${label}`)
  if (rawValue.includes('\\') || decoded.includes('\\')) {
    throw new Error(`GitHub ${label} 包含非法路径分隔符`)
  }
  const rawParts = rawValue.split('/')
  const decParts = decoded.split('/')
  if (!allowSlash && (rawParts.length !== 1 || decParts.length !== 1)) {
    throw new Error(`GitHub ${label} 不允许包含斜杠`)
  }
  for (const part of [...rawParts, ...decParts]) {
    if (!part || part === '.' || part === '..') {
      throw new Error(`GitHub ${label} 不允许包含空段或上级目录引用（..）`)
    }
    if (!SAFE_REPO_ATOM_RE.test(part)) {
      throw new Error(`GitHub ${label} 含受限字符`)
    }
  }
  return decParts.join('/')
}

function isForbiddenLiteralHost(rawHostname: string): boolean {
  const host = rawHostname.trim().toLowerCase().replace(/\.$/, '')
  if (!host) return true
  if (
    host === 'localhost' ||
    host === 'localhost.localdomain' ||
    host.endsWith('.local') ||
    host.endsWith('.internal') ||
    host.endsWith('.localhost')
  ) {
    return true
  }

  const bare = host.startsWith('[') && host.endsWith(']') ? host.slice(1, -1) : host
  if (bare.includes('%')) return true

  const ipv4Match = bare.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/)
  if (ipv4Match) {
    const octets = ipv4Match.slice(1).map(Number)
    if (octets.some(n => Number.isNaN(n) || n < 0 || n > 255)) return true
    const [a, b] = octets
    if (a === 0 || a === 10 || a === 127) return true
    if (a === 169 && b === 254) return true
    if (a === 172 && b >= 16 && b <= 31) return true
    if (a === 192 && b === 168) return true
    if (a === 100 && b >= 64 && b <= 127) return true
    if (a === 198 && (b === 18 || b === 19)) return true
    if (a >= 224) return true
    return false
  }

  if (bare.includes(':')) {
    const norm = bare.toLowerCase()
    if (
      norm === '::' ||
      norm === '::1' ||
      norm.startsWith('fe8') ||
      norm.startsWith('fe9') ||
      norm.startsWith('fea') ||
      norm.startsWith('feb') ||
      norm.startsWith('fc') ||
      norm.startsWith('fd') ||
      norm.startsWith('ff') ||
      norm.includes('::ffff:') ||
      norm.startsWith('64:ff9b:') ||
      norm.startsWith('100::') ||
      norm.startsWith('2001:db8:')
    ) {
      return true
    }
  }

  return false
}

function assertNoStructuralDotSegments(rawPath: string, label: string): void {
  assertNoControlChars(rawPath, label)
  const decodedPath = safeDecodeURIComponent(rawPath, label)
  assertNoControlChars(decodedPath, label)
  if (rawPath.includes('\\') || decodedPath.includes('\\')) {
    throw new Error(`${label}包含非法字符`)
  }
  for (const seg of [...rawPath.split('/'), ...decodedPath.split('/')]) {
    const baseSeg = seg.split(';', 1)[0]
    const decodedBase = safeDecodeURIComponent(baseSeg, label)
    assertNoControlChars(decodedBase, label)
    if (
      seg === '.' ||
      seg === '..' ||
      baseSeg === '.' ||
      baseSeg === '..' ||
      decodedBase === '.' ||
      decodedBase === '..'
    ) {
      throw new Error(`${label}不允许包含相对路径穿越片段（. 或 ..）`)
    }
  }
}

function validateHttpsCandidateUrl(rawUrl: string): string {
  // 在任何空白裁剪或 WHATWG URL 解析之前先对原始输入执行 ASCII 控制字符拦截
  assertNoControlChars(rawUrl, '远程模组 URL ')
  const cleaned = rawUrl.replace(/^ +| +$/g, '')
  if (cleaned.includes('\\')) {
    throw new Error('远程模组 URL 包含非法反斜杠')
  }
  if (!/^https:\/\//i.test(cleaned)) {
    throw new Error('仅支持 HTTPS 安全协议拉取远程模组清单')
  }

  const afterScheme = cleaned.replace(/^https:\/\//i, '')
  const authorityAndPath = afterScheme.split(/[?#]/, 1)[0]
  const slashPos = authorityAndPath.indexOf('/')
  const rawAuthority = slashPos >= 0 ? authorityAndPath.slice(0, slashPos) : authorityAndPath
  if (!rawAuthority || /\s/.test(rawAuthority)) {
    throw new Error('远程模组 URL 缺少有效主机名')
  }
  if (rawAuthority.includes('@')) {
    throw new Error('远程模组 URL 不允许包含认证凭据')
  }
  const rawUnnormalizedPath = slashPos >= 0 ? authorityAndPath.slice(slashPos) : '/'
  assertNoStructuralDotSegments(rawUnnormalizedPath, '远程模组 URL 路径')

  let parsed: URL
  try {
    parsed = new URL(cleaned)
  } catch {
    throw new Error('远程模组 URL 格式无效')
  }

  if (parsed.protocol !== 'https:') {
    throw new Error('仅支持 HTTPS 安全协议拉取远程模组清单')
  }
  if (parsed.username || parsed.password) {
    throw new Error('远程模组 URL 不允许包含认证凭据')
  }
  if (parsed.port !== '' && parsed.port !== '443') {
    throw new Error('远程模组 URL 仅允许标准 443 端口')
  }
  if (isForbiddenLiteralHost(parsed.hostname)) {
    throw new Error('不允许访问本地、内网或保留地址')
  }

  assertNoStructuralDotSegments(parsed.pathname || '/', '远程模组 URL 路径')

  parsed.hash = ''
  return parsed.toString()
}

function buildRawGithubCandidates(
  owner: string,
  repo: string,
  refs: string[],
  explicitSubpath: string | null,
  allowSlashInRef = true,
): { originLabel: string; candidateUrls: string[] } {
  const safeOwner = validateRepoAtom(owner, 'owner')
  const cleanRepoRaw = repo.toLowerCase().endsWith('.git') ? repo.slice(0, -4) : repo
  const safeRepo = validateRepoAtom(cleanRepoRaw, 'repo')
  const safeRefs = refs.map(r => validateCleanSegments(r, 'ref', allowSlashInRef))
  const subpaths = explicitSubpath
    ? [validateCleanSegments(explicitSubpath.replace(/^\/+/, ''), 'path', true)]
    : [...DEFAULT_MANIFEST_FILENAMES]

  const candidateUrls: string[] = []
  for (const refItem of safeRefs) {
    for (const sp of subpaths) {
      candidateUrls.push(
        validateHttpsCandidateUrl(
          `https://raw.githubusercontent.com/${safeOwner}/${safeRepo}/${refItem}/${sp}`,
        ),
      )
    }
  }

  return {
    originLabel: `github:${safeOwner}/${safeRepo}`,
    candidateUrls,
  }
}

function parseCanonicalGithubShorthand(ghShort: string): {
  originLabel: string
  candidateUrls: string[]
} {
  assertNoControlChars(ghShort, 'GitHub 简写')
  const cleaned = ghShort.replace(/^\/+|\/+$/g, '')
  if (!cleaned) {
    throw new Error('GitHub 仓库格式无效，示例：github:owner/repo')
  }

  const hasAt = cleaned.includes('@')
  const hasHash = cleaned.includes('#')
  if (hasAt && hasHash) {
    throw new Error('请勿同时混用 @ref 与 #ref')
  }

  const sigil: '@' | '#' | null = hasAt ? '@' : hasHash ? '#' : null
  if (sigil === null) {
    const parts = cleaned.split('/')
    if (parts.length < 2) {
      throw new Error('GitHub 仓库格式无效，示例：github:owner/repo')
    }
    const [ownerPart, repoPart, ...rest] = parts
    const explicitPath = rest.length > 0 ? rest.join('/') : null
    return buildRawGithubCandidates(ownerPart, repoPart, ['main', 'master'], explicitPath, false)
  }

  if (cleaned.split(sigil).length - 1 > 1) {
    throw new Error(`GitHub 简写中不允许出现多个 '${sigil}' 分隔符`)
  }

  const sigilIdx = cleaned.indexOf(sigil)
  const beforeSigil = cleaned.slice(0, sigilIdx)
  const sigilTail = cleaned.slice(sigilIdx + 1)
  if (!sigilTail) {
    throw new Error('GitHub 分支或标签名不能为空')
  }

  const headParts = beforeSigil.split('/')
  if (headParts.length < 2) {
    throw new Error('GitHub 仓库格式无效，示例：github:owner/repo')
  }

  const [ownerPart, repoPart] = headParts
  if (headParts.length === 2) {
    const slashIdx = sigilTail.indexOf('/')
    if (slashIdx >= 0) {
      const chosenRef = sigilTail.slice(0, slashIdx)
      const explicitPath = sigilTail.slice(slashIdx + 1)
      if (!chosenRef || !explicitPath) {
        throw new Error('GitHub 分支或路径格式非法')
      }
      return buildRawGithubCandidates(ownerPart, repoPart, [chosenRef], explicitPath, false)
    }
    return buildRawGithubCandidates(ownerPart, repoPart, [sigilTail], null, false)
  }

  const explicitPath = headParts.slice(2).join('/')
  return buildRawGithubCandidates(ownerPart, repoPart, [sigilTail], explicitPath, true)
}

export function resolveRemoteCandidateUrls(rawInput: string): {
  originLabel: string
  candidateUrls: string[]
} {
  if (typeof rawInput !== 'string') {
    throw new Error('请输入 GitHub 仓库地址（如 github:owner/repo）或 HTTPS 模组 JSON 链接')
  }
  assertNoControlChars(rawInput, '模组来源地址')
  const raw = rawInput.replace(/^ +| +$/g, '')
  if (!raw) {
    throw new Error('请输入 GitHub 仓库地址（如 github:owner/repo）或 HTTPS 模组 JSON 链接')
  }

  if (/^http:\/\//i.test(raw)) {
    throw new Error('出于安全限制，仅支持 HTTPS 协议拉取远程模组清单')
  }

  let ghShort: string | null = null
  if (raw.toLowerCase().startsWith('github:')) {
    ghShort = raw.slice('github:'.length).replace(/^ +| +$/g, '')
  } else if (!raw.includes('://')) {
    const headBeforeSigil = raw.split('#', 1)[0].split('@', 1)[0]
    const slashHead = headBeforeSigil.split('/')
    if (
      slashHead.length >= 2 &&
      !slashHead[0].includes('.') &&
      SAFE_REPO_ATOM_RE.test(slashHead[0])
    ) {
      ghShort = raw
    }
  }

  if (ghShort !== null) {
    return parseCanonicalGithubShorthand(ghShort)
  }

  if (/^https:\/\//i.test(raw)) {
    // 任何 HTTPS 链接（包含 github.com / www.github.com）均先对原始未归一化字符串执行完整路径穿越与控制字符校验（F2 / F3）
    const validatedUrl = validateHttpsCandidateUrl(raw)
    const parsed = new URL(raw)
    const hostLower = parsed.hostname.toLowerCase()
    if (hostLower === 'github.com' || hostLower === 'www.github.com') {
      const decodedPath = safeDecodeURIComponent(parsed.pathname, 'GitHub 链接路径')
      assertNoControlChars(decodedPath, 'GitHub 链接路径')
      if (raw.includes('\\') || decodedPath.includes('\\')) {
        throw new Error('GitHub 链接包含非法路径分隔符')
      }
      const parts = parsed.pathname.split('/').filter(Boolean)
      if (parts.length < 2) {
        throw new Error('GitHub 链接缺少 owner/repo')
      }
      const [owner, repo] = parts
      if (parts.length >= 4 && parts[2] === 'blob') {
        const branch = parts[3]
        const filePath = parts.slice(4).join('/')
        if (!filePath) {
          throw new Error('GitHub blob 链接缺少文件路径')
        }
        return buildRawGithubCandidates(owner, repo, [branch], filePath)
      }
      if (parts.length >= 4 && parts[2] === 'tree') {
        const branch = parts[3]
        const dirPath = parts.slice(4).join('/').replace(/^\/+|\/+$/g, '')
        if (dirPath) {
          const safeDir = validateCleanSegments(dirPath, 'path', true)
          const mergedUrls: string[] = []
          let originLabel = `github:${owner}/${repo}`
          for (const fname of DEFAULT_MANIFEST_FILENAMES) {
            const res = buildRawGithubCandidates(owner, repo, [branch], `${safeDir}/${fname}`)
            originLabel = res.originLabel
            mergedUrls.push(...res.candidateUrls)
          }
          return { originLabel, candidateUrls: mergedUrls }
        }
        return buildRawGithubCandidates(owner, repo, [branch], null)
      }
      if (parts.length === 2) {
        const rawHash = parsed.hash ? parsed.hash.slice(1) : ''
        const decodedHash = safeDecodeURIComponent(rawHash, 'GitHub 分支片段')
        assertNoControlChars(decodedHash, 'GitHub 分支片段')
        const hashBranch = rawHash.replace(/^ +| +$/g, '')
        const refs = hashBranch ? [hashBranch] : ['main', 'master']
        return buildRawGithubCandidates(owner, repo, refs, null)
      }
      throw new Error('不支持的 GitHub 路径格式，请提供仓库主页或 blob 文件链接')
    }

    return {
      originLabel: hostLower,
      candidateUrls: [validatedUrl],
    }
  }

  throw new Error('格式不受支持：请输入 github:owner/repo、HTTPS GitHub 链接或 HTTPS .json 直链')
}

export async function fetchTrustedBrowserFallbackJson(url: string): Promise<unknown> {
  const validated = validateHttpsCandidateUrl(url)
  const parsed = new URL(validated)
  if (!TRUSTED_BROWSER_FALLBACK_HOSTS.has(parsed.hostname.toLowerCase())) {
    throw new Error(
      '当前旧版后端未启用远程安全代理（/mods/fetch-remote），兼容模式仅允许从受信任 GitHub 源（github:owner/repo）拉取模组',
    )
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), LEGACY_FALLBACK_TIMEOUT_MS)
  try {
    const resp = await fetch(validated, {
      method: 'GET',
      redirect: 'error',
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
      signal: controller.signal,
    })

    if (resp.status === 404) {
      return null
    }
    if (!resp.ok) {
      throw new Error(`GitHub Raw 返回 HTTP ${resp.status}`)
    }
    if (resp.url) {
      const finalUrl = new URL(resp.url)
      if (
        finalUrl.protocol !== 'https:' ||
        (finalUrl.port !== '' && finalUrl.port !== '443') ||
        !TRUSTED_BROWSER_FALLBACK_HOSTS.has(finalUrl.hostname.toLowerCase())
      ) {
        throw new Error('远程响应最终源超出受信任主机范围，已拦截')
      }
    }

    const clHeader = resp.headers.get('content-length')
    if (clHeader && /^\d+$/.test(clHeader) && Number(clHeader) > MOD_MANIFEST_MAX_BYTES) {
      throw new Error('远程模组清单超过 1MB 安全上限')
    }

    if (!resp.body || typeof resp.body.getReader !== 'function') {
      throw new Error('当前环境不支持流式字节上限校验，已拒绝无界读取响应体')
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8', { fatal: true })
    const chunks: string[] = []
    let totalBytes = 0
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (value) {
        totalBytes += value.byteLength
        if (totalBytes > MOD_MANIFEST_MAX_BYTES) {
          await reader.cancel()
          throw new Error('远程模组清单超过 1MB 安全上限')
        }
        chunks.push(decoder.decode(value, { stream: true }))
      }
    }
    chunks.push(decoder.decode())
    const rawText = chunks.join('')

    const parsedJson = JSON.parse(rawText) as unknown
    if (!parsedJson || typeof parsedJson !== 'object' || Array.isArray(parsedJson)) {
      throw new Error('远程模组清单根节点必须为 JSON 对象')
    }
    return parsedJson
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('拉取远程模组清单超时（10s）')
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

export function inferRoleFromZone(zone?: string): {
  category: Exclude<ModRoleCategory, 'all'>
  label: string
} {
  switch (zone) {
    case 'genre_hooks':
    case 'opening_artifact':
      return { category: 'opening-hook', label: '题材开局包' }
    case 'structure_pacing':
      return { category: 'pacing-plot', label: '剧情节拍器' }
    case 'packaging_benchmarking':
      return { category: 'review-guard', label: '毒点审稿官' }
    case 'creative_components':
      return { category: 'worldbuilding', label: '世界观营造' }
    default:
      return { category: 'opening-hook', label: '题材开局包' }
  }
}

export function parseAnyModJson(
  rawObj: unknown,
  originLabel = '本地导入',
  defaultTrust: ModTrustLevel = 'community-unreviewed',
): NarrativeModPack {
  if (!rawObj || typeof rawObj !== 'object' || Array.isArray(rawObj)) {
    throw new Error('模组文件不是有效的 JSON 对象')
  }
  const obj = rawObj as Record<string, unknown>

  if (obj.schema === 'plotpilot-mod/v1' && obj.pack && typeof obj.pack === 'object') {
    const pack = obj.pack as Partial<NarrativeModPack>
    return normalizePackObject(pack, originLabel, defaultTrust)
  }

  if (typeof obj.name === 'string' && Array.isArray(obj.overrides)) {
    return normalizePackObject(obj as Partial<NarrativeModPack>, originLabel, defaultTrust)
  }

  if (Array.isArray(obj.prompts) && obj.prompts.length > 0) {
    const meta = (
      obj._meta && typeof obj._meta === 'object' ? obj._meta : {}
    ) as Record<string, unknown>
    const prompts = obj.prompts as Array<Record<string, unknown>>
    const seenKeys = new Set<string>()
    const overrides: ModNodeOverride[] = []

    for (let idx = 0; idx < prompts.length && overrides.length < 24; idx += 1) {
      const p = prompts[idx]
      if (!p || typeof p !== 'object') continue
      const rawKey = String(p.node_key || p.id || `imported-node-${idx + 1}`).trim()
      const key = assertValidNodeKey(rawKey)
      if (seenKeys.has(key)) {
        throw new Error(`导入提示词包存在重复节点键「${key}」`)
      }
      seenKeys.add(key)

      const systemContent = String(p.system || p.system_prompt || '')
      if (!systemContent.trim()) continue
      assertSafeProtocolBody(systemContent, `节点「${key}」内容`)
      if (typeof p.user_template === 'string') {
        assertSafeProtocolBody(p.user_template, `节点「${key}」User 模板`)
      }

      const label = String(p.name || key).trim() || key
      const isBuiltin = Boolean(p.is_builtin)
      overrides.push({
        nodeKey: key,
        nodeLabel: label,
        mode: isBuiltin ? 'replace_system' : 'standalone_node',
        systemContent,
        userTemplate: typeof p.user_template === 'string' ? p.user_template : undefined,
        backendCategory: typeof p.category === 'string' ? p.category : 'generation',
      })
    }

    if (!overrides.length) {
      throw new Error('prompts 数组中未找到包含有效提示词正文的节点定义')
    }

    const packName = String(
      meta.name || meta.title || `导入提示词包（${overrides.length} 节点）`,
    )
    const generatedId = assertValidModId(`mod-import-${Date.now().toString(36)}`)
    return {
      id: generatedId,
      name: packName,
      glyph: packName.trim().charAt(0) || '模',
      author: String(meta.author || '社区创作者'),
      repoOrOrigin: originLabel,
      trustLevel: defaultTrust,
      roleCategory: 'style-anti-ai',
      roleLabel: '综合模组包',
      summary: String(
        meta.description ||
          `从 ${originLabel} 导入的提示词模组包，共包含 ${overrides.length} 个引擎节点配置。`,
      ),
      readmeSections: [
        {
          heading: '导入说明',
          body: `该模组由标准提示词备份转换生成，共接管或新增 ${overrides.length} 个节点，卸载时可一键无损回滚至安装前基线。`,
        },
      ],
      version: String(meta.version || 'v1.0.0'),
      license: String(meta.license || 'Custom'),
      updatedAt: new Date().toISOString().slice(0, 10),
      usageLabel: defaultTrust === 'local' ? '本地导入' : '外部仓库',
      replacesBuiltin: overrides.some(o => o.mode !== 'standalone_node'),
      overrides,
      tags: ['外部导入', `${overrides.length} 节点`],
    }
  }

  throw new Error(
    '无法识别的模组 JSON 结构：请提供 plotpilot-mod/v1 清单或包含 prompts 数组的备份文件',
  )
}

function normalizePackObject(
  raw: Partial<NarrativeModPack>,
  originLabel: string,
  defaultTrust: ModTrustLevel,
): NarrativeModPack {
  const name = (raw.name || '').trim()
  if (!name) {
    throw new Error('模组缺少名称（name）字段')
  }
  const rawOverrides = Array.isArray(raw.overrides) ? raw.overrides : []
  const seenKeys = new Set<string>()
  const overrides: ModNodeOverride[] = []

  for (const o of rawOverrides) {
    if (!o || typeof o.nodeKey !== 'string' || typeof o.systemContent !== 'string') {
      continue
    }
    const cleanKey = assertValidNodeKey(o.nodeKey)
    if (seenKeys.has(cleanKey)) {
      throw new Error(`模组清单包含重复的目标节点键「${cleanKey}」`)
    }
    seenKeys.add(cleanKey)
    if (!o.systemContent.trim()) {
      throw new Error(`模组节点「${cleanKey}」的提示词内容（systemContent）不能为空`)
    }
    assertSafeProtocolBody(o.systemContent, `模组节点「${cleanKey}」`)
    if (typeof o.userTemplate === 'string') {
      assertSafeProtocolBody(o.userTemplate, `模组节点「${cleanKey}」User 模板`)
    }

    overrides.push({
      nodeKey: cleanKey,
      nodeLabel: (o.nodeLabel || cleanKey).trim(),
      mode:
        o.mode === 'replace_system' || o.mode === 'standalone_node'
          ? o.mode
          : 'append_protocol',
      systemContent: o.systemContent,
      userTemplate: typeof o.userTemplate === 'string' ? o.userTemplate : undefined,
      backendCategory: typeof o.backendCategory === 'string' ? o.backendCategory : undefined,
    })
  }

  if (!overrides.length) {
    throw new Error('模组未声明任何有效的节点接管规则（overrides 为空）')
  }

  const id = assertValidModId(raw.id ? raw.id.trim() : `mod-${Date.now().toString(36)}`)
  const trustLevel: ModTrustLevel = raw.trustLevel === 'local' ? 'local' : defaultTrust

  return {
    id,
    name,
    glyph: (raw.glyph || name.charAt(0) || '模').slice(0, 2),
    author: (raw.author || '社区作者').trim(),
    repoOrOrigin: (raw.repoOrOrigin || originLabel).trim(),
    trustLevel,
    roleCategory: raw.roleCategory || 'style-anti-ai',
    roleLabel: (raw.roleLabel || '社区模组').trim(),
    summary: (raw.summary || `安装后接管 ${overrides.length} 个叙事节点。`).trim(),
    readmeSections:
      Array.isArray(raw.readmeSections) && raw.readmeSections.length > 0
        ? raw.readmeSections
        : [{ heading: '模组说明', body: raw.summary || name }],
    version: (raw.version || 'v1.0.0').trim(),
    license: (raw.license || 'MIT').trim(),
    updatedAt: (raw.updatedAt || new Date().toISOString().slice(0, 10)).trim(),
    usageLabel: (raw.usageLabel || (trustLevel === 'local' ? '本地自制' : '社区仓库')).trim(),
    replacesBuiltin:
      raw.replacesBuiltin ?? overrides.some(o => o.mode !== 'standalone_node'),
    overrides,
    showcase: raw.showcase,
    tags: Array.isArray(raw.tags) ? raw.tags.slice(0, 6) : [],
    cloudSourceId: raw.cloudSourceId,
  }
}

export function validatePackInvariants(pack: NarrativeModPack): void {
  assertValidModId(pack.id)
  if (!Array.isArray(pack.overrides) || pack.overrides.length === 0) {
    throw new Error('模组未声明任何有效的节点接管规则')
  }
  const seenKeys = new Set<string>()
  for (const ov of pack.overrides) {
    const cleanKey = assertValidNodeKey(ov.nodeKey)
    if (seenKeys.has(cleanKey)) {
      throw new Error(`模组存在重复的目标节点键「${cleanKey}」`)
    }
    seenKeys.add(cleanKey)
    if (!ov.systemContent.trim()) {
      throw new Error(`模组节点「${cleanKey}」缺少有效提示词内容`)
    }
    assertSafeProtocolBody(ov.systemContent, `模组节点「${cleanKey}」`)
    if (ov.userTemplate !== undefined) {
      assertSafeProtocolBody(ov.userTemplate, `模组节点「${cleanKey}」User 模板`)
    }
  }
}
