import { apiClient } from './config'

export type LLMVendor = 'claude' | 'openai' | 'codex'
export type LLMApiFormat = 'anthropic_messages' | 'openai_chat_completions' | 'openai_responses'

export interface LLMSettings {
  vendor: LLMVendor | string
  api_format: LLMApiFormat | string
  base_url: string
  api_key: string
  api_key_masked?: string
  model: string
  fast_model: string
  review_model: string
  scene_director_model: string
  state_extractor_model: string
  temperature: number
  max_tokens: number
  timeout_ms: number
}

export interface LLMPreset extends LLMSettings {
  id: string
  name: string
  updated_at: string
}

export interface LLMSettingsResponse extends LLMSettings {
  active_preset_id?: string | null
  presets: LLMPreset[]
}

export interface LLMTestPayload extends LLMSettings {
  prompt?: string
}

export interface LLMTestResult {
  success: boolean
  vendor: string
  api_format: string
  model: string
  message: string
}

export interface ModelOption {
  label: string
  value: string
}

export interface ModelListResult {
  success: boolean
  items: ModelOption[]
  count: number
}

export interface SavePresetPayload {
  preset_id?: string | null
  name: string
  set_active: boolean
  settings: LLMSettings
}

export const llmSettingsApi = {
  get: () => apiClient.get<LLMSettingsResponse>('/settings/llm') as Promise<LLMSettingsResponse>,
  save: (payload: LLMSettings) => apiClient.put<LLMSettingsResponse>('/settings/llm', payload) as Promise<LLMSettingsResponse>,
  test: (payload: LLMTestPayload) => apiClient.post<LLMTestResult>('/settings/llm/test', payload) as Promise<LLMTestResult>,
  listModels: (payload: LLMSettings) => apiClient.post<ModelListResult>('/settings/llm/models', payload) as Promise<ModelListResult>,
  savePreset: (payload: SavePresetPayload) => apiClient.post<LLMSettingsResponse>('/settings/llm/presets', payload) as Promise<LLMSettingsResponse>,
  activatePreset: (presetId: string) => apiClient.post<LLMSettingsResponse>(`/settings/llm/presets/${presetId}/activate`, {}) as Promise<LLMSettingsResponse>,
  deletePreset: (presetId: string) => apiClient.delete<LLMSettingsResponse>(`/settings/llm/presets/${presetId}`) as Promise<LLMSettingsResponse>,
}
