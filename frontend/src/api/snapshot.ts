/**
 * 统一快照 API - 合并 Checkpoint 和 Snapshot
 */
import { apiClient } from './config'

export interface UnifiedSnapshot {
  id: string
  novelId: string
  parentId?: string
  branchName: string

  // 触发信息
  triggerType: 'CHAPTER' | 'ACT' | 'MILESTONE' | 'MANUAL' | 'AUTO'
  triggerReason: string
  name: string
  description?: string

  // 章节指针
  chapterPointers: string[]

  // 引擎状态
  storyState: Record<string, any>
  characterMasks: Record<string, any>
  emotionLedger: Record<string, any>
  activeForeshadows: string[]
  outline: string
  recentChaptersSummary: string

  // 元数据
  createdAt: string
  isHead: boolean
}

export interface CreateSnapshotRequest {
  triggerType: string
  name: string
  description?: string
  chapterNumber?: number

  // 引擎状态（可选）
  storyState?: Record<string, any>
  characterMasks?: Record<string, any>
  emotionLedger?: Record<string, any>
  activeForeshadows?: string[]
  outline?: string
  recentChaptersSummary?: string
}

export interface RollbackSnapshotResponse {
  deletedChapterIds: string[]
  deletedCount: number
  hasEngineState: boolean
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
    apiClient.post<{ snapshotId: string; message: string }>(
      `/novels/${novelId}/snapshots`,
      body,
    ) as Promise<{ snapshotId: string; message: string }>,

  /** POST /novels/{novel_id}/snapshots/{snapshot_id}/rollback */
  rollback: (novelId: string, snapshotId: string) =>
    apiClient.post<RollbackSnapshotResponse>(
      `/novels/${novelId}/snapshots/${snapshotId}/rollback`,
      {},
    ) as Promise<RollbackSnapshotResponse>,

  /** DELETE /novels/{novel_id}/snapshots/{snapshot_id} */
  delete: (novelId: string, snapshotId: string) =>
    apiClient.delete<{ message: string }>(
      `/novels/${novelId}/snapshots/${snapshotId}`,
    ) as Promise<{ message: string }>,
}
