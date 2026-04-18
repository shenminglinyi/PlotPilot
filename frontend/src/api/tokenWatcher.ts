import axios from 'axios'

const API_BASE = '/api/v1/token-watcher'

export interface TokenLogItem {
  id: number
  timestamp: string
  model: string
  provider: string
  operation_type: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  latency_ms: number
  success: number
  error_message: string | null
  request_preview: string | null
  response_preview: string | null
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
  success_count: number
  error_count: number
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

  getLogs: async (page: number = 1, pageSize?: number): Promise<TokenLogsResponse> => {
    const params: Record<string, unknown> = { page }
    if (pageSize) params.page_size = pageSize
    const response = await axios.get(`${API_BASE}/logs`, { params })
    return response.data
  },

  getSummary: async (): Promise<TokenSummary> => {
    const response = await axios.get(`${API_BASE}/summary`)
    return response.data
  },

  clearLogs: async (): Promise<{ success: boolean; deleted_count: number }> => {
    const response = await axios.delete(`${API_BASE}/logs`)
    return response.data
  },

  deleteLog: async (logId: number): Promise<{ success: boolean; deleted_id: number }> => {
    const response = await axios.delete(`${API_BASE}/logs/${logId}`)
    return response.data
  },
}
