import { apiClient } from './config'

export interface CocCanonEntry {
  id: string
  novel_id: string
  canon_type: string
  title: string
  lock_level: 'soft' | 'strict' | 'absolute' | string
  public_facts: string
  hidden_truth: string
  mutable_notes: string
  status: 'active' | 'draft' | 'archived' | string
  created_at: string
  updated_at: string
}

export interface CocCanonEvent {
  id: string
  novel_id: string
  entry_id: string | null
  title: string
  chapter_number: number
  event_type: string
  evidence: string
  notes: string
  created_at: string
}

export interface CocCanonOverview {
  novel_id: string
  entries: CocCanonEntry[]
  recent_events: CocCanonEvent[]
  cognition_layers: {
    author_truth: string[]
    reader_known: string[]
    author_truth_snippets: string[]
  }
}

export interface CocPresetTemplate {
  key: string
  name: string
  description: string
  source_novel_id: string
  canon_count: number
  clue_count: number
  prop_count: number
}

export interface ApplyCocPresetRequest {
  preset_key?: string
  overwrite_existing?: boolean
}

export interface ApplyCocPresetResponse {
  preset_key: string
  novel_id: string
  created_canon: number
  created_clues: number
  created_props: number
  skipped: number
  overwrite_existing: boolean
}

export interface UpsertCocCanonEntryRequest {
  canon_type: string
  title: string
  lock_level?: string
  public_facts?: string
  hidden_truth?: string
  mutable_notes?: string
  status?: string
}

export interface CreateCocCanonEventRequest {
  title?: string
  entry_id?: string
  chapter_number: number
  event_type?: string
  evidence?: string
  notes?: string
}

export const cocCanonApi = {
  getOverview: (novelId: string) =>
    apiClient.get<CocCanonOverview>(`/novels/${novelId}/coc-canon/overview`) as Promise<CocCanonOverview>,

  upsertEntry: (novelId: string, data: UpsertCocCanonEntryRequest) =>
    apiClient.post<CocCanonEntry>(`/novels/${novelId}/coc-canon/entries`, data) as Promise<CocCanonEntry>,

  createEvent: (novelId: string, data: CreateCocCanonEventRequest) =>
    apiClient.post<CocCanonEvent>(`/novels/${novelId}/coc-canon/events`, data) as Promise<CocCanonEvent>,

  listPresetTemplates: (novelId: string) =>
    apiClient.get<CocPresetTemplate[]>(`/novels/${novelId}/coc-preset/templates`) as Promise<CocPresetTemplate[]>,

  applyPreset: (novelId: string, data: ApplyCocPresetRequest = {}) =>
    apiClient.post<ApplyCocPresetResponse>(`/novels/${novelId}/coc-preset/apply`, data) as Promise<ApplyCocPresetResponse>,
}
