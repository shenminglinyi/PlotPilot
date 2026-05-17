/**
 * 统一的规划 API
 */

import { apiClient, resolveHttpUrl } from './config'

/** 开发态前端日志：与后端 `continuous_planning_routes` 中 `[MacroSSEWatch]` 等关键词对齐，便于同一控制台/filter 对照 */
function truncFeMsg(s: string, max: number): string {
  if (s.length <= max) return s
  return `${s.slice(0, max)}…`
}

/** 单次读里可能含多条 SSE；同步连续触发 onNode/onChapter 会被 Vue 批量合并成一次 DOM 更新，侧栏看起来像「一次性出来」。每节点后交出一帧。 */
function yieldForIncrementalUi(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => resolve())
  })
}

/** SSE 帧分隔：标准为 LF，部分运行栈用 CRLF；仅用 `\n\n` 会在 `\r\n\r\n` 下永远拆不出帧。 */
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

/** 单条 SSE event 内：多行 `data:` 需用换行拼回（与 WHATWG / RFC 8895 一致），原先只取最后一行会截断长 JSON。 */
function parseSseEventBlock(block: string): { eventType: string; dataStr: string } {
  let eventType = 'message'
  const dataLines: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) {
      eventType = line.startsWith('event: ') ? line.slice(7).trim() : line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.startsWith('data: ') ? line.slice(6) : line.slice(5).replace(/^\s/, ''))
    }
  }
  return { eventType, dataStr: dataLines.join('\n') }
}

function macroSseWatchFeDebug(novelId: string, message: string, extra?: Record<string, unknown>): void {
  if (!import.meta.env.DEV) return
  if (extra && Object.keys(extra).length > 0) {
    console.debug(`[MacroSSEWatch][FE] novel=${novelId} ${message}`, extra)
  } else {
    console.debug(`[MacroSSEWatch][FE] novel=${novelId} ${message}`)
  }
}

function macroSseWatchFeInfo(novelId: string, message: string, extra?: Record<string, unknown>): void {
  if (!import.meta.env.DEV) return
  if (extra && Object.keys(extra).length > 0) {
    console.info(`[MacroSSEWatch][FE] novel=${novelId} ${message}`, extra)
  } else {
    console.info(`[MacroSSEWatch][FE] novel=${novelId} ${message}`)
  }
}

function macroSseWatchFeWarn(novelId: string, message: string, extra?: Record<string, unknown>): void {
  if (!import.meta.env.DEV) return
  if (extra && Object.keys(extra).length > 0) {
    console.warn(`[MacroSSEWatch][FE] novel=${novelId} ${message}`, extra)
  } else {
    console.warn(`[MacroSSEWatch][FE] novel=${novelId} ${message}`)
  }
}

function macroPlanStreamFeWarn(novelId: string, message: string, extra?: Record<string, unknown>): void {
  if (!import.meta.env.DEV) return
  const tag = '[MacroPlanStream][FE]'
  if (extra && Object.keys(extra).length > 0) {
    console.warn(`${tag} novel=${novelId} ${message}`, extra)
  } else {
    console.warn(`${tag} novel=${novelId} ${message}`)
  }
}

function macroPlanStreamFeDebug(novelId: string, message: string, extra?: Record<string, unknown>): void {
  if (!import.meta.env.DEV) return
  const tag = '[MacroPlanStream][FE]'
  if (extra && Object.keys(extra).length > 0) {
    console.debug(`${tag} novel=${novelId} ${message}`, extra)
  } else {
    console.debug(`${tag} novel=${novelId} ${message}`)
  }
}

// ==================== 类型定义 ====================

export interface StructurePreference {
  parts: number
  volumes_per_part: number
  acts_per_volume: number
}

export interface MacroPlanRequest {
  target_chapters: number
  structure: StructurePreference
}

export interface MacroActNode {
  title: string
  description?: string
  [key: string]: unknown
}

export interface MacroVolumeNode {
  title: string
  description?: string
  acts?: MacroActNode[]
  [key: string]: unknown
}

export interface MacroPartNode {
  title: string
  description?: string
  volumes?: MacroVolumeNode[]
  [key: string]: unknown
}

export interface MacroPlanGenerateResponse {
  success: boolean
  task_started: boolean
  novel_id: string
  [key: string]: unknown
}

export interface MacroPlanProgress {
  status: 'idle' | 'running' | 'completed' | 'failed'
  current: number
  total: number
  percent: number
  message: string
  /** LLM 流式输出的累积文本（宏观规划生成过程中） */
  llm_stream_text?: string
}

export interface MacroPlanResultPayload {
  success: boolean
  structure: MacroPartNode[]
  quality_metrics?: Record<string, unknown>
  generation_time?: number
  [key: string]: unknown
}

export interface MacroPlanResultResponse {
  ready: boolean
  result: MacroPlanResultPayload | null
  error: string | null
}

export interface ActChaptersRequest {
  chapter_count?: number
}

export interface ContinuePlanningRequest {
  current_chapter: number
}

export interface ContinuePlanResult {
  /** 当前幕是否写完 */
  is_act_complete: boolean
  /** 是否需要创建下一幕 */
  needs_next_act: boolean
  /** 当前幕 story_node id（用于 createNextAct） */
  current_act_id: string | null
  /** 当前幕标题 */
  current_act_title?: string
  /** 当前章号在幕内的进度说明 */
  progress_message?: string
  /** 幕内已写章节数 */
  completed_chapters?: number
  /** 幕内总规划章节数 */
  total_chapters?: number
  /** 后端原始消息（兜底） */
  message?: string
  [key: string]: unknown
}

/** story_node 结构节点（树形，与后端 to_dict / 层级树一致） */
export interface StoryNode {
  id: string
  novel_id?: string
  node_type: 'part' | 'volume' | 'act' | 'chapter'
  title: string
  number?: number
  description?: string
  outline?: string
  children?: StoryNode[]
  /** 章节：视角角色 id、时间线等 */
  pov_character_id?: string | null
  timeline_start?: string | null
  timeline_end?: string | null
  metadata?: Record<string, unknown>
  [key: string]: unknown
}

/** GET /planning/novels/:id/structure 的 data 载荷 */
export interface PlanningStructurePayload {
  novel_id: string
  nodes: StoryNode[]
}

// ==================== SSE 流式宏观规划 ====================

export interface MacroStreamStatusEvent {
  phase: 'start' | 'generating' | 'streaming' | string
  message: string
  current?: number
  total?: number
  percent?: number
  total_nodes?: number
}

export interface MacroStreamNodeEvent {
  type: 'part' | 'volume' | 'act'
  part_index: number
  volume_index?: number
  act_index?: number
  title: string
  description?: string
  estimated_chapters?: number
  narrative_goal?: string
}

export interface MacroStreamChunkEvent {
  text: string
}

export interface MacroStreamDoneEvent {
  structure: MacroPartNode[]
  quality_metrics?: Record<string, unknown>
  generation_time?: number
}

/**
 * 连接宏观规划 SSE 流。
 * 返回 AbortController，调用 .abort() 可中止连接。
 */
export function streamMacroPlan(
  novelId: string,
  handlers: {
    onStatus?: (e: MacroStreamStatusEvent) => void
    onChunk?: (e: MacroStreamChunkEvent) => void
    onNode?: (e: MacroStreamNodeEvent) => void
    onDone?: (e: MacroStreamDoneEvent) => void
    onError?: (message: string) => void
  },
): AbortController {
  const ctrl = new AbortController()
  const url = resolveHttpUrl(`/api/v1/planning/novels/${novelId}/macro/stream`)

  void (async () => {
    try {
      const res = await fetch(url, {
        signal: ctrl.signal,
        headers: { Accept: 'text/event-stream', 'Cache-Control': 'no-cache' },
      })
      if (!res.ok || !res.body) {
        macroPlanStreamFeWarn(novelId, `macro/stream HTTP ${res.status}`)
        handlers.onError?.(`HTTP ${res.status}`)
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let lastStatusMsg = ''
      let feChunkEvents = 0

      macroPlanStreamFeDebug(novelId, 'GET macro/stream reader open')

      const flush = async (buf: string): Promise<string> => {
        let rest = buf
        while (true) {
          const taken = takeNextSseBlock(rest)
          if (!taken) break
          rest = taken.rest
          const block = taken.block
          const { eventType, dataStr } = parseSseEventBlock(block)
          if (!dataStr) continue
          try {
            const data = JSON.parse(dataStr) as Record<string, unknown>
            if (eventType === 'status') {
              const msg = typeof data.message === 'string' ? data.message : ''
              if (msg && msg !== lastStatusMsg) {
                lastStatusMsg = msg
                macroPlanStreamFeDebug(novelId, 'status phase update', {
                  phase: data.phase,
                  message: truncFeMsg(msg, 120),
                })
              }
              handlers.onStatus?.(data as unknown as MacroStreamStatusEvent)
            } else if (eventType === 'chunk') {
              const t = data.text
              if (typeof t === 'string' && t.length > 0) {
                feChunkEvents++
                if (feChunkEvents === 1 || feChunkEvents % 25 === 0) {
                  macroPlanStreamFeDebug(novelId, `sse_chunk #${feChunkEvents} delta_chars`, {
                    delta_chars: t.length,
                  })
                }
                handlers.onChunk?.({ text: t })
              }
            } else if (eventType === 'node') {
              const node = data as unknown as MacroStreamNodeEvent
              macroPlanStreamFeDebug(novelId, 'node event', {
                type: node.type,
                title: truncFeMsg(node.title ?? '', 80),
              })
              handlers.onNode?.(node)
              await yieldForIncrementalUi()
            } else if (eventType === 'done') {
              macroPlanStreamFeDebug(novelId, 'done received')
              handlers.onDone?.(data as unknown as MacroStreamDoneEvent)
            } else if (eventType === 'error') {
              macroPlanStreamFeDebug(novelId, `error ${String(data.message ?? '')}`)
              handlers.onError?.(String(data.message ?? '未知错误'))
            }
          } catch {
            /* 忽略残缺行 */
          }
        }
        return rest
      }

      while (true) {
        const { done, value } = await reader.read()
        if (value) buffer += decoder.decode(value, { stream: true })
        buffer = await flush(buffer)
        if (done) {
          buffer += decoder.decode()
          buffer = await flush(buffer)
          break
        }
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return
      macroPlanStreamFeWarn(novelId, 'stream aborted/failed', {
        error: e instanceof Error ? e.message : String(e),
      })
      handlers.onError?.(e instanceof Error ? e.message : '连接失败')
    }
  })()

  return ctrl
}

/** 全托管已触发宏观规划时：旁观内存进度 SSE（不重复启动生成） */
export interface MacroProgressWatchStatusEvent extends MacroStreamStatusEvent {
  status?: string
}

export interface MacroProgressWatchTerminalEvent {
  status: string
  message?: string
}

/**
 * 订阅 GET .../macro/progress/stream：chunk / status / heartbeat / terminal。
 * terminal 后 fetch 正常结束；若仍处于宏观规划且需继续观摩，由调用方自行重连。
 */
export function watchMacroPlanProgress(
  novelId: string,
  handlers: {
    onStatus?: (e: MacroProgressWatchStatusEvent) => void
    onChunk?: (e: MacroStreamChunkEvent) => void
    /** completed 后服务端按序推送部/卷/幕，便于侧栏逐节点挂载 */
    onNode?: (e: MacroStreamNodeEvent) => void
    onDone?: (e: MacroStreamDoneEvent) => void
    onHeartbeat?: (tick: number) => void
    onTerminal?: (e: MacroProgressWatchTerminalEvent) => void
    onError?: (message: string) => void
    onStreamClosed?: () => void
  },
): AbortController {
  const ctrl = new AbortController()
  const url = resolveHttpUrl(`/api/v1/planning/novels/${novelId}/macro/progress/stream`)

  void (async () => {
    try {
      const res = await fetch(url, {
        signal: ctrl.signal,
        headers: { Accept: 'text/event-stream', 'Cache-Control': 'no-cache' },
      })
      if (!res.ok || !res.body) {
        macroSseWatchFeWarn(novelId, `macro/progress/stream HTTP ${res.status}`)
        handlers.onError?.(`HTTP ${res.status}`)
        return
      }
      macroSseWatchFeInfo(novelId, 'client subscribed macro/progress/stream')
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let lastProgressSig: string | null = null
      let feChunkEvents = 0
      let feHeartbeatEvents = 0

      const flush = async (buf: string): Promise<string> => {
        let rest = buf
        while (true) {
          const taken = takeNextSseBlock(rest)
          if (!taken) break
          rest = taken.rest
          const block = taken.block
          const { eventType, dataStr } = parseSseEventBlock(block)
          if (!dataStr) continue
          try {
            const data = JSON.parse(dataStr) as Record<string, unknown>
            if (eventType === 'status') {
              const st = String(data.status ?? data.phase ?? '')
              const msg = String(data.message ?? '')
              const sig = `${st}\u0000${msg}`
              if (sig !== lastProgressSig) {
                lastProgressSig = sig
                macroSseWatchFeDebug(novelId, `progress status=${st} message=${truncFeMsg(msg, 120)}`)
              }
              handlers.onStatus?.(data as unknown as MacroProgressWatchStatusEvent)
            } else if (eventType === 'chunk') {
              const t = data.text
              if (typeof t === 'string' && t.length > 0) {
                feChunkEvents++
                if (feChunkEvents === 1 || feChunkEvents % 25 === 0) {
                  macroSseWatchFeDebug(novelId, `sse_chunk #${feChunkEvents} delta_chars=${t.length}`)
                }
                handlers.onChunk?.({ text: t })
              }
            } else if (eventType === 'heartbeat') {
              const tk = data.tick
              if (typeof tk === 'number') {
                feHeartbeatEvents++
                if (feHeartbeatEvents === 1 || feHeartbeatEvents % 5 === 0) {
                  macroSseWatchFeDebug(novelId, `heartbeat tick=${tk} (fe recv #${feHeartbeatEvents})`)
                }
                handlers.onHeartbeat?.(tk)
              }
            } else if (eventType === 'node') {
              const node = data as unknown as MacroStreamNodeEvent
              macroSseWatchFeDebug(novelId, `node type=${node.type} title=${truncFeMsg(node.title ?? '', 80)}`)
              handlers.onNode?.(node)
              await yieldForIncrementalUi()
            } else if (eventType === 'done') {
              macroSseWatchFeDebug(novelId, 'emitted done event (received)')
              handlers.onDone?.(data as unknown as MacroStreamDoneEvent)
            } else if (eventType === 'terminal') {
              const termStatus = String(data.status ?? '')
              const termMsg = data.message != null ? String(data.message) : ''
              macroSseWatchFeInfo(
                novelId,
                `terminal status=${termStatus} message=${truncFeMsg(termMsg, 160)}`,
              )
              handlers.onTerminal?.({
                status: termStatus,
                message: data.message != null ? String(data.message) : undefined,
              })
            }
          } catch {
            /* 残缺帧 */
          }
        }
        return rest
      }

      while (true) {
        const { done, value } = await reader.read()
        if (value) buffer += decoder.decode(value, { stream: true })
        buffer = await flush(buffer)
        if (done) {
          buffer += decoder.decode()
          buffer = await flush(buffer)
          break
        }
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return
      macroSseWatchFeWarn(novelId, 'stream read failed', {
        error: e instanceof Error ? e.message : String(e),
      })
      handlers.onError?.(e instanceof Error ? e.message : '连接失败')
    } finally {
      macroSseWatchFeDebug(novelId, 'sse fetch body closed')
      handlers.onStreamClosed?.()
    }
  })()

  return ctrl
}

// ==================== SSE 幕级章节规划 ====================

export interface ActStreamStatusEvent {
  phase: 'start' | 'generating' | 'streaming' | string
  message: string
  percent?: number
  expected_chapters?: number
}

export interface ActStreamChapterEvent {
  index: number
  title?: string
  outline?: string
  description?: string
  bible_elements?: string[]
  [key: string]: unknown
}

export interface ActStreamChunkEvent {
  text: string
}

export interface ActStreamDoneEvent {
  success: boolean
  act_id: string
  chapters: Record<string, unknown>[]
}

/**
 * 幕级章节规划 SSE：生成阶段心跳 + 逐章骨架呈现。
 */
export function streamActChapterPlan(
  actId: string,
  handlers: {
    onStatus?: (e: ActStreamStatusEvent) => void
    onChunk?: (e: ActStreamChunkEvent) => void
    onChapter?: (e: ActStreamChapterEvent) => void
    onDone?: (e: ActStreamDoneEvent) => void
    onError?: (message: string) => void
  },
  options?: { chapterCount?: number | null },
): AbortController {
  const ctrl = new AbortController()
  const q =
    options?.chapterCount != null && options.chapterCount > 0
      ? `?chapter_count=${options.chapterCount}`
      : ''
  const url = resolveHttpUrl(`/api/v1/planning/acts/${actId}/chapters/stream${q}`)

  void (async () => {
    try {
      const res = await fetch(url, {
        signal: ctrl.signal,
        headers: { Accept: 'text/event-stream', 'Cache-Control': 'no-cache' },
      })
      if (!res.ok || !res.body) {
        handlers.onError?.(`HTTP ${res.status}`)
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      const flush = async (buf: string): Promise<string> => {
        let rest = buf
        while (true) {
          const taken = takeNextSseBlock(rest)
          if (!taken) break
          rest = taken.rest
          const block = taken.block
          const { eventType, dataStr } = parseSseEventBlock(block)
          if (!dataStr) continue
          try {
            const data = JSON.parse(dataStr) as Record<string, unknown>
            if (eventType === 'status') {
              handlers.onStatus?.(data as unknown as ActStreamStatusEvent)
            } else if (eventType === 'chunk') {
              const t = data.text
              if (typeof t === 'string' && t.length > 0) {
                handlers.onChunk?.({ text: t })
              }
            } else if (eventType === 'chapter') {
              handlers.onChapter?.(data as unknown as ActStreamChapterEvent)
              await yieldForIncrementalUi()
            } else if (eventType === 'done') {
              handlers.onDone?.(data as unknown as ActStreamDoneEvent)
            } else if (eventType === 'error') {
              handlers.onError?.(String(data.message ?? '未知错误'))
            }
          } catch {
            /* 残缺块 */
          }
        }
        return rest
      }

      while (true) {
        const { done, value } = await reader.read()
        if (value) buffer += decoder.decode(value, { stream: true })
        buffer = await flush(buffer)
        if (done) {
          buffer += decoder.decode()
          buffer = await flush(buffer)
          break
        }
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return
      handlers.onError?.(e instanceof Error ? e.message : '连接失败')
    }
  })()

  return ctrl
}

// ==================== API ====================

export const planningApi = {
  // ==================== 宏观规划 ====================

  generateMacro: (novelId: string, data: MacroPlanRequest) =>
    apiClient.post<MacroPlanGenerateResponse>(
      `/planning/novels/${novelId}/macro/generate`,
      data,
      { timeout: 300000 }
    ) as unknown as Promise<MacroPlanGenerateResponse>,

  getMacroProgress: (novelId: string) =>
    apiClient.get<{ success: boolean; data: MacroPlanProgress }>(
      `/planning/novels/${novelId}/macro/progress`
    ) as unknown as Promise<{ success: boolean; data: MacroPlanProgress }>,

  getMacroResult: (novelId: string) =>
    apiClient.get<{ success: boolean; data: MacroPlanResultResponse }>(
      `/planning/novels/${novelId}/macro/result`
    ) as unknown as Promise<{ success: boolean; data: MacroPlanResultResponse }>,

  confirmMacro: (novelId: string, data: { structure: Record<string, unknown>[] }) =>
    apiClient.post(`/planning/novels/${novelId}/macro/confirm`, data),

  // ==================== 幕级规划 ====================

  generateActChapters: (actId: string, data: ActChaptersRequest) =>
    apiClient.post(`/planning/acts/${actId}/chapters/generate`, data),

  confirmActChapters: (actId: string, data: { chapters: Record<string, unknown>[] }) =>
    apiClient.post(`/planning/acts/${actId}/chapters/confirm`, data),

  // ==================== AI 续规划 ====================

  continuePlanning: (novelId: string, data: ContinuePlanningRequest) =>
    apiClient.post<ContinuePlanResult>(`/planning/novels/${novelId}/continue`, data) as unknown as Promise<ContinuePlanResult>,

  createNextAct: (actId: string) =>
    apiClient.post<Record<string, unknown>>(`/planning/acts/${actId}/create-next`) as unknown as Promise<Record<string, unknown>>,

  // ==================== 查询 ====================

  getStructure: (novelId: string) =>
    apiClient.get<{ success: boolean; data: PlanningStructurePayload }>(
      `/planning/novels/${novelId}/structure`
    ) as unknown as Promise<{ success: boolean; data: PlanningStructurePayload }>,

  getActDetail: (actId: string) =>
    apiClient.get<{ success: boolean; data: StoryNode }>(`/planning/acts/${actId}`) as unknown as Promise<{ success: boolean; data: StoryNode }>,

  getChapterDetail: (chapterId: string) =>
    apiClient.get<{ success: boolean; data: { chapter: StoryNode; elements: unknown[] } }>(`/planning/chapters/${chapterId}`) as unknown as Promise<{ success: boolean; data: { chapter: StoryNode; elements: unknown[] } }>,
}
