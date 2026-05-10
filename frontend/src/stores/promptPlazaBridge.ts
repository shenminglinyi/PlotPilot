/**
 * PromptPlazaBridge — DAG ↔ 提示词广场联动桥
 *
 * 职责：
 * 1. DAG 节点类型 → CPMS node_key 映射（动态从注册表获取）
 * 2. 提供 openPromptInPlaza() 方法，供 DAG 节点调用
 * 3. 通过事件通知 PromptPlazaFAB 打开并选中指定提示词
 * 4. 提示词保存后回调通知 DAG 刷新
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useDAGStore } from '@/stores/dagStore'

// ─── DAG 节点类型 → CPMS 提示词节点 key 静态映射（兜底用）───
// 与后端各 Node 实现中 _WORKFLOW_*_NODE_KEY 及 CPMS 注册一致
export const DAG_TYPE_TO_CPMS_KEY: Record<string, string> = {
  // Context 注入
  ctx_blueprint: 'context-blueprint',
  ctx_foreshadow: 'context-foreshadow',
  ctx_voice: 'context-voice-style',
  ctx_memory: 'context-memory',
  ctx_debt: 'context-debt',

  // Execution 执行
  exec_planning: 'macro-planning',
  exec_writer: 'chapter-generation-main',
  exec_beat: 'autopilot-stream-beat',
  exec_scene: 'scene-director',

  // Validation 校验
  val_style: 'voice-drift',
  val_tension: 'tension-scoring',
  val_anti_ai: 'cliche-scan',
  val_foreshadow: 'foreshadow-check',
  val_narrative: 'chapter-aftermath',
  val_kg_infer: 'kg-inference',

  // Gateway 网关
  gw_circuit: 'circuit-breaker',
  gw_review: 'review-gateway',
  gw_condition: 'condition-gateway',
  gw_retry: 'retry-gateway',
}

/**
 * 反查：CPMS node_key → DAG 节点类型
 */
export const CPMS_KEY_TO_DAG_TYPE: Record<string, string> = Object.fromEntries(
  Object.entries(DAG_TYPE_TO_CPMS_KEY).map(([k, v]) => [v, k])
)

export const usePromptPlazaBridge = defineStore('promptPlazaBridge', () => {
  // 当前需要打开的 nodeKey（由 DAG 节点设置）
  const pendingNodeKey = ref<string | null>(null)
  // 是否需要打开广场（由 DAG 节点设置）
  const shouldOpenPlaza = ref(false)

  // ★ 提示词保存后回调（DAG 视图注册，用于刷新节点提示词）
  const onPlazaSaved = ref<((nodeKey: string) => void) | null>(null)

  /**
   * 动态映射：优先从注册表 meta.cpms_node_key 获取，兜底用静态映射
   */
  function getCpmsKey(dagNodeType: string): string | null {
    const dagStore = useDAGStore()
    const meta = dagStore.nodeTypeRegistry[dagNodeType]
    // ★ 优先从注册表元数据动态获取
    if (meta?.cpms_node_key) {
      return meta.cpms_node_key
    }
    // 兜底静态映射
    return DAG_TYPE_TO_CPMS_KEY[dagNodeType] || null
  }

  /**
   * 打开提示词广场并选中指定节点
   * @param nodeKey CPMS node_key 或 DAG 节点类型
   * @param isDagType 如果传入的是 DAG 节点类型而非 CPMS key，设为 true
   */
  function openPromptInPlaza(nodeKey: string, isDagType = false) {
    const cpmsKey = isDagType ? getCpmsKey(nodeKey) : nodeKey
    if (cpmsKey) {
      pendingNodeKey.value = cpmsKey
    } else {
      // 即使找不到映射，也打开广场（用户可以自行搜索）
      pendingNodeKey.value = nodeKey
    }
    shouldOpenPlaza.value = true
  }

  /**
   * 消费打开请求（由 PromptPlazaFAB 调用）
   */
  function consumeOpenRequest() {
    const key = pendingNodeKey.value
    shouldOpenPlaza.value = false
    pendingNodeKey.value = null
    return key
  }

  /**
   * ★ 注册提示词保存回调（由 DAG 视图调用）
   */
  function setOnPlazaSaved(callback: (nodeKey: string) => void) {
    onPlazaSaved.value = callback
  }

  /**
   * ★ 提示词广场保存后通知 DAG（由 PromptDetailPanel 调用）
   */
  function notifyPromptSaved(nodeKey: string) {
    if (onPlazaSaved.value) {
      onPlazaSaved.value(nodeKey)
    }
  }

  return {
    pendingNodeKey,
    shouldOpenPlaza,
    getCpmsKey,
    openPromptInPlaza,
    consumeOpenRequest,
    setOnPlazaSaved,
    notifyPromptSaved,
  }
})
