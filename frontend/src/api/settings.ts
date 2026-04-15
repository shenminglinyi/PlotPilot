import { apiClient } from './config'

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
}
