import { apiClient } from './config'

export interface MonitorHealth {
  status: 'ok' | 'warning' | 'error' | string
  score: number
  error_count: number
  warning_count: number
  alert_count: number
}

export interface ObsidianMemorySummary {
  primary_memory: boolean
  premise_locked: boolean
  fact_count: number
  chapter_count: number
  relationship_graph_path: string
}

export interface KnowledgeGraphSummary {
  fact_count: number
  relationship_count: number
  entity_count: number
}

export interface ContinuityMonitorSummary {
  dropout_count: number
  stale_relationship_count: number
  active_relationship_signal_count: number
  voice_drift_alert: boolean
  timeline_conflict_count: number
  current_chapter_has_timeline_event: boolean
  outline_status: string
}

export interface PowerMonitorSummary {
  profile_count: number
  warning_count: number
}

export interface NovelProMonitorAlert {
  severity: 'info' | 'success' | 'warning' | 'error' | string
  source: 'obsidian' | 'knowledge' | 'continuity' | 'power' | string
  title: string
  message: string
  action: string
}

export interface NovelProMonitorOverview {
  novel_id: string
  chapter_number: number
  health: MonitorHealth
  obsidian: ObsidianMemorySummary
  knowledge_graph: KnowledgeGraphSummary
  continuity: ContinuityMonitorSummary
  power: PowerMonitorSummary
  alerts: NovelProMonitorAlert[]
}

export const novelproMonitorApi = {
  getOverview: (novelId: string, chapterNumber?: number | null) =>
    apiClient.get<NovelProMonitorOverview>(
      `/novels/${novelId}/novelpro/monitor`,
      {
        params: chapterNumber ? { chapter_number: chapterNumber } : undefined,
      },
    ) as Promise<NovelProMonitorOverview>,
}
