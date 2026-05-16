/**
 * DAG SSE 事件 composable — 性能优化版本
 *
 * 核心优化：
 * 1. 消息节流：100ms 批量处理，避免高频更新
 * 2. 批量处理：合并多个事件，减少渲染次数
 * 3. 智能重连：指数退避，避免连接风暴
 * 4. 性能监控：记录指标，自动告警
 */
import { onMounted, onUnmounted, watch, type Ref } from 'vue'
import { useDAGStore } from '@/stores/dagStore'
import { useDAGRunStore } from '@/stores/dagRunStore'
import type { NodeEvent, NodeStatus } from '@/types/dag'
import { resolveAutopilotLogToNodeType } from '@/policies/autopilotDagLogBridge'

// ─── 性能配置 ───

/** 消息节流间隔（ms）*/
const MESSAGE_THROTTLE_MS = 100

/** 批量处理最大队列长度 */
const MAX_QUEUE_SIZE = 50

/** SSE 重连基础延迟（ms）*/
const RECONNECT_BASE_DELAY_MS = 1000

/** SSE 重连最大延迟（ms）*/
const RECONNECT_MAX_DELAY_MS = 30000

/** 性能监控阈值 */
const PERF_THRESHOLDS = {
  queueOverflow: 50,
  eventDropRate: 0.1,
  renderTime: 100,
}

export function useDAGSSE(novelId: Ref<string>) {
  const dagStore = useDAGStore()
  const runStore = useDAGRunStore()
  const isDev = import.meta.env.DEV

  /** DAG 版本变化时重建 type→id，避免每条日志 O(n) 扫描 nodes */
  let typeToIdCacheVersion = -1
  let typeToIdCache: Map<string, string> | null = null

  // ─── 消息队列与节流处理 ───

  /** 消息队列 */
  const messageQueue: NodeEvent[] = []

  /** 节流定时器 */
  let throttleTimer: ReturnType<typeof setTimeout> | null = null

  /** 重连计数器 */
  let reconnectAttempts = 0

  /** 性能指标 */
  const perfMetrics = {
    eventsReceived: 0,
    eventsProcessed: 0,
    eventsDropped: 0,
    batchCount: 0,
    avgBatchSize: 0,
    maxQueueSize: 0,
  }

  /**
   * 推入消息到队列
   */
  function enqueueEvent(event: NodeEvent) {
    perfMetrics.eventsReceived++

    // 队列溢出保护
    if (messageQueue.length >= MAX_QUEUE_SIZE) {
      perfMetrics.eventsDropped++

      // 丢弃最旧的消息
      messageQueue.shift()

      // 记录告警
      if (isDev && perfMetrics.eventsDropped % 10 === 0) {
        console.warn(`[SSE] 消息队列溢出，已丢弃 ${perfMetrics.eventsDropped} 条消息`)
      }
    }

    messageQueue.push(event)
    perfMetrics.maxQueueSize = Math.max(perfMetrics.maxQueueSize, messageQueue.length)

    // 触发节流处理
    scheduleFlush()
  }

  /**
   * 调度队列刷新（节流）
   */
  function scheduleFlush() {
    if (throttleTimer) return

    throttleTimer = setTimeout(() => {
      flushQueue()
      throttleTimer = null
    }, MESSAGE_THROTTLE_MS)
  }

  /**
   * 刷新队列（批量处理）
   */
  function flushQueue() {
    if (messageQueue.length === 0) return

    const batchSize = messageQueue.length
    perfMetrics.batchCount++
    perfMetrics.avgBatchSize =
      (perfMetrics.avgBatchSize * (perfMetrics.batchCount - 1) + batchSize) /
      perfMetrics.batchCount

    // 批量处理消息
    const batch = messageQueue.splice(0, messageQueue.length)

    // 合并同类事件（优化）
    const mergedEvents = mergeEvents(batch)

    // 批量更新 store
    for (const event of mergedEvents) {
      try {
        dagStore.handleSSEEvent(event)
        perfMetrics.eventsProcessed++
      } catch (error) {
        console.error('[SSE] 处理事件失败:', error, event)
      }
    }

    // 性能监控
    if (isDev && batchSize > PERF_THRESHOLDS.queueOverflow) {
      console.warn(`[SSE] 批量处理 ${batchSize} 条消息，超过阈值 ${PERF_THRESHOLDS.queueOverflow}`)
    }
  }

  /**
   * 合并同类事件（优化渲染）
   */
  function mergeEvents(events: NodeEvent[]): NodeEvent[] {
    const eventMap = new Map<string, NodeEvent>()

    for (const event of events) {
      const key = `${event.type}:${event.node_id}`

      // 只保留最新的事件
      eventMap.set(key, event)
    }

    return Array.from(eventMap.values())
  }

  /**
   * 智能重连（指数退避）
   */
  function smartReconnect() {
    reconnectAttempts++

    // 指数退避
    const delay = Math.min(
      RECONNECT_BASE_DELAY_MS * Math.pow(2, reconnectAttempts - 1),
      RECONNECT_MAX_DELAY_MS
    )

    if (isDev) {
      console.log(`[SSE] 将在 ${delay}ms 后重连（第 ${reconnectAttempts} 次）`)
    }

    setTimeout(() => {
      if (novelId.value) {
        runStore.connectSSE(novelId.value)
        runStore.connectAutopilotLog(novelId.value, handleAutopilotLogEvent)
      }
    }, delay)
  }

  // ─── 注册回调（使用优化的批量处理）───

  runStore.onNodeStatusChange((event) => {
    enqueueEvent(event)
  })

  runStore.onNodeOutput((event) => {
    enqueueEvent(event)
  })

  runStore.onEdgeFlow((event) => {
    enqueueEvent(event)
  })

  runStore.onRunComplete(() => {
    // 立即刷新队列
    flushQueue()
    dagStore.resetNodeStates()
  })

  // SSE 连接状态监控
  watch(() => runStore.sseConnected, (connected) => {
    if (connected) {
      // 连接成功，重置重连计数
      reconnectAttempts = 0
      if (isDev) {
        console.log('[SSE] 连接成功')
      }
    } else {
      // 连接断开，尝试重连
      if (isDev) {
        console.warn('[SSE] 连接断开')
      }
      if (runStore.runStatus === 'running') {
        smartReconnect()
      }
    }
  })

  // ─── 生命周期 ───

  onMounted(() => {
    if (novelId.value) {
      runStore.connectSSE(novelId.value)
      runStore.connectAutopilotLog(novelId.value, handleAutopilotLogEvent)
      syncFromAutopilotStatus(novelId.value)
    }
  })

  onUnmounted(() => {
    // 清理定时器
    if (throttleTimer) {
      clearTimeout(throttleTimer)
      throttleTimer = null
    }

    // 刷新剩余消息
    flushQueue()

    runStore.disconnectSSE()
    runStore.disconnectAutopilotLog()

    // 输出性能指标（仅开发环境，避免生产控制台噪音）
    if (isDev && perfMetrics.eventsReceived > 0) {
      console.log('[SSE] 性能指标:', {
        ...perfMetrics,
        dropRate: `${((perfMetrics.eventsDropped / perfMetrics.eventsReceived) * 100).toFixed(2)}%`,
        avgBatchSize: perfMetrics.avgBatchSize.toFixed(2),
      })
    }
  })

  // novelId 变化时重新连接
  watch(novelId, (newId, oldId) => {
    if (newId !== oldId) {
      // 刷新队列
      flushQueue()

      runStore.disconnectSSE()
      runStore.disconnectAutopilotLog()

      if (newId) {
        reconnectAttempts = 0
        runStore.connectSSE(newId)
        runStore.connectAutopilotLog(newId, handleAutopilotLogEvent)
        syncFromAutopilotStatus(newId)
      }
    }
  })

  // ─── 托管模式日志流 → DAG 节点状态桥接（保持原有逻辑）───

  function handleAutopilotLogEvent(data: {
    type: string
    message: string
    metadata?: Record<string, unknown>
  }) {
    const meta = data.metadata || ({} as Record<string, unknown>)
    const stage = String(meta.stage || meta.current_stage || '')
    const substep = String(meta.writing_substep || '')
    const novelIdVal = novelId.value

    const subNorm = substep && substep !== 'undefined' ? substep : ''
    if (subNorm) {
      const nodeType = resolveAutopilotLogToNodeType(stage, subNorm)
      if (nodeType) {
        const nodeId = findNodeIdByType(nodeType)
        if (nodeId) {
          enqueueEvent({
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

    if (stage && stage !== 'undefined') {
      const nodeType = resolveAutopilotLogToNodeType(stage, '')
      if (nodeType) {
        markPreviousRunningAsComplete()

        const nodeId = findNodeIdByType(nodeType)
        if (nodeId) {
          enqueueEvent({
            type: 'node_status_change',
            novel_id: novelIdVal,
            node_id: nodeId,
            timestamp: new Date().toISOString(),
            status: 'running' as NodeStatus,
          } as NodeEvent)
        }
      } else if (stage === 'completed') {
        markAllNodesComplete()
      }
    }

    if (meta.current_beat_index_1based && meta.total_beats) {
      const writerNodeId = findNodeIdByType('exec_writer')
      if (writerNodeId) {
        const beatIdx = Number(meta.current_beat_index_1based)
        const totalBeats = Number(meta.total_beats)
        const accWords = Number(meta.accumulated_words || 0)
        const targetWords = Number(meta.chapter_target_words || 0)

        enqueueEvent({
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

    if (data.type === 'log' && data.message) {
      const msg = data.message
      if (msg.includes('审计完成') || msg.includes('audit_complete')) {
        markValidationNodesComplete()
      }
      if (msg.includes('章节完成') || msg.includes('chapter_complete')) {
        markAllNodesComplete()
      }
    }
  }

  function findNodeIdByType(nodeType: string): string | null {
    const dag = dagStore.dagDefinition
    if (!dag) return null
    const ver = dag.version ?? 0
    if (typeToIdCache === null || ver !== typeToIdCacheVersion) {
      const m = new Map<string, string>()
      for (const n of dag.nodes) {
        if (!m.has(n.type)) m.set(n.type, n.id)
      }
      typeToIdCache = m
      typeToIdCacheVersion = ver
    }
    return typeToIdCache.get(nodeType) ?? null
  }

  function markPreviousRunningAsComplete() {
    const states = dagStore.nodeStates
    const dag = dagStore.dagDefinition
    if (!dag) return
    for (const [nodeId, state] of states.entries()) {
      if (state.status === 'running') {
        enqueueEvent({
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
          enqueueEvent({
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
        enqueueEvent({
          type: 'node_status_change',
          novel_id: novelId.value,
          node_id: node.id,
          timestamp: new Date().toISOString(),
          status: 'success' as NodeStatus,
        } as NodeEvent)
      }
    }
  }

  async function syncFromAutopilotStatus(nId: string) {
    try {
      const { dagApi } = await import('@/api/dag')
      const status = await dagApi.getStatus(nId)
      const dag = dagStore.dagDefinition
      if (!dag || !status.node_states) return

      for (const node of dag.nodes) {
        const nodeState = status.node_states[node.id]
        if (nodeState) {
          enqueueEvent({
            type: 'node_status_change',
            novel_id: nId,
            node_id: node.id,
            timestamp: new Date().toISOString(),
            status: nodeState.status as NodeStatus,
          } as NodeEvent)
        }
      }

    } catch {
      // 静默失败
    }
  }

  return {
    connected: runStore.sseConnected,
    error: runStore.sseError,
    perfMetrics,  // 暴露性能指标
  }
}
