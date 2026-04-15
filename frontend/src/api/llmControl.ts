import { apiClient } from './config'

export type LLMProtocol = 'openai' | 'anthropic' | 'gemini'

export interface LLMPreset {
  key: string
  label: string
  protocol: LLMProtocol
  default_base_url: string
  default_model: string
  description: string
  tags: string[]
}

export interface LLMProfile {
  id: string
  name: string
  preset_key: string
  protocol: LLMProtocol
  base_url: string
  api_key: string
  model: string
  temperature: number
  max_tokens: number
  timeout_seconds: number
  extra_headers: Record<string, string>
  extra_query: Record<string, unknown>
  extra_body: Record<string, unknown>
  notes: string
}

export interface LLMControlConfig {
  version: number
  active_profile_id: string | null
  profiles: LLMProfile[]
}

export interface LLMRuntimeSummary {
  source: 'profile' | 'mock'
  active_profile_id: string | null
  active_profile_name: string | null
  protocol: LLMProtocol | null
  model: string | null
  base_url: string | null
  using_mock: boolean
  reason: string | null
}

export interface LLMControlPanelData {
  config: LLMControlConfig
  presets: LLMPreset[]
  runtime: LLMRuntimeSummary
}

export interface LLMTestResult {
  ok: boolean
  provider_label: string
  model: string
  latency_ms: number
  preview: string
  error: string | null
}

export interface ModelItem {
  id: string
  name: string
  owned_by: string
}

export interface ModelListResponse {
  success: boolean
  items: ModelItem[]
  count: number
}

export interface FetchModelsPayload {
  protocol: string
  base_url: string
  api_key: string
  timeout_ms?: number
}

export const llmControlApi = {
  getPanel: () => apiClient.get<LLMControlPanelData>('/llm-control') as Promise<LLMControlPanelData>,
  saveConfig: (config: LLMControlConfig) =>
    apiClient.put<LLMControlPanelData>('/llm-control', config) as Promise<LLMControlPanelData>,
  testProfile: (profile: LLMProfile) =>
    apiClient.post<LLMTestResult>('/llm-control/test', profile, { timeout: 120_000 }) as Promise<LLMTestResult>,
  fetchModels: (payload: FetchModelsPayload) =>
    apiClient.post<ModelListResponse>('/llm-control/models', payload, { timeout: 30_000 }) as Promise<ModelListResponse>,
}
