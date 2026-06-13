import type { AxiosRequestConfig } from 'axios'

import { WIZARD_STEP_TIMEOUT_MS } from '@/constants/wizard'
import { runtimePerformance } from '@/config/performance'
import { apiClient, resolveHttpUrl } from './config'

/** Bible 人物关系：字符串 或 LLM 结构化对象 */
export type BibleRelationshipEntry =
  | string
  | { target?: string; relation?: string; description?: string }

export interface CharacterDTO {
  id: string
  name: string
  description: string
  relationships: BibleRelationshipEntry[]
  gender?: string
  age?: string
  appearance?: string
  personality?: string
  background?: string
  core_motivation?: string
  inner_lack?: string
  /** AI 生成时的角色定位（主角/配角等）— 后端不持久化此字段，仅从 description 解析 */
  role?: string
  mental_state?: string
  verbal_tic?: string
  idle_behavior?: string
  mental_state_reason?: string
  core_belief?: string
  moral_taboos?: string[]
  voice_profile?: Record<string, unknown>
  active_wounds?: Array<Record<string, string>>
  /** POV 防火墙：公开人设 */
  public_profile?: string
  /** POV 防火墙：隐藏身份 */
  hidden_profile?: string
  /** 揭示隐藏身份的章节号 */
  reveal_chapter?: number | null
}

export interface WorldSettingDTO {
  id: string
  name: string
  description: string
  setting_type: string
}

export interface LocationDTO {
  id: string
  name: string
  description: string
  location_type: string
}

export interface TimelineNoteDTO {
  id: string
  event: string
  time_point: string
  description: string
}

export interface StyleNoteDTO {
  id: string
  category: string
  content: string
}

export interface BibleDTO {
  id: string
  novel_id: string
  characters: CharacterDTO[]
  world_settings: WorldSettingDTO[]
  locations: LocationDTO[]
  timeline_notes: TimelineNoteDTO[]
  style_notes: StyleNoteDTO[]
  style?: string
}

export interface AddCharacterRequest {
  character_id: string
  name: string
  description: string
}

type SilentAxiosRequestConfig = AxiosRequestConfig & { silentGlobalFeedback?: boolean }

function createRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `req_${Date.now()}_${Math.random().toString(16).slice(2)}`
}

function bibleWriteSnapshot(bible: BibleDTO | null | undefined): string {
  if (!bible) return ''
  return JSON.stringify({
    characters: bible.characters ?? [],
    world_settings: bible.world_settings ?? [],
    locations: bible.locations ?? [],
    timeline_notes: bible.timeline_notes ?? [],
    style_notes: bible.style_notes ?? [],
  })
}

function bibleUpdatePayloadSnapshot(data: {
  characters: CharacterDTO[]
  world_settings: WorldSettingDTO[]
  locations: LocationDTO[]
  timeline_notes: TimelineNoteDTO[]
  style_notes: StyleNoteDTO[]
}): string {
  return JSON.stringify({
    characters: data.characters ?? [],
    world_settings: data.world_settings ?? [],
    locations: data.locations ?? [],
    timeline_notes: data.timeline_notes ?? [],
    style_notes: data.style_notes ?? [],
  })
}

async function verifyBibleWrite(
  novelId: string,
  expectedPayload: {
    characters: CharacterDTO[]
    world_settings: WorldSettingDTO[]
    locations: LocationDTO[]
    timeline_notes: TimelineNoteDTO[]
    style_notes: StyleNoteDTO[]
  },
): Promise<BibleDTO | null> {
  try {
    const current = await apiClient.get<BibleDTO>(`/bible/novels/${novelId}/bible`, {
      silentGlobalFeedback: true,
    } as SilentAxiosRequestConfig)
    return bibleWriteSnapshot(current) === bibleUpdatePayloadSnapshot(expectedPayload) ? current : null
  } catch {
    return null
  }
}

async function updateBibleWithVerification(
  novelId: string,
  data: {
    characters: CharacterDTO[]
    world_settings: WorldSettingDTO[]
    locations: LocationDTO[]
    timeline_notes: TimelineNoteDTO[]
    style_notes: StyleNoteDTO[]
  },
): Promise<BibleDTO> {
  const requestId = createRequestId()
  const config: SilentAxiosRequestConfig = {
    headers: {
      'X-Request-Id': requestId,
      'X-Idempotency-Key': requestId,
    },
  }
  try {
    return await apiClient.put<BibleDTO>(`/bible/novels/${novelId}/bible`, data, config)
  } catch (err) {
    const verified = await verifyBibleWrite(novelId, data)
    if (verified) {
      return verified
    }
    try {
      const secondAttempt = await apiClient.put<BibleDTO>(`/bible/novels/${novelId}/bible`, data, config)
      return secondAttempt
    } catch (secondErr) {
      const verifiedAgain = await verifyBibleWrite(novelId, data)
      if (verifiedAgain) {
        return verifiedAgain
      }
      throw secondErr ?? err
    }
  }
}

export const bibleApi = {
  /**
   * Create bible for a novel
   * POST /api/v1/bible/novels/{novelId}/bible
   */
  createBible: (novelId: string, bibleId: string) =>
    apiClient.post<BibleDTO>(`/bible/novels/${novelId}/bible`, {
      bible_id: bibleId,
      novel_id: novelId,
    }) as Promise<BibleDTO>,

  /**
   * Get bible by novel ID
   * GET /api/v1/bible/novels/{novelId}/bible
   */
  getBible: (novelId: string, config?: AxiosRequestConfig) =>
    apiClient.get<BibleDTO>(`/bible/novels/${novelId}/bible`, config) as Promise<BibleDTO>,

  /**
   * List all characters in a bible
   * GET /api/v1/bible/novels/{novelId}/bible/characters
   */
  listCharacters: (novelId: string) =>
    apiClient.get<CharacterDTO[]>(`/bible/novels/${novelId}/bible/characters`) as Promise<CharacterDTO[]>,

  /**
   * Add character to bible
   * POST /api/v1/bible/novels/{novelId}/bible/characters
   */
  addCharacter: (novelId: string, data: AddCharacterRequest) =>
    apiClient.post<BibleDTO>(`/bible/novels/${novelId}/bible/characters`, data) as Promise<BibleDTO>,

  /**
   * Add world setting to bible
   * POST /api/v1/bible/novels/{novelId}/bible/world-settings
   */
  addWorldSetting: (
    novelId: string,
    data: { setting_id: string; name: string; description: string; setting_type: string }
  ) =>
    apiClient.post<BibleDTO>(`/bible/novels/${novelId}/bible/world-settings`, data) as Promise<BibleDTO>,

  /**
   * Bulk update entire bible
   * PUT /api/v1/bible/novels/{novelId}/bible
   */
  updateBible: (
    novelId: string,
    data: {
      characters: CharacterDTO[]
      world_settings: WorldSettingDTO[]
      locations: LocationDTO[]
      timeline_notes: TimelineNoteDTO[]
      style_notes: StyleNoteDTO[]
    }
  ) => updateBibleWithVerification(novelId, data),

  /**
   * AI generate (or regenerate) Bible for a novel
   * POST /api/v1/bible/novels/{novelId}/generate
   */
  /** 后端 202 即返回；冷启动、远程网关或本地代理较慢时需留足握手时间（引导页默认 400s） */
  generateBible: (novelId: string, stage: string = 'all') =>
    apiClient.post<{ message: string; novel_id: string; status_url: string }>(
      `/bible/novels/${novelId}/generate?stage=${stage}`,
      {},
      { timeout: WIZARD_STEP_TIMEOUT_MS }
    ) as Promise<{ message: string; novel_id: string; status_url: string }>,

  /**
   * Check Bible generation status
   * GET /api/v1/bible/novels/{novelId}/bible/status
   */
  getBibleStatus: (novelId: string) =>
    apiClient.get<{ exists: boolean; ready: boolean; novel_id: string }>(
      `/bible/novels/${novelId}/bible/status`,
      { timeout: WIZARD_STEP_TIMEOUT_MS }
    ) as Promise<{ exists: boolean; ready: boolean; novel_id: string }>,

  /**
   * 异步 Bible 生成失败原因（单进程内存；成功或未失败时 error 为 null）
   * GET /api/v1/bible/novels/{novelId}/bible/generation-feedback
   */
  getBibleGenerationFeedback: (novelId: string) =>
    apiClient.get<{
      novel_id: string
      error: string | null
      stage: string | null
      at: string | null
    }>(`/bible/novels/${novelId}/bible/generation-feedback`, {
      timeout: runtimePerformance.network.shortTaskTimeoutMs,
    }) as Promise<{
      novel_id: string
      error: string | null
      stage: string | null
      at: string | null
    }>,
}

// ---------------------------------------------------------------------------
// SSE 流式 Bible 生成
// ---------------------------------------------------------------------------

/** 世界观某个维度的数据 */
export interface WorldbuildingDimensionData {
  dimension: string    // core_rules / geography / society / culture / daily_life
  label: string        // 核心法则 / 地理生态 / 社会结构 / 历史文化 / 沉浸感细节
  content: Record<string, string>
}

/** SSE 事件类型 */
export type BibleStreamPhaseEvent = {
  type: 'phase'
  phase: string    // init / worldbuilding / characters / locations / knowledge / *_done
  message: string
}

export type BibleStreamDataEvent = {
  type: 'data'
  data_type: 'style' | 'worldbuilding_dimension' | 'character' | 'location'
  /** style → string; worldbuilding_dimension → WorldbuildingDimensionData; character/location → 对象 */
  content: unknown
  /** worldbuilding_dimension 专属 */
  dimension?: string
  label?: string
  /** character / location 专属 */
  index?: number
}

export type BibleStreamDoneEvent = {
  type: 'done'
  message: string
  novel_id: string
  invocation_session_id?: string
}

export type BibleStreamApprovalRequiredEvent = {
  type: 'approval_required'
  session_id: string
  status?: string
  next_action?: string
  stage?: string
}

export type BibleStreamErrorEvent = {
  type: 'error'
  message: string
}

export type BibleStreamEvent =
  | BibleStreamPhaseEvent
  | BibleStreamDataEvent
  | BibleStreamApprovalRequiredEvent
  | BibleStreamDoneEvent
  | BibleStreamErrorEvent

/**
 * POST /api/v1/bible/novels/{novelId}/generate-stream（SSE）
 * 流式 Bible 生成：逐步推送每个维度的数据，前端可实时渲染。
 */
export async function consumeBibleGenerateStream(
  novelId: string,
  stage: string,
  handlers: {
    onPhase?: (phase: string, message: string) => void
    onStyle?: (content: string) => void
    onStyleChunk?: (chunk: string) => void
    onWorldbuildingDimension?: (data: WorldbuildingDimensionData) => void
    /** 字段到达时更新 UI（服务端 schema 归一化后的规范键） */
    onWorldbuildingField?: (dimension: string, field: string, value: string) => void
    /** 整包世界观 JSON token（兼容旧服务端；UI 应依赖完整 field/dimension 事件） */
    onWorldbuildingChunk?: (chunk: string) => void
    onCharacter?: (char: Record<string, unknown>, index: number) => void
    /** 人物生成时 LLM 逐 token chunk（打字效果/进度） */
    onCharacterChunk?: (chunk: string) => void
    onLocation?: (loc: Record<string, unknown>, index: number) => void
    /** 地点生成时 LLM 逐 token chunk（打字效果/进度） */
    onLocationChunk?: (chunk: string) => void
    onApprovalRequired?: (sessionId: string, status?: string, nextAction?: string, stage?: string) => void
    onDone?: (novelId: string) => void
    onError?: (message: string) => void
    signal?: AbortSignal
  }
): Promise<void> {
  const url = resolveHttpUrl(`/api/v1/bible/novels/${novelId}/generate-stream?stage=${stage}`)
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
    signal: handlers.signal,
  })
  if (!res.ok || !res.body) {
    const t = await res.text().catch(() => '')
    handlers.onError?.(t || `HTTP ${res.status}`)
    return
  }

  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''

  function takeNextSseBlock(buffer: string): { block: string; rest: string } | null {
    const lfIdx = buffer.indexOf('\n\n')
    const crlfIdx = buffer.indexOf('\r\n\r\n')
    let sep = -1
    let sepLen = 2
    if (lfIdx !== -1 && (crlfIdx === -1 || lfIdx <= crlfIdx)) {
      sep = lfIdx
      sepLen = 2
    } else if (crlfIdx !== -1) {
      sep = crlfIdx
      sepLen = 4
    }
    if (sep < 0) return null
    return {
      block: buffer.slice(0, sep),
      rest: buffer.slice(sep + sepLen),
    }
  }

  /** 解析 SSE 块中的 event + data 行 */
  function parseSseBlock(block: string): { event: string; data: string } | null {
    let event = ''
    const dataLines: string[] = []
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith('event:')) {
        event = line.startsWith('event: ') ? line.slice(7).trim() : line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.startsWith('data: ') ? line.slice(6) : line.slice(5).replace(/^\s/, ''))
      }
    }
    const data = dataLines.join('\n')
    if (!event && !data) return null
    return { event, data }
  }

  try {
    const drainCompleteFrames = (): boolean => {
      let next: { block: string; rest: string } | null
      while ((next = takeNextSseBlock(buf))) {
        const block = next.block
        buf = next.rest

        const parsed = parseSseBlock(block)
        if (!parsed) continue

        const { event, data: dataStr } = parsed
        let payload: Record<string, unknown> | null = null
        try {
          payload = JSON.parse(dataStr) as Record<string, unknown>
        } catch {
          continue
        }

        if (event === 'phase') {
          handlers.onPhase?.(String(payload?.phase ?? ''), String(payload?.message ?? ''))
        } else if (event === 'data') {
          const dataType = String(payload?.type ?? '')
          if (dataType === 'style') {
            handlers.onStyle?.(String(payload?.content ?? ''))
          } else if (dataType === 'style_chunk') {
            handlers.onStyleChunk?.(String(payload?.chunk ?? ''))
          } else if (dataType === 'worldbuilding_chunk') {
            handlers.onWorldbuildingChunk?.(String(payload?.chunk ?? ''))
          } else if (dataType === 'worldbuilding_field') {
            handlers.onWorldbuildingField?.(
              String(payload?.dimension ?? ''),
              String(payload?.field ?? ''),
              String(payload?.value ?? ''),
            )
          } else if (dataType === 'worldbuilding_dimension') {
            handlers.onWorldbuildingDimension?.({
              dimension: String(payload?.dimension ?? ''),
              label: String(payload?.label ?? ''),
              content: (payload?.content ?? {}) as Record<string, string>,
            })
          } else if (dataType === 'character') {
            handlers.onCharacter?.((payload?.content ?? {}) as Record<string, unknown>, Number(payload?.index ?? 0))
          } else if (dataType === 'character_chunk') {
            handlers.onCharacterChunk?.(String(payload?.chunk ?? ''))
          } else if (dataType === 'location') {
            handlers.onLocation?.((payload?.content ?? {}) as Record<string, unknown>, Number(payload?.index ?? 0))
          } else if (dataType === 'location_chunk') {
            handlers.onLocationChunk?.(String(payload?.chunk ?? ''))
          } else if (dataType === 'approval_required') {
            const sessionId = String(payload?.session_id ?? '')
            if (sessionId) {
              handlers.onApprovalRequired?.(
                sessionId,
                typeof payload?.status === 'string' ? payload.status : undefined,
                typeof payload?.next_action === 'string' ? payload.next_action : undefined,
                typeof payload?.stage === 'string' ? payload.stage : undefined,
              )
            }
            return true
          }
        } else if (event === 'done') {
          handlers.onDone?.(String(payload?.novel_id ?? novelId))
          return true
        } else if (event === 'error') {
          handlers.onError?.(String(payload?.message ?? '生成失败'))
          return true
        }
      }
      return false
    }

    while (true) {
      const { done, value } = await reader.read()
      if (value) buf += dec.decode(value, { stream: true })
      if (drainCompleteFrames()) return
      if (done) {
        buf += dec.decode()
        drainCompleteFrames()
        break
      }
    }
  } catch (e: unknown) {
    if (e instanceof Error && e.name === 'AbortError') return
    handlers.onError?.(e instanceof Error ? e.message : '流式连接失败')
  }
}
