import { apiClient, API_BASE_URL } from './config'
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
  }) => apiClient.put<NovelDTO>(`/novels/${novelId}`, data) as Promise<NovelDTO>,

  /**
   * 小说统计（与 Chapter 仓储一致，用于顶栏等；勿再用 /api/stats/book）
   * GET /api/v1/novels/{novelId}/statistics
   */
  getNovelStatistics: (novelId: string) =>
    apiClient.get<BookStats>(`/novels/${novelId}/statistics`) as Promise<BookStats>,

  /**
   * Update auto approve mode
   * PATCH /api/v1/novels/{novelId}/auto-approve-mode
   */
  updateAutoApproveMode: (novelId: string, autoApproveMode: boolean) =>
    apiClient.patch<NovelDTO>(`/novels/${novelId}/auto-approve-mode`, { 
      auto_approve_mode: autoApproveMode 
    }) as Promise<NovelDTO>,

  exportNovel: (novelId: string, format: 'txt' | 'md' | 'epub') => {
    const url = `/novels/${novelId}/export?format=${format}`
    return fetch(`${API_BASE_URL}${url}`).then(res => {
      if (!res.ok) throw new Error(`Export failed: ${res.status}`)
      const disposition = res.headers.get('Content-Disposition') || ''
      let filename = `novel.${format}`
      const match = disposition.match(/filename\*=UTF-8''(.+)/)
      if (match) filename = decodeURIComponent(match[1])
      return res.blob().then(blob => ({ blob, filename }))
    })
  },

  exportChapter: (chapterId: string, format: string) =>
    apiClient.get<Blob>(`/export/chapter/${chapterId}`, {
      params: { format },
      responseType: 'blob'
    }) as Promise<Blob>,
}
