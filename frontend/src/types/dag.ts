/**
 * DAG 工作流类型定义 — 前后端共享 Schema
 */

// ─── 枚举 ───

export type NodeCategory = 'context' | 'execution' | 'validation' | 'gateway'
export type NodeStatus = 'idle' | 'pending' | 'running' | 'success' | 'warning' | 'error' | 'bypassed' | 'disabled' | 'completed'
export type EdgeCondition = 'on_success' | 'on_error' | 'on_drift_alert' | 'on_no_drift' | 'on_breaker_open' | 'on_breaker_closed' | 'on_review_approved' | 'on_review_rejected' | 'always'
export type PortDataType = 'text' | 'json' | 'score' | 'boolean' | 'list' | 'prompt'

// ─── 端口 ───

export interface NodePort {
  name: string
  data_type: PortDataType
  required: boolean
  default?: unknown
  description?: string
}

// ─── 节点元数据 ───

export interface NodeMeta {
  node_type: string
  display_name: string
  category: NodeCategory
  icon: string
  color: string
  input_ports: NodePort[]
  output_ports: NodePort[]
  prompt_template: string
  prompt_variables: string[]
  is_configurable: boolean
  can_disable: boolean
  default_timeout_seconds: number
  default_max_retries: number
}

// ─── 节点配置 ───

export interface NodeConfig {
  prompt_template?: string | null
  prompt_variables?: Record<string, string>
  thresholds?: Record<string, number>
  model_override?: string | null
  max_retries?: number
  timeout_seconds?: number
  temperature?: number
  max_tokens?: number | null
}

// ─── 节点定义 ───

export interface NodeDefinition {
  id: string
  type: string
  label: string
  position: { x: number; y: number }
  enabled: boolean
  config: NodeConfig
}

// ─── 边定义 ───

export interface EdgeDefinition {
  id: string
  source: string
  source_port?: string
  target: string
  target_port?: string
  condition: EdgeCondition
  animated: boolean
}

// ─── DAG 元数据 ───

export interface DAGMetadata {
  created_at: string
  updated_at: string
  created_by: string
}

// ─── DAG 定义 ───

export interface DAGDefinition {
  id: string
  name: string
  version: number
  description: string
  nodes: NodeDefinition[]
  edges: EdgeDefinition[]
  metadata: DAGMetadata
}

// ─── 节点运行时状态 ───

export interface NodeRunState {
  node_id: string
  status: NodeStatus
  started_at?: string | null
  completed_at?: string | null
  duration_ms: number
  outputs: Record<string, unknown>
  metrics: Record<string, number>
  error?: string | null
  progress: number
}

// ─── SSE 节点事件 ───

export interface NodeEvent {
  type: 'node_status_change' | 'node_output' | 'edge_data_flow'
  novel_id: string
  node_id?: string
  timestamp: string
  status?: NodeStatus | null
  metrics?: Record<string, unknown>
  outputs?: Record<string, unknown>
  duration_ms?: number
  error?: string | null
  source_node?: string
  target_node?: string
  port?: string
  data_type?: string
  data_size?: number
}

// ─── DAG 运行结果 ───

export interface DAGRunResult {
  dag_run_id: string
  novel_id: string
  status: 'completed' | 'error' | 'interrupted'
  node_results: Record<string, unknown>
  total_duration_ms: number
  error_count: number
  started_at: string
  completed_at: string
}

// ─── 验证结果 ───

export interface DAGValidationResult {
  errors: string[]
  warnings: string[]
  is_valid: boolean
  summary: string
}

// ─── 版本摘要 ───

export interface DAGVersionSummary {
  version: number
  name: string
  updated_at: string
  node_count: number
  edge_count: number
}

// ─── DAG 状态响应 ───

export interface DAGStatusResponse {
  novel_id: string
  dag_enabled: boolean
  current_version: number
  node_states: Record<string, { status: NodeStatus; enabled: boolean }>
}

// ─── 节点分类颜色映射 ───

export const CATEGORY_COLORS: Record<NodeCategory, string> = {
  context: '#6366f1',
  execution: '#3b82f6',
  validation: '#f59e0b',
  gateway: '#ef4444',
}

export const CATEGORY_LABELS: Record<NodeCategory, string> = {
  context: '📦 上下文注入',
  execution: '⚙️ 执行与生成',
  validation: '🔍 校验与监控',
  gateway: '🚦 网关与熔断',
}

// ─── 节点状态视觉映射 ───

export const STATUS_COLORS: Record<NodeStatus, string> = {
  idle: '#94a3b8',
  pending: '#94a3b8',
  running: '#3b82f6',
  success: '#22c55e',
  warning: '#f59e0b',
  error: '#ef4444',
  bypassed: '#6b7280',
  disabled: '#d1d5db',
  completed: '#22c55e',
}

export const STATUS_BG_COLORS: Record<NodeStatus, string> = {
  idle: 'transparent',
  pending: 'transparent',
  running: 'rgba(59,130,246,0.08)',
  success: 'rgba(34,197,94,0.06)',
  warning: 'rgba(245,158,11,0.06)',
  error: 'rgba(239,68,68,0.08)',
  bypassed: 'rgba(107,114,128,0.04)',
  disabled: 'rgba(209,213,219,0.04)',
  completed: 'rgba(34,197,94,0.06)',
}

export const STATUS_LABELS: Record<NodeStatus, string> = {
  idle: '空闲',
  pending: '等待中',
  running: '运行中',
  success: '成功',
  warning: '警告',
  error: '错误',
  bypassed: '已旁路',
  disabled: '已禁用',
  completed: '已完成',
}
