/**
 * 监控大盘 API
 * 提供张力曲线、人声漂移、伏笔统计等监控数据
 */

import type { AxiosRequestConfig } from 'axios'

import { apiClient } from './config'

export interface TensionPoint {
  chapter: number
  tension: number
  title: string
  evaluated?: boolean  // 是否已完成真实评估
}

export interface TensionCurveStats {
  avg_tension: number       // 平均张力（0-10）
  max_tension: number       // 最高张力
  min_tension: number       // 最低张力
  variance: number          // 张力方差（衡量起伏程度）
  is_flat: boolean          // 曲线是否过于平缓
  evaluated_count: number   // 已评估章节数
  unevaluated_count: number // 未评估章节数
  consecutive_low: number   // 连续低张力章节数
}

export interface TensionCurveResponse {
  novel_id: string
  points: TensionPoint[]
  stats: TensionCurveStats | null
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
  getTensionCurve(
    novelId: string,
    config?: AxiosRequestConfig,
  ): Promise<TensionCurveResponse> {
    return apiClient.get(
      `/novels/${novelId}/monitor/tension-curve`,
      config,
    ) as unknown as Promise<TensionCurveResponse>
  },

  /** GET /api/v1/novels/{novel_id}/monitor/voice-drift */
  getVoiceDrift(novelId: string): Promise<VoiceDriftResponse[]> {
    return apiClient.get(`/novels/${novelId}/monitor/voice-drift`) as unknown as Promise<VoiceDriftResponse[]>
  },

  /** GET /api/v1/novels/{novel_id}/monitor/foreshadow-stats */
  getForeshadowStats(novelId: string): Promise<ForeshadowStatsResponse> {
    return apiClient.get(`/novels/${novelId}/monitor/foreshadow-stats`) as unknown as Promise<ForeshadowStatsResponse>
  },
}
