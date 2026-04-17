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
  target_words_per_chapter?: number
  premise?: string
  stage: string
  chapters: ChapterDTO[]
  total_word_count: number
  has_bible?: boolean
  has_outline?: boolean
  autopilot_status?: string
  auto_approve_mode?: boolean
  genre?: string
  theme_agent_enabled?: boolean
  enabled_theme_skills?: string[]
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
    target_words_per_chapter?: number
    premise?: string
    genre?: string
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
    target_words_per_chapter?: number
    premise?: string
    genre?: string
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

  /**
   * Update theme agent enabled
   * PATCH /api/v1/novels/{novelId}/theme-agent-enabled
   */
  updateThemeAgentEnabled: (novelId: string, themeAgentEnabled: boolean) =>
    apiClient.patch<NovelDTO>(`/novels/${novelId}/theme-agent-enabled`, {
      theme_agent_enabled: themeAgentEnabled
    }) as Promise<NovelDTO>,

  /**
   * Get available theme skills for a novel (filtered by genre)
   * GET /api/v1/novels/{novelId}/theme-skills/available
   */
  getAvailableThemeSkills: (novelId: string) =>
    apiClient.get<{
      novel_id: string
      genre: string
      available_skills: Array<{
        key: string
        name: string
        description: string
        compatible_genres: string[]
      }>
      enabled_skills: string[]
    }>(`/novels/${novelId}/theme-skills/available`) as Promise<{
      novel_id: string
      genre: string
      available_skills: Array<{
        key: string
        name: string
        description: string
        compatible_genres: string[]
      }>
      enabled_skills: string[]
    }>,

  /**
   * Update enabled theme skills for a novel
   * PATCH /api/v1/novels/{novelId}/theme-skills
   */
  updateEnabledThemeSkills: (novelId: string, skillKeys: string[]) =>
    apiClient.patch<NovelDTO>(`/novels/${novelId}/theme-skills`, {
      skill_keys: skillKeys
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

  // ─── 自定义技能 CRUD ───

  /**
   * Create custom theme skill
   * POST /api/v1/novels/{novelId}/theme-skills/custom
   */
  createCustomSkill: (novelId: string, data: {
    skill_name: string
    skill_description?: string
    context_prompt?: string
    beat_prompt?: string
    beat_triggers?: string
    audit_checks?: string[]
  }) => apiClient.post(`/novels/${novelId}/theme-skills/custom`, data) as Promise<{ key: string; id: string }>,

  /**
   * Update custom theme skill
   * PUT /api/v1/novels/{novelId}/theme-skills/custom/{skillId}
   */
  updateCustomSkill: (novelId: string, skillId: string, data: {
    skill_name?: string
    skill_description?: string
    context_prompt?: string
    beat_prompt?: string
    beat_triggers?: string
    audit_checks?: string[]
  }) => apiClient.put(`/novels/${novelId}/theme-skills/custom/${skillId}`, data) as Promise<void>,

  /**
   * Delete custom theme skill
   * DELETE /api/v1/novels/{novelId}/theme-skills/custom/{skillId}
   */
  deleteCustomSkill: (novelId: string, skillId: string) =>
    apiClient.delete(`/novels/${novelId}/theme-skills/custom/${skillId}`) as Promise<void>,
}
