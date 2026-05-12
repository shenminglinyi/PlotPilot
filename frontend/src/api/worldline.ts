/**
 * 世界线管理 API（故事 git 模型）
 */
import { apiClient } from './config'

export interface CheckpointNode {
  id: string
  name: string
  trigger_type: string
  branch_name: string
  created_at: string
  anchor_chapter: number | null
}

export interface BranchInfo {
  id: string
  name: string
  head_id: string
  is_default: number
  storyline_id: string | null
}

export interface WorldlineGraph {
  nodes: CheckpointNode[]
  edges: { from: string; to: string }[]
  branches: BranchInfo[]
  head_id: string | null
}

export interface CheckoutResult {
  stash_id: string
  restored_chapters: number
  deleted_chapters: number
  message: string
}

export const worldlineApi = {
  getGraph: (novelId: string) =>
    apiClient.get<WorldlineGraph>(`/novels/${novelId}/worldline/graph`) as unknown as Promise<WorldlineGraph>,

  listCheckpoints: (novelId: string) =>
    apiClient.get<CheckpointNode[]>(`/novels/${novelId}/worldline/checkpoints`) as unknown as Promise<CheckpointNode[]>,

  createCheckpoint: (novelId: string, body: {
    trigger_type?: string; name: string; description?: string; branch_name?: string
  }) =>
    apiClient.post<{ checkpoint_id: string }>(
      `/novels/${novelId}/worldline/checkpoints`,
      body,
    ) as unknown as Promise<{ checkpoint_id: string }>,

  listBranches: (novelId: string) =>
    apiClient.get<BranchInfo[]>(`/novels/${novelId}/worldline/branches`) as unknown as Promise<BranchInfo[]>,

  createBranch: (novelId: string, body: { name: string; from_checkpoint_id: string; storyline_id?: string }) =>
    apiClient.post<{ branch_id: string }>(
      `/novels/${novelId}/worldline/branches`,
      body,
    ) as unknown as Promise<{ branch_id: string }>,

  checkout: (novelId: string, checkpointId: string) =>
    apiClient.post<CheckoutResult>(
      `/novels/${novelId}/worldline/checkpoints/${checkpointId}/checkout`,
      {},
    ) as unknown as Promise<CheckoutResult>,

  hardReset: (novelId: string, checkpointId: string) =>
    apiClient.post<CheckoutResult>(
      `/novels/${novelId}/worldline/checkpoints/${checkpointId}/hard-reset`,
      {},
    ) as unknown as Promise<CheckoutResult>,

  deleteCheckpoint: (novelId: string, checkpointId: string) =>
    apiClient.delete(`/novels/${novelId}/worldline/checkpoints/${checkpointId}`),
}
