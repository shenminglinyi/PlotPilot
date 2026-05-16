/** PlotPilot Axios 可选开关（供全局诊断层识别） */

import 'axios'

declare module 'axios' {
  interface AxiosRequestConfig {
    /**
     * 为 true 时跳过全局「事故通知」仍会 reject，用于业务已在 UI 中用 message 说明过的可控错误，
     * 避免与 Axios 全局拦截重叠。
     */
    silentGlobalFeedback?: boolean
  }
}

export {}
