/**
 * 监控大盘 API
 * 提供张力曲线、人声漂移、伏笔统计等监控数据
 */

import { apiClient } from './config'

export interface TensionPoint {
  chapter: number
  tension: number
  title: string
}

export interface TensionCurveResponse {
  novel_id: string
  points: TensionPoint[]
}

export interface VoiceDriftResponse {
  character_id: string
  character_name: string
  drift_score: number
  status: 'normal' | 'warning' | 'critical'
  sample_count: number
}

export interface ForeshadowStatsResponse {
  total_planted: number
  total_resolved: number
  pending: number
  forgotten_risk: number
  resolution_rate: number
}

export const monitorApi = {
  /** GET /api/v1/novels/{novel_id}/monitor/tension-curve */
  getTensionCurve(novelId: string): Promise<TensionCurveResponse> {
    return apiClient.get(`/api/v1/novels/${novelId}/monitor/tension-curve`) as unknown as Promise<TensionCurveResponse>
  },

  /** GET /api/v1/novels/{novel_id}/monitor/voice-drift */
  getVoiceDrift(novelId: string): Promise<VoiceDriftResponse[]> {
    return apiClient.get(`/api/v1/novels/${novelId}/monitor/voice-drift`) as unknown as Promise<VoiceDriftResponse[]>
  },

  /** GET /api/v1/novels/{novel_id}/monitor/foreshadow-stats */
  getForeshadowStats(novelId: string): Promise<ForeshadowStatsResponse> {
    return apiClient.get(`/api/v1/novels/${novelId}/monitor/foreshadow-stats`) as unknown as Promise<ForeshadowStatsResponse>
  },
}
