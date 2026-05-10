/**
 * 统一快照 API - 合并 Checkpoint 和 Snapshot
 * 注意：使用 snake_case 匹配后端数据库字段命名
 */
import { apiClient } from './config'

export interface UnifiedSnapshot {
  id: string
  novel_id: string
  parent_snapshot_id?: string
  branch_name: string

  // 触发信息
  trigger_type: 'CHAPTER' | 'ACT' | 'MILESTONE' | 'MANUAL' | 'AUTO'
  name: string
  description?: string

  // 章节指针
  chapter_pointers: string[]

  // 引擎状态
  story_state: Record<string, any>
  character_masks: Record<string, any>
  emotion_ledger: Record<string, any>
  active_foreshadows: string[]
  outline: string
  recent_chapters_summary: string

  // 元数据
  created_at: string
  bible_state: Record<string, any>
  foreshadow_state: Record<string, any>
}

export interface CreateSnapshotRequest {
  trigger_type: string
  name: string
  description?: string
  chapter_number?: number

  // 引擎状态（可选）
  story_state?: Record<string, any>
  character_masks?: Record<string, any>
  emotion_ledger?: Record<string, any>
  active_foreshadows?: string[]
  outline?: string
  recent_summary?: string
}

export interface RollbackSnapshotResponse {
  deleted_chapter_ids: string[]
  deleted_count: number
  has_engine_state: boolean
}

export const snapshotApi = {
  /** GET /novels/{novel_id}/snapshots */
  list: (novelId: string) =>
    apiClient.get<{ snapshots: UnifiedSnapshot[] }>(
      `/novels/${novelId}/snapshots`,
    ) as Promise<{ snapshots: UnifiedSnapshot[] }>,

  /** GET /novels/{novel_id}/snapshots/{snapshot_id} */
  get: (novelId: string, snapshotId: string) =>
    apiClient.get<UnifiedSnapshot>(
      `/novels/${novelId}/snapshots/${snapshotId}`,
    ) as Promise<UnifiedSnapshot>,

  /** POST /novels/{novel_id}/snapshots */
  create: (novelId: string, body: CreateSnapshotRequest) =>
    apiClient.post<{ snapshot_id: string; message: string }>(
      `/novels/${novelId}/snapshots`,
      body,
    ) as Promise<{ snapshot_id: string; message: string }>,

  /** POST /novels/{novel_id}/snapshots/{snapshot_id}/rollback */
  rollback: (novelId: string, snapshotId: string) =>
    apiClient.post<RollbackSnapshotResponse>(
      `/novels/${novelId}/snapshots/${snapshotId}/rollback`,
      {},
    ) as Promise<RollbackSnapshotResponse>,

  /** DELETE /novels/{novel_id}/snapshots/{snapshot_id} */
  delete: (novelId: string, snapshotId: string) =>
    apiClient.delete<void>(
      `/novels/${novelId}/snapshots/${snapshotId}`,
    ) as Promise<void>,
}
