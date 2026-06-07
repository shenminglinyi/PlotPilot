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

export function getHttpStatus(error: unknown): number | undefined {
  if (!error || typeof error !== 'object') return undefined
  const record = error as {
    status?: number
    response?: { status?: number }
  }
  if (typeof record.response?.status === 'number') return record.response.status
  if (typeof record.status === 'number') return record.status
  return undefined
}

export function getApiErrorDetail(error: unknown): string {
  const record = error as {
    body?: unknown
    response?: { data?: unknown }
    message?: string
  }
  const responseData = record?.response?.data
  if (responseData && typeof responseData === 'object' && 'detail' in responseData) {
    const detail = readableErrorValue((responseData as { detail?: unknown }).detail)
    if (detail) return detail
  }
  if (record?.body && typeof record.body === 'object' && 'detail' in record.body) {
    const detail = readableErrorValue((record.body as { detail?: unknown }).detail)
    if (detail) return detail
  }
  const responseText = readableErrorValue(responseData)
  if (responseText) return responseText
  if (record?.message && typeof record.message === 'string') return record.message
  return ''
}

export function formatApiError(error: unknown, fallback = ''): string {
  return getApiErrorDetail(error) || fallback
}

export function isLikelyTimeoutError(error: unknown): boolean {
  const code = error && typeof error === 'object'
    ? String((error as { code?: unknown }).code ?? '')
    : ''
  const text = `${getApiErrorDetail(error)} ${error instanceof Error ? error.message : ''} ${code}`
  return /timeout|ECONNABORTED|ETIMEDOUT|aborted|超时/i.test(text)
}
