import axios, { type AxiosRequestConfig } from 'axios'

// ---------------------------------------------------------------------------
// 单一数据源：axiosInstance.defaults.baseURL
// - 浏览器：`/api/v1`（相对路径，走 Vite 代理）
// - Tauri：`http://127.0.0.1:<port>/api/v1`（initApiClient 内 IPC 写入）
// fetch / EventSource 使用 resolveHttpUrl()，从同一 baseURL 推导 origin。
// Legacy `/api`（非 v1）使用 legacyBookHttp / legacyStatsHttp，由 syncLegacyRootsFromV1 同步主机。
// ---------------------------------------------------------------------------
let _isTauri: boolean | null = null

function isTauri(): boolean {
  if (_isTauri === null) {
    if (typeof window === 'undefined') {
      _isTauri = false
    } else {
      const w = window as Window & {
        __TAURI__?: unknown
        __TAURI_INTERNALS__?: unknown
      }
      _isTauri = !!(w.__TAURI__ || w.__TAURI_INTERNALS__)
    }
  }
  return _isTauri
}

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

const axiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/** 与 apiClient 同一实例，供需完整 Axios 配置（timeout、params）的模块使用 */
export const apiAxios = axiosInstance

/** 旧版 /api 路由（book、jobs），与 v1 共用主机 */
export const legacyBookHttp = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})
legacyBookHttp.interceptors.response.use(response => response.data)

/** 旧版 /api/stats，带 SuccessResponse 解包 */
export const legacyStatsHttp = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})
legacyStatsHttp.interceptors.response.use(response => {
  const body = response.data
  if (
    body &&
    typeof body === 'object' &&
    'success' in body &&
    (body as { success?: boolean }).success === true &&
    'data' in body
  ) {
    return (body as { data: unknown }).data
  }
  return body
})

function syncLegacyRootsFromV1(): void {
  const v1 = axiosInstance.defaults.baseURL || '/api/v1'
  if (/^https?:\/\//i.test(v1)) {
    const origin = new URL(v1).origin
    legacyBookHttp.defaults.baseURL = `${origin}/api`
    legacyStatsHttp.defaults.baseURL = `${origin}/api`
  } else {
    legacyBookHttp.defaults.baseURL = '/api'
    legacyStatsHttp.defaults.baseURL = '/api'
  }
}

/**
 * 将必须以 `/` 开头的绝对路径（如 `/api/v1/...`）转为实际请求 URL。
 * 与当前 `apiAxios.defaults.baseURL` 一致：浏览器保持相对路径；桌面壳补全 origin。
 */
export function resolveHttpUrl(absolutePathFromRoot: string): string {
  if (!absolutePathFromRoot.startsWith('/')) {
    throw new Error(`resolveHttpUrl: path must start with /, got: ${absolutePathFromRoot}`)
  }
  const v1 = axiosInstance.defaults.baseURL || '/api/v1'
  if (/^https?:\/\//i.test(v1)) {
    return `${new URL(v1).origin}${absolutePathFromRoot}`
  }
  return absolutePathFromRoot
}

async function initTauriConnection(): Promise<void> {
  if (!isTauri()) {
    return
  }
  console.log(`[Tauri] API baseURL: ${axiosInstance.defaults.baseURL}`)
}

/**
 * 初始化 API（应用启动时调用一次）
 */
export async function initApiClient(): Promise<void> {
  let port: number | null = null
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    const p = await invoke<number>('get_backend_port')
    if (p && p > 0) {
      port = p
    }
  } catch {
    // 浏览器 / 无 IPC
  }

  if (port != null) {
    axiosInstance.defaults.baseURL = `http://127.0.0.1:${port}/api/v1`
    console.log(`[API] 桌面模式 baseURL: ${axiosInstance.defaults.baseURL}`)
  } else if (isTauri()) {
    axiosInstance.defaults.baseURL = 'http://127.0.0.1:8005/api/v1'
    console.warn('[API] Tauri 下未能通过 IPC 取得端口，回退 8005')
  }

  syncLegacyRootsFromV1()
  await initTauriConnection()
}

axiosInstance.interceptors.response.use(response => response.data)

export interface ApiClient {
  get<T>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T>
}

export const apiClient: ApiClient = axiosInstance as unknown as ApiClient

export interface ChapterStreamEvent {
  type: 'connected' | 'chapter_start' | 'chapter_chunk' | 'chapter_content' | 'autopilot_stopped' | 'heartbeat'
  message: string
  timestamp: string
  metadata?: {
    chapter_number?: number
    chunk?: string
    beat_index?: number
    content?: string
    word_count?: number
  }
}

export function subscribeChapterStream(
  novelId: string,
  handlers: {
    onChapterStart?: (chapterNumber: number) => void
    onChapterChunk?: (chunk: string, beatIndex: number) => void
    onChapterContent?: (data: { chapterNumber: number; content: string; wordCount: number; beatIndex: number }) => void
    onAutopilotStopped?: (status: string) => void
    onError?: (error: Error) => void
    onConnected?: () => void
    onDisconnected?: () => void
  }
): AbortController {
  const ctrl = new AbortController()

  void (async () => {
    try {
      const streamUrl = resolveHttpUrl(`/api/v1/autopilot/${novelId}/chapter-stream`)
      const res = await fetch(streamUrl, {
        signal: ctrl.signal,
        headers: {
          'Accept': 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
      })

      if (!res.ok || !res.body) {
        handlers.onError?.(new Error(`HTTP ${res.status}`))
        handlers.onDisconnected?.()
        return
      }

      handlers.onConnected?.()

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        let sep: number
        while ((sep = buffer.indexOf('\n\n')) >= 0) {
          const block = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)

          for (const line of block.split('\n')) {
            if (!line.startsWith('data: ')) continue
            try {
              const event = JSON.parse(line.slice(6)) as ChapterStreamEvent

              if (event.type === 'chapter_start' && event.metadata?.chapter_number) {
                handlers.onChapterStart?.(event.metadata.chapter_number)
              } else if (event.type === 'chapter_chunk' && event.metadata?.chunk) {
                handlers.onChapterChunk?.(event.metadata.chunk, event.metadata.beat_index || 0)
              } else if (event.type === 'chapter_content' && event.metadata) {
                handlers.onChapterContent?.({
                  chapterNumber: event.metadata.chapter_number!,
                  content: event.metadata.content || '',
                  wordCount: event.metadata.word_count || 0,
                  beatIndex: event.metadata.beat_index || 0,
                })
              } else if (event.type === 'autopilot_stopped') {
                handlers.onAutopilotStopped?.(event.message)
              }
            } catch {
              // 忽略解析错误
            }
          }
        }
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return
      handlers.onError?.(e instanceof Error ? e : new Error('Stream error'))
      handlers.onDisconnected?.()
    }
  })()

  return ctrl
}
