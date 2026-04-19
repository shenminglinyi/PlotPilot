import axios, { type AxiosRequestConfig } from 'axios'

// ---------------------------------------------------------------------------
// Tauri 桌面壳适配（浏览器中 isTauri 为 false，invoke 失败即走 Vite 代理）
// 不单独维护 tauri.ts，避免仓库出现「仅打包机需要」的额外文件。
// ---------------------------------------------------------------------------
let _isTauri: boolean | null = null
let _cachedPort: number | null = null

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

async function getApiBaseUrl(): Promise<string> {
  if (_cachedPort && _cachedPort > 0) {
    return `http://127.0.0.1:${_cachedPort}`
  }
  if (!isTauri()) {
    return ''
  }
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    const port = await invoke<number>('get_backend_port')
    if (port && port > 0) {
      _cachedPort = port as number
      return `http://127.0.0.1:${_cachedPort}`
    }
  } catch (e) {
    console.warn('[Tauri] 无法获取后端端口，使用默认值', e)
  }
  return 'http://127.0.0.1:8005'
}

/**
 * 将 `/api/...` 解析为实际请求 URL。
 * 浏览器：保持相对路径，走 Vite 代理；Tauri：补全 `http://127.0.0.1:<port>`（与 axios 一致）。
 */
export async function resolveApiFetchUrl(path: string): Promise<string> {
  if (!path.startsWith('/')) {
    throw new Error(`resolveApiFetchUrl: path must start with /, got: ${path}`)
  }
  const base = await getApiBaseUrl()
  return base ? `${base}${path}` : path
}

function setBackendPort(port: number): void {
  _cachedPort = port
}

async function initTauriConnection(): Promise<void> {
  if (!isTauri()) {
    return
  }
  try {
    const baseUrl = await getApiBaseUrl()
    console.log(`[Tauri] 后端地址已连接: ${baseUrl}`)
  } catch (e) {
    console.error('[Tauri] 后端连接初始化失败:', e)
  }
}

// Tauri 模式下使用动态端口，开发模式使用 Vite proxy
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

// 创建原始 axios 实例（baseURL 稍后可能被动态更新）
const axiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 增加到 120 秒，因为 LLM 生成可能需要较长时间
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * 初始化 API 基础 URL（在 App 启动时调用）
 * Tauri 模式：从 Rust 后端获取动态端口并更新 axios baseURL
 * 开发模式：保持 Vite proxy 不变
 */
export async function initApiClient(): Promise<void> {
  let boundViaIpc = false

  // 桌面壳：优先 IPC 取端口（不依赖 window.__TAURI__；Tauri 2 默认无该全局）
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    const port = await invoke<number>('get_backend_port')
    if (port && port > 0) {
      setBackendPort(port)
      axiosInstance.defaults.baseURL = `http://127.0.0.1:${port}/api/v1`
      boundViaIpc = true
      console.log(`[API] 桌面模式 baseURL: ${axiosInstance.defaults.baseURL}`)
    }
  } catch {
    // 浏览器 / 非 Tauri：无 IPC，继续走下方或保持 Vite 代理
  }

  if (!boundViaIpc && isTauri()) {
    const baseUrl = await getApiBaseUrl()
    if (baseUrl) {
      axiosInstance.defaults.baseURL = `${baseUrl}/api/v1`
      console.log(`[API] Tauri 模式，baseURL 已更新为: ${axiosInstance.defaults.baseURL}`)
    }
  }

  await initTauriConnection()
}

// Add response interceptor to extract data
axiosInstance.interceptors.response.use(response => response.data)

// 类型安全的 API 客户端接口
export interface ApiClient {
  get<T>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T>
}

// 导出类型安全的 apiClient
export const apiClient: ApiClient = axiosInstance as unknown as ApiClient

// ============================================================================
// SSE 流式接口辅助函数
// ============================================================================

export interface ChapterStreamEvent {
  type: 'connected' | 'chapter_start' | 'chapter_chunk' | 'chapter_content' | 'autopilot_stopped' | 'heartbeat'
  message: string
  timestamp: string
  metadata?: {
    chapter_number?: number
    chunk?: string  // 增量文字
    beat_index?: number
    content?: string  // 完整内容（向后兼容）
    word_count?: number
  }
}

/**
 * 订阅自动驾驶章节内容流（SSE）
 * @param novelId 小说 ID
 * @param handlers 事件处理器
 * @returns AbortController 用于取消订阅
 */
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

  ;(async () => {
    try {
      // 桌面壳在 initApiClient 里会写入 _cachedPort；开发模式 baseUrl 为空则走 Vite 代理
      const baseUrl = await getApiBaseUrl()
      const streamUrl = baseUrl
        ? `${baseUrl}/api/v1/autopilot/${novelId}/chapter-stream`
        : `/api/v1/autopilot/${novelId}/chapter-stream`

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
      
      // 通知连接成功
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
                // 真正的流式：增量文字
                handlers.onChapterChunk?.(event.metadata.chunk, event.metadata.beat_index || 0)
              } else if (event.type === 'chapter_content' && event.metadata) {
                // 向后兼容：完整内容
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
