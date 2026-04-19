import type { AxiosRequestConfig } from 'axios'

import { WIZARD_STEP_TIMEOUT_MS } from '@/constants/wizard'
import { apiClient } from './config'

/** Bible 人物关系：字符串 或 LLM 结构化对象 */
export type BibleRelationshipEntry =
  | string
  | { target?: string; relation?: string; description?: string }

export interface CharacterDTO {
  id: string
  name: string
  description: string
  relationships: BibleRelationshipEntry[]
  /** AI 生成时的角色定位（主角/配角等） */
  role?: string
  mental_state?: string
  verbal_tic?: string
  idle_behavior?: string
}

export interface WorldSettingDTO {
  id: string
  name: string
  description: string
  setting_type: string
}

export interface LocationDTO {
  id: string
  name: string
  description: string
  location_type: string
}

export interface TimelineNoteDTO {
  id: string
  event: string
  time_point: string
  description: string
}

export interface StyleNoteDTO {
  id: string
  category: string
  content: string
}

export interface BibleDTO {
  id: string
  novel_id: string
  characters: CharacterDTO[]
  world_settings: WorldSettingDTO[]
  locations: LocationDTO[]
  timeline_notes: TimelineNoteDTO[]
  style_notes: StyleNoteDTO[]
}

export interface AddCharacterRequest {
  character_id: string
  name: string
  description: string
}

export const bibleApi = {
  /**
   * Create bible for a novel
   * POST /api/v1/bible/novels/{novelId}/bible
   */
  createBible: (novelId: string, bibleId: string) =>
    apiClient.post<BibleDTO>(`/bible/novels/${novelId}/bible`, {
      bible_id: bibleId,
      novel_id: novelId,
    }) as Promise<BibleDTO>,

  /**
   * Get bible by novel ID
   * GET /api/v1/bible/novels/{novelId}/bible
   */
  getBible: (novelId: string, config?: AxiosRequestConfig) =>
    apiClient.get<BibleDTO>(`/bible/novels/${novelId}/bible`, config) as Promise<BibleDTO>,

  /**
   * List all characters in a bible
   * GET /api/v1/bible/novels/{novelId}/bible/characters
   */
  listCharacters: (novelId: string) =>
    apiClient.get<CharacterDTO[]>(`/bible/novels/${novelId}/bible/characters`) as Promise<CharacterDTO[]>,

  /**
   * Add character to bible
   * POST /api/v1/bible/novels/{novelId}/bible/characters
   */
  addCharacter: (novelId: string, data: AddCharacterRequest) =>
    apiClient.post<BibleDTO>(`/bible/novels/${novelId}/bible/characters`, data) as Promise<BibleDTO>,

  /**
   * Add world setting to bible
   * POST /api/v1/bible/novels/{novelId}/bible/world-settings
   */
  addWorldSetting: (
    novelId: string,
    data: { setting_id: string; name: string; description: string; setting_type: string }
  ) =>
    apiClient.post<BibleDTO>(`/bible/novels/${novelId}/bible/world-settings`, data) as Promise<BibleDTO>,

  /**
   * Bulk update entire bible
   * PUT /api/v1/bible/novels/{novelId}/bible
   */
  updateBible: (
    novelId: string,
    data: {
      characters: CharacterDTO[]
      world_settings: WorldSettingDTO[]
      locations: LocationDTO[]
      timeline_notes: TimelineNoteDTO[]
      style_notes: StyleNoteDTO[]
    }
  ) =>
    apiClient.put<BibleDTO>(`/bible/novels/${novelId}/bible`, data) as Promise<BibleDTO>,

  /**
   * AI generate (or regenerate) Bible for a novel
   * POST /api/v1/bible/novels/{novelId}/generate
   */
  /** 后端 202 即返回；冷启动、远程网关或本地代理较慢时需留足握手时间（引导页默认 400s） */
  generateBible: (novelId: string, stage: string = 'all') =>
    apiClient.post<{ message: string; novel_id: string; status_url: string }>(
      `/bible/novels/${novelId}/generate?stage=${stage}`,
      {},
      { timeout: WIZARD_STEP_TIMEOUT_MS }
    ) as Promise<{ message: string; novel_id: string; status_url: string }>,

  /**
   * Check Bible generation status
   * GET /api/v1/bible/novels/{novelId}/bible/status
   */
  getBibleStatus: (novelId: string) =>
    apiClient.get<{ exists: boolean; ready: boolean; novel_id: string }>(
      `/bible/novels/${novelId}/bible/status`,
      { timeout: WIZARD_STEP_TIMEOUT_MS }
    ) as Promise<{ exists: boolean; ready: boolean; novel_id: string }>,

  /**
   * 异步 Bible 生成失败原因（单进程内存；成功或未失败时 error 为 null）
   * GET /api/v1/bible/novels/{novelId}/bible/generation-feedback
   */
  getBibleGenerationFeedback: (novelId: string) =>
    apiClient.get<{
      novel_id: string
      error: string | null
      stage: string | null
      at: string | null
    }>(`/bible/novels/${novelId}/bible/generation-feedback`, { timeout: 30_000 }) as Promise<{
      novel_id: string
      error: string | null
      stage: string | null
      at: string | null
    }>,
}
