const API_V1_ROOT = '/api/v1'

type QueryValue = string | number | boolean | null | undefined
type QueryParams = Record<string, QueryValue | QueryValue[]>

function encodeSegment(value: string | number | boolean): string {
  return encodeURIComponent(String(value))
}

function joinSegments(segments: Array<string | number | boolean>): string {
  return segments
    .filter(segment => String(segment).length > 0)
    .map(encodeSegment)
    .join('/')
}

function normalizeClientPath(path: string): string {
  return path.startsWith('/') ? path : `/${path}`
}

export function apiClientPath(...segments: Array<string | number | boolean>): string {
  return normalizeClientPath(joinSegments(segments))
}

export function apiRootPath(...segments: Array<string | number | boolean>): string {
  return `${API_V1_ROOT}${apiClientPath(...segments)}`
}

export function withQuery(path: string, params: QueryParams = {}): string {
  const query = new URLSearchParams()
  for (const [key, raw] of Object.entries(params)) {
    const values = Array.isArray(raw) ? raw : [raw]
    for (const value of values) {
      if (value === null || value === undefined || value === '') continue
      query.append(key, String(value))
    }
  }
  const qs = query.toString()
  return qs ? `${path}?${qs}` : path
}

export const apiRoutes = {
  novels: {
    root: () => apiClientPath('novels'),
    detail: (novelId: string) => apiClientPath('novels', novelId),
    stage: (novelId: string) => apiClientPath('novels', novelId, 'stage'),
    statistics: (novelId: string) => apiClientPath('novels', novelId, 'statistics'),
    autoApproveModeClient: (novelId: string) => apiClientPath('novels', novelId, 'auto-approve-mode'),
    autoApproveMode: (novelId: string) => apiRootPath('novels', novelId, 'auto-approve-mode'),
    chapters: (novelId: string, params?: QueryParams) =>
      withQuery(apiRootPath('novels', novelId, 'chapters'), params),
    chaptersClient: (novelId: string) => apiClientPath('novels', novelId, 'chapters'),
    chapterStream: (novelId: string) => apiRootPath('autopilot', novelId, 'chapter-stream'),
    exportNovel: (novelId: string) => apiClientPath('export', 'novel', novelId),
    exportChapter: (chapterId: string) => apiClientPath('export', 'chapter', chapterId),
  },
  autopilot: {
    root: (novelId: string) => apiRootPath('autopilot', novelId),
    status: (novelId: string) => apiRootPath('autopilot', novelId, 'status'),
    start: (novelId: string) => apiRootPath('autopilot', novelId, 'start'),
    stop: (novelId: string) => apiRootPath('autopilot', novelId, 'stop'),
    resume: (novelId: string) => apiRootPath('autopilot', novelId, 'resume'),
    stream: (novelId: string, params?: QueryParams) =>
      withQuery(apiRootPath('autopilot', novelId, 'stream'), params),
    logStream: (novelId: string) => apiRootPath('autopilot', novelId, 'log-stream'),
    circuitBreaker: (novelId: string) => apiRootPath('autopilot', novelId, 'circuit-breaker'),
    circuitBreakerReset: (novelId: string) => apiRootPath('autopilot', novelId, 'circuit-breaker', 'reset'),
  },
  dag: {
    events: (novelId: string) => withQuery(apiRootPath('dag', 'events'), { novel_id: novelId }),
  },
  monitor: {
    voiceDrift: (novelId: string) => apiRootPath('novels', novelId, 'monitor', 'voice-drift'),
    tensionCurve: (novelId: string) => apiClientPath('novels', novelId, 'monitor', 'tension-curve'),
  },
}
