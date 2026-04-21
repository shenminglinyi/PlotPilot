import { apiClient, resolveHttpUrl } from './config'

export interface LLMConfigProfile {
  id: string
  name: string
  provider: 'openai' | 'anthropic'
  api_key: string
  base_url: string
  model: string
  system_model: string
  writing_model: string
  created_at: string
  updated_at: string
}

export interface LLMConfigStore {
  active_id: string | null
  configs: LLMConfigProfile[]
}

export interface EmbeddingConfig {
  mode: 'local' | 'openai'
  api_key: string
  base_url: string
  model: string
  use_gpu: boolean
  model_path: string
}

// ── 扩展包安装相关类型 ──

export interface ExtensionsStatus {
  faiss: boolean
  numpy: boolean
  sentence_transformers: boolean
  all_installed: boolean
  install_running: boolean
  install_progress: string
}

export interface InstallEvent {
  type: 'info' | 'success' | 'warn' | 'error' | 'progress' | 'log' | 'done'
  message: string
  percent?: number
  success?: boolean
  installed?: ExtensionsStatus
}

export const settingsApi = {
  listLLMConfigs: () =>
    apiClient.get<LLMConfigStore>('/settings/llm-configs'),

  createLLMConfig: (data: Pick<LLMConfigProfile, 'name' | 'provider' | 'api_key' | 'base_url' | 'model'>) =>
    apiClient.post<LLMConfigProfile>('/settings/llm-configs', data),

  updateLLMConfig: (id: string, data: Partial<LLMConfigProfile>) =>
    apiClient.put<LLMConfigProfile>(`/settings/llm-configs/${id}`, data),

  deleteLLMConfig: (id: string) =>
    apiClient.delete<void>(`/settings/llm-configs/${id}`),

  activateLLMConfig: (id: string) =>
    apiClient.post<void>(`/settings/llm-configs/${id}/activate`),

  fetchModels: (data: { provider: string; api_key: string; base_url: string }) =>
    apiClient.post<string[]>('/settings/llm-configs/fetch-models', data),

  getEmbeddingConfig: () =>
    apiClient.get<EmbeddingConfig>('/settings/embedding'),

  updateEmbeddingConfig: (data: EmbeddingConfig) =>
    apiClient.put<EmbeddingConfig>('/settings/embedding', data),

  fetchEmbeddingModels: (data: { provider: string; api_key: string; base_url: string }) =>
    apiClient.post<string[]>('/settings/embedding/fetch-models', data),

  // ── 扩展包安装（本地 AI 引擎）──

  /** 检查本地 AI 扩展包安装状态 */
  getExtensionsStatus: () =>
    apiClient.get<ExtensionsStatus>('/system/extensions-status'),

  /**
   * 安装本地 AI 扩展包（SSE 流式）
   * 返回 AbortController 用于取消
   */
  installExtensions: (handlers: {
    onEvent?: (event: InstallEvent) => void
    onDone?: (success: boolean) => void
    onError?: (error: Error) => void
  }): AbortController => {
    const ctrl = new AbortController()

    void (async () => {
      try {
        const url = resolveHttpUrl('/api/v1/system/install-extensions')
        const res = await fetch(url, {
          method: 'POST',
          signal: ctrl.signal,
          headers: {
            'Accept': 'text/event-stream',
            'Cache-Control': 'no-cache',
          },
        })

        if (!res.ok || !res.body) {
          const err = new Error(`HTTP ${res.status}`)
          handlers.onError?.(err)
          return
        }

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
                const event = JSON.parse(line.slice(6)) as InstallEvent
                handlers.onEvent?.(event)

                if (event.type === 'done') {
                  handlers.onDone?.(event.success ?? false)
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
      }
    })()

    return ctrl
  },
}
