/**
 * DAG 工作流 API 层
 */
import { apiClient, resolveHttpUrl } from './config'
import type {
  DAGDefinition,
  DAGStatusResponse,
  DAGValidationResult,
  DAGVersionSummary,
  NodeMeta,
} from '@/types/dag'

// ─── DAG 定义管理 ───

export const dagApi = {
  /** GET /api/v1/dag/{novel_id} — 获取当前 DAG 定义 */
  getDAG: (novelId: string) =>
    apiClient.get<DAGDefinition>(`/dag/${novelId}`) as unknown as Promise<DAGDefinition>,

  /** PUT /api/v1/dag/{novel_id} — 更新 DAG 定义 */
  updateDAG: (novelId: string, data: {
    name?: string
    description?: string
    nodes?: Record<string, unknown>[]
    edges?: Record<string, unknown>[]
  }) =>
    apiClient.put<{ version: number; dag: DAGDefinition }>(`/dag/${novelId}`, data) as unknown as Promise<{ version: number; dag: DAGDefinition }>,

  /** POST /api/v1/dag/{novel_id}/validate — 校验 DAG 有效性 */
  validateDAG: (novelId: string) =>
    apiClient.post<DAGValidationResult>(`/dag/${novelId}/validate`, {}) as unknown as Promise<DAGValidationResult>,

  // ─── 节点操作 ───

  /** GET /api/v1/dag/{novel_id}/nodes/{node_id} — 获取节点详情 */
  getNode: (novelId: string, nodeId: string) =>
    apiClient.get<Record<string, unknown>>(`/dag/${novelId}/nodes/${nodeId}`) as unknown as Promise<Record<string, unknown>>,

  /** PUT /api/v1/dag/{novel_id}/nodes/{node_id} — 更新节点配置 */
  updateNodeConfig: (novelId: string, nodeId: string, config: Record<string, unknown>) =>
    apiClient.put<DAGDefinition>(`/dag/${novelId}/nodes/${nodeId}`, config) as unknown as Promise<DAGDefinition>,

  /** POST /api/v1/dag/{novel_id}/nodes/{node_id}/toggle — 切换启用/禁用 */
  toggleNode: (novelId: string, nodeId: string) =>
    apiClient.post<DAGDefinition>(`/dag/${novelId}/nodes/${nodeId}/toggle`, {}) as unknown as Promise<DAGDefinition>,

  /** POST /api/v1/dag/{novel_id}/nodes/{node_id}/rerun — 从该节点重新执行 */
  rerunFromNode: (novelId: string, nodeId: string) =>
    apiClient.post<{ status: string; node_id: string }>(`/dag/${novelId}/nodes/${nodeId}/rerun`, {}) as unknown as Promise<{ status: string; node_id: string }>,

  /** GET /api/v1/dag/{novel_id}/nodes/{node_id}/prompt — 获取渲染后的 Prompt */
  getRenderedPrompt: (novelId: string, nodeId: string) =>
    apiClient.get<{ node_id: string; template: string; variables: Record<string, string>; rendered: string }>(`/dag/${novelId}/nodes/${nodeId}/prompt`) as unknown as Promise<{ node_id: string; template: string; variables: Record<string, string>; rendered: string }>,

  // ─── DAG 运行 ───

  /** POST /api/v1/dag/{novel_id}/run — 启动 DAG 运行 */
  runDAG: (novelId: string) =>
    apiClient.post<{ status: string; novel_id: string }>(`/dag/${novelId}/run`, {}) as unknown as Promise<{ status: string; novel_id: string }>,

  /** POST /api/v1/dag/{novel_id}/stop — 停止 DAG 运行 */
  stopDAG: (novelId: string) =>
    apiClient.post<{ status: string; novel_id: string }>(`/dag/${novelId}/stop`, {}) as unknown as Promise<{ status: string; novel_id: string }>,

  /** GET /api/v1/dag/{novel_id}/status — 获取运行状态 */
  getStatus: (novelId: string) =>
    apiClient.get<DAGStatusResponse>(`/dag/${novelId}/status`) as unknown as Promise<DAGStatusResponse>,

  // ─── 版本管理 ───

  /** GET /api/v1/dag/{novel_id}/versions — DAG 版本列表 */
  listVersions: (novelId: string) =>
    apiClient.get<{ novel_id: string; versions: DAGVersionSummary[] }>(`/dag/${novelId}/versions`) as unknown as Promise<{ novel_id: string; versions: DAGVersionSummary[] }>,

  /** POST /api/v1/dag/{novel_id}/versions/{version}/rollback — 回滚到指定版本 */
  rollbackVersion: (novelId: string, version: number) =>
    apiClient.post<{ status: string; version: number; dag: DAGDefinition }>(`/dag/${novelId}/versions/${version}/rollback`, {}) as unknown as Promise<{ status: string; version: number; dag: DAGDefinition }>,

  // ─── 节点注册表 ───

  /** GET /api/v1/dag/registry/types — 获取所有已注册的节点类型 */
  listNodeTypes: () =>
    apiClient.get<{ types: Record<string, NodeMeta> }>('/dag/registry/types') as unknown as Promise<{ types: Record<string, NodeMeta> }>,

  /** GET /api/v1/dag/registry/types/{node_type} — 获取单个节点类型的元数据 */
  getNodeTypeMeta: (nodeType: string) =>
    apiClient.get<NodeMeta>(`/dag/registry/types/${nodeType}`) as unknown as Promise<NodeMeta>,

  // ─── 健康检查 ───

  /** GET /api/v1/dag/health/dag — DAG 引擎健康检查 */
  healthCheck: () =>
    apiClient.get<Record<string, unknown>>('/dag/health/dag') as unknown as Promise<Record<string, unknown>>,
}
