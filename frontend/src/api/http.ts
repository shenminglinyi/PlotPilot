import { resolveHttpUrl } from './config'

export class HttpError extends Error {
  status: number
  statusText: string
  body: unknown

  constructor(response: Response, body: unknown) {
    super(`HTTP ${response.status} ${response.statusText}`.trim())
    this.name = 'HttpError'
    this.status = response.status
    this.statusText = response.statusText
    this.body = body
  }
}

export interface FetchJsonOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  timeoutMs?: number
}

function mergeHeaders(headers?: HeadersInit, hasBody = false): Headers {
  const merged = new Headers(headers)
  if (hasBody && !merged.has('Content-Type')) {
    merged.set('Content-Type', 'application/json')
  }
  return merged
}

function composeAbortSignal(signal?: AbortSignal | null, timeoutMs?: number): {
  signal?: AbortSignal
  cleanup: () => void
} {
  if (!timeoutMs) {
    return { signal: signal ?? undefined, cleanup: () => {} }
  }
  const controller = new AbortController()
  const abort = () => controller.abort()
  const timer = window.setTimeout(abort, timeoutMs)

  if (signal?.aborted) {
    abort()
  } else {
    signal?.addEventListener('abort', abort, { once: true })
  }

  return {
    signal: controller.signal,
    cleanup: () => {
      window.clearTimeout(timer)
      signal?.removeEventListener('abort', abort)
    },
  }
}

async function readResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined
  const text = await response.text()
  if (!text.trim()) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

export async function fetchJson<T>(absolutePathFromRoot: string, options: FetchJsonOptions = {}): Promise<T> {
  const { body, timeoutMs, signal, headers, ...rest } = options
  const hasBody = body !== undefined
  const abort = composeAbortSignal(signal, timeoutMs)
  try {
    const response = await fetch(resolveHttpUrl(absolutePathFromRoot), {
      ...rest,
      signal: abort.signal,
      headers: mergeHeaders(headers, hasBody),
      body: hasBody ? JSON.stringify(body) : undefined,
    })
    const data = await readResponseBody(response)
    if (!response.ok) {
      throw new HttpError(response, data)
    }
    return data as T
  } finally {
    abort.cleanup()
  }
}

export async function fetchOk(absolutePathFromRoot: string, options: FetchJsonOptions = {}): Promise<Response> {
  const { timeoutMs, signal, body, headers, ...rest } = options
  const hasBody = body !== undefined
  const abort = composeAbortSignal(signal, timeoutMs)
  try {
    const response = await fetch(resolveHttpUrl(absolutePathFromRoot), {
      ...rest,
      signal: abort.signal,
      headers: mergeHeaders(headers, hasBody),
      body: hasBody ? JSON.stringify(body) : undefined,
    })
    if (!response.ok) {
      throw new HttpError(response, await readResponseBody(response))
    }
    return response
  } finally {
    abort.cleanup()
  }
}

export function fetchUrl(absolutePathFromRoot: string): string {
  return resolveHttpUrl(absolutePathFromRoot)
}
