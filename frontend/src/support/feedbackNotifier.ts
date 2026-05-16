import { h } from 'vue'
import type { AxiosError } from 'axios'
import { NButton, NSpace } from 'naive-ui'
import { createDiscreteApi } from 'naive-ui'

import type { FeedbackIncidentPayload } from './feedbackIncident'
import {
  FEEDBACK_NOTIFY_PREVIEW_CHARS,
  augmentIncidentWithAxios,
  buildDiagnosticBundle,
  buildIncidentFromUnknown,
  copyTextFallback,
  downloadText,
  markErrorFeedbackEmitted,
  preferDownloadForDetail,
  serializeDiagnosticBundle,
  serializeIncidentsPlain,
  wasErrorFeedbackEmitted,
} from './feedbackIncident'

const RING_CAP = 30
const dedupeHits = new Map<string, number>()
const DEDUPE_MS = 4000

const ringBuffer: FeedbackIncidentPayload[] = []

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

export function peekRecentFeedbackIncidents(): readonly FeedbackIncidentPayload[] {
  return ringBuffer.slice()
}

export function exportRecentFeedbackBundle(): void {
  const bundle = buildDiagnosticBundle(ringBuffer.slice())
  downloadText(
    `plotpilot-diagnostic-${new Date().toISOString().replace(/:/g, '-')}.json`,
    serializeDiagnosticBundle(bundle),
    'application/json;charset=utf-8',
  )
}

async function dispatchPrimary(payload: FeedbackIncidentPayload) {
  const fullPlain = serializeIncidentsPlain([payload])
  const bundleStr = serializeDiagnosticBundle(buildDiagnosticBundle([payload]))
  const preferDl = preferDownloadForDetail(payload.detail) || preferDownloadForDetail(fullPlain)

  if (preferDl) {
    const fn = `plotpilot-incident-${payload.occurred_at.replace(/:/g, '-').slice(0, 19)}.txt`
    downloadText(fn, `${fullPlain}\n\n===== JSON =====\n${bundleStr}`)
    await copyTextFallback(payload.summary)
    notification.success({
      title: '已下载完整日志',
      content: '摘要已尽力复制到剪贴板（部分浏览器受限时可忽略此项）。请将下载的 .txt 作为附件。',
      duration: 4200,
    })
  } else {
    const ok = await copyTextFallback(`${fullPlain}\n\n===== JSON =====\n${bundleStr}`)
    notification.success({
      title: ok ? '复制成功' : '复制失败',
      content: ok ? '完整文本与 JSON 已写入剪贴板。' : '浏览器阻止复制，请使用「一键下载」。',
      duration: 3200,
    })
  }
}

async function dispatchCopyStructured(payload: FeedbackIncidentPayload) {
  const bundleStr = serializeDiagnosticBundle(buildDiagnosticBundle([payload]))
  const ok = await copyTextFallback(bundleStr)
  notification.success({
    title: ok ? 'JSON 报告已复制' : '复制失败',
    duration: 2200,
  })
}

function showFeedbackNotification(payload: FeedbackIncidentPayload) {
  const clipped =
    [...payload.detail].length > FEEDBACK_NOTIFY_PREVIEW_CHARS
      ? [...payload.detail].slice(0, FEEDBACK_NOTIFY_PREVIEW_CHARS).join('') + '…'
      : payload.detail
  const preferDl = preferDownloadForDetail(payload.detail)

  notification.create({
    title: payload.summary,
    description: clipped.trim() ? clipped : '(无堆栈或其它详情)',
    type: payload.severity === 'warning' ? 'warning' : 'error',
    duration: preferDl ? 0 : 8200,
    closable: true,
    meta: () =>
      h(
        NSpace,
        { vertical: true, style: 'margin-top: 10px; max-width: 420px;' },
        {
          default: () =>
            [
              h(
                NSpace,
                {},
                {
                  default: () => [
                    h(
                      NButton,
                      {
                        type: 'primary',
                        size: 'small',
                        onClick: () => dispatchPrimary(payload),
                      },
                      { default: () => (preferDl ? '一键下载日志' : '一键复制全文') },
                    ),
                    h(
                      NButton,
                      { size: 'small', tertiary: true, onClick: () => dispatchCopyStructured(payload) },
                      { default: () => '复制 JSON' },
                    ),
                  ],
                },
              ),
              h(
                'div',
                { style: 'font-size:12px;line-height:1.5;opacity:.75;' },
                preferDl ? '长篇诊断优先打包为文件；短消息则默认剪贴板。' : '内容较短时已优先剪贴板。',
              ),
            ],
        },
      ),
  })
}

/** 捕获并提示一次用户可导出的事故快照（节流相同错误在短时间内重复刷屏） */
export function emitFeedbackIncident(payload: FeedbackIncidentPayload): void {
  pushRing(payload)
  const key = incidentDedupeKey(payload)
  if (shouldSkipNotify(key)) return
  showFeedbackNotification(payload)
}

/** 业务代码显式报错：与用户 toast 联动时调用，可避免再写零碎序列化逻辑 */
export function emitManualIncident(summary: string, err?: unknown, extra?: Record<string, unknown>): void {
  emitFeedbackIncident(
    buildIncidentFromUnknown('manual', summary, err ?? summary, {
      meta: { extra: extra ?? {} },
    }),
  )
}

/** Axios 链路：拼装 HTTP 上下文后派发；打标可防止再触发 unhandledrejection 双侧栏 */
export function emitAxiosFeedbackIncident(summary: string, err: AxiosError): void {
  const base = buildIncidentFromUnknown('axios', summary, err)
  emitFeedbackIncident(augmentIncidentWithAxios(base, err))
  markErrorFeedbackEmitted(err)
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
