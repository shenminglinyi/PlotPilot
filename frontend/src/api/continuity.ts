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

export interface ContinuityOverviewResponse {
  novel_id: string
  chapter_number: number
  latest_chapter_number: number
  character_dropouts: CharacterDropoutItem[]
  relationship_spotlights: RelationshipSpotlightItem[]
  voice_drift: VoiceDriftSummary
  timeline: TimelineSummary
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
