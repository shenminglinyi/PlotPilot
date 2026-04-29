import { apiClient } from './config'

export interface CharacterDropoutItem {
  character_id: string
  character_name: string
  last_appearance_chapter: number
  chapters_absent: number
  appearance_count: number
  severity: 'low' | 'medium' | 'high' | string
  tracked_relationship_count: number
  stale_relationship_count: number
  stale_relationship_targets: string[]
  dropout_scope: 'solo' | 'tracked' | 'linked' | string
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
  source: 'structured' | 'heuristic' | string
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
  source: 'structured' | 'heuristic' | string
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

export interface OutlineNodeStatusItem {
  node_key: string
  outline_text: string
  status: 'pending' | 'completed' | 'matched' | 'changed' | 'missing' | 'blocked' | string
  note: string
  evidence: string
}

export interface OutlineDeviationSummary {
  source: 'structured' | 'heuristic' | string
  status: 'aligned' | 'watch' | 'warning' | 'unavailable' | string
  overlap_score: number | null
  outline_excerpt: string
  summary_excerpt: string
  warning_reasons: string[]
  outline_nodes: OutlineNodeStatusItem[]
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

export interface RelationshipEventRequest {
  chapter_number: number
  source_character: string
  target_character?: string
  relation?: string
  event_type?: string
  description?: string
  evidence?: string
  severity?: string
}

export interface RelationshipEventResponse extends Required<RelationshipEventRequest> {
  id: string
  novel_id: string
}

export interface OutlineNodeStatusRequest {
  chapter_number: number
  node_key: string
  outline_text: string
  status?: string
  note?: string
  evidence?: string
}

export interface OutlineNodeStatusResponse extends Required<OutlineNodeStatusRequest> {
  id: string
  novel_id: string
}

export const continuityApi = {
  getOverview: (novelId: string, chapterNumber?: number | null) =>
    apiClient.get<ContinuityOverviewResponse>(
      `/novels/${novelId}/continuity/overview`,
      {
        params: chapterNumber ? { chapter_number: chapterNumber } : undefined,
      },
    ) as Promise<ContinuityOverviewResponse>,
  recordRelationshipEvent: (novelId: string, payload: RelationshipEventRequest) =>
    apiClient.post<RelationshipEventResponse>(
      `/novels/${novelId}/continuity/relationship-events`,
      payload,
    ) as Promise<RelationshipEventResponse>,
  upsertOutlineNodeStatus: (novelId: string, payload: OutlineNodeStatusRequest) =>
    apiClient.put<OutlineNodeStatusResponse>(
      `/novels/${novelId}/continuity/outline-nodes`,
      payload,
    ) as Promise<OutlineNodeStatusResponse>,
}
