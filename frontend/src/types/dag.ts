/**
 * DAG 工作流类型定义 — 纯展示层
 *
 * 设计原则：
 * - DAG 不需要判断能否执行 — 执行权在全托管，DAG 只是展示状态流转
 * - 节点注册是代码行为 — 写一个节点就注册一个，不存在"同步"一说
 * - 保存/校验/广场按钮都是多余的 — DAG 是纯展示层
 *
 * 颜色策略：所有 UI 色值统一走 CSS 自定义属性（--dag-* / --color-* / --app-*），
 * 此文件仅保留语义标签，具体色值由 main.css 三套主题变量层驱动。
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
  // ★ CPMS 关联字段
  cpms_node_key: string
  description: string
  default_edges: string[]
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

// ─── DAG 状态响应 ───

export interface DAGStatusResponse {
  novel_id: string
  dag_enabled: boolean
  current_version: number
  node_states: Record<string, { status: NodeStatus; enabled: boolean }>
}

// ─── DAG 运行结果（dagRunStore 使用） ───

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

// ─── 节点实时提示词 ───

export interface NodePromptLive {
  node_id: string
  node_type: string
  cpms_node_key: string
  system: string
  user_template: string
  source: 'cpms' | 'config' | 'meta' | 'none'
  variables: string[]
}

// ─── DAG ↔ CPMS 联动内核（GET /dag/registry/linkage）───

export interface DagLinkageSubKey {
  cpms_node_key: string
  target_variable: string
  description: string
  required: boolean
}

export interface DagLinkageNodeRow {
  node_id: string
  node_type: string
  label: string
  enabled_default: boolean
  cpms_node_key: string
  cpms_sub_keys: DagLinkageSubKey[]
  prompt_mode: string
  category: string
  display_name: string
}

export interface RegistryCpmsEntry {
  cpms_node_key: string
  cpms_sub_keys: DagLinkageSubKey[]
  prompt_mode: string
  category: string
  display_name: string
}

export interface DagRegistryLinkageResponse {
  pipeline_node_ids: string[]
  nodes: DagLinkageNodeRow[]
  registry_cpms_by_type: Record<string, RegistryCpmsEntry>
}

// ─── 节点分类 → CSS 变量名映射 ───

export const CATEGORY_COLORS: Record<NodeCategory, string> = {
  context:  'var(--color-purple)',
  execution: 'var(--color-info)',
  validation: 'var(--color-warning)',
  gateway:  'var(--color-danger)',
}

export const CATEGORY_LABELS: Record<NodeCategory, string> = {
  context: '📦 上下文注入',
  execution: '⚙️ 执行与生成',
  validation: '🔍 校验与监控',
  gateway: '🚦 网关与熔断',
}

// ─── 节点状态 → CSS 变量名映射 ───

export const STATUS_COLORS: Record<NodeStatus, string> = {
  idle:      'var(--app-text-muted)',
  pending:   'var(--app-text-muted)',
  running:   'var(--color-brand)',
  success:   'var(--color-success)',
  warning:   'var(--color-warning)',
  error:     'var(--color-danger)',
  bypassed:  'var(--app-text-muted)',
  disabled:  'var(--app-border-strong)',
  completed: 'var(--color-success)',
}

export const STATUS_BG_COLORS: Record<NodeStatus, string> = {
  idle:      'transparent',
  pending:   'transparent',
  running:   'var(--color-brand-light)',
  success:   'var(--color-success-dim)',
  warning:   'var(--color-warning-dim)',
  error:     'var(--color-danger-dim)',
  bypassed:  'var(--app-divider)',
  disabled:  'var(--app-divider)',
  completed: 'var(--color-success-dim)',
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
