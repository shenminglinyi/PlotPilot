import { apiClient } from './config'

export interface PropLedgerItem {
  id: string
  novel_id: string
  name: string
  category: string
  status: string
  current_holder: string
  current_location: string
  first_seen_chapter: number | null
  last_seen_chapter: number | null
  importance: string
  description: string
  notes: string
  created_at: string
  updated_at: string
}

export interface PropLedgerEvent {
  id: string
  novel_id: string
  prop_id: string
  prop_name: string
  chapter_number: number
  event_type: string
  holder: string
  location: string
  status: string
  evidence: string
  notes: string
  created_at: string
}

export interface PropLedgerWarning {
  severity: 'info' | 'warning' | 'error' | string
  title: string
  message: string
}

export interface PropLedgerOverview {
  novel_id: string
  items: PropLedgerItem[]
  recent_events: PropLedgerEvent[]
  warnings: PropLedgerWarning[]
}

export interface UpsertPropItemRequest {
  name: string
  category?: string
  status?: string
  current_holder?: string
  current_location?: string
  first_seen_chapter?: number | null
  last_seen_chapter?: number | null
  importance?: string
  description?: string
  notes?: string
}

export interface CreatePropEventRequest {
  prop_name: string
  chapter_number: number
  event_type?: string
  holder?: string
  location?: string
  status?: string
  evidence?: string
  notes?: string
}

export const propLedgerApi = {
  getOverview: (novelId: string) =>
    apiClient.get<PropLedgerOverview>(`/novels/${novelId}/prop-ledger/overview`) as Promise<PropLedgerOverview>,

  saveItem: (novelId: string, data: UpsertPropItemRequest) =>
    apiClient.post<PropLedgerItem>(`/novels/${novelId}/prop-ledger/items`, data) as Promise<PropLedgerItem>,

  createEvent: (novelId: string, data: CreatePropEventRequest) =>
    apiClient.post<PropLedgerEvent>(`/novels/${novelId}/prop-ledger/events`, data) as Promise<PropLedgerEvent>,
}
