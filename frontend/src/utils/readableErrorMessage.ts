/**
 * 把响应体文本（JSON {"detail":...}/{"message":...} 或纯文本）读成可读报错文案。
 * 用于 SSE/fetch 手写路径：axios 的 formatApiError 只接受 Error 形状，
 * 这里补上「拿到原始 Response body 文本」时的同款解析。
 */
function readableErrorValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    return value.map(readableErrorValue).filter(Boolean).join('；')
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    for (const key of ['message', 'detail', 'msg', 'error', 'reason']) {
      const text = readableErrorValue(record[key])
      if (text) return text
    }
    return ''
  }
  return ''
}

export function readableErrorMessage(text: string): string {
  if (!text.trim()) return ''
  try {
    return readableErrorValue(JSON.parse(text))
  } catch {
    // 非 JSON：截掉可能的 HTML 标签头，保留首行
    return text.replace(/<[^>]+>/g, '').trim().split('\n')[0].slice(0, 200)
  }
}
