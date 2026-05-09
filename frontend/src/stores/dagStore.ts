/**
 * DAG 画布核心状态管理
 */
import { defineStore } from 'pinia'
import { useDebounceFn } from '@vueuse/core'
import { ref, computed, watch } from 'vue'
import type {
  DAGDefinition,
  DAGVersionSummary,
  NodeDefinition,
  NodeEvent,
  NodeMeta,
  NodeRunState,
  NodeStatus,
} from '@/types/dag'
import { dagApi } from '@/api/dag'

export const useDAGStore = defineStore('dag', () => {
  // ─── DAG 定义 ───
  const dagDefinition = ref<DAGDefinition | null>(null)
  const dagVersions = ref<DAGVersionSummary[]>([])
  const nodeTypeRegistry = ref<Record<string, NodeMeta>>({})

  // ─── 节点运行时状态 ───
  const nodeStates = ref<Map<string, NodeRunState>>(new Map())

  // ─── 边动画状态 ───
  const edgeFlows = ref<Map<string, { port: string; timestamp: number }>>(new Map())

  // ─── 交互状态 ───
  const selectedNodeId = ref<string | null>(null)
  const editingNodeId = ref<string | null>(null)
  const viewMode = ref<'card' | 'dag'>('card')
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // ─── 校验状态和未保存追踪 ───
  const validationStatus = ref<{
    isValid: boolean
    message: string
    errors?: string[]
  }>({
    isValid: true,
    message: '',
    errors: [],
  })

  const hasUnsavedChanges = ref(false)

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
        isEditing: editingNodeId.value === nodeDef.id,
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
        // 条件边：虚线样式（具体色值由 CustomEdge 组件 CSS 驱动，此处仅标记）
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
    currentNovelId.value = novelId
    hasUnsavedChanges.value = false
    try {
      const dag = await dagApi.getDAG(novelId)
      dagDefinition.value = dag
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '加载 DAG 失败'
    } finally {
      isLoading.value = false
    }
  }

  async function saveDAG(novelId: string) {
    if (!dagDefinition.value) return

    isLoading.value = true
    currentNovelId.value = novelId

    // ★ 保存前先校验
    const result = await validateDAG(novelId)
    if (!result.is_valid) {
      validationStatus.value = {
        isValid: false,
        message: result.summary,
        errors: result.errors,
      }
      error.value = `保存失败：${result.summary}`
      isLoading.value = false
      return false
    }

    // ★ 校验通过才保存
    try {
      const updated = await dagApi.updateDAG(novelId, {
        nodes: dagDefinition.value.nodes as unknown as Record<string, unknown>[],
        edges: dagDefinition.value.edges as unknown as Record<string, unknown>[],
      })
      dagDefinition.value = updated.dag
      hasUnsavedChanges.value = false
      error.value = null
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '保存 DAG 失败'
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function loadVersions(novelId: string) {
    try {
      const result = await dagApi.listVersions(novelId)
      dagVersions.value = result.versions
    } catch {
      // 静默失败
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

  async function updateNodeConfig(novelId: string, nodeId: string, config: Record<string, unknown>) {
    try {
      const dag = await dagApi.updateNodeConfig(novelId, nodeId, config)
      dagDefinition.value = dag
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '更新节点配置失败'
    }
  }

  async function validateDAG(novelId: string) {
    try {
      return await dagApi.validateDAG(novelId)
    } catch {
      return { errors: ['验证请求失败'], warnings: [], is_valid: false, summary: '❌ 验证失败' }
    }
  }

  // ─── 自动校验逻辑 ───
  const currentNovelId = ref<string | null>(null)

  const debouncedValidate = useDebounceFn(async () => {
    if (!currentNovelId.value) return

    try {
      const result = await dagApi.validateDAG(currentNovelId.value)

      if (!result.is_valid) {
        validationStatus.value = {
          isValid: false,
          message: result.summary,
          errors: result.errors,
        }
      } else {
        validationStatus.value = {
          isValid: true,
          message: result.summary,
          errors: [],
        }
      }
    } catch (e) {
      console.error('自动校验失败:', e)
      validationStatus.value = {
        isValid: false,
        message: '校验失败：网络错误或服务不可用',
        errors: ['无法连接到验证服务'],
      }
    }
  }, 1000)

  // 监听 DAG 变更，自动触发校验
  watch(
    () => dagDefinition.value,
    () => {
      if (dagDefinition.value && currentNovelId.value && hasUnsavedChanges.value) {
        debouncedValidate()
      }
    },
    { deep: true }
  )

  // ─── SSE 事件处理 ───

  function handleSSEEvent(event: NodeEvent) {
    switch (event.type) {
      case 'node_status_change':
        if (event.node_id) {
          const existing = nodeStates.value.get(event.node_id)
          nodeStates.value.set(event.node_id, {
            node_id: event.node_id,
            status: (event.status ?? 'idle') as NodeStatus,
            timestamp: event.timestamp,
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
              timestamp: event.timestamp,
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

  // ─── 视图切换 ───

  function switchView(mode: 'card' | 'dag') {
    viewMode.value = mode
  }

  function selectNode(nodeId: string | null) {
    selectedNodeId.value = nodeId
  }

  function startEditing(nodeId: string | null) {
    editingNodeId.value = nodeId
  }

  function resetNodeStates() {
    nodeStates.value.clear()
    edgeFlows.value.clear()
  }

  // ─── 更新节点位置（拖拽后） ───

  function updateNodePosition(nodeId: string, position: { x: number; y: number }) {
    if (!dagDefinition.value) return
    const node = dagDefinition.value.nodes.find(n => n.id === nodeId)
    if (node) {
      node.position = position
      hasUnsavedChanges.value = true
    }
  }

  return {
    // State
    dagDefinition,
    dagVersions,
    nodeTypeRegistry,
    nodeStates,
    edgeFlows,
    selectedNodeId,
    editingNodeId,
    viewMode,
    isLoading,
    error,
    validationStatus,
    hasUnsavedChanges,

    // Computed
    vueFlowNodes,
    vueFlowEdges,
    dagStats,

    // Actions
    loadDAG,
    saveDAG,
    loadVersions,
    loadNodeTypeRegistry,
    toggleNode,
    updateNodeConfig,
    validateDAG,
    handleSSEEvent,
    switchView,
    selectNode,
    startEditing,
    resetNodeStates,
    updateNodePosition,
  }
})
