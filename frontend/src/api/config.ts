import axios, { type AxiosRequestConfig } from 'axios'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

// 创建原始 axios 实例
const axiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 增加到 120 秒，因为 LLM 生成可能需要较长时间
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add response interceptor to extract data
axiosInstance.interceptors.response.use(response => response.data, (error) => {
  if (error.code === 'ECONNABORTED' || error.code === 'ERR_CANCELED') {
    return Promise.reject(new Error('请求超时，请检查网络连接'))
  }
  if (!error.response) {
    return Promise.reject(new Error('网络连接失败，请检查后端是否已启动'))
  }
  const { status, data } = error.response
  const detail = data?.detail
  const msg = typeof detail === 'string' ? detail : (detail?.msg || '')
  if (status === 401) {
    return Promise.reject(new Error('API Key 无效或已过期，请在设置中重新配置'))
  }
  if (status === 429) {
    return Promise.reject(new Error('请求过于频繁，请稍后再试'))
  }
  if (status === 404) {
    return Promise.reject(new Error(msg || '请求的资源不存在'))
  }
  if (status >= 500) {
    return Promise.reject(new Error(msg || '服务器内部错误，请稍后重试'))
  }
  return Promise.reject(new Error(msg || `请求失败 (${status})`))
})

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
      const res = await fetch(`/api/v1/autopilot/${novelId}/chapter-stream`, {
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
