import { apiClient } from './config'

export interface LLMConfig {
  provider: string
  default_model_provider: string
  default_model_api_key?: string
  default_model_base_url?: string
  default_model: string
  
  cheap_model_provider: string
  cheap_model_api_key?: string
  cheap_model_base_url?: string
  cheap_model: string

  knowledge_model_provider: string
  knowledge_model_api_key?: string
  knowledge_model_base_url?: string
  knowledge_model: string

  research_model_provider: string
  research_model_api_key?: string
  research_model_base_url?: string
  research_model: string
}

export function getLLMConfig() {
  return apiClient.get<LLMConfig>('/api/v1/system/llm/config')
}

export function saveLLMConfig(data: LLMConfig) {
  return apiClient.post<{ status: string }>('/api/v1/system/llm/config', data)
}

export function verifyAndFetchModels(provider: string, api_key: string, base_url?: string) {
  return apiClient.post<{ models: string[] }>('/api/v1/system/llm/verify', {
    provider,
    api_key,
    base_url
  })
}
