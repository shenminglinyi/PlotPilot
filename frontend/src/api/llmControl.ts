import { apiClient } from './config'

export type LLMProtocol = 'openai' | 'anthropic' | 'gemini'

export interface LLMPreset {
  key: string
  label: string
  protocol: LLMProtocol
  default_base_url: string
  default_model: string
  description: string
  tags: string[]
}

export interface LLMProfile {
  id: string
  name: string
  preset_key: string
  protocol: LLMProtocol
  base_url: string
  api_key: string
  model: string
  temperature: number
  max_tokens: number
  timeout_seconds: number
  extra_headers: Record<string, string>
  extra_query: Record<string, unknown>
  extra_body: Record<string, unknown>
  notes: string
}

export interface LLMControlConfig {
  version: number
  active_profile_id: string | null
  profiles: LLMProfile[]
}

export interface LLMRuntimeSummary {
  source: 'profile' | 'mock'
  active_profile_id: string | null
  active_profile_name: string | null
  protocol: LLMProtocol | null
  model: string | null
  base_url: string | null
  using_mock: boolean
  reason: string | null
}

export interface LLMControlPanelData {
  config: LLMControlConfig
  presets: LLMPreset[]
  runtime: LLMRuntimeSummary
}

export interface LLMTestResult {
  ok: boolean
  provider_label: string
  model: string
  latency_ms: number
  preview: string
  error: string | null
}

export interface ModelItem {
  id: string
  name: string
  owned_by: string
}

export interface ModelListResponse {
  success: boolean
  items: ModelItem[]
  count: number
}

export interface FetchModelsPayload {
  protocol: string
  base_url: string
  api_key: string
  timeout_ms?: number
}

export const llmControlApi = {
  getPanel: () => apiClient.get<LLMControlPanelData>('/llm-control') as Promise<LLMControlPanelData>,
  saveConfig: (config: LLMControlConfig) =>
    apiClient.put<LLMControlPanelData>('/llm-control', config) as Promise<LLMControlPanelData>,
  testProfile: (profile: LLMProfile) =>
    apiClient.post<LLMTestResult>('/llm-control/test', profile, { timeout: 120_000 }) as Promise<LLMTestResult>,
  fetchModels: (payload: FetchModelsPayload) =>
    apiClient.post<ModelListResponse>('/llm-control/models', payload, { timeout: 30_000 }) as Promise<ModelListResponse>,
}

// ========== 提示词广场 API (Prompt Plaza) ==========

/** 分类信息 */
export interface PromptCategoryInfo {
  key: string
  name: string
  icon: string
  description: string
  color: string
  count: number
}

/** 模板包 */
export interface PromptTemplate {
  id: string
  name: string
  description: string
  category: string
  version: string
  author: string
  icon: string
  color: string
  is_builtin: boolean
  metadata: Record<string, unknown>
  node_count: number
}

/** 变量定义 */
export interface PromptVariable {
  name: string
  desc: string
  type: string
  required?: boolean
  default?: unknown
}

/** 提示词节点（列表项） */
export interface PromptNode {
  id: string
  node_key: string
  name: string
  description: string
  category: string
  source: string
  output_format: 'text' | 'json'
  contract_module: string | null
  contract_model: string | null
  tags: string[]
  variables: PromptVariable[]
  variable_names: string[]
  system_file: string | null
  is_builtin: boolean
  sort_order: number
  template_id: string
  version_count: number
  system_preview: string
  user_template_preview: string
  has_user_edit: boolean
}

/** 提示词节点详情（含完整内容） */
export interface PromptNodeDetail extends PromptNode {
  system: string
  user_template: string
}

/** 版本信息 */
export interface PromptVersion {
  id: string
  version_number: number
  change_summary: string
  created_by: string
  created_at: string
  system_preview: string
  user_preview: string
}

/** 版本详情（含完整内容） */
export interface PromptVersionDetail extends PromptVersion {
  system_prompt: string
  user_template: string
}

/** 版本对比结果 */
export interface VersionCompareResult {
  v1: PromptVersionDetail
  v2: PromptVersionDetail
  diff: {
    system_changed: boolean
    user_changed: boolean
  }
}

/** 统计信息 */
export interface PromptStats {
  total_nodes: number
  total_templates: number
  total_versions: number
  builtin_count: number
  custom_count: number
  categories: Record<string, number>
}

/** 渲染结果 */
export interface RenderResult {
  system: string
  user: string
}

// ---------- 请求类型 ----------

export interface PromptUpdatePayload {
  system?: string
  user_template?: string
  name?: string
  description?: string
  tags?: string[]
  change_summary?: string
}

export interface CreateNodePayload {
  template_id?: string
  node_key?: string
  name: string
  description?: string
  category?: string
  system?: string
  user_template?: string
}

export interface CreateTemplatePayload {
  name: string
  description?: string
  category?: string
}

export interface RenderPayload {
  variables: Record<string, unknown>
}

// ---------- API 调用 ----------

export const promptPlazaApi = {
  /** 统计 */
  getStats: () => apiClient.get<PromptStats>('/llm-control/prompts/stats'),

  /** 分类信息（含计数） */
  getCategoriesInfo: () => apiClient.get<PromptCategoryInfo[]>('/llm-control/prompts/categories-info'),

  /** 模板包列表 */
  listTemplates: () => apiClient.get<PromptTemplate[]>('/llm-control/prompts/templates'),

  /** 创建模板包 */
  createTemplate: (payload: CreateTemplatePayload) =>
    apiClient.post<{ status: string; template: PromptTemplate }>('/llm-control/prompts/templates', payload),

  /** 列举节点（支持分类过滤和搜索） */
  listNodes: (params?: { category?: string; template_id?: string; search?: string }) => {
    const query = new URLSearchParams()
    if (params?.category) query.set('category', params.category)
    if (params?.template_id) query.set('template_id', params.template_id)
    if (params?.search) query.set('search', params.search)
    const qs = query.toString()
    return apiClient.get<PromptNode[]>(`/llm-control/prompts${qs ? `?${qs}` : ''}`)
  },

  /** 按分类分组 */
  listNodesByCategory: () =>
    apiClient.get<Record<string, PromptNode[]>>('/llm-control/prompts/by-category'),

  /** 单个节点详情 */
  getNodeDetail: (nodeKey: string) =>
    apiClient.get<PromptNodeDetail>(`/llm-control/prompts/${nodeKey}`),

  /** 创建自定义节点 */
  createNode: (payload: CreateNodePayload) =>
    apiClient.post<{ status: string; node: PromptNode }>('/llm-control/prompts/nodes', payload),

  /** 删除自定义节点 */
  deleteNode: (nodeId: string) =>
    apiClient.delete<{ status: string; node_id: string }>(`/llm-control/prompts/nodes/${nodeId}`),

  // ---- 版本管理 ----

  /** 节点版本历史 */
  getNodeVersions: (nodeKey: string) =>
    apiClient.get<PromptVersion[]>(`/llm-control/prompts/${nodeKey}/versions`),

  /** 单个版本详情 */
  getVersionDetail: (versionId: string) =>
    apiClient.get<PromptVersionDetail>(`/llm-control/prompts/versions/${versionId}`),

  /** 更新节点（自动创建新版本） */
  updateNode: (nodeKey: string, payload: PromptUpdatePayload) =>
    apiClient.put<{ status: string; node: PromptNode | null; message: string }>(
      `/llm-control/prompts/${nodeKey}`, payload,
    ),

  /** 回滚到指定版本 */
  rollbackNode: (nodeKey: string, versionId: string) =>
    apiClient.post<{ status: string; node: PromptNode; message: string }>(
      `/llm-control/prompts/${nodeKey}/rollback/${versionId}`,
    ),

  /** 对比两个版本 */
  compareVersions: (v1Id: string, v2Id: string) =>
    apiClient.get<VersionCompareResult>(`/llm-control/prompts/compare/${v1Id}/${v2Id}`),

  // ---- 渲染 ----

  /** 渲染提示词模板 */
  renderPrompt: (nodeKey: string, variables: Record<string, unknown>) =>
    apiClient.post<RenderResult>(
      `/llm-control/prompts/${nodeKey}/render`,
      { variables } as RenderPayload,
    ),

  // ---- 导出 / 导入 ----

  /** 导出所有提示词（返回完整 JSON） */
  exportAll: () =>
    apiClient.get<Record<string, unknown>>('/llm-control/prompts/export'),

  /** 导入提示词 JSON */
  importData: (payload: { _meta?: Record<string, unknown>; categories?: Record<string, unknown>[]; prompts: Record<string, unknown>[] }) =>
    apiClient.post<{ status: string; summary: { created: number; updated: number; skipped: number; total: number }; errors: string[]; message: string }>(
      '/llm-control/prompts/import',
      payload,
    ),
}
