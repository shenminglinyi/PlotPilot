import axios from 'axios'

const API_BASE = '/api/v1/token-watcher'

export interface TokenLogItem {
  id: number
  timestamp: string
  model: string
  provider: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  latency_ms: number
  success: number
  error_message: string | null
}

export interface TokenLogsResponse {
  logs: TokenLogItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface TokenSummary {
  total_calls: number
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  avg_latency_ms: number
}

export interface TokenStatsItem {
  provider?: string
  model?: string
  total_calls: number
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  avg_latency_ms: number
}

export interface TokenWatcherConfig {
  enabled: boolean
  paginate: number
  usage_only: boolean
}

export interface TokenWatcherStatus {
  config: TokenWatcherConfig
  summary: TokenSummary
}

export interface UpdateConfigRequest {
  enabled?: boolean
  paginate?: number
  usage_only?: boolean
}

export interface FiltersResponse {
  providers: string[]
  models: string[]
}

export interface LogsQueryParams {
  page?: number
  pageSize?: number
  provider?: string
  model?: string
  timeRange?: string
}

export const tokenWatcherApi = {
  getStatus: async (): Promise<TokenWatcherStatus> => {
    const response = await axios.get(`${API_BASE}/status`)
    return response.data
  },

  getConfig: async (): Promise<TokenWatcherConfig> => {
    const response = await axios.get(`${API_BASE}/config`)
    return response.data
  },

  updateConfig: async (request: UpdateConfigRequest): Promise<TokenWatcherConfig> => {
    const response = await axios.put(`${API_BASE}/config`, request)
    return response.data
  },

  getLogs: async (params: LogsQueryParams = {}): Promise<TokenLogsResponse> => {
    const queryParams: Record<string, unknown> = { page: params.page || 1 }
    if (params.pageSize) queryParams.page_size = params.pageSize
    if (params.provider) queryParams.provider = params.provider
    if (params.model) queryParams.model = params.model
    if (params.timeRange) queryParams.time_range = params.timeRange
    const response = await axios.get(`${API_BASE}/logs`, { params: queryParams })
    return response.data
  },

  getSummary: async (): Promise<TokenSummary> => {
    const response = await axios.get(`${API_BASE}/summary`)
    return response.data
  },

  getStats: async (
    groupBy: string = 'provider',
    provider?: string,
    model?: string,
    timeRange?: string
  ): Promise<TokenStatsItem[]> => {
    const params: Record<string, unknown> = { group_by: groupBy }
    if (provider) params.provider = provider
    if (model) params.model = model
    if (timeRange) params.time_range = timeRange
    const response = await axios.get(`${API_BASE}/stats`, { params })
    return response.data
  },

  getFilters: async (): Promise<FiltersResponse> => {
    const response = await axios.get(`${API_BASE}/filters`)
    return response.data
  },

  resetStats: async (): Promise<{ success: boolean; deleted_count: number }> => {
    const response = await axios.delete(`${API_BASE}/stats`)
    return response.data
  },

  exportLogs: async (params: LogsQueryParams = {}): Promise<Record<string, unknown>[]> => {
    const queryParams: Record<string, unknown> = {}
    if (params.provider) queryParams.provider = params.provider
    if (params.model) queryParams.model = params.model
    if (params.timeRange) queryParams.time_range = params.timeRange
    const response = await axios.get(`${API_BASE}/logs/export`, { params: queryParams })
    return response.data
  },
}
