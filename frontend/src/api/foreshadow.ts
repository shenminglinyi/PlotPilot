/**
 * 伏笔手账本 API：当下的疑问，本阶段兑现即可
 * /api/v1/novels/{novel_id}/foreshadow-ledger
 */
import { apiClient } from './config'

export interface ForeshadowEntry {
  id: string
  chapter: number
  character_id: string
  /** 主角或读者当下的疑问（宜短句） */
  question: string
  status: 'pending' | 'consumed'
  consumed_at_chapter: number | null
  suggested_resolve_chapter: number | null
  resolve_chapter_window: number | null
  importance: 'low' | 'medium' | 'high' | 'critical'
  created_at: string
}

export interface CreateForeshadowPayload {
  entry_id: string
  chapter: number
  character_id: string
  question: string
  suggested_resolve_chapter?: number
  resolve_chapter_window?: number
  importance?: 'low' | 'medium' | 'high' | 'critical'
}

export interface UpdateForeshadowPayload {
  chapter?: number
  character_id?: string
  question?: string
  status?: 'pending' | 'consumed'
  consumed_at_chapter?: number
  suggested_resolve_chapter?: number
  resolve_chapter_window?: number
  importance?: 'low' | 'medium' | 'high' | 'critical'
}

export const foreshadowApi = {
  /**
   * 获取伏笔列表
   * @param novelId 小说 ID
   * @param status 可选筛选状态
   * @param config 可选 AxiosRequestConfig（支持 timeout / signal 等覆盖全局配置）
   */
  list: (novelId: string, status?: 'pending' | 'consumed', config?: Record<string, unknown>) =>
    apiClient.get<ForeshadowEntry[]>(`/novels/${novelId}/foreshadow-ledger`, {
      params: status ? { status } : {},
      ...config,
    }) as Promise<ForeshadowEntry[]>,

  get: (novelId: string, entryId: string) =>
    apiClient.get<ForeshadowEntry>(`/novels/${novelId}/foreshadow-ledger/${entryId}`) as Promise<ForeshadowEntry>,

  create: (novelId: string, payload: CreateForeshadowPayload) =>
    apiClient.post<ForeshadowEntry>(`/novels/${novelId}/foreshadow-ledger`, payload) as Promise<ForeshadowEntry>,

  update: (novelId: string, entryId: string, patch: UpdateForeshadowPayload) =>
    apiClient.put<ForeshadowEntry>(`/novels/${novelId}/foreshadow-ledger/${entryId}`, patch) as Promise<ForeshadowEntry>,

  remove: (novelId: string, entryId: string) =>
    apiClient.delete(`/novels/${novelId}/foreshadow-ledger/${entryId}`) as Promise<void>,

  markConsumed: (novelId: string, entryId: string, consumedAtChapter: number) =>
    foreshadowApi.update(novelId, entryId, {
      status: 'consumed',
      consumed_at_chapter: consumedAtChapter,
    }),
}
