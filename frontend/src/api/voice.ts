/**
 * 文风金库 API
 * 后端路由：/api/v1/novels/{novel_id}/voice/...
 */
import { apiClient } from './config'

export interface VoiceSamplePayload {
  ai_original: string
  author_refined: string
  chapter_number: number
  scene_type?: string
}

export interface VoiceSampleResponse {
  sample_id: string
}

export interface VoiceFingerprintDTO {
  adjective_density: number
  avg_sentence_length: number
  sentence_count: number
  sample_count: number
  last_updated: string
}

export const voiceApi = {
  /** POST /api/v1/novels/{novel_id}/voice/samples — 提交文风样本对 */
  createSample: (novelId: string, payload: VoiceSamplePayload) =>
    apiClient.post<VoiceSampleResponse>(
      `/api/v1/novels/${novelId}/voice/samples`,
      payload
    ) as unknown as Promise<VoiceSampleResponse>,

  /** GET /api/v1/novels/{novel_id}/voice/fingerprint — 查看文风指纹统计 */
  getFingerprint: (novelId: string, povCharacterId?: string) =>
    apiClient.get<VoiceFingerprintDTO>(
      `/api/v1/novels/${novelId}/voice/fingerprint`,
      { params: povCharacterId ? { pov_character_id: povCharacterId } : {} }
    ) as unknown as Promise<VoiceFingerprintDTO>,
}
