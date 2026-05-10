import type { AxiosRequestConfig } from 'axios'

import { WIZARD_STEP_TIMEOUT_MS } from '@/constants/wizard'
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
  /** AI 生成时的角色定位（主角/配角等） */
  role?: string
  mental_state?: string
  verbal_tic?: string
  idle_behavior?: string
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
}

export interface AddCharacterRequest {
  character_id: string
  name: string
  description: string
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
  ) =>
    apiClient.put<BibleDTO>(`/bible/novels/${novelId}/bible`, data) as Promise<BibleDTO>,

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
    }>(`/bible/novels/${novelId}/bible/generation-feedback`, { timeout: 30_000 }) as Promise<{
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
}

export type BibleStreamErrorEvent = {
  type: 'error'
  message: string
}

export type BibleStreamEvent =
  | BibleStreamPhaseEvent
  | BibleStreamDataEvent
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
    onWorldbuildingDimension?: (data: WorldbuildingDimensionData) => void
    /** 字段级流式回调：每个世界观字段到达时触发 */
    onWorldbuildingField?: (dimension: string, field: string, value: string) => void
    /** 字段级 chunk 回调：LLM 逐 token 输出时触发（真正的流式渲染） */
    onWorldbuildingFieldChunk?: (dimension: string, field: string, chunk: string) => void
    /** 字段级完成回调：该字段 LLM 流式输出结束 */
    onWorldbuildingFieldDone?: (dimension: string, field: string, value: string) => void
    /** 维度级 chunk 回调：LLM 逐 token 输出维度 JSON 时触发 */
    onWorldbuildingDimChunk?: (dimension: string, chunk: string) => void
    onCharacter?: (char: Record<string, unknown>, index: number) => void
    onLocation?: (loc: Record<string, unknown>, index: number) => void
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

  /** 解析 SSE 块中的 event + data 行 */
  function parseSseBlock(block: string): { event: string; data: string } | null {
    let event = ''
    let data = ''
    for (const line of block.split('\n')) {
      if (line.startsWith('event: ')) {
        event = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        data = line.slice(6)
      }
    }
    if (!event && !data) return null
    return { event, data }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })

      let sep: number
      while ((sep = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, sep)
        buf = buf.slice(sep + 2)

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
          } else if (dataType === 'worldbuilding_field_chunk') {
            // 逐 token 流式 chunk：追加到字段内容
            handlers.onWorldbuildingFieldChunk?.(
              String(payload?.dimension ?? ''),
              String(payload?.field ?? ''),
              String(payload?.chunk ?? ''),
            )
          } else if (dataType === 'worldbuilding_field_done') {
            // 字段流式输出完成
            handlers.onWorldbuildingFieldDone?.(
              String(payload?.dimension ?? ''),
              String(payload?.field ?? ''),
              String(payload?.value ?? ''),
            )
          } else if (dataType === 'worldbuilding_dim_chunk') {
            // 维度级流式 chunk：LLM 逐 token 输出维度 JSON
            handlers.onWorldbuildingDimChunk?.(
              String(payload?.dimension ?? ''),
              String(payload?.chunk ?? ''),
            )
          } else if (dataType === 'worldbuilding_field') {
            // 字段级流式推送：每个字段单独到达
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
          } else if (dataType === 'location') {
            handlers.onLocation?.((payload?.content ?? {}) as Record<string, unknown>, Number(payload?.index ?? 0))
          }
        } else if (event === 'done') {
          handlers.onDone?.(String(payload?.novel_id ?? novelId))
          return
        } else if (event === 'error') {
          handlers.onError?.(String(payload?.message ?? '生成失败'))
          return
        }
      }
    }
  } catch (e: unknown) {
    if (e instanceof Error && e.name === 'AbortError') return
    handlers.onError?.(e instanceof Error ? e.message : '流式连接失败')
  }
}
