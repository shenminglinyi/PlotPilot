/**
 * DAG 画布核心状态管理 — 纯展示层
 *
 * 设计原则：
 * - DAG 不需要判断能否执行 — 执行权在全托管，DAG 只是展示状态流转
 * - 节点注册是代码行为 — 写一个节点就注册一个，不存在"同步"一说
 * - 保存/校验/广场按钮都是多余的 — DAG 是纯展示层
 * - 暂时不走数据库 — DAG 定义从注册表生成
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  DAGDefinition,
  NodeDefinition,
  NodeEvent,
  NodeMeta,
  NodePromptLive,
  NodeRunState,
  NodeStatus,
} from '@/types/dag'
import { dagApi } from '@/api/dag'

export const useDAGStore = defineStore('dag', () => {
  // ─── DAG 定义（只读展示） ───
  const dagDefinition = ref<DAGDefinition | null>(null)
  const nodeTypeRegistry = ref<Record<string, NodeMeta>>({})

  // ─── 节点运行时状态（SSE 推送） ───
  const nodeStates = ref<Map<string, NodeRunState>>(new Map())

  // ─── 边动画状态 ───
  const edgeFlows = ref<Map<string, { port: string; timestamp: number }>>(new Map())

  // ─── 节点提示词缓存 ───
  const nodePromptLive = ref<Map<string, NodePromptLive>>(new Map())

  // ─── 交互状态 ───
  const selectedNodeId = ref<string | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // ─── 视图切换（AutopilotDashboard 使用） ───
  const viewMode = ref<'card' | 'dag'>('card')

  // ─── 计算属性：Vue Flow 节点数据 ───
  const vueFlowNodes = computed(() => {
    if (!dagDefinition.value) return []

    return dagDefinition.value.nodes.map(nodeDef => ({
      id: nodeDef.id,
      type: 'dagCustom',
      position: nodeDef.position,
      data: {
        ...nodeDef,
        runState: nodeStates.value.get(nodeDef.id),
        isSelected: selectedNodeId.value === nodeDef.id,
      },
    }))
  })

  // ─── 计算属性：Vue Flow 边数据 ───
  const vueFlowEdges = computed(() => {
    if (!dagDefinition.value) return []

    return dagDefinition.value.edges.map(edgeDef => {
      const flowKey = `${edgeDef.source}->${edgeDef.target}`
      const flow = edgeFlows.value.get(flowKey)
      const isActive = flow && (Date.now() - flow.timestamp < 2000)

      return {
        id: edgeDef.id,
        source: edgeDef.source,
        target: edgeDef.target,
        sourceHandle: edgeDef.source_port || undefined,
        targetHandle: edgeDef.target_port || undefined,
        animated: edgeDef.animated || isActive,
        data: {
          condition: edgeDef.condition,
          isActive,
        },
        style: {
          strokeDasharray: edgeDef.condition !== 'always' ? '5 5' : undefined,
        },
      }
    })
  })

  // ─── 计算属性：DAG 统计 ───
  const dagStats = computed(() => {
    const nodes = dagDefinition.value?.nodes ?? []
    const states = nodeStates.value
    return {
      total: nodes.length,
      enabled: nodes.filter(n => n.enabled).length,
      running: nodes.filter(n => states.get(n.id)?.status === 'running').length,
      success: nodes.filter(n => states.get(n.id)?.status === 'success').length,
      error: nodes.filter(n => states.get(n.id)?.status === 'error').length,
      bypassed: nodes.filter(n => states.get(n.id)?.status === 'bypassed').length,
      version: dagDefinition.value?.version ?? 0,
    }
  })

  // ─── Actions ───

  async function loadDAG(novelId: string) {
    isLoading.value = true
    error.value = null
    try {
      const dag = await dagApi.getDAG(novelId)
      dagDefinition.value = dag
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '加载 DAG 失败'
    } finally {
      isLoading.value = false
    }
  }

  async function loadNodeTypeRegistry() {
    try {
      const result = await dagApi.listNodeTypes()
      nodeTypeRegistry.value = result.types
    } catch {
      // 静默失败
    }
  }

  async function toggleNode(novelId: string, nodeId: string) {
    try {
      const dag = await dagApi.toggleNode(novelId, nodeId)
      dagDefinition.value = dag
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '切换节点状态失败'
    }
  }

  // ─── SSE 事件处理 ───

  function handleSSEEvent(event: NodeEvent) {
    switch (event.type) {
      case 'node_status_change':
        if (event.node_id) {
          const existing = nodeStates.value.get(event.node_id)
          nodeStates.value.set(event.node_id, {
            node_id: event.node_id,
            status: (event.status ?? 'idle') as NodeStatus,
            duration_ms: existing?.duration_ms ?? 0,
            outputs: existing?.outputs ?? {},
            metrics: existing?.metrics ?? (event.metrics as Record<string, number>) ?? {},
            progress: existing?.progress ?? 0,
            error: event.error ?? null,
          })
        }
        break

      case 'node_output':
        if (event.node_id) {
          const existing = nodeStates.value.get(event.node_id)
          if (existing) {
            existing.outputs = event.outputs ?? {}
            existing.duration_ms = event.duration_ms ?? 0
          } else {
            nodeStates.value.set(event.node_id, {
              node_id: event.node_id,
              status: 'success',
              outputs: event.outputs ?? {},
              duration_ms: event.duration_ms ?? 0,
              metrics: (event.metrics as Record<string, number>) ?? {},
              progress: 1.0,
            })
          }
        }
        break

      case 'edge_data_flow':
        if (event.source_node && event.target_node) {
          edgeFlows.value.set(
            `${event.source_node}->${event.target_node}`,
            { port: event.port ?? '', timestamp: Date.now() }
          )
        }
        break
    }
  }

  function selectNode(nodeId: string | null) {
    selectedNodeId.value = nodeId
  }

  function switchView(mode: 'card' | 'dag') {
    viewMode.value = mode
  }

  /** 更新节点运行参数（NodeEditorDrawer 使用，DAG 本身不提供编辑 UI） */
  async function updateNodeConfig(novelId: string, nodeId: string, config: Record<string, unknown>) {
    try {
      // ★ 暂时直接更新内存中的 DAG 定义（不走数据库）
      const node = dagDefinition.value?.nodes.find(n => n.id === nodeId)
      if (node && dagDefinition.value) {
        // 合并配置
        if (config.temperature !== undefined) node.config.temperature = config.temperature as number
        if (config.max_tokens !== undefined) node.config.max_tokens = config.max_tokens as number | null
        if (config.timeout_seconds !== undefined) node.config.timeout_seconds = config.timeout_seconds as number
        if (config.max_retries !== undefined) node.config.max_retries = config.max_retries as number
        if (config.model_override !== undefined) node.config.model_override = config.model_override as string | null
      }
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '更新节点配置失败'
    }
  }

  function resetNodeStates() {
    nodeStates.value.clear()
    edgeFlows.value.clear()
  }

  async function loadNodePromptLive(novelId: string, nodeId: string) {
    try {
      const result = await dagApi.getNodePromptLive(novelId, nodeId)
      nodePromptLive.value.set(nodeId, result)
      return result
    } catch {
      return null
    }
  }

  return {
    // State
    dagDefinition,
    nodeTypeRegistry,
    nodeStates,
    edgeFlows,
    nodePromptLive,
    selectedNodeId,
    isLoading,
    error,
    viewMode,

    // Computed
    vueFlowNodes,
    vueFlowEdges,
    dagStats,

    // Actions
    loadDAG,
    loadNodeTypeRegistry,
    toggleNode,
    updateNodeConfig,
    handleSSEEvent,
    selectNode,
    switchView,
    resetNodeStates,
    loadNodePromptLive,
  }
})
