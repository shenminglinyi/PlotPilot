import { apiClient } from './config'

export interface StyleScoreItem {
  chapter_number: number
  similarity_score: number
  adjective_density: number
  avg_sentence_length: number
  sentence_count: number
  computed_at: string
}

export interface DriftReportResponse {
  novel_id: string
  scores: StyleScoreItem[]
  drift_alert: boolean
  alert_threshold: number
  alert_consecutive: number
}

export interface ScoreChapterResponse {
  chapter_number: number
  similarity_score: number | null
  drift_alert: boolean
}

export const voiceDriftApi = {
  /** 计算章节文风评分 */
  scoreChapter(
    novelId: string,
    payload: { chapter_number: number; content: string; pov_character_id?: string }
  ): Promise<ScoreChapterResponse> {
    return apiClient.post(
      `/api/v1/novels/${novelId}/voice/drift/score`,
      payload
    ) as unknown as Promise<ScoreChapterResponse>
  },

  /** 获取漂移报告 */
  getDriftReport(novelId: string): Promise<DriftReportResponse> {
    return apiClient.get(
      `/api/v1/novels/${novelId}/voice/drift`
    ) as unknown as Promise<DriftReportResponse>
  },
}
