import { apiClient } from './config'
import type { GuardrailCheckResponse } from './engineCore'

export interface ChapterDTO {
  id: string
  novel_id: string
  number: number
  title: string
  content: string
  status: string
  word_count: number
  created_at: string
  updated_at: string
}

export interface UpdateChapterRequest {
  content: string
}

export interface ChapterReviewDTO {
  status: string
  memo: string
  created_at: string
  updated_at: string
}

export interface ChapterStructureDTO {
  word_count: number
  paragraph_count: number
  dialogue_ratio: number
  scene_count: number
  pacing: string
}

export interface ChapterReviewAiResponse {
  ok: boolean
  status: string
  memo: string
  saved: boolean
}

export const chapterApi = {
  /**
   * List all chapters for a novel
   * GET /api/v1/novels/{novelId}/chapters
   */
  listChapters: (novelId: string) =>
    apiClient.get<ChapterDTO[]>(`/novels/${novelId}/chapters`) as Promise<ChapterDTO[]>,

  /**
   * Get a specific chapter by number
   * GET /api/v1/novels/{novelId}/chapters/{chapterNumber}
   */
  getChapter: (novelId: string, chapterNumber: number) =>
    apiClient.get<ChapterDTO>(`/novels/${novelId}/chapters/${chapterNumber}`) as Promise<ChapterDTO>,

  /**
   * Update a chapter
   * PUT /api/v1/novels/{novelId}/chapters/{chapterNumber}
   */
  updateChapter: (novelId: string, chapterNumber: number, data: UpdateChapterRequest) =>
    apiClient.put<ChapterDTO>(`/novels/${novelId}/chapters/${chapterNumber}`, data) as Promise<ChapterDTO>,

  /**
   * Get chapter review
   * GET /api/v1/novels/{novelId}/chapters/{chapterNumber}/review
   */
  getChapterReview: (novelId: string, chapterNumber: number) =>
    apiClient.get<ChapterReviewDTO>(`/novels/${novelId}/chapters/${chapterNumber}/review`) as Promise<ChapterReviewDTO>,

  /**
   * Save chapter review
   * PUT /api/v1/novels/{novelId}/chapters/{chapterNumber}/review
   */
  saveChapterReview: (novelId: string, chapterNumber: number, status: string, memo: string) =>
    apiClient.put<ChapterReviewDTO>(`/novels/${novelId}/chapters/${chapterNumber}/review`, { status, memo }) as Promise<ChapterReviewDTO>,

  /**
   * AI review chapter
   * POST /api/v1/novels/{novelId}/chapters/{chapterNumber}/review-ai
   */
  reviewChapterAi: (novelId: string, chapterNumber: number, save: boolean) =>
    apiClient.post<ChapterReviewAiResponse>(`/novels/${novelId}/chapters/${chapterNumber}/review-ai`, { save }) as Promise<ChapterReviewAiResponse>,

  /**
   * Get chapter structure analysis
   * GET /api/v1/novels/{novelId}/chapters/{chapterNumber}/structure
   */
  getChapterStructure: (novelId: string, chapterNumber: number) =>
    apiClient.get<ChapterStructureDTO>(`/novels/${novelId}/chapters/${chapterNumber}/structure`) as Promise<ChapterStructureDTO>,

  /**
   * 保存后自动护栏快照（建议模式）；尚无快照时返回 null（对应 HTTP 404）
   * GET /novels/{novelId}/chapters/{chapterNumber}/guardrail-snapshot
   */
  getGuardrailSnapshot: async (
    novelId: string,
    chapterNumber: number
  ): Promise<GuardrailCheckResponse | null> => {
    try {
      return (await apiClient.get(
        `/novels/${novelId}/chapters/${chapterNumber}/guardrail-snapshot`
      )) as GuardrailCheckResponse
    } catch (e: unknown) {
      const ax = e as { response?: { status?: number } }
      if (ax.response?.status === 404) return null
      throw e
    }
  },

  /**
   * 确保章节在正文库中存在；若不存在则创建空白记录
   * POST /api/v1/novels/{novelId}/chapters/{chapterNumber}/ensure
   */
  ensureChapter: (novelId: string, chapterNumber: number, title = '') =>
    apiClient.post<ChapterDTO>(`/novels/${novelId}/chapters/${chapterNumber}/ensure`, { title }) as Promise<ChapterDTO>,
}
