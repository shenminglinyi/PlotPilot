import { apiClient } from './config'

export interface NovelProSuggestionRequest {
  suggestion_type: string
  fields: string[]
  chapter_number?: number | null
  target?: Record<string, unknown>
  current_values?: Record<string, unknown>
  instruction?: string
}

export interface NovelProSuggestionResponse {
  suggestion_type: string
  fields: Record<string, unknown>
  rationale: string
}

export const novelproSuggestionsApi = {
  suggestFields: (novelId: string, data: NovelProSuggestionRequest) =>
    apiClient.post<NovelProSuggestionResponse>(
      `/novels/${novelId}/novelpro/suggestions`,
      data,
    ) as Promise<NovelProSuggestionResponse>,
}
