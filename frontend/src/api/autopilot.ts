import { apiRoutes } from './endpoints'
import { fetchJson, fetchOk, fetchUrl, HttpError, type FetchJsonOptions } from './http'

export type AutopilotStatus = Record<string, any> & {
  active_pipeline_step?: string
  active_pipeline_run_id?: string
  last_stable_stage?: string
  autopilot_run_epoch?: number
  autopilot_recovery_reason?: string
}

export interface AutopilotStartRequest {
  max_auto_chapters: number
  target_chapters: number
  target_words_per_chapter: number
}

export interface AutopilotResumeResponse {
  current_stage?: string
  message?: string
  [key: string]: unknown
}

export interface AutopilotErrorRecord {
  message: string
  timestamp: string
  context?: string
}

export interface AutopilotCircuitBreakerData {
  status: 'closed' | 'open' | 'half_open'
  error_count: number
  max_errors: number
  last_error?: AutopilotErrorRecord
  error_history?: AutopilotErrorRecord[]
}

export const autopilotApi = {
  getStatus(novelId: string, options?: FetchJsonOptions): Promise<AutopilotStatus> {
    return fetchJson<AutopilotStatus>(apiRoutes.autopilot.status(novelId), options)
  },

  start(novelId: string, data: AutopilotStartRequest): Promise<Response> {
    return fetchOk(apiRoutes.autopilot.start(novelId), {
      method: 'POST',
      body: data,
    })
  },

  stop(novelId: string, timeoutMs?: number): Promise<Response> {
    return fetchOk(apiRoutes.autopilot.stop(novelId), {
      method: 'POST',
      timeoutMs,
    })
  },

  resume(novelId: string): Promise<AutopilotResumeResponse> {
    return fetchJson<AutopilotResumeResponse>(apiRoutes.autopilot.resume(novelId), {
      method: 'POST',
    })
  },

  getCircuitBreaker(novelId: string): Promise<AutopilotCircuitBreakerData> {
    return fetchJson<AutopilotCircuitBreakerData>(apiRoutes.autopilot.circuitBreaker(novelId))
  },

  resetCircuitBreaker(novelId: string): Promise<Response> {
    return fetchOk(apiRoutes.autopilot.circuitBreakerReset(novelId), {
      method: 'POST',
    })
  },

  streamUrl(novelId: string, afterSeq?: number): string {
    const params = afterSeq && afterSeq > 0 ? { after_seq: afterSeq } : undefined
    return fetchUrl(apiRoutes.autopilot.stream(novelId, params))
  },

  logStreamUrl(novelId: string): string {
    return fetchUrl(apiRoutes.autopilot.logStream(novelId))
  },
}

export function isAutopilotNotFoundError(error: unknown): boolean {
  return error instanceof HttpError && error.status === 404
}

export function isAutopilotHttpError(error: unknown): boolean {
  return error instanceof HttpError
}

export function getAutopilotHttpStatus(error: unknown): number | null {
  return error instanceof HttpError ? error.status : null
}

export function getAutopilotErrorDetail(error: unknown): string {
  if (!(error instanceof HttpError)) return ''
  const body = error.body
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail?: unknown }).detail
    return typeof detail === 'string' ? detail : ''
  }
  return ''
}
