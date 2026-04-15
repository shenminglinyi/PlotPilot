/**
 * 伏笔账本 API
 * 后端路由：/api/v1/novels/{novel_id}/foreshadow-ledger
 */
import { apiClient } from './config'

export interface ForeshadowEntry {
  id: string
  chapter: number
  character_id: string
  hidden_clue: string
  sensory_anchors: Record<string, string>
  status: 'pending' | 'consumed'
  consumed_at_chapter: number | null
  // 新增字段：预期回收机制
  suggested_resolve_chapter: number | null  // 预期回收章节
  resolve_chapter_window: number | null    // 宽容窗口
  importance: 'low' | 'medium' | 'high' | 'critical'  // 重要性
  created_at: string
}

export interface CreateForeshadowPayload {
  entry_id: string
  chapter: number
  character_id: string
  hidden_clue: string
  sensory_anchors: Record<string, string>
  // 新增可选字段
  suggested_resolve_chapter?: number  // 预期回收章节
  resolve_chapter_window?: number    // 宽容窗口
  importance?: 'low' | 'medium' | 'high' | 'critical'
}

export interface UpdateForeshadowPayload {
  chapter?: number
  character_id?: string
  hidden_clue?: string
  sensory_anchors?: Record<string, string>
  status?: 'pending' | 'consumed'
  consumed_at_chapter?: number
  // 新增字段
  suggested_resolve_chapter?: number  // 预期回收章节
  resolve_chapter_window?: number    // 宽容窗口
  importance?: 'low' | 'medium' | 'high' | 'critical'
}

export interface MatchForeshadowResponse {
  matched: boolean
  entry: ForeshadowEntry | null
}

export interface ChapterForeshadowSuggestionItem {
  entry: ForeshadowEntry
  score: number
  reason: string
}

export interface ChapterForeshadowSuggestionsResponse {
  chapter_number: number
  outline_excerpt: string
  items: ChapterForeshadowSuggestionItem[]
  note: string
}

export const foreshadowApi = {
  /** GET /api/v1/novels/{novel_id}/foreshadow-ledger */
  list: (novelId: string, status?: 'pending' | 'consumed') =>
    apiClient.get<ForeshadowEntry[]>(
      `/api/v1/novels/${novelId}/foreshadow-ledger`,
      { params: status ? { status } : {} }
    ) as unknown as Promise<ForeshadowEntry[]>,

  /** GET /api/v1/novels/{novel_id}/foreshadow-ledger/{entry_id} */
  get: (novelId: string, entryId: string) =>
    apiClient.get<ForeshadowEntry>(
      `/api/v1/novels/${novelId}/foreshadow-ledger/${entryId}`
    ) as unknown as Promise<ForeshadowEntry>,

  /** POST /api/v1/novels/{novel_id}/foreshadow-ledger */
  create: (novelId: string, payload: CreateForeshadowPayload) =>
    apiClient.post<ForeshadowEntry>(
      `/api/v1/novels/${novelId}/foreshadow-ledger`,
      payload
    ) as unknown as Promise<ForeshadowEntry>,

  /** PUT /api/v1/novels/{novel_id}/foreshadow-ledger/{entry_id} */
  update: (novelId: string, entryId: string, patch: UpdateForeshadowPayload) =>
    apiClient.put<ForeshadowEntry>(
      `/api/v1/novels/${novelId}/foreshadow-ledger/${entryId}`,
      patch
    ) as unknown as Promise<ForeshadowEntry>,

  /** DELETE /api/v1/novels/{novel_id}/foreshadow-ledger/{entry_id} */
  remove: (novelId: string, entryId: string) =>
    apiClient.delete(`/api/v1/novels/${novelId}/foreshadow-ledger/${entryId}`),

  /**
   * POST /api/v1/novels/{novel_id}/foreshadow-ledger/match
   * 根据当前场景的感官锚点查找最佳匹配的 pending 伏笔。
   */
  match: (novelId: string, currentAnchors: Record<string, string>) =>
    apiClient.post<MatchForeshadowResponse>(
      `/api/v1/novels/${novelId}/foreshadow-ledger/match`,
      { current_anchors: currentAnchors }
    ) as unknown as Promise<MatchForeshadowResponse>,

  /**
   * 快捷方法：将一条伏笔标记为已消费。
   */
  markConsumed: (novelId: string, entryId: string, consumedAtChapter: number) =>
    foreshadowApi.update(novelId, entryId, {
      status: 'consumed',
      consumed_at_chapter: consumedAtChapter,
    }),

  /**
   * GET …/foreshadow-ledger/chapter-suggestions
   * 按本章大纲与 pending 伏笔做词重叠打分（后端可升级为向量检索）。
   */
  chapterSuggestions: (
    novelId: string,
    chapterNumber: number,
    outline: string,
    params?: { min_score?: number; limit?: number }
  ) =>
    apiClient.get<ChapterForeshadowSuggestionsResponse>(
      `/api/v1/novels/${novelId}/foreshadow-ledger/chapter-suggestions`,
      {
        params: {
          chapter_number: chapterNumber,
          outline,
          min_score: params?.min_score,
          limit: params?.limit,
        },
      }
    ) as unknown as Promise<ChapterForeshadowSuggestionsResponse>,
}
