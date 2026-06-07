/**
 * 监控大盘 API
 */

import type { AxiosRequestConfig } from 'axios'

import { apiClient } from './config'
import { apiRoutes } from './endpoints'
import { fetchJson } from './http'

export interface TensionPoint {
  chapter: number
  tension: number
  title: string
  evaluated?: boolean
}

export interface TensionCurveStats {
  avg_tension: number
  max_tension: number
  min_tension: number
  variance: number
  is_flat: boolean
  evaluated_count: number
  unevaluated_count: number
  consecutive_low: number
}

export interface TensionCurveResponse {
  novel_id: string
  points: TensionPoint[]
  stats: TensionCurveStats | null
}

export interface VoiceDriftApiItem {
  drift_score?: number
  status?: string
  [key: string]: unknown
}

export const monitorApi = {
  getTensionCurve(novelId: string, config?: AxiosRequestConfig): Promise<TensionCurveResponse> {
    return apiClient.get(
      apiRoutes.monitor.tensionCurve(novelId),
      config,
    ) as unknown as Promise<TensionCurveResponse>
  },

  getVoiceDrift(novelId: string): Promise<VoiceDriftApiItem[]> {
    return fetchJson<VoiceDriftApiItem[]>(apiRoutes.monitor.voiceDrift(novelId))
  },
}
