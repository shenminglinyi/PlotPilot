/**
 * 通用响应类型 / Generic Response Types
 */

export interface SuccessResponse<T> {
  success: true
  data: T
  message?: string
}

export interface ErrorResponse {
  success: false
  message: string
  code: string
  details?: unknown
}

export type ApiResponse<T> = SuccessResponse<T> | ErrorResponse

export interface PaginatedResponse<T> {
  success: true
  data: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
  message?: string
}

export interface SimpleResponse {
  ok: boolean
}

export interface SlugResponse {
  ok: boolean
  slug: string
}

export interface MessageIdResponse {
  ok: boolean
  id: string
}

// ── Job 状态 ──────────────────────────────────────────────────

export type JobKind = 'plan' | 'write' | 'run'
export type JobStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled'

export interface JobCreateResponse {
  ok: boolean
  job_id: string
}

export interface JobStatusResponse {
  job_id: string
  kind: JobKind
  slug: string
  status: JobStatus
  phase: string
  message: string
  error?: string
  started?: string
  finished?: string
  done: boolean
  ok: boolean
}

// ── 日志流 ────────────────────────────────────────────────────

export interface LogEntry {
  timestamp: string
  level: string
  logger: string
  message: string
  [key: string]: unknown
}
