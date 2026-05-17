/**
 * 用户反馈用的「一次性事故快照」（Incident）。
 * 与 Naive/UI 无关，便于测试与离线序列化。
 */

export type FeedbackSource = 'vue' | 'promise' | 'axios' | 'manual' | 'telemetry'

/** 语义化严重程度，仅占位枚举，不参与 UI */
export type FeedbackSeverity = 'error' | 'warning'

export interface FeedbackIncidentPayload {
  /** 唯一键，便于去重与支持「多次相同错误」归档 */
  id: string
  /** ISO 8601 */
  occurred_at: string
  source: FeedbackSource
  severity: FeedbackSeverity
  /** 给用户看的单行摘要（短） */
  summary: string
  /** 可读长文（可为 stack + 拼装 detail） */
  detail: string
  /** 机器可读上下文 */
  meta: FeedbackIncidentMeta
}

export interface FeedbackIncidentMeta {
  session_id?: string
  route_path?: string
  api_base_url?: string
  axios?: FeedbackAxiosMeta
  vue?: FeedbackVueMeta
  promise?: FeedbackPromiseMeta
  /** 预留扩展槽 */
  extra?: Record<string, unknown>
}

export interface FeedbackVueMeta {
  component_name?: string
  lifecycle?: string
}

export interface FeedbackPromiseMeta {
  reason_type?: string
}

export interface FeedbackAxiosMeta {
  method?: string
  url?: string
  base_url?: string
  status?: number
  status_text?: string
  response_body_preview?: string
  code?: string
}

/** 简短复制建议阈值（≤ 则用「一键复制全文」更合适） */
export const FEEDBACK_SHORT_COPY_THRESHOLD = 360

/** 通知内正文预览字数 */
export const FEEDBACK_NOTIFY_PREVIEW_CHARS = 120

let _sid: string | null = null

function sessionId(): string {
  if (_sid === null && typeof crypto !== 'undefined' && crypto.randomUUID) {
    _sid = crypto.randomUUID()
  }
  return _sid || `s-${Date.now()}`
}

function isTauri(): boolean {
  if (typeof window === 'undefined') return false
  const w = window as Window & { __TAURI__?: unknown; __TAURI_INTERNALS__?: unknown }
  return !!(w.__TAURI__ || w.__TAURI_INTERNALS__)
}

export function inferRoutePath(): string {
  try {
    return typeof window !== 'undefined' ? window.location.pathname + window.location.search : ''
  } catch {
    return ''
  }
}

export function newIncidentId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `id-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function safeTrim(s: unknown, max: number): string {
  const t = typeof s === 'string' ? s : String(s ?? '')
  if (t.length <= max) return t
  return `${t.slice(0, max)}… (${t.length} chars)`
}

function extractAxiosResponsePreview(data: unknown): string {
  try {
    if (data == null) return ''
    if (typeof data === 'string') return safeTrim(data, 4000)
    return safeTrim(JSON.stringify(data, null, 2), 4000)
  } catch {
    return '[不可序列化的响应体]'
  }
}

export function buildIncidentFromUnknown(
  source: FeedbackSource,
  summary: string,
  err: unknown,
  partial?: Partial<Pick<FeedbackIncidentPayload, 'summary'>> & {
    meta?: Partial<FeedbackIncidentMeta>
    severity?: FeedbackSeverity
    detailOverride?: string
  },
): FeedbackIncidentPayload {
  const severity = partial?.severity ?? 'error'
  const stack =
    err instanceof Error
      ? `${err.stack || err.message}`
      : typeof err === 'string'
        ? err
        : (() => {
            try {
              return JSON.stringify(err, null, 2)
            } catch {
              return String(err)
            }
          })()
  const detail = partial?.detailOverride ?? stack
  return {
    id: newIncidentId(),
    occurred_at: new Date().toISOString(),
    source,
    severity,
    summary: partial?.summary ?? summary,
    detail,
    meta: {
      session_id: sessionId(),
      route_path: inferRoutePath(),
      extra: {},
      ...(partial?.meta ?? {}),
    },
  }
}

/** 服务端日志快照附录（`/api/v1/system/feedback-log-snapshot`） */
export interface BackendFeedbackAppendix {
  generated_at?: string
  backend_release?: string
  backend_build_id?: string
  backend_uptime_seconds?: number | null
  log_file_env?: string
  log_file_resolved?: string
  log_file_missing?: boolean
  log_truncated?: boolean
  log_tail_line_count?: number
  log_tail_lines?: string[]
  memory_ring_recent?: Array<Record<string, unknown>>
  /** 前端拉取失败 */
  fetch_error?: string
}

/** 前端上报包：用于复制 / 下载，结构稳定便于后端工单系统对接 */
export function buildDiagnosticBundle(
  incidents: FeedbackIncidentPayload[],
  backendAppendix?: BackendFeedbackAppendix | null,
) {
  return {
    kind: 'plotpilot_frontend_diagnostic_bundle',
    bundle_version: 2,
    generated_at: new Date().toISOString(),
    app: {
      name: 'PlotPilot',
      frontend_version:
        typeof import.meta !== 'undefined' && import.meta.env
          ? String(import.meta.env.VITE_APP_VERSION || import.meta.env.MODE || 'dev')
          : 'dev',
    },
    environment: {
      user_agent:
        typeof navigator !== 'undefined' && typeof navigator.userAgent === 'string' ? navigator.userAgent : '',
      is_tauri: isTauri(),
      language:
        typeof navigator !== 'undefined' && typeof navigator.language === 'string' ? navigator.language : '',
    },
    incidents,
    ...(backendAppendix && Object.keys(backendAppendix).length > 0 ? { backend_appendix: backendAppendix } : {}),
  }
}

export function serializeDiagnosticBundle(bundle: ReturnType<typeof buildDiagnosticBundle>): string {
  return JSON.stringify(bundle, null, 2)
}

/** Axios 等在全局链路打标：避免 interceptor + unhandledrejection 双提示 */
export const FEEDBACK_EMITTED_SYM = Symbol.for('plotpilot_feedback_emitted')

export function markErrorFeedbackEmitted(reason: unknown): void {
  if (reason !== null && typeof reason === 'object') {
    try {
      Object.defineProperty(reason, FEEDBACK_EMITTED_SYM, {
        value: true,
        enumerable: false,
        configurable: true,
      })
    } catch {
      ;(reason as Record<symbol | string, unknown>)[FEEDBACK_EMITTED_SYM as unknown as string] = true
    }
  }
}

export function wasErrorFeedbackEmitted(reason: unknown): boolean {
  if (reason !== null && typeof reason === 'object') {
    return !!(reason as { [FEEDBACK_EMITTED_SYM]?: boolean })[FEEDBACK_EMITTED_SYM]
  }
  return false
}

function appendBackendAppendixPlain(lines: string[], be?: BackendFeedbackAppendix | null) {
  if (!be) return
  lines.push('## 后端附录（同日志文件尾部 / 内存环）')
  lines.push('')
  if (be.fetch_error) {
    lines.push(`拉取后端快照失败：${be.fetch_error}`)
    lines.push('')
    return
  }
  lines.push(`生成(UTC)：${be.generated_at ?? ''}`)
  lines.push(`版本：${be.backend_release ?? ''} · 构建 ${be.backend_build_id ?? ''} · uptime_s ${be.backend_uptime_seconds ?? ''}`)
  lines.push(`日志配置路径：${be.log_file_env ?? ''}`)
  lines.push(`解析路径：${be.log_file_resolved ?? ''}`)
  lines.push(`文件缺失：${Boolean(be.log_file_missing)} · 内容截断标记：${Boolean(be.log_truncated)} · 行数：${be.log_tail_line_count ?? be.log_tail_lines?.length ?? 0}`)
  lines.push('')
  lines.push('### LOG 尾部')
  lines.push('')
  for (const row of be.log_tail_lines ?? []) {
    lines.push(row)
  }
  lines.push('')
  const ring = be.memory_ring_recent ?? []
  if (ring.length > 0) {
    lines.push('### API 内存环（近期）')
    lines.push('')
    for (const r of ring) {
      lines.push(JSON.stringify(r))
    }
    lines.push('')
  }
}

/** 可读性更好的纯文本，适合直接贴工单 */
export function serializeIncidentsPlain(
  incidents: FeedbackIncidentPayload[],
  backendAppendix?: BackendFeedbackAppendix | null,
): string {
  const lines: string[] = []
  lines.push('# PlotPilot 诊断（前端事故快照 + 后端日志附录）')
  lines.push(`生成时间：${bundleNow()}`)
  lines.push(`会话：${incidents[0]?.meta.session_id ?? sessionId()}`)
  lines.push('')

  for (const inc of incidents) {
    lines.push(`---`)
    lines.push(`[${inc.source}] ${inc.summary}`)
    lines.push(`时间：${inc.occurred_at}`)
    lines.push(`路由：${inc.meta.route_path ?? ''}`)
    if (inc.meta.axios) {
      const ax = inc.meta.axios
      lines.push(`HTTP ${ax.method ?? '?'} ${ax.url ?? '?'} → ${String(ax.status ?? '?')} ${ax.status_text ?? ''}`)
      if (ax.response_body_preview) {
        lines.push('响应节选：')
        lines.push(ax.response_body_preview)
      }
    }
    lines.push('')
    lines.push('详细：')
    lines.push(inc.detail)
    lines.push('')
  }
  appendBackendAppendixPlain(lines, backendAppendix)
  return lines.join('\n').trimEnd() + '\n'
}

function bundleNow(): string {
  return new Date().toISOString()
}

export function preferDownloadForDetail(detail: string): boolean {
  return [...detail].length > FEEDBACK_SHORT_COPY_THRESHOLD
}

export async function copyTextFallback(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.left = '-9999px'
      document.body.appendChild(ta)
      ta.focus()
      ta.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(ta)
      return ok
    } catch {
      return false
    }
  }
}

export function downloadText(filename: string, text: string, mime = 'text/plain;charset=utf-8'): void {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/** 从 Axios 错误拼装 meta（尽量不依赖 Axios 类型，运行时 duck-typing） */
export function augmentIncidentWithAxios(
  base: FeedbackIncidentPayload,
  axErr: {
    message?: string
    code?: string
    config?: { baseURL?: string; url?: string; method?: string }
    response?: { status?: number; statusText?: string; data?: unknown }
  },
): FeedbackIncidentPayload {
  const url = typeof axErr.config?.url === 'string' ? axErr.config.url : ''
  const method = typeof axErr.config?.method === 'string' ? axErr.config.method.toUpperCase() : undefined
  const status = typeof axErr.response?.status === 'number' ? axErr.response.status : undefined
  const preview = extractAxiosResponsePreview(axErr.response?.data)
  const summary =
    typeof status === 'number'
      ? `请求失败（HTTP ${status}）`
      : axErr.code === 'ECONNABORTED'
        ? '请求超时'
        : '请求失败'

  return {
    ...base,
    summary: base.summary || summary,
    detail: `${base.detail}\n\n--- Axios ---\nmessage: ${axErr.message ?? ''}\ncode: ${axErr.code ?? ''}\n${method ?? ''} ${url}\n`,
    meta: {
      ...base.meta,
      api_base_url:
        typeof axErr.config?.baseURL === 'string' && axErr.config.baseURL.trim()
          ? axErr.config.baseURL
          : base.meta.api_base_url,
      axios: {
        method,
        url,
        base_url: typeof axErr.config?.baseURL === 'string' ? axErr.config.baseURL : undefined,
        status,
        status_text:
          typeof axErr.response?.statusText === 'string' ? axErr.response.statusText : undefined,
        response_body_preview: preview || undefined,
        code: axErr.code,
      },
    },
  }
}
