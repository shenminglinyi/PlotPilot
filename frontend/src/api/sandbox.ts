/**
 * 对话沙盒 API
 * 获取对话白名单，用于沙盒场景规划
 */

import { apiClient } from './config'

export interface DialogueEntry {
  dialogue_id: string
  chapter: number
  speaker: string
  content: string
  context: string
  tags: string[]
}

export interface DialogueWhitelistResponse {
  dialogues: DialogueEntry[]
  total_count: number
}

export interface CharacterAnchor {
  character_id: string
  character_name: string
  mental_state: string
  verbal_tic: string
  idle_behavior: string
}

export interface GenerateDialogueRequest {
  novel_id: string
  character_id: string
  scene_prompt: string
  mental_state?: string
  verbal_tic?: string
  idle_behavior?: string
}

export interface GenerateDialogueResponse {
  dialogue: string
  character_name: string
}

export const sandboxApi = {
  /** GET /api/v1/novels/{novel_id}/sandbox/dialogue-whitelist */
  getDialogueWhitelist(
    novelId: string,
    chapterNumber?: number,
    speaker?: string
  ): Promise<DialogueWhitelistResponse> {
    return apiClient.get(
      `/api/v1/novels/${novelId}/sandbox/dialogue-whitelist`,
      { params: { ...(chapterNumber ? { chapter_number: chapterNumber } : {}), ...(speaker ? { speaker } : {}) } }
    ) as unknown as Promise<DialogueWhitelistResponse>
  },

  /** GET /api/v1/novels/{novel_id}/sandbox/character/{character_id}/anchor */
  getCharacterAnchor(novelId: string, characterId: string): Promise<CharacterAnchor> {
    return apiClient.get(`/api/v1/novels/${novelId}/sandbox/character/${characterId}/anchor`) as unknown as Promise<CharacterAnchor>
  },

  /** PATCH /api/v1/novels/{novel_id}/sandbox/character/{character_id}/anchor */
  patchCharacterAnchor(
    novelId: string,
    characterId: string,
    body: { mental_state: string; verbal_tic: string; idle_behavior: string }
  ): Promise<CharacterAnchor> {
    return apiClient.patch(
      `/api/v1/novels/${novelId}/sandbox/character/${characterId}/anchor`,
      body
    ) as unknown as Promise<CharacterAnchor>
  },

  /** POST /api/v1/novels/sandbox/generate-dialogue */
  generateDialogue(request: GenerateDialogueRequest): Promise<GenerateDialogueResponse> {
    return apiClient.post('/api/v1/novels/sandbox/generate-dialogue', request) as unknown as Promise<GenerateDialogueResponse>
  },
}
