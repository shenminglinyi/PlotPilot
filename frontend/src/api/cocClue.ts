import { apiClient } from './config'

export interface CocClueItem {
  id: string
  novel_id: string
  clue_key: string
  clue_text: string
  visibility: string
  reveal_chapter: number | null
  known_by: string[] | string
  confidence: number | null
  lock_level: string
  status: string
  notes: string
  created_at: string
  updated_at: string
}

export interface CocClueEvent {
  id: string
  novel_id: string
  clue_id: string | null
  clue_key: string
  chapter_number: number
  event_type: string
  evidence: string
  notes: string
  created_at: string
}

export interface CocClueOverview {
  novel_id: string
  items: CocClueItem[]
  recent_events: CocClueEvent[]
  cognition_layers: {
    author_truth: string[]
    character_known: string[]
    reader_known: string[]
  }
}

export interface UpsertCocClueItemRequest {
  clue_key: string
  clue_text: string
  visibility?: string
  reveal_chapter?: number | null
  known_by?: string
  confidence?: number | null
  lock_level?: string
  status?: string
  notes?: string
}

export interface CreateCocClueEventRequest {
  clue_id?: string
  clue_key?: string
  chapter_number: number
  event_type?: string
  evidence?: string
  notes?: string
}

export const cocClueApi = {
  getOverview: (novelId: string) =>
    apiClient.get<CocClueOverview>(`/novels/${novelId}/coc-clues/overview`) as Promise<CocClueOverview>,

  upsertItem: (novelId: string, data: UpsertCocClueItemRequest) =>
    apiClient.post<CocClueItem>(`/novels/${novelId}/coc-clues/items`, data) as Promise<CocClueItem>,

  createEvent: (novelId: string, data: CreateCocClueEventRequest) =>
    apiClient.post<CocClueEvent>(`/novels/${novelId}/coc-clues/events`, data) as Promise<CocClueEvent>,
}
