/**
 * PromptPlazaBridge — DAG ↔ 提示词广场联动桥
 *
 * 职责：
 * 1. DAG 节点类型 → CPMS node_key：来自后端 ``NodeMeta.cpms_node_key`` 与 ``GET /dag/registry/linkage``
 * 2. 提供 openPromptInPlaza() 方法，供 DAG 节点调用
 * 3. 通过事件通知 PromptPlazaFAB 打开并选中指定提示词
 * 4. 提示词保存后回调通知 DAG 刷新
 *
 * 修改 CPMS 映射：只改后端节点 meta.cpms_node_key；前端不维护影子映射。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useDAGStore } from '@/stores/dagStore'

export const usePromptPlazaBridge = defineStore('promptPlazaBridge', () => {
  // 当前需要打开的 nodeKey（由 DAG 节点设置）
  const pendingNodeKey = ref<string | null>(null)
  // 是否需要打开广场（由 DAG 节点设置）
  const shouldOpenPlaza = ref(false)

  // ★ 提示词保存后回调（DAG 视图注册，用于刷新节点提示词）
  const onPlazaSaved = ref<((nodeKey: string) => void) | null>(null)

  /**
   * 动态映射：注册表 meta → linkage 表。
   */
  function getCpmsKey(dagNodeType: string): string | null {
    const dagStore = useDAGStore()
    const meta = dagStore.nodeTypeRegistry[dagNodeType]
    if (meta?.cpms_node_key) {
      return meta.cpms_node_key
    }
    const row = dagStore.registryLinkage?.nodes.find(n => n.node_type === dagNodeType)
    if (row?.cpms_node_key) {
      return row.cpms_node_key
    }
    const fromRegistryIndex = dagStore.registryLinkage?.registry_cpms_by_type[dagNodeType]?.cpms_node_key
    if (fromRegistryIndex) {
      return fromRegistryIndex
    }
    return null
  }

  /** 按画布 node_id 解析 CPMS（默认 DAG 上 id 与 type 常一致，仍走 type 映射） */
  function getCpmsKeyForNodeId(nodeId: string): string | null {
    const dagStore = useDAGStore()
    const dag = dagStore.dagDefinition
    if (!dag) return null
    const node = dag.nodes.find(n => n.id === nodeId)
    return node ? getCpmsKey(node.type) : null
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
    getCpmsKeyForNodeId,
    openPromptInPlaza,
    consumeOpenRequest,
    setOnPlazaSaved,
    notifyPromptSaved,
  }
})
