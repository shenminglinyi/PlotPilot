/**
 * DAG SSE 事件 composable — 自动连接/断开 + 与 store 联动
 *
 * 核心改进：同时监听 DAG 专用 SSE 和托管模式日志流，
 * 将托管进程的阶段变更/写作子步骤映射为 DAG 节点状态更新，
 * 实现「DAG 视图 = 托管模式实时仪表盘」的统一体验。
 *
 * 用法：
 *   const { connected, error } = useDAGSSE(novelId)
 */
import { onMounted, onUnmounted, watch, type Ref } from 'vue'
import { useDAGStore } from '@/stores/dagStore'
import { useDAGRunStore } from '@/stores/dagRunStore'
import type { NodeEvent, NodeStatus } from '@/types/dag'

// ─── 托管模式阶段 → DAG 节点类型映射 ───
const STAGE_NODE_MAP: Record<string, string> = {
  macro_planning: 'exec_planning',
  act_planning: 'exec_planning',
  writing: 'exec_writer',
  auditing: 'val_aftermath',
  paused_for_review: 'gw_review',
  completed: null,
}

// ─── 子步骤 → DAG 节点类型映射（更精细） ───
const SUBSTEP_NODE_MAP: Record<string, string> = {
  context_assembly: 'ctx_style',
  beat_magnification: 'exec_beat',
  llm_calling: 'exec_writer',
  soft_landing: 'exec_writer',
  persisting: 'exec_writer',
  continuity_check: 'val_tension',
  chapter_persist: 'exec_writer',
  audit_voice_check: 'val_style',
  audit_tension: 'val_tension',
  audit_aftermath: 'val_aftermath',
  audit_anti_ai: 'val_anti_ai',
  macro_planning: 'exec_planning',
  act_planning: 'exec_planning',
}

// ─── DAG 节点类型 → 托管模式阶段反向映射（初始加载） ───
const NODE_TYPE_STAGE_MAP: Record<string, string> = {
  exec_planning: 'macro_planning',
  exec_writer: 'writing',
  exec_beat: 'writing',
  exec_scene: 'writing',
  val_style: 'auditing',
  val_tension: 'auditing',
  val_aftermath: 'auditing',
  val_anti_ai: 'auditing',
  gw_review: 'paused_for_review',
  gw_circuit: 'auditing',
}

export function useDAGSSE(novelId: Ref<string>) {
  const dagStore = useDAGStore()
  const runStore = useDAGRunStore()

  // 注册 SSE 事件回调 → 转发到 dagStore
  runStore.onNodeStatusChange((event) => {
    dagStore.handleSSEEvent(event)
  })

  runStore.onNodeOutput((event) => {
    dagStore.handleSSEEvent(event)
  })

  runStore.onEdgeFlow((event) => {
    dagStore.handleSSEEvent(event)
  })

  runStore.onRunComplete(() => {
    dagStore.resetNodeStates()
  })

  // 自动连接/断开
  onMounted(() => {
    if (novelId.value) {
      runStore.connectSSE(novelId.value)
      // ★ 同时订阅托管模式日志流，桥接状态到 DAG
      runStore.connectAutopilotLog(novelId.value, handleAutopilotLogEvent)
      // ★ 初始同步：从托管状态恢复 DAG 节点状态
      syncFromAutopilotStatus(novelId.value)
    }
  })

  onUnmounted(() => {
    runStore.disconnectSSE()
    runStore.disconnectAutopilotLog()
  })

  // novelId 变化时重新连接
  watch(novelId, (newId, oldId) => {
    if (newId !== oldId) {
      runStore.disconnectSSE()
      runStore.disconnectAutopilotLog()
      if (newId) {
        runStore.connectSSE(newId)
        runStore.connectAutopilotLog(newId, handleAutopilotLogEvent)
        syncFromAutopilotStatus(newId)
      }
    }
  })

  // ─── 托管模式日志流 → DAG 节点状态桥接 ───

  function handleAutopilotLogEvent(data: {
    type: string
    message: string
    metadata?: Record<string, unknown>
  }) {
    const meta = data.metadata || ({} as Record<string, unknown>)
    const stage = String(meta.stage || meta.current_stage || '')
    const substep = String(meta.writing_substep || '')
    const novelIdVal = novelId.value

    // 1. 子步骤级映射（优先）
    if (substep && substep !== 'undefined') {
      const nodeType = SUBSTEP_NODE_MAP[substep]
      if (nodeType) {
        const nodeId = findNodeIdByType(nodeType)
        if (nodeId) {
          dagStore.handleSSEEvent({
            type: 'node_status_change',
            novel_id: novelIdVal,
            node_id: nodeId,
            timestamp: new Date().toISOString(),
            status: 'running' as NodeStatus,
            metrics: {
              progress: 0.5,
              ...(meta.accumulated_words ? { word_count: Number(meta.accumulated_words) } : {}),
              ...(meta.chapter_target_words ? { target_words: Number(meta.chapter_target_words) } : {}),
            },
          } as NodeEvent)
        }
      }
      return
    }

    // 2. 阶段级映射
    if (stage && stage !== 'undefined') {
      const nodeType = STAGE_NODE_MAP[stage]
      if (nodeType) {
        // 先将之前运行的节点标记为完成
        markPreviousRunningAsComplete()

        const nodeId = findNodeIdByType(nodeType)
        if (nodeId) {
          dagStore.handleSSEEvent({
            type: 'node_status_change',
            novel_id: novelIdVal,
            node_id: nodeId,
            timestamp: new Date().toISOString(),
            status: 'running' as NodeStatus,
          } as NodeEvent)
        }
      } else if (stage === 'completed') {
        // 全书完成：所有节点标记完成
        markAllNodesComplete()
      }
    }

    // 3. 节拍进度 → 更新 exec_writer 的进度和字数
    if (meta.current_beat_index_1based && meta.total_beats) {
      const writerNodeId = findNodeIdByType('exec_writer')
      if (writerNodeId) {
        const beatIdx = Number(meta.current_beat_index_1based)
        const totalBeats = Number(meta.total_beats)
        const accWords = Number(meta.accumulated_words || 0)
        const targetWords = Number(meta.chapter_target_words || 0)

        dagStore.handleSSEEvent({
          type: 'node_status_change',
          novel_id: novelIdVal,
          node_id: writerNodeId,
          timestamp: new Date().toISOString(),
          status: 'running' as NodeStatus,
          metrics: {
            progress: beatIdx / totalBeats,
            word_count: accWords,
            target_words: targetWords,
            beat_index: beatIdx,
            total_beats: totalBeats,
          },
        } as NodeEvent)
      }
    }

    // 4. 审计完成 → 标记对应验证节点完成
    if (data.type === 'log' && data.message) {
      const msg = data.message
      if (msg.includes('审计完成') || msg.includes('audit_complete')) {
        markValidationNodesComplete()
      }
      if (msg.includes('章节完成') || msg.includes('chapter_complete')) {
        // 单章完成：写作和验证节点都标记完成
        markAllNodesComplete()
      }
    }
  }

  // ─── 辅助方法 ───

  function findNodeIdByType(nodeType: string): string | null {
    const dag = dagStore.dagDefinition
    if (!dag) return null
    const node = dag.nodes.find(n => n.type === nodeType)
    return node?.id || null
  }

  function markPreviousRunningAsComplete() {
    const states = dagStore.nodeStates
    const dag = dagStore.dagDefinition
    if (!dag) return
    for (const [nodeId, state] of states.entries()) {
      if (state.status === 'running') {
        dagStore.handleSSEEvent({
          type: 'node_status_change',
          novel_id: novelId.value,
          node_id: nodeId,
          timestamp: new Date().toISOString(),
          status: 'success' as NodeStatus,
          duration_ms: state.duration_ms,
        } as NodeEvent)
      }
    }
  }

  function markValidationNodesComplete() {
    const dag = dagStore.dagDefinition
    if (!dag) return
    for (const node of dag.nodes) {
      if (node.type.startsWith('val_')) {
        const currentState = dagStore.nodeStates.get(node.id)
        if (currentState?.status === 'running') {
          dagStore.handleSSEEvent({
            type: 'node_status_change',
            novel_id: novelId.value,
            node_id: node.id,
            timestamp: new Date().toISOString(),
            status: 'success' as NodeStatus,
          } as NodeEvent)
        }
      }
    }
  }

  function markAllNodesComplete() {
    const dag = dagStore.dagDefinition
    if (!dag) return
    for (const node of dag.nodes) {
      if (node.enabled) {
        dagStore.handleSSEEvent({
          type: 'node_status_change',
          novel_id: novelId.value,
          node_id: node.id,
          timestamp: new Date().toISOString(),
          status: 'success' as NodeStatus,
        } as NodeEvent)
      }
    }
  }

  // ─── 初始同步：从托管状态恢复 DAG 节点状态 ───

  async function syncFromAutopilotStatus(nId: string) {
    try {
      const { dagApi } = await import('@/api/dag')
      const status = await dagApi.getStatus(nId)
      const dag = dagStore.dagDefinition
      if (!dag || !status.node_states) return

      // 根据当前阶段和节点状态恢复 DAG 画布上的节点运行状态
      for (const node of dag.nodes) {
        const nodeState = status.node_states[node.id]
        if (nodeState) {
          dagStore.handleSSEEvent({
            type: 'node_status_change',
            novel_id: nId,
            node_id: node.id,
            timestamp: new Date().toISOString(),
            status: nodeState.status as NodeStatus,
          } as NodeEvent)
        }
      }

      // ★ 如果当前正在运行，根据阶段映射激活对应节点
      if (status.dag_enabled && status.current_version > 0) {
        const sharedState = await fetchAutopilotSharedState(nId)
        if (sharedState?.autopilot_status === 'running') {
          const stage = String(sharedState.current_stage || 'writing')
          const nodeType = STAGE_NODE_MAP[stage]
          if (nodeType) {
            const nodeId = findNodeIdByType(nodeType)
            if (nodeId) {
              dagStore.handleSSEEvent({
                type: 'node_status_change',
                novel_id: nId,
                node_id: nodeId,
                timestamp: new Date().toISOString(),
                status: 'running' as NodeStatus,
              } as NodeEvent)
            }
          }
        }
      }
    } catch {
      // 静默失败
    }
  }

  async function fetchAutopilotSharedState(nId: string): Promise<Record<string, unknown> | null> {
    try {
      const { apiClient } = await import('@/api/config')
      const result = await apiClient.get(`/autopilot/${nId}/status`)
      return result as unknown as Record<string, unknown>
    } catch {
      return null
    }
  }

  return {
    connected: runStore.sseConnected,
    error: runStore.sseError,
  }
}
