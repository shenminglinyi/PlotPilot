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
    apiClient.post<BibleDTO>(`/api/v1/bible/novels/${novelId}/bible`, {
      bible_id: bibleId,
      novel_id: novelId,
    }) as unknown as Promise<BibleDTO>,

  /**
   * Get bible by novel ID
   * GET /api/v1/bible/novels/{novelId}/bible
   */
  getBible: (novelId: string) =>
    apiClient.get<BibleDTO>(`/api/v1/bible/novels/${novelId}/bible`) as unknown as Promise<BibleDTO>,

  /**
   * List all characters in a bible
   * GET /api/v1/bible/novels/{novelId}/bible/characters
   */
  listCharacters: (novelId: string) =>
    apiClient.get<CharacterDTO[]>(`/api/v1/bible/novels/${novelId}/bible/characters`) as unknown as Promise<CharacterDTO[]>,

  /**
   * Add character to bible
   * POST /api/v1/bible/novels/{novelId}/bible/characters
   */
  addCharacter: (novelId: string, data: AddCharacterRequest) =>
    apiClient.post<BibleDTO>(`/api/v1/bible/novels/${novelId}/bible/characters`, data) as unknown as Promise<BibleDTO>,

  /**
   * Add world setting to bible
   * POST /api/v1/bible/novels/{novelId}/bible/world-settings
   */
  addWorldSetting: (
    novelId: string,
    data: { setting_id: string; name: string; description: string; setting_type: string }
  ) =>
    apiClient.post<BibleDTO>(`/api/v1/bible/novels/${novelId}/bible/world-settings`, data) as unknown as Promise<BibleDTO>,

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
    apiClient.put<BibleDTO>(`/api/v1/bible/novels/${novelId}/bible`, data) as unknown as Promise<BibleDTO>,

  /**
   * AI generate (or regenerate) Bible for a novel
   * POST /api/v1/bible/novels/{novelId}/generate
   */
  /** 后端 202 即返回，但冷启动/代理连后端较慢时默认 30s 不够，易报 timeout of 30000ms exceeded */
  generateBible: (novelId: string, stage: string = 'all') =>
    apiClient.post<{ message: string; novel_id: string; status_url: string }>(
      `/api/v1/bible/novels/${novelId}/generate?stage=${stage}`,
      {},
      { timeout: 300_000 }
    ) as unknown as Promise<{ message: string; novel_id: string; status_url: string }>,

  /**
   * generation.status: running|done|error
   */
  getBibleStatus: (novelId: string) =>
    apiClient.get<{
      exists: boolean
      ready: boolean
      novel_id: string
      counts?: { style_notes?: number; world_settings?: number; characters?: number }
      generation?: { status?: string; stage?: string; error?: string; step?: string; message?: string }
    }>(`/api/v1/bible/novels/${novelId}/bible/status`, { timeout: 60_000 }) as unknown as Promise<{
      exists: boolean
      ready: boolean
      novel_id: string
      counts?: { style_notes?: number; world_settings?: number; characters?: number }
      generation?: { status?: string; stage?: string; error?: string; step?: string; message?: string }
    }>,
}
