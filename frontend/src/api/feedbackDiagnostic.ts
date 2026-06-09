import { apiAxios } from './config'
import { runtimePerformance } from '../config/performance'
import type { BackendFeedbackAppendix } from '../support/feedbackIncident'

export type { BackendFeedbackAppendix } from '../support/feedbackIncident'

/**
 * 拉取后端日志尾部 + API 内存环（仅当请求来自本机时可用；否则会失败并附带 fetch_error）。
 * 采用已配置 baseURL / 拦截器的 apiAxios：成功时为解包后的 body。
 */
export async function fetchBackendFeedbackAppendix(
  params: { max_lines?: number; ring_limit?: number } = {},
): Promise<BackendFeedbackAppendix> {
  const max_lines = params.max_lines ?? 600
  const ring_limit = params.ring_limit ?? 200
  try {
    const body = await apiAxios.get<BackendFeedbackAppendix>('/system/feedback-log-snapshot', {
      params: { max_lines, ring_limit },
      timeout: runtimePerformance.network.mediumTaskTimeoutMs,
      validateStatus: status => status === 200,
    })
    return body as BackendFeedbackAppendix
  } catch (e: unknown) {
    const ax = e as { response?: { status?: number; data?: unknown }; message?: string }
    const detail =
      typeof ax.response?.data === 'object' && ax.response.data !== null && 'detail' in ax.response.data
        ? String((ax.response.data as { detail?: unknown }).detail)
        : ax.response?.data != null
          ? JSON.stringify(ax.response.data)
          : ''
    const st = ax.response?.status
    let msg = typeof ax.message === 'string' ? ax.message : String(e ?? 'unknown')
    if (st === 403) {
      msg +=
        '；后端快照仅限本机访问。若你从局域网其它机器打开前端，需向运维索要服务器端的 plotpilot.log。'
    } else if (detail) {
      msg += `；${detail}`
    }
    return { fetch_error: msg.trim() }
  }
}
