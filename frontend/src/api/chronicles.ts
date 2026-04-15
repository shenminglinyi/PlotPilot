/**
 * 双螺旋编年史 BFF
 * GET /api/v1/novels/{novel_id}/chronicles
 */
import { apiClient } from './config'

export interface ChronicleStoryEvent {
  note_id: string
  time: string
  title: string
  description: string
  source_chapter: number | null
}

export interface ChronicleSnapshot {
  id: string
  kind: string
  name: string
  branch_name: string
  created_at: string | null
  description: string | null
  anchor_chapter: number | null
}

export interface ChronicleRow {
  chapter_index: number
  story_events: ChronicleStoryEvent[]
  snapshots: ChronicleSnapshot[]
}

export interface ChroniclesResponse {
  rows: ChronicleRow[]
  max_chapter_in_book: number
  note: string
}

export interface SnapshotRollbackResponse {
  deleted_chapter_ids: string[]
  deleted_count: number
}

export const chroniclesApi = {
  get: (novelId: string) =>
    apiClient.get<ChroniclesResponse>(`/api/v1/novels/${novelId}/chronicles`) as unknown as Promise<ChroniclesResponse>,

  rollbackToSnapshot: (novelId: string, snapshotId: string) =>
    apiClient.post<SnapshotRollbackResponse>(
      `/api/v1/novels/${novelId}/snapshots/${snapshotId}/rollback`,
    ) as unknown as Promise<SnapshotRollbackResponse>,
}
