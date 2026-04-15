import axios, { type AxiosRequestConfig } from 'axios'
import type {
  BookListItem,
  BookDeskResponse,
  CastGraph,
  CastSearchResponse,
  CastCoverage,
  StoryKnowledge,
  KnowledgeSearchResponse,
  Bible,
  ChapterBody,
  ChapterReview,
  ChapterReviewAiResponse,
  ChapterStructure,
  SimpleResponse,
  SlugResponse,
  JobCreateResponse,
  JobStatusResponse,
} from '../types/api'

// Legacy API client (old /api endpoints)
// DEPRECATED: This file is maintained for backward compatibility only.
// Do NOT use these APIs in new code.
//
// Migration Status (as of 2026-04-01):
// ✅ MIGRATED:
//   - Chapter content: Use chapterApi.getChapter() / updateChapter()
//   - Chapter review: Use chapterApi.getChapterReview() / saveChapterReview()
//   - Chapter AI review: Use chapterApi.reviewChapterAi()
//   - Chapter structure: Use chapterApi.getChapterStructure()
//
// ⚠️ PENDING MIGRATION:
//   - Bible operations: BiblePanel.vue still uses bookApi.getBible() / saveBible()
//     Reason: New Bible API lacks bulk update endpoint; needs backend enhancement
//   - Cast operations: Multiple components use bookApi cast methods
//   - Knowledge operations: Multiple components use bookApi knowledge methods
//   - Desk operations: useWorkbench.ts uses bookApi.getDesk()
//
// Current dependencies:
// - bookApi: BiblePanel.vue, CastGraphCompact.vue, KnowledgePanel.vue,
//            KnowledgeTripleGraph.vue, useWorkbench.ts, Cast.vue, Chapter.vue (desk only)
// - jobApi: 已迁移至 api/workflow.ts（workflowApi）
//
// For new code, use the RESTful API clients:
// - novelApi from './novel.ts' for novel operations
// - chapterApi from './chapter.ts' for chapter operations (✅ FULLY MIGRATED)
// - bibleApi from './bible.ts' for bible operations (partial - needs bulk update)
//
// TODO: Migrate existing components to new API clients before removing this file.

interface LegacyApiClient {
  get<T>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T>
}

const axiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 添加响应拦截器，直接返回数据
axiosInstance.interceptors.response.use(response => response.data)

const request = axiosInstance as unknown as LegacyApiClient

export const bookApi = {
  getList: () => request.get<BookListItem[]>('/books'),
  create: (data: unknown) => request.post<SlugResponse>('/jobs/create-book', data),
  deleteBook: (slug: string) => request.delete<SimpleResponse>(`/book/${slug}`),
  getCast: (slug: string) => request.get<CastGraph>(`/book/${slug}/cast`),
  putCast: (slug: string, data: unknown) => request.put(`/book/${slug}/cast`, data),
  searchCast: (slug: string, q: string) =>
    request.get<CastSearchResponse>(`/book/${slug}/cast/search`, { params: { q } }),
  /** 正文与关系图对照：章节出现、设定未入库、书名号未匹配等 */
  getCastCoverage: (slug: string) =>
    request.get<CastCoverage>(`/book/${slug}/cast/coverage`),
  getKnowledge: (slug: string) =>
    request.get<StoryKnowledge>(`/book/${slug}/knowledge`),
  putKnowledge: (slug: string, data: unknown) => request.put(`/book/${slug}/knowledge`, data),
  knowledgeSearch: (slug: string, q: string, k = 6) =>
    request.get<KnowledgeSearchResponse>(`/book/${slug}/knowledge/search`, { params: { q, k } }),
  getDesk: (slug: string) =>
    request.get<BookDeskResponse>(`/book/${slug}/desk`),
  /** @deprecated Use bibleApi.getBible() - Note: New API has different structure, needs bulk update endpoint */
  getBible: (slug: string) => request.get<Bible>(`/book/${slug}/bible`),
  /** @deprecated Use bibleApi - Note: New API has different structure, needs bulk update endpoint */
  saveBible: (slug: string, data: unknown) => request.put(`/book/${slug}/bible`, data),
  /** @deprecated Use chapterApi.getChapter() instead */
  getChapterBody: (slug: string, chapterId: number) =>
    request.get<ChapterBody>(`/book/${slug}/chapter/${chapterId}/body`),
  /** @deprecated Use chapterApi.updateChapter() instead */
  saveChapterBody: (slug: string, chapterId: number, content: string) =>
    request.put(`/book/${slug}/chapter/${chapterId}/body`, { content }),
  /** @deprecated Use chapterApi.getChapterReview() instead */
  getChapterReview: (slug: string, chapterId: number) =>
    request.get<ChapterReview>(`/book/${slug}/chapter/${chapterId}/review`),
  /** @deprecated Use chapterApi.saveChapterReview() instead */
  saveChapterReview: (slug: string, chapterId: number, status: string, memo: string) =>
    request.put(`/book/${slug}/chapter/${chapterId}/review`, { status, memo }),
  /** @deprecated Use chapterApi.reviewChapterAi() instead - 自动审读：返回 status/memo；save=true 时写入 editorial */
  reviewChapterAi: (slug: string, chapterId: number, save = false) =>
    request.post<ChapterReviewAiResponse>(`/book/${slug}/chapter/${chapterId}/review-ai`, { save }),
  /** @deprecated Use chapterApi.getChapterStructure() instead */
  getChapterStructure: (slug: string, chapterId: number) =>
    request.get<ChapterStructure>(`/book/${slug}/chapter/${chapterId}/structure`),
}

export const jobApi = {
  startPlan: (slug: string, dryRun = false, mode: 'initial' | 'revise' = 'initial') =>
    request.post<JobCreateResponse>(`/jobs/${slug}/plan`, { dry_run: dryRun, mode }),
  startWrite: (slug: string, from: number, to?: number, dryRun = false, continuity = false) =>
    request.post<JobCreateResponse>(`/jobs/${slug}/write`, { from_chapter: from, to_chapter: to, dry_run: dryRun, continuity }),
  startRun: (slug: string, dryRun = false, continuity = false) =>
    request.post<JobCreateResponse>(`/jobs/${slug}/run`, { dry_run: dryRun, continuity }),
  startExport: (slug: string) => request.post(`/jobs/${slug}/export`, {}),
  cancelJob: (jobId: string) => request.post<SimpleResponse>(`/jobs/${jobId}/cancel`, {}),
  getStatus: (jobId: string) =>
    request.get<JobStatusResponse>(`/jobs/${jobId}`),
}
