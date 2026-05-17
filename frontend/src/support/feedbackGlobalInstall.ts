import type { App, ComponentPublicInstance } from 'vue'

import { buildIncidentFromUnknown } from './feedbackIncident'
import {
  emitFeedbackIncident,
  emitManualIncident,
  exportRecentFeedbackBundle,
  installUnhandledPromiseCapture,
  peekRecentFeedbackIncidents,
} from './feedbackNotifier'

function resolveVueComponentDebugName(instance: ComponentPublicInstance | null | undefined): string | undefined {
  if (!instance) return undefined
  const typed = instance as unknown as {
    type?: { name?: string; __name?: string }
    $?: { type?: { name?: string } }
  }
  const t = typed.type ?? typed.$?.type
  if (t && typeof t === 'object') {
    const n = (t as { name?: string }).name
    if (typeof n === 'string' && n) return n
    const u = (t as { __name?: string }).__name
    if (typeof u === 'string' && u) return u
  }
  return undefined
}

/**
 * Vue 运行时错误 / 未处理 Promise：离散 Notification，根组件外也可用。
 */
export function installGlobalFeedbackIncidentCapture(app: App): void {
  installUnhandledPromiseCapture()

  const prev = app.config.errorHandler
  app.config.errorHandler = (err, instance, info) => {
    emitFeedbackIncident(
      buildIncidentFromUnknown(
        'vue',
        err instanceof Error ? err.message || '组件运行时错误' : '组件运行时异常',
        err,
        {
          meta: {
            vue: {
              component_name: resolveVueComponentDebugName(instance),
              lifecycle: info,
            },
          },
        },
      ),
    )
    if (prev) {
      prev(err, instance, info)
      return
    }
    console.error('[Vue]', err)
  }

  if (typeof window !== 'undefined') {
    window.PlotPilotFeedback = {
      reportError(summary, err) {
        emitManualIncident(summary, err)
      },
      peekRecentIncidents() {
        return [...peekRecentFeedbackIncidents()].map(({ summary, occurred_at: occurredAt, detail }) => ({
          summary,
          occurred_at: occurredAt,
          detail_length: [...detail].length,
        }))
      },
      exportRecentBundle: exportRecentFeedbackBundle,
    }
  }
}
