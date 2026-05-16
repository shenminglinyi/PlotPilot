import type { App } from 'vue'

import { buildIncidentFromUnknown } from './feedbackIncident'
import { emitFeedbackIncident, installUnhandledPromiseCapture } from './feedbackNotifier'

/**
 * Vue 运行时错误 / 未处理 Promise：
 * Naive 「离散 Notification」在项目任意位置可直接调用。
 */
export function installGlobalFeedbackIncidentCapture(app: App): void {
  installUnhandledPromiseCapture()

  const prev = app.config.errorHandler
  app.config.errorHandler = (err, instance, info) => {
    const comp = instance?.type as { name?: string } | undefined
    emitFeedbackIncident(
      buildIncidentFromUnknown(
        'vue',
        err instanceof Error ? err.message || '组件运行时错误' : '组件运行时异常',
        err,
        {
          meta: {
            vue: {
              component_name:
                typeof comp?.name === 'string' && comp.name ? comp.name : undefined,
              lifecycle: info,
            },
          },
        },
      ),
    )
    prev?.(err, instance, info)
    if (!prev && err instanceof Error) {
      console.error(err)
    }
  }

  /** 兜底：控制台也可手动触发快照 */
  if (typeof window !== 'undefined') {
    const w = window as Window &
      PlotPilotFeedbackGlobal & {
        PlotPilotFeedback?: PlotPilotFeedbackGlobal['PlotPilotFeedback']
      }
    w.PlotPilotFeedback = {
      reportError: summary => emitFeedbackIncident(buildIncidentFromUnknown('manual', summary, summary)),
      peekRecentIncidents() {
        return import('./feedbackNotifier').then(m =>
          [...m.peekRecentFeedbackIncidents()].map(({ detail, summary, occurred_at }) => ({
            summary,
            occurred_at,
            detail_length: [...detail].length,
          })),
        )
      },
      exportRecentBundle() {
        return import('./feedbackNotifier').then(m => m.exportRecentFeedbackBundle())
      },
    }
  }
}

export interface PlotPilotFeedbackGlobal {
  PlotPilotFeedback?: {
    reportError(summary: string, err?: unknown): void
    peekRecentIncidents(): Promise<Array<{ summary: string; occurred_at: string; detail_length: number }>>
    exportRecentBundle(): Promise<void>
  }
}
