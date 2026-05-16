import { h } from 'vue'
import type { AxiosError } from 'axios'
import { NButton, NCollapse, NCollapseItem, NSpace } from 'naive-ui'
import { createDiscreteApi } from 'naive-ui'

import type { FeedbackIncidentPayload } from './feedbackIncident'
import {
  FEEDBACK_NOTIFY_PREVIEW_CHARS,
  augmentIncidentWithAxios,
  buildDiagnosticBundle,
  buildIncidentFromUnknown,
  copyTextFallback,
  downloadText,
  inferRoutePath,
  markErrorFeedbackEmitted,
  newIncidentId,
  preferDownloadForDetail,
  serializeDiagnosticBundle,
  serializeIncidentsPlain,
  wasErrorFeedbackEmitted,
} from './feedbackIncident'

const RING_CAP = 30
const dedupeHits = new Map<string, number>()
const DEDUPE_MS = 4500

/** 同一时间窗内多起 Axios 异常合并为一则通知（避免并行 502 刷屏） */
const AXIOS_AGG_SILENCE_MS = 520

const ringBuffer: FeedbackIncidentPayload[] = []

/** @internal 供测试或可观测性挂接（勿在业务中依赖） */
let _axiosAggBuffer: FeedbackIncidentPayload[] = []
let _axiosAggTimer: ReturnType<typeof setTimeout> | null = null

const { notification } = createDiscreteApi(['notification'], {
  notificationProviderProps: {
    placement: 'bottom-right',
  },
})

function pushRing(inc: FeedbackIncidentPayload) {
  ringBuffer.unshift(inc)
  if (ringBuffer.length > RING_CAP) ringBuffer.pop()
}

function shouldSkipNotify(key: string): boolean {
  const now = Date.now()
  const last = dedupeHits.get(key)
  if (last != null && now - last < DEDUPE_MS) return true
  dedupeHits.set(key, now)
  return false
}

function incidentDedupeKey(inc: FeedbackIncidentPayload): string {
  const ax = inc.meta.axios
  return `${inc.source}:${inc.summary.slice(0, 160)}:${ax?.method ?? ''}:${String(ax?.status ?? '')}:${ax?.url ?? ''}:${inc.detail.slice(0, 96)}`
}

function aggregatedDedupeKey(batch: FeedbackIncidentPayload[]): string {
  const ax = batch[0]?.meta?.axios
  const urls = [...new Set(batch.map(b => `${b.meta.axios?.method ?? ''}:${b.meta.axios?.url ?? ''}`))].sort()
  const st = [...new Set(batch.map(b => b.meta.axios?.status).filter((x): x is number => typeof x === 'number'))].join(',')
  return `axios:aggregate:${batch.length}:${st}:${urls.join('|').slice(0, 240)}`
}

function axiosRouteShort(p: FeedbackIncidentPayload): string {
  const m = (p.meta.axios?.method ?? 'GET').toUpperCase()
  let pathStr = String(p.meta.axios?.url ?? '')
  try {
    if (pathStr.startsWith('http')) {
      const u = new URL(pathStr)
      pathStr = `${u.pathname}${u.search}`
    }
  } catch {
    /* ignore */
  }
  const shortened = pathStr.length > 76 ? `${pathStr.slice(0, 74)}…` : pathStr
  return `${m} ${shortened}`.trim()
}

function collapseDetailSnippet(p: FeedbackIncidentPayload): string {
  let t = [...p.detail].length > 900 ? [...p.detail].slice(0, 897).join('') + '…' : p.detail
  if ((p.meta.axios?.response_body_preview ?? '').trim()) {
    t += `\n\n响应节选：${p.meta.axios?.response_body_preview}`
  }
  return t.trim()
}

function mergeAxiosBatch(batch: FeedbackIncidentPayload[]): FeedbackIncidentPayload {
  const statuses = [
    ...new Set(batch.map(b => b.meta.axios?.status).filter((x): x is number => typeof x === 'number')),
  ]
  const stLabel = statuses.length === 1 ? String(statuses[0]) : (statuses.length ? statuses.sort().join(' / ') : '?')
  const detail = batch
    .map((b, i) => {
      const lbl = axiosRouteShort(b)
      return `── #${i + 1} ${lbl} ──\n${b.detail}`
    })
    .join('\n\n')
  const lastGoodAxios = [...batch].reverse().find(b => b.meta.axios)?.meta.axios
  const firstMeta = batch[0].meta ?? {}
  return {
    id: newIncidentId(),
    occurred_at: new Date().toISOString(),
    source: 'axios',
    severity: 'error',
    summary: `${batch.length} 个并行请求失败（HTTP ${stLabel}）`,
    detail,
    meta: {
      session_id: batch[0]?.meta.session_id,
      route_path: firstMeta.route_path ?? inferRoutePath(),
      axios: lastGoodAxios
        ? { ...lastGoodAxios }
        : { method: '?', url: `(共 ${batch.length} 笔)` },
      extra: {
        aggregated: true,
        aggregated_from: batch.length,
        statuses,
      },
    },
  }
}

function scheduleAxiosAggregateFlush(): void {
  if (_axiosAggTimer != null) {
    window.clearTimeout(_axiosAggTimer)
  }
  _axiosAggTimer = window.setTimeout(flushAxiosAggregateBuffer, AXIOS_AGG_SILENCE_MS)
}

function enqueueAxiosAggregation(payload: FeedbackIncidentPayload): void {
  pushRing(payload)
  _axiosAggBuffer.push(payload)
  scheduleAxiosAggregateFlush()
}

function flushAxiosAggregateBuffer(): void {
  _axiosAggTimer = null
  const batch = _axiosAggBuffer.splice(0)
  if (batch.length === 0) return

  if (batch.length === 1) {
    const p = batch[0]
    const key = incidentDedupeKey(p)
    if (shouldSkipNotify(key)) return
    showFeedbackNotification(p)
    return
  }

  const merged = mergeAxiosBatch(batch)
  const key = aggregatedDedupeKey(batch)
  if (shouldSkipNotify(key)) return
  showAggregatedFeedbackNotification(batch, merged)
}

export function peekRecentFeedbackIncidents(): readonly FeedbackIncidentPayload[] {
  return ringBuffer.slice()
}

export function exportRecentFeedbackBundle(): void {
  void (async () => {
    const mod = await import('../api/feedbackDiagnostic')
    const appendix = await mod.fetchBackendFeedbackAppendix({
      max_lines: 900,
      ring_limit: 300,
    })
    const bundle = buildDiagnosticBundle(ringBuffer.slice(), appendix)
    downloadText(
      `plotpilot-diagnostic-${new Date().toISOString().replace(/:/g, '-')}.json`,
      serializeDiagnosticBundle(bundle),
      'application/json;charset=utf-8',
    )
  })()
}

async function dispatchPrimary(payload: FeedbackIncidentPayload) {
  const { fetchBackendFeedbackAppendix } = await import('../api/feedbackDiagnostic')
  const appendix = await fetchBackendFeedbackAppendix({ max_lines: 700, ring_limit: 200 })
  const fullPlain = serializeIncidentsPlain([payload], appendix)
  const bundleStr = serializeDiagnosticBundle(buildDiagnosticBundle([payload], appendix))
  const preferDl = preferDownloadForDetail(payload.detail) || preferDownloadForDetail(fullPlain)

  if (preferDl) {
    const fn = `plotpilot-incident-${payload.occurred_at.replace(/:/g, '-').slice(0, 19)}.txt`
    downloadText(fn, `${fullPlain}\n\n===== JSON =====\n${bundleStr}`)
    await copyTextFallback(payload.summary)
    notification.success({
      title: '已下载完整日志',
      content: '若浏览器允许，摘要已写入剪贴板，便于粘贴工单标题。',
      duration: 3800,
    })
  } else {
    const ok = await copyTextFallback(`${fullPlain}\n\n===== JSON =====\n${bundleStr}`)
    notification.success({
      title: ok ? '复制成功' : '复制失败',
      content: ok ? '诊断文本（含后端附录）已在剪贴板。' : '请改用下载文件。',
      duration: 2600,
    })
  }
}

async function dispatchCopyStructured(payload: FeedbackIncidentPayload) {
  const { fetchBackendFeedbackAppendix } = await import('../api/feedbackDiagnostic')
  const appendix = await fetchBackendFeedbackAppendix({ max_lines: 700, ring_limit: 200 })
  const bundleStr = serializeDiagnosticBundle(buildDiagnosticBundle([payload], appendix))
  const ok = await copyTextFallback(bundleStr)
  notification.success({
    title: ok ? 'JSON 报告已复制' : '复制失败',
    duration: 2000,
  })
}

/** 单列失败：简明通知 */
function showFeedbackNotification(payload: FeedbackIncidentPayload) {
  const clipped =
    [...payload.detail].length > FEEDBACK_NOTIFY_PREVIEW_CHARS
      ? [...payload.detail].slice(0, FEEDBACK_NOTIFY_PREVIEW_CHARS).join('') + '…'
      : payload.detail
  const preferDl = preferDownloadForDetail(payload.detail)

  notification.create({
    title: payload.summary,
    description: clipped.trim() ? clipped : '(无更多信息)',
    type: payload.severity === 'warning' ? 'warning' : 'error',
    duration: preferDl ? 0 : 7600,
    closable: true,
    meta: () =>
      h(
        NSpace,
        {
          vertical: true,
          size: 'small',
          style: 'margin-top: 10px; width:min(448px,calc(100vw - 32px));',
        },
        {
          default: () =>
            [
              footnotePreferMedia(preferDl),
              actionsRow(payload, preferDl),
            ].flat(),
        },
      ),
  })
}

/** 并行 / 多起失败：单卡片 + 可折叠明细（类似常见网关错误聚合页） */
function showAggregatedFeedbackNotification(
  batch: FeedbackIncidentPayload[],
  merged: FeedbackIncidentPayload,
) {
  const preferDl = preferDownloadForDetail(merged.detail)
  const codes = [...new Set(batch.map(b => String(b.meta.axios?.status ?? '?')))].join(', ')

  const headLine = batch.slice(0, 2).map(axiosRouteShort).join(' · ')
  const previewLine =
    batch.length <= 2 ? headLine : `${headLine} · …（共 ${batch.length} 条，点击下方展开明细）`

  notification.create({
    title: merged.summary,
    description: () =>
      h('div', { style: 'line-height: 1.5;' }, [
        h(
          'div',
          { style: 'font-size:13px;color:var(--n-title-text-color,inherit);opacity:0.88;margin-bottom:6px;' },
          '常为反向代理不可用、后端进程重启或未监听端口。可先确认本地 API 是否正常，再按需导出诊断。',
        ),
        h(
          'div',
          {
            style:
              'font-size:11px;font-family:ui-monospace,Menlo,Consolas,monospace;opacity:.75;word-break:break-all;',
          },
          previewLine,
        ),
        NTagMuted(codes),
      ]),
    type: 'error',
    duration: 0,
    closable: true,
    meta: () =>
      h(
        NSpace,
        {
          vertical: true,
          size: 'small',
          style: 'margin-top: 8px; width:min(472px,calc(100vw - 32px));',
        },
        {
          default: () =>
            [
              h(
                NCollapse,
                {
                  bordered: false,
                  displayDirective: 'show',
                  defaultExpandedNames: null,
                  style:
                    'background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.22);border-radius:10px;padding:6px 4px;',
                },
                {
                  default: () =>
                    batch.map((p, i) =>
                      h(
                        NCollapseItem,
                        { title: axiosRouteShort(p), name: String(i) },
                        {
                          default: () =>
                            h(
                              'pre',
                              {
                                style:
                                  'margin:8px 0 2px;font-size:11px;line-height:1.45;white-space:pre-wrap;' +
                                  'word-break:break-word;max-height:200px;overflow:auto;font-family:ui-monospace,Menlo,Consolas,monospace;' +
                                  'background:rgba(0,0,0,0.04);padding:10px;border-radius:8px;',
                              },
                              collapseDetailSnippet(p),
                            ),
                        },
                      ),
                    ),
                },
              ),
              footnotePreferMedia(preferDl),
              actionsRow(merged, preferDl),
            ].flat(),
        },
      ),
  })
}

function footnotePreferMedia(preferDl: boolean) {
  return h(
    'div',
    { style: 'font-size:11px;line-height:1.45;color:var(--n-text-color,inherit);opacity:0.55;' },
    preferDl ? '条目较多时建议导出文件；短错误可直接复制全文。导出含后端附录。' : '可直接复制全文；结构化数据用「复制 JSON」。',
  )
}

function actionsRow(payload: FeedbackIncidentPayload, preferDl: boolean) {
  return h(
    NSpace,
    {},
    {
      default: () => [
        h(
          NButton,
          { type: 'primary', size: 'small', onClick: () => dispatchPrimary(payload) },
          { default: () => (preferDl ? '下载诊断包' : '复制诊断') },
        ),
        h(
          NButton,
          { size: 'small', tertiary: true, onClick: () => dispatchCopyStructured(payload) },
          { default: () => '复制 JSON' },
        ),
      ],
    },
  )
}

/** 小号状态标签样式（仅用 h） */
function NTagMuted(codes: string) {
  return h(
    'span',
    {
      style:
        'display:inline-block;margin-top:8px;font-size:10px;font-weight:600;letter-spacing:0.04em;' +
        'padding:3px 8px;border-radius:999px;' +
        'background:rgba(239,68,68,0.12);color:#b91c1c;',
    },
    `HTTP · ${codes}`,
  )
}

/**
 * Vue / Promise / 手动：逐项通知。
 * Axios：进入短窗聚合，避免并行失败堆满右侧。
 */
export function emitFeedbackIncident(payload: FeedbackIncidentPayload): void {
  if (payload.source === 'axios') {
    enqueueAxiosAggregation(payload)
    return
  }
  pushRing(payload)
  const key = incidentDedupeKey(payload)
  if (shouldSkipNotify(key)) return
  showFeedbackNotification(payload)
}

export function emitManualIncident(summary: string, err?: unknown, extra?: Record<string, unknown>): void {
  emitFeedbackIncident(
    buildIncidentFromUnknown('manual', summary, err ?? summary, {
      meta: { extra: extra ?? {} },
    }),
  )
}

/** Axios：拼装 HTTP 上下文后派发；打标可避免 unhandledrejection 再来一条 */
export function emitAxiosFeedbackIncident(summary: string, err: AxiosError): void {
  const base = buildIncidentFromUnknown('axios', summary, err)
  const full = augmentIncidentWithAxios(base, err)
  markErrorFeedbackEmitted(err)
  enqueueAxiosAggregation(full)
}

export function installUnhandledPromiseCapture(): void {
  if (typeof window === 'undefined') return
  window.addEventListener('unhandledrejection', ev => {
    const reason = (ev as PromiseRejectionEvent).reason
    if (wasErrorFeedbackEmitted(reason)) return

    emitFeedbackIncident(
      buildIncidentFromUnknown('promise', '未处理的 Promise 拒绝', reason ?? '(empty reason)', {
        meta: {
          promise: { reason_type: reason === null ? 'null' : typeof reason },
          extra: {},
        },
      }),
    )
  })
}
