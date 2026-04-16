export type RewriteMode = 'rewrite' | 'expand' | 'shrink' | 'polish' | 'continue'

export interface RewritePayload {
  text: string
  mode: RewriteMode
  context?: string
}

export interface RewriteStreamHandlers {
  onChunk?: (text: string) => void
  onDone?: () => void
  onError?: (message: string) => void
  signal?: AbortSignal
}

function parseSseDataLine(line: string): Record<string, unknown> | null {
  if (!line.startsWith('data: ')) return null
  try {
    return JSON.parse(line.slice(6)) as Record<string, unknown>
  } catch {
    return null
  }
}

export async function consumeRewriteStream(
  payload: RewritePayload,
  handlers: RewriteStreamHandlers
): Promise<void> {
  const res = await fetch('/api/v1/rewrite', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: handlers.signal,
  })
  if (!res.ok || !res.body) {
    const t = await res.text().catch(() => '')
    handlers.onError?.(t || `HTTP ${res.status}`)
    return
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      let sep: number
      while ((sep = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, sep)
        buf = buf.slice(sep + 2)
        for (const line of block.split('\n')) {
          const raw = parseSseDataLine(line)
          if (!raw) continue
          const typ = raw.type as string
          if (typ === 'chunk') {
            handlers.onChunk?.(String(raw.text ?? ''))
          } else if (typ === 'done') {
            handlers.onDone?.()
            return
          } else if (typ === 'error') {
            handlers.onError?.(String(raw.message ?? '改写失败'))
            return
          }
        }
      }
    }
  } catch (e: unknown) {
    if (e instanceof Error && e.name === 'AbortError') return
    handlers.onError?.(e instanceof Error ? e.message : '流式连接失败')
  }
}

export const REWRITE_MODE_LABELS: Record<RewriteMode, string> = {
  rewrite: '改写',
  expand: '扩写',
  shrink: '缩写',
  polish: '润色',
  continue: '续写',
}
