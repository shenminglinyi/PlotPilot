/**
 * DAG 运行状态管理 — 运行控制、历史记录、SSE 事件连接
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { DAGRunResult, DAGStatusResponse, NodeEvent, NodeStatus } from '@/types/dag'
import { dagApi } from '@/api/dag'
import { autopilotApi } from '@/api/autopilot'
import { runtimePerformance } from '@/config/performance'

export type DAGRunStatus = 'idle' | 'running' | 'stopping' | 'completed' | 'error'

export const useDAGRunStore = defineStore('dagRun', () => {
  // ─── 运行状态 ───
  const runStatus = ref<DAGRunStatus>('idle')
  const currentRunId = ref<string | null>(null)
  const dagEnabled = ref(false)
  const currentVersion = ref(0)

  // ─── 节点运行时状态快照 ───
  const nodeStates = ref<Record<string, { status: NodeStatus; enabled: boolean }>>({})

  // ─── 运行历史 ───
  const runHistory = ref<DAGRunResult[]>([])
  const latestResult = ref<DAGRunResult | null>(null)

  // ─── SSE 连接 ───
  const sseConnected = ref(false)
  const sseError = ref<string | null>(null)
  let _eventSource: EventSource | null = null
  let _reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let _reconnectAttempts = 0

  // ─── 计算属性 ───
  const isRunning = computed(() => runStatus.value === 'running')
  const canStart = computed(() => runStatus.value === 'idle' || runStatus.value === 'completed' || runStatus.value === 'error')
  const canStop = computed(() => runStatus.value === 'running')

  // ─── 运行控制 ───

  async function startRun(novelId: string) {
    if (!canStart.value) return
    try {
      runStatus.value = 'running'
      const result = await dagApi.runDAG(novelId)
      currentRunId.value = result.novel_id
    } catch (e: unknown) {
      runStatus.value = 'error'
      sseError.value = e instanceof Error ? e.message : '启动运行失败'
      throw e
    }
  }

  async function stopRun(novelId: string) {
    if (!canStop.value) return
    try {
      runStatus.value = 'stopping'
      await dagApi.stopDAG(novelId)
      runStatus.value = 'idle'
    } catch (e: unknown) {
      sseError.value = e instanceof Error ? e.message : '停止运行失败'
      // 即使停止失败，也标记为 idle 以避免 UI 卡住
      runStatus.value = 'idle'
    }
  }

  async function fetchStatus(novelId: string) {
    try {
      const status = await dagApi.getStatus(novelId)
      dagEnabled.value = status.dag_enabled
      currentVersion.value = status.current_version
      nodeStates.value = status.node_states

      // 如果有节点正在运行，标记运行状态
      const hasRunning = Object.values(status.node_states).some(
        s => s.status === 'running' || s.status === 'pending'
      )
      if (hasRunning && runStatus.value !== 'running') {
        runStatus.value = 'running'
      } else if (!hasRunning && runStatus.value === 'running') {
        runStatus.value = 'idle'
      }
    } catch {
      // 静默失败
    }
  }

  // ─── SSE 事件连接 ───

  function connectSSE(novelId: string, options: { resetReconnect?: boolean } = {}) {
    disconnectSSE({ resetReconnect: options.resetReconnect ?? true })

    // 构建 SSE URL（由 dagApi 兼容 Tauri 桌面模式）
    const url = dagApi.eventsUrl(novelId)

    try {
      const source = new EventSource(url)
      _eventSource = source
      sseConnected.value = false
      sseError.value = null

      source.onopen = () => {
        if (_eventSource !== source) return
        sseConnected.value = true
        sseError.value = null
        _reconnectAttempts = 0
      }

      source.onmessage = (event) => {
        if (_eventSource !== source) return
        try {
          const data = JSON.parse(event.data) as NodeEvent
          handleSSEMessage(data)
        } catch {
          // 忽略解析错误
        }
      }

      // 监听特定事件类型
      source.addEventListener('node_status_change', (event) => {
        if (_eventSource !== source) return
        try {
          const data = JSON.parse((event as MessageEvent).data) as NodeEvent
          handleNodeStatusChange(data)
        } catch { /* ignore */ }
      })

      source.addEventListener('node_output', (event) => {
        if (_eventSource !== source) return
        try {
          const data = JSON.parse((event as MessageEvent).data) as NodeEvent
          handleNodeOutput(data)
        } catch { /* ignore */ }
      })

      source.addEventListener('edge_data_flow', (event) => {
        if (_eventSource !== source) return
        try {
          const data = JSON.parse((event as MessageEvent).data) as NodeEvent
          handleEdgeFlow(data)
        } catch { /* ignore */ }
      })

      source.addEventListener('dag_run_complete', (event) => {
        if (_eventSource !== source) return
        try {
          const data = JSON.parse((event as MessageEvent).data) as DAGRunResult
          handleDAGRunComplete(data)
        } catch { /* ignore */ }
      })

      source.onerror = () => {
        if (_eventSource !== source) return
        source.close()
        _eventSource = null
        sseConnected.value = false
        // 自动重连
        scheduleReconnect(novelId)
      }
    } catch (e: unknown) {
      sseError.value = e instanceof Error ? e.message : 'SSE 连接失败'
      scheduleReconnect(novelId)
    }
  }

  function disconnectSSE(options: { resetReconnect?: boolean } = {}) {
    if (_eventSource) {
      _eventSource.close()
      _eventSource = null
    }
    if (_reconnectTimer) {
      clearTimeout(_reconnectTimer)
      _reconnectTimer = null
    }
    if (options.resetReconnect ?? true) {
      _reconnectAttempts = 0
    }
    sseConnected.value = false
  }

  function scheduleReconnect(novelId: string) {
    if (_reconnectTimer) return
    _reconnectAttempts += 1
    const perf = runtimePerformance.dagSse
    const delayMs = Math.min(
      perf.reconnectBaseDelayMs * (2 ** (_reconnectAttempts - 1)),
      perf.reconnectMaxDelayMs,
    )
    _reconnectTimer = setTimeout(() => {
      _reconnectTimer = null
      if (runStatus.value === 'running') {
        connectSSE(novelId, { resetReconnect: false })
      }
    }, delayMs)
  }

  // ─── SSE 事件处理回调 ───
  // 通过注册回调与 dagStore 解耦

  type SSECallback = (event: NodeEvent) => void
  type RunCompleteCallback = (result: DAGRunResult) => void

  const _nodeStatusCallbacks: SSECallback[] = []
  const _nodeOutputCallbacks: SSECallback[] = []
  const _edgeFlowCallbacks: SSECallback[] = []
  const _runCompleteCallbacks: RunCompleteCallback[] = []

  function removeCallback<T>(callbacks: T[], cb: T) {
    const ix = callbacks.indexOf(cb)
    if (ix >= 0) callbacks.splice(ix, 1)
  }

  function onNodeStatusChange(cb: SSECallback) {
    _nodeStatusCallbacks.push(cb)
    return () => removeCallback(_nodeStatusCallbacks, cb)
  }
  function onNodeOutput(cb: SSECallback) {
    _nodeOutputCallbacks.push(cb)
    return () => removeCallback(_nodeOutputCallbacks, cb)
  }
  function onEdgeFlow(cb: SSECallback) {
    _edgeFlowCallbacks.push(cb)
    return () => removeCallback(_edgeFlowCallbacks, cb)
  }
  function onRunComplete(cb: RunCompleteCallback) {
    _runCompleteCallbacks.push(cb)
    return () => removeCallback(_runCompleteCallbacks, cb)
  }

  function handleSSEMessage(event: NodeEvent) {
    // 通用消息分发
    switch (event.type) {
      case 'node_status_change':
        handleNodeStatusChange(event)
        break
      case 'node_output':
        handleNodeOutput(event)
        break
      case 'edge_data_flow':
        handleEdgeFlow(event)
        break
    }
  }

  function handleNodeStatusChange(event: NodeEvent) {
    // 更新本地节点状态
    if (event.node_id && event.status) {
      const existing = nodeStates.value[event.node_id] || { status: 'idle' as NodeStatus, enabled: true }
      nodeStates.value[event.node_id] = { ...existing, status: event.status }

      // 如果所有节点完成，标记 DAG 完成
      if (event.status === 'success' || event.status === 'error') {
        const allDone = Object.values(nodeStates.value).every(
          s => ['success', 'error', 'bypassed', 'disabled', 'completed'].includes(s.status)
        )
        if (allDone && runStatus.value === 'running') {
          runStatus.value = 'completed'
        }
      }
    }
    // 通知回调
    _nodeStatusCallbacks.forEach(cb => cb(event))
  }

  function handleNodeOutput(event: NodeEvent) {
    _nodeOutputCallbacks.forEach(cb => cb(event))
  }

  function handleEdgeFlow(event: NodeEvent) {
    _edgeFlowCallbacks.forEach(cb => cb(event))
  }

  function handleDAGRunComplete(result: DAGRunResult) {
    runStatus.value = result.status === 'completed' ? 'completed' : 'error'
    latestResult.value = result
    runHistory.value.unshift(result)
    // 只保留最近 20 条
    if (runHistory.value.length > 20) {
      runHistory.value = runHistory.value.slice(0, 20)
    }
    _runCompleteCallbacks.forEach(cb => cb(result))
  }

  // ─── 托管模式日志流连接（桥接到 DAG 节点状态） ───

  let _autopilotLogSource: EventSource | null = null
  let _autopilotLogCallback: ((data: { type: string; message: string; metadata?: Record<string, unknown> }) => void) | null = null

  function connectAutopilotLog(
    novelId: string,
    callback: (data: { type: string; message: string; metadata?: Record<string, unknown> }) => void,
  ) {
    disconnectAutopilotLog()
    _autopilotLogCallback = callback

    const url = autopilotApi.logStreamUrl(novelId)
    try {
      _autopilotLogSource = new EventSource(url)

      _autopilotLogSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (_autopilotLogCallback && data.type !== 'heartbeat' && data.type !== 'connected') {
            _autopilotLogCallback({
              type: data.type || 'log',
              message: data.message || '',
              metadata: data.metadata || data.meta || {},
            })
          }
        } catch {
          // 忽略解析错误
        }
      }

      _autopilotLogSource.onerror = () => {
        // 静默失败，不重连（DAG SSE 已有自己的重连机制）
      }
    } catch {
      // 连接失败，静默
    }
  }

  function disconnectAutopilotLog() {
    if (_autopilotLogSource) {
      _autopilotLogSource.close()
      _autopilotLogSource = null
    }
    _autopilotLogCallback = null
  }

  // ─── 重置 ───

  function resetForNovel(novelId: string) {
    runStatus.value = 'idle'
    currentRunId.value = null
    latestResult.value = null
    nodeStates.value = {}
    sseError.value = null
    disconnectSSE()
    disconnectAutopilotLog()
  }

  return {
    // State
    runStatus,
    currentRunId,
    dagEnabled,
    currentVersion,
    nodeStates,
    runHistory,
    latestResult,
    sseConnected,
    sseError,

    // Computed
    isRunning,
    canStart,
    canStop,

    // Actions
    startRun,
    stopRun,
    fetchStatus,
    connectSSE,
    disconnectSSE,
    resetForNovel,

    // Event callbacks
    onNodeStatusChange,
    onNodeOutput,
    onEdgeFlow,
    onRunComplete,

    // Autopilot log bridge
    connectAutopilotLog,
    disconnectAutopilotLog,
  }
})
