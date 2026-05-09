/**
 * DAG SSE 事件 composable — 自动连接/断开 + 与 store 联动
 *
 * 用法：
 *   const { connected, error } = useDAGSSE(novelId)
 */
import { onMounted, onUnmounted, watch, type Ref } from 'vue'
import { useDAGStore } from '@/stores/dagStore'
import { useDAGRunStore } from '@/stores/dagRunStore'

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
    }
  })

  onUnmounted(() => {
    runStore.disconnectSSE()
  })

  // novelId 变化时重新连接
  watch(novelId, (newId, oldId) => {
    if (newId !== oldId) {
      runStore.disconnectSSE()
      if (newId) {
        runStore.connectSSE(newId)
      }
    }
  })

  return {
    connected: runStore.sseConnected,
    error: runStore.sseError,
  }
}
