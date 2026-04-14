import { apiClient } from './config'

export interface LLMConfig {
  provider: string
  openai_api_key?: string
  openai_base_url?: string
  anthropic_api_key?: string
  anthropic_base_url?: string
  default_model: string
  cheap_model: string
}

export function getLLMConfig() {
  return apiClient.get<LLMConfig>('/system/llm/config')
}

export function saveLLMConfig(data: LLMConfig) {
  return apiClient.post<{ status: string }>('/system/llm/config', data)
}

export function verifyAndFetchModels(provider: string, api_key: string, base_url?: string) {
  return apiClient.post<{ models: string[] }>('/system/llm/verify', {
    provider,
    api_key,
    base_url
  })
}
