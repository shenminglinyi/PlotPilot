import { apiClient } from './config'
import type { BookStats } from '../types/api'

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
  chapters: ChapterDTO[]
  total_word_count: number
  has_bible?: boolean
  has_outline?: boolean
  autopilot_status?: string
  auto_approve_mode?: boolean
}

export const novelApi = {
  /**
   * List all novels
   * GET /api/v1/novels
   */
  listNovels: () => apiClient.get<NovelDTO[]>('/api/v1/novels') as unknown as Promise<NovelDTO[]>,

  /**
   * Get novel by ID
   * GET /api/v1/novels/{novelId}
   */
  getNovel: (novelId: string) => apiClient.get<NovelDTO>(`/api/v1/novels/${novelId}`) as unknown as Promise<NovelDTO>,

  /**
   * Create a new novel
   * POST /api/v1/novels
   */
  createNovel: (data: {
    novel_id: string
    title: string
    author: string
    target_chapters: number
  }) => apiClient.post<NovelDTO>('/api/v1/novels', data) as unknown as Promise<NovelDTO>,

  /**
   * Delete a novel
   * DELETE /api/v1/novels/{novelId}
   */
  deleteNovel: (novelId: string) => apiClient.delete<void>(`/api/v1/novels/${novelId}`) as unknown as Promise<void>,

  /**
   * Update novel stage
   * PUT /api/v1/novels/{novelId}/stage
   */
  updateNovelStage: (novelId: string, stage: string) =>
    apiClient.put<NovelDTO>(`/api/v1/novels/${novelId}/stage`, { stage }) as unknown as Promise<NovelDTO>,

  /**
   * Update novel basic information
   * PUT /api/v1/novels/{novelId}
   */
  updateNovel: (novelId: string, data: { 
    title?: string
    author?: string
    target_chapters?: number
    premise?: string
  }) => apiClient.put<NovelDTO>(`/api/v1/novels/${novelId}`, data) as unknown as Promise<NovelDTO>,

  /**
   * 小说统计（与 Chapter 仓储一致，用于顶栏等；勿再用 /api/stats/book）
   * GET /api/v1/novels/{novelId}/statistics
   */
  getNovelStatistics: (novelId: string) =>
    apiClient.get<BookStats>(`/api/v1/novels/${novelId}/statistics`) as unknown as Promise<BookStats>,

  /**
   * Update auto approve mode
   * PATCH /api/v1/novels/{novelId}/auto-approve-mode
   */
  updateAutoApproveMode: (novelId: string, autoApproveMode: boolean) =>
    apiClient.patch<NovelDTO>(`/api/v1/novels/${novelId}/auto-approve-mode`, { 
      auto_approve_mode: autoApproveMode 
    }) as unknown as Promise<NovelDTO>,
}
