import { apiClient } from './config'

export interface PowerSystemRules {
  id: string
  novel_id: string
  genre_type: string
  tier_schema: string
  core_rules: string
  taboo_rules: string
  escalation_rules: string
  created_at: string
  updated_at: string
}

export interface PowerCharacterProfile {
  id: string
  novel_id: string
  character_name: string
  tier: string
  rank_score: number
  abilities: string
  limitations: string
  growth_stage: string
  last_verified_chapter: number | null
  notes: string
  created_at: string
  updated_at: string
}

export interface PowerProgressionEvent {
  id: string
  novel_id: string
  chapter_number: number
  character_name: string
  event_type: string
  opponent: string
  outcome: string
  power_delta: number
  evidence: string
  created_at: string
}

export interface PowerWarning {
  severity: 'info' | 'warning' | 'error' | string
  title: string
  message: string
}

export interface PowerSystemOverview {
  novel_id: string
  standard: string
  rules: PowerSystemRules
  profiles: PowerCharacterProfile[]
  recent_events: PowerProgressionEvent[]
  warnings: PowerWarning[]
}

export interface UpsertPowerRulesRequest {
  genre_type?: string
  tier_schema?: string
  core_rules?: string
  taboo_rules?: string
  escalation_rules?: string
}

export interface UpsertPowerProfileRequest {
  character_name: string
  tier?: string
  rank_score?: number
  abilities?: string
  limitations?: string
  growth_stage?: string
  last_verified_chapter?: number | null
  notes?: string
}

export interface CreatePowerEventRequest {
  chapter_number: number
  character_name: string
  event_type?: string
  opponent?: string
  outcome?: string
  power_delta?: number
  evidence?: string
}

export const powerSystemApi = {
  getOverview: (novelId: string) =>
    apiClient.get<PowerSystemOverview>(`/novels/${novelId}/power-system/overview`) as Promise<PowerSystemOverview>,

  saveRules: (novelId: string, data: UpsertPowerRulesRequest) =>
    apiClient.put<PowerSystemRules>(`/novels/${novelId}/power-system/rules`, data) as Promise<PowerSystemRules>,

  saveProfile: (novelId: string, data: UpsertPowerProfileRequest) =>
    apiClient.post<PowerCharacterProfile>(`/novels/${novelId}/power-system/profiles`, data) as Promise<PowerCharacterProfile>,

  createEvent: (novelId: string, data: CreatePowerEventRequest) =>
    apiClient.post<PowerProgressionEvent>(`/novels/${novelId}/power-system/events`, data) as Promise<PowerProgressionEvent>,
}
