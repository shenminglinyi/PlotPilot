import { apiClient } from './config'

export type AIProvider = 'ark' | 'anthropic' | 'openai'

export interface AISettings {
  provider: AIProvider
  model: string
  base_url: string
  has_api_key: boolean
  api_key_hint: string
}

export interface AISettingsUpdate {
  provider: AIProvider
  api_key?: string
  model?: string
  base_url?: string
}

export interface AIConnectionTestResult {
  ok: boolean
  provider: AIProvider
  model: string
  latency_ms: number
  message: string
  sample: string
}

export const aiSettingsApi = {
  get: () => apiClient.get<AISettings>('/settings/ai'),
  update: (data: AISettingsUpdate) => apiClient.put<AISettings>('/settings/ai', data),
  test: (data?: AISettingsUpdate) => apiClient.post<AIConnectionTestResult>('/settings/ai/test', data ?? {}),
}
