import { apiClient } from './config'
import type { BookStats } from '../types/api'

function pickNumber(raw: Record<string, unknown>, keys: string[], fallback = 0): number {
  for (const key of keys) {
    const v = raw[key]
    if (typeof v === 'number' && Number.isFinite(v)) {
      return v
    }
    if (typeof v === 'string' && v.trim() !== '') {
      const n = Number(v)
      if (Number.isFinite(n)) {
        return n
      }
    }
  }
  return fallback
}

function pickString(raw: Record<string, unknown>, keys: string[], fallback = ''): string {
  for (const key of keys) {
    const v = raw[key]
    if (typeof v === 'string') {
      return v
    }
  }
  return fallback
}

/**
 * 将 GET /novels/:id/statistics 的 JSON 转为 BookStats。
 * 使用 unknown + 窄化，避免部分环境下 axios 泛型与 store 的 Map 类型推导冲突（如 vue-tsc 报 NovelStatisticsResponse）。
 */
function toBookStatsFromStatisticsPayload(raw: unknown, novelId: string): BookStats {
  if (raw === null || typeof raw !== 'object') {
    throw new Error('novel statistics: 响应不是 JSON 对象')
  }
  const r = raw as Record<string, unknown>

  const totalChapters = pickNumber(r, ['total_chapters', 'chapters_total'])
  const completedChapters = pickNumber(r, ['completed_chapters', 'chapters_completed'])
  const totalWords = pickNumber(r, ['total_words'])
  const avgChapterWords = pickNumber(r, ['avg_chapter_words', 'average_chapter_length'])

  let completionRate: number
  if (Object.prototype.hasOwnProperty.call(r, 'completion_rate')) {
    completionRate = pickNumber(r, ['completion_rate'])
  } else if (totalChapters > 0) {
    completionRate = completedChapters / totalChapters
  } else {
    completionRate = 0
  }

  let lastUpdated = pickString(r, ['last_updated', 'last_activity'])
  if (!lastUpdated) {
    lastUpdated = new Date().toISOString()
  }

  return {
    slug: pickString(r, ['slug']) || novelId,
    title: pickString(r, ['title']),
    total_chapters: totalChapters,
    completed_chapters: completedChapters,
    total_words: totalWords,
    avg_chapter_words: avgChapterWords,
    completion_rate: completionRate,
    last_updated: lastUpdated,
  }
}

export interface ChapterDTO {
  id: string
  number: number
  title: string
  content: string
  word_count: number
}

export interface NovelDTO {
  id: string
  title: string
  author: string
  target_chapters: number
  stage: string
  premise?: string
  /** 服务端从 premise 解析，优先用于「本书锁定」展示 */
  locked_genre?: string
  locked_world_preset?: string
  chapters: ChapterDTO[]
  total_word_count: number
  has_bible?: boolean
  has_outline?: boolean
  autopilot_status?: string
  auto_approve_mode?: boolean
  /** 每章目标字数（与首页建档/PUT 一致；部分接口可能未返回） */
  target_words_per_chapter?: number
}

export const novelApi = {
  /**
   * List all novels
   * GET /api/v1/novels
   */
  listNovels: () => apiClient.get<NovelDTO[]>('/novels') as Promise<NovelDTO[]>,

  /**
   * Get novel by ID
   * GET /api/v1/novels/{novelId}
   */
  getNovel: (novelId: string) => apiClient.get<NovelDTO>(`/novels/${novelId}`) as Promise<NovelDTO>,

  /**
   * Create a new novel
   * POST /api/v1/novels
   */
  createNovel: (data: {
    novel_id: string
    title: string
    author: string
    target_chapters: number
    premise?: string
    genre?: string
    world_preset?: string
    /** V1 体量档：与 target_chapters 二选一由后端解析 */
    length_tier?: 'short' | 'standard' | 'epic' | null
    target_words_per_chapter?: number | null
  }) => apiClient.post<NovelDTO>('/novels', data) as Promise<NovelDTO>,

  /**
   * Delete a novel
   * DELETE /api/v1/novels/{novelId}
   */
  deleteNovel: (novelId: string) => apiClient.delete<void>(`/novels/${novelId}`) as Promise<void>,

  /**
   * Update novel stage
   * PUT /api/v1/novels/{novelId}/stage
   */
  updateNovelStage: (novelId: string, stage: string) =>
    apiClient.put<NovelDTO>(`/novels/${novelId}/stage`, { stage }) as Promise<NovelDTO>,

  /**
   * Update novel basic information
   * PUT /api/v1/novels/{novelId}
   */
  updateNovel: (novelId: string, data: { 
    title?: string
    author?: string
    target_chapters?: number
    premise?: string
    target_words_per_chapter?: number
  }) => apiClient.put<NovelDTO>(`/novels/${novelId}`, data) as Promise<NovelDTO>,

  /**
   * 小说统计（与 Chapter 仓储一致，用于顶栏等；勿再用 /api/stats/book）
   * GET /api/v1/novels/{novelId}/statistics
   */
  getNovelStatistics: async (novelId: string): Promise<BookStats> => {
    const raw = await apiClient.get<unknown>(`/novels/${novelId}/statistics`)
    return toBookStatsFromStatisticsPayload(raw, novelId)
  },

  /**
   * Update auto approve mode
   * PATCH /api/v1/novels/{novelId}/auto-approve-mode
   */
  updateAutoApproveMode: (novelId: string, autoApproveMode: boolean) =>
    apiClient.patch<NovelDTO>(`/novels/${novelId}/auto-approve-mode`, { 
      auto_approve_mode: autoApproveMode 
    }) as Promise<NovelDTO>,

  /**
   * Export novel
   * GET /api/v1/export/novel/{novelId}
   */
  exportNovel: (novelId: string, format: string) =>
    apiClient.get<Blob>(`/export/novel/${novelId}`, {
      params: { format },
      responseType: 'blob'
    }) as Promise<Blob>,

  /**
   * Export chapter
   * GET /api/v1/export/chapter/{chapterId}
   */
  exportChapter: (chapterId: string, format: string) =>
    apiClient.get<Blob>(`/export/chapter/${chapterId}`, {
      params: { format },
      responseType: 'blob'
    }) as Promise<Blob>,
}
