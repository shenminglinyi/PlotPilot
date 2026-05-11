/**
 * DAG 工作流 API 层 — 纯展示接口
 *
 * 设计原则：
 * - DAG 是纯展示层，不提供保存/校验/编辑接口
 * - 节点注册是代码行为，不存在前端"同步"一说
 * - 执行权在全托管模式，DAG 只展示状态流转
 */
import { apiClient } from './config'
import type {
  DAGDefinition,
  DAGStatusResponse,
  DagRegistryLinkageResponse,
  NodeMeta,
  NodePromptLive,
} from '@/types/dag'

// ─── DAG 只读展示 ───

export const dagApi = {
  /** GET /api/v1/dag/{novel_id} — 获取当前 DAG 定义（只读） */
  getDAG: (novelId: string) =>
    apiClient.get<DAGDefinition>(`/dag/${novelId}`) as unknown as Promise<DAGDefinition>,

  /** GET /api/v1/dag/{novel_id}/nodes/{node_id} — 获取节点详情（只读） */
  getNode: (novelId: string, nodeId: string) =>
    apiClient.get<Record<string, unknown>>(`/dag/${novelId}/nodes/${nodeId}`) as unknown as Promise<Record<string, unknown>>,

  /** POST /api/v1/dag/{novel_id}/nodes/{node_id}/toggle — 切换启用/禁用（唯一写操作） */
  toggleNode: (novelId: string, nodeId: string) =>
    apiClient.post<DAGDefinition>(`/dag/${novelId}/nodes/${nodeId}/toggle`, {}) as unknown as Promise<DAGDefinition>,

  /** GET /api/v1/dag/{novel_id}/status — 获取运行状态 */
  getStatus: (novelId: string) =>
    apiClient.get<DAGStatusResponse>(`/dag/${novelId}/status`) as unknown as Promise<DAGStatusResponse>,

  // ─── 节点注册表 ───

  /** GET /api/v1/dag/registry/types — 获取所有已注册的节点类型 */
  listNodeTypes: () =>
    apiClient.get<{ types: Record<string, NodeMeta> }>('/dag/registry/types') as unknown as Promise<{ types: Record<string, NodeMeta> }>,

  /** GET /api/v1/dag/registry/types/{node_type} — 获取单个节点类型的元数据 */
  getNodeTypeMeta: (nodeType: string) =>
    apiClient.get<NodeMeta>(`/dag/registry/types/${nodeType}`) as unknown as Promise<NodeMeta>,

  /** GET /api/v1/dag/registry/linkage — 默认 DAG 与 CPMS 一一对应 + 全类型索引 */
  getRegistryLinkage: () =>
    apiClient.get<DagRegistryLinkageResponse>('/dag/registry/linkage') as unknown as Promise<DagRegistryLinkageResponse>,

  // ─── 健康检查 ───

  /** GET /api/v1/dag/health/dag — DAG 引擎健康检查 */
  healthCheck: () =>
    apiClient.get<Record<string, unknown>>('/dag/health/dag') as unknown as Promise<Record<string, unknown>>,

  // ─── 提示词 ───

  /** GET /api/v1/dag/{novel_id}/nodes/{node_id}/prompt-live — 实时提示词 */
  getNodePromptLive: (novelId: string, nodeId: string) =>
    apiClient.get<NodePromptLive>(`/dag/${novelId}/nodes/${nodeId}/prompt-live`) as unknown as Promise<NodePromptLive>,

  /** GET /api/v1/dag/{novel_id}/nodes/{node_id}/prompt — 获取渲染后的 Prompt（预览） */
  getRenderedPrompt: (novelId: string, nodeId: string) =>
    apiClient.get<{ node_id: string; template: string; variables: Record<string, string>; rendered: string }>(`/dag/${novelId}/nodes/${nodeId}/prompt`) as unknown as Promise<{ node_id: string; template: string; variables: Record<string, string>; rendered: string }>,

  // ─── 运行控制（dagRunStore 使用） ───

  /** POST /api/v1/dag/{novel_id}/run — 启动 DAG 运行 */
  runDAG: (novelId: string) =>
    apiClient.post<{ status: string; novel_id: string }>(`/dag/${novelId}/run`, {}) as unknown as Promise<{ status: string; novel_id: string }>,

  /** POST /api/v1/dag/{novel_id}/stop — 停止 DAG 运行 */
  stopDAG: (novelId: string) =>
    apiClient.post<{ status: string; novel_id: string }>(`/dag/${novelId}/stop`, {}) as unknown as Promise<{ status: string; novel_id: string }>,

  // ─── 节点配置更新（nodeEditorStore 使用） ───

  /** PUT /api/v1/dag/{novel_id}/nodes/{node_id} — 更新节点配置 */
  updateNodeConfig: (novelId: string, nodeId: string, config: Record<string, unknown>) =>
    apiClient.put<DAGDefinition>(`/dag/${novelId}/nodes/${nodeId}`, config) as unknown as Promise<DAGDefinition>,
}
