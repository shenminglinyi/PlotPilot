import { apiClient } from './config'

export interface CharacterDropoutItem {
  character_id: string
  character_name: string
  last_appearance_chapter: number
  chapters_absent: number
  appearance_count: number
  severity: 'low' | 'medium' | 'high' | string
}

export interface RelationshipSpotlightItem {
  source_character: string
  target_character: string
  relation: string
  description: string
}

export interface RelationshipSignalItem {
  source_character: string
  target_character: string
  relation: string
  description: string
  last_joint_chapter: number
  joint_appearance_count: number
  change_signal: string
  signal_excerpt: string
  severity: 'info' | 'success' | 'warning' | 'error' | string
}

export interface StaleRelationshipItem {
  source_character: string
  target_character: string
  relation: string
  description: string
  last_joint_chapter: number
  chapters_since_joint: number
  severity: 'info' | 'success' | 'warning' | 'error' | string
}

export interface RelationshipTrackingSummary {
  tracked_pairs: number
  active_signals: RelationshipSignalItem[]
  stale_pairs: StaleRelationshipItem[]
}

export interface TimelineEventItem {
  id: string
  chapter_number: number
  event: string
  timestamp: string
  timestamp_type: string
}

export interface TimelineSummary {
  total_events: number
  current_chapter_has_event: boolean
  current_chapter_events: TimelineEventItem[]
  recent_events: TimelineEventItem[]
}

export interface VoiceDriftSummary {
  drift_alert: boolean
  latest_similarity_score: number | null
  scored_chapters: number
  alert_threshold: number
  alert_consecutive: number
}

export interface OutlineDeviationSummary {
  status: 'aligned' | 'watch' | 'warning' | 'unavailable' | string
  overlap_score: number | null
  outline_excerpt: string
  summary_excerpt: string
  warning_reasons: string[]
}

export interface ContinuityOverviewResponse {
  novel_id: string
  chapter_number: number
  latest_chapter_number: number
  character_dropouts: CharacterDropoutItem[]
  relationship_spotlights: RelationshipSpotlightItem[]
  relationship_tracking: RelationshipTrackingSummary
  voice_drift: VoiceDriftSummary
  timeline: TimelineSummary
  outline_deviation: OutlineDeviationSummary
}

export const continuityApi = {
  getOverview: (novelId: string, chapterNumber?: number | null) =>
    apiClient.get<ContinuityOverviewResponse>(
      `/novels/${novelId}/continuity/overview`,
      {
        params: chapterNumber ? { chapter_number: chapterNumber } : undefined,
      },
    ) as Promise<ContinuityOverviewResponse>,
}
