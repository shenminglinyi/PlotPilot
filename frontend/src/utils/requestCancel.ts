import axios from 'axios'

/**
 * 判断是否为「主动取消 / 超时中止」类错误（含 Axios 与 fetch Abort）。
 * 用于避免把 superseded 请求或用户导航取消当作业务错误刷屏。
 */
export function isRequestCanceled(err: unknown): boolean {
  if (axios.isCancel(err)) return true
  if (!(err instanceof Error)) {
    const code = (err as { code?: string })?.code
    return code === 'ERR_CANCELED'
  }
  const name = err.name
  if (name === 'AbortError' || name === 'CanceledError') return true
  const code = (err as { code?: string }).code
  return code === 'ERR_CANCELED' || code === 'ECONNABORTED'
}
