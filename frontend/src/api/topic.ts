import { apiClient } from './config'
import type { NovelDTO } from './novel'

export type TopicIdeaStatus = 'draft' | 'adopted' | 'archived'
export type TopicLengthTier = 'short' | 'standard' | 'epic'

export interface TopicIdea {
  id: string
  title: string
  genre: string
  world_preset: string
  length_tier: TopicLengthTier | string
  logline: string
  premise: string
  protagonist_hook: string
  core_conflict: string
  opening_hook: string
  selling_points: string[]
  long_term_potential: string
  risk_notes: string[]
  market_tags: string[]
  score: number
  status: TopicIdeaStatus
  adopted_novel_id?: string | null
  source_brief: Record<string, unknown>
  development_notes: Record<string, unknown>
  evaluation: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface TopicCompareRanking {
  topic_id: string
  title: string
  score: number
  reason: string
  risks: string[]
}

export interface TopicCompareResult {
  recommended_topic_id: string
  summary: string
  rankings: TopicCompareRanking[]
}

export interface TopicMarketSignal {
  id: string
  source: string
  title: string
  genre: string
  tags: string[]
  summary: string
  raw_text: string
  created_at: string
}

export type TopicMarketSignalSourceType = 'public_page' | 'api' | 'authenticated_source'

export interface TopicMarketSignalSource {
  key: string
  name: string
  url: string
  category: string
  source_type?: TopicMarketSignalSourceType
  requires_auth?: boolean
  rank_urls?: Record<string, string>
}

export interface TopicMarketSignalSummary {
  total: number
  source_counts: Record<string, number>
  genre_counts: Record<string, number>
  tag_counts: Record<string, number>
  category_counts: Record<string, number>
  window_days: number
  weighted_source_scores: Record<string, number>
  weighted_genre_scores: Record<string, number>
  weighted_tag_scores: Record<string, number>
  comic_opportunities: string[]
  daily_counts: Array<{ date: string; count: number }>
  recent_samples: TopicMarketSignal[]
}

export interface TopicMarketSignalAutomationSettings {
  enabled: boolean
  interval_minutes: number
  limit_per_source: number
  lookback_days: number
  source_weights: Record<string, number>
  selected_source_keys: string[]
  last_run_at: string
  last_status: string
  last_error: string
  updated_at: string
}

export interface TopicMarketSignalSourceCredentialStatus {
  source_key: string
  api_key_configured: boolean
  cookie_configured: boolean
  endpoint_configured: boolean
  header_keys: string[]
  updated_at: string
}

export interface TopicMarketSignalSourceConnection {
  source_key: string
  source_name: string
  ok: boolean
  count: number
  message: string
  sample_titles: string[]
}

export interface TopicMarketSignalSourceHealth {
  source_key: string
  source_name: string
  status: 'success' | 'error' | 'unknown' | string
  last_run_at: string
  last_success_at: string
  last_count: number
  last_error: string
  next_run_at: string
}

export interface TopicGeneratePayload {
  brief?: string
  genre?: string
  world_preset?: string
  keywords?: string[]
  desired_selling_points?: string[]
  avoid_patterns?: string[]
  market_signals?: Array<Record<string, unknown>>
  length_tier?: TopicLengthTier
  count?: number
}

export interface TopicUpdatePayload {
  status?: TopicIdeaStatus
  title?: string
  genre?: string
  world_preset?: string
  length_tier?: TopicLengthTier | string
  logline?: string
  premise?: string
  protagonist_hook?: string
  core_conflict?: string
  opening_hook?: string
  selling_points?: string[]
  long_term_potential?: string
  risk_notes?: string[]
  market_tags?: string[]
  score?: number
  development_notes?: Record<string, unknown>
  evaluation?: Record<string, unknown>
}

export const topicApi = {
  generate: (data: TopicGeneratePayload) =>
    apiClient.post<TopicIdea[]>('/topics/generate', data, { timeout: 300000 }) as Promise<TopicIdea[]>,

  list: (status?: TopicIdeaStatus) =>
    apiClient.get<TopicIdea[]>('/topics', { params: status ? { status } : undefined }) as Promise<TopicIdea[]>,

  updateStatus: (topicId: string, status: TopicIdeaStatus) =>
    apiClient.patch<TopicIdea>(`/topics/${topicId}`, { status }) as Promise<TopicIdea>,

  update: (topicId: string, data: TopicUpdatePayload) =>
    apiClient.patch<TopicIdea>(`/topics/${topicId}`, data) as Promise<TopicIdea>,

  deepen: (topicId: string) =>
    apiClient.post<TopicIdea>(`/topics/${topicId}/deepen`, undefined, { timeout: 300000 }) as Promise<TopicIdea>,

  evaluate: (topicId: string) =>
    apiClient.post<TopicIdea>(`/topics/${topicId}/evaluate`, undefined, { timeout: 300000 }) as Promise<TopicIdea>,

  compare: (topicIds: string[]) =>
    apiClient.post<TopicCompareResult>('/topics/compare', { topic_ids: topicIds }, { timeout: 300000 }) as Promise<TopicCompareResult>,

  importSignals: (data: { raw_text: string; source?: string }) =>
    apiClient.post<TopicMarketSignal[]>('/topics/signals/import', data) as Promise<TopicMarketSignal[]>,

  collectSignals: (data: { source_keys: string[]; limit_per_source?: number }) =>
    apiClient.post<TopicMarketSignal[]>('/topics/signals/collect', data) as Promise<TopicMarketSignal[]>,

  testSignalSources: (data: { source_keys: string[]; limit_per_source?: number }) =>
    apiClient.post<TopicMarketSignalSourceConnection[]>('/topics/signals/sources/test', data) as Promise<TopicMarketSignalSourceConnection[]>,

  listSignalSourceHealth: () =>
    apiClient.get<TopicMarketSignalSourceHealth[]>('/topics/signals/source-health') as Promise<TopicMarketSignalSourceHealth[]>,

  listSignalSources: () =>
    apiClient.get<TopicMarketSignalSource[]>('/topics/signals/sources') as Promise<TopicMarketSignalSource[]>,

  listSignals: (limit = 20) =>
    apiClient.get<TopicMarketSignal[]>('/topics/signals', { params: { limit } }) as Promise<TopicMarketSignal[]>,

  signalSummary: (limit = 100) =>
    apiClient.get<TopicMarketSignalSummary>('/topics/signals/summary', { params: { limit } }) as Promise<TopicMarketSignalSummary>,

  getAutomationSettings: () =>
    apiClient.get<TopicMarketSignalAutomationSettings>('/topics/signals/automation') as Promise<TopicMarketSignalAutomationSettings>,

  updateAutomationSettings: (data: Partial<TopicMarketSignalAutomationSettings>) =>
    apiClient.patch<TopicMarketSignalAutomationSettings>('/topics/signals/automation', data) as Promise<TopicMarketSignalAutomationSettings>,

  listSourceCredentials: () =>
    apiClient.get<TopicMarketSignalSourceCredentialStatus[]>('/topics/signals/source-credentials') as Promise<TopicMarketSignalSourceCredentialStatus[]>,

  updateSourceCredentials: (sourceKey: string, data: { api_key?: string; cookie?: string; endpoint_url?: string; headers?: Record<string, string> }) =>
    apiClient.patch<TopicMarketSignalSourceCredentialStatus>(`/topics/signals/sources/${sourceKey}/credentials`, data) as Promise<TopicMarketSignalSourceCredentialStatus>,

  adopt: (topicId: string) =>
    apiClient.post<NovelDTO>(`/topics/${topicId}/adopt`) as Promise<NovelDTO>,
}
