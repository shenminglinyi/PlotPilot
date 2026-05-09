<template>
  <div class="dag-canvas">
    <VueFlow
      v-model:nodes="flowNodes"
      v-model:edges="flowEdges"
      :default-viewport="{ zoom: 0.8, x: 0, y: 0 }"
      :min-zoom="0.3"
      :max-zoom="2"
      :connect-on-click="false"
      fit-view-on-init
      @node-click="handleNodeClick"
      @node-double-click="handleNodeDoubleClick"
      @node-context-menu="handleNodeContextMenu"
      @connect="handleConnect"
      @edge-update="handleEdgeUpdate"
      @nodes-change="handleNodesChange"
    >
      <!-- 自定义节点类型 -->
      <template #node-dagCustom="nodeProps">
        <CustomNode v-bind="nodeProps" @contextmenu="handleCustomNodeContextmenu" />
      </template>

      <!-- 自定义边 -->
      <template #edge-custom="edgeProps">
        <CustomEdge v-bind="edgeProps" />
      </template>

      <!-- 背景 -->
      <Background :gap="20" :size="1" />
      <!-- 控制面板 -->
      <Controls position="bottom-right" />
      <!-- 小地图 -->
      <MiniMap position="bottom-left" :pannable="true" :zoomable="true" />
    </VueFlow>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { VueFlow, type Connection, type EdgeChangeEvent, type NodeChange } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import { useDAGStore } from '@/stores/dagStore'
import { useDAGRunStore } from '@/stores/dagRunStore'
import { useNodeEditorStore } from '@/stores/nodeEditorStore'
import { useDAGSSE } from '@/composables/useDAGSSE'
import CustomNode from './CustomNode.vue'
import CustomEdge from './CustomEdge.vue'

const props = defineProps<{
  novelId: string
}>()

const emit = defineEmits<{
  contextmenu: [event: MouseEvent, nodeId: string, enabled: boolean]
}>()

const dagStore = useDAGStore()
const runStore = useDAGRunStore()
const editorStore = useNodeEditorStore()

// SSE 连接（自动管理生命周期）
useDAGSSE(toRef(props, 'novelId'))

// ─── 响应式节点/边 ───

const flowNodes = computed({
  get: () => dagStore.vueFlowNodes,
  set: (val) => {
    // 更新节点位置
    for (const node of val) {
      dagStore.updateNodePosition(node.id, node.position)
    }
  },
})

const flowEdges = computed(() => dagStore.vueFlowEdges)

// ─── 事件处理 ───

function handleNodeClick(event: { node: { id: string } }) {
  dagStore.selectNode(event.node.id)
}

function handleNodeDoubleClick(event: { node: { id: string } }) {
  const nodeId = event.node.id
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === nodeId)
  if (node) {
    const meta = dagStore.nodeTypeRegistry[node.type]
    if (meta?.is_configurable) {
      editorStore.open(
        props.novelId,
        nodeId,
        node.config.prompt_template || meta?.prompt_template || '',
        node.config.prompt_variables || {},
      )
    }
  }
}

function handleNodeContextMenu(event: { event: MouseEvent; node: { id: string } }) {
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === event.node.id)
  if (node) {
    emit('contextmenu', event.event, node.id, node.enabled)
  }
}

function handleCustomNodeContextmenu(event: MouseEvent) {
  // CustomNode 内部触发 contextmenu 时的事件
  // 这个事件不携带 nodeId，需要通过其他方式获取
  // 主要的右键菜单通过 handleNodeContextMenu 处理
}

function handleConnect(params: Connection) {
  // 新建连线
  if (!params.source || !params.target) return

  const dag = dagStore.dagDefinition
  if (!dag) return

  // 生成新边 ID
  const edgeCount = dag.edges.length + 1
  const edgeId = `edge_${String(edgeCount).padStart(2, '0')}_${params.source}_${params.target}`

  // 添加新边到 DAG
  const newEdge = {
    id: edgeId,
    source: params.source,
    source_port: params.sourceHandle || undefined,
    target: params.target,
    target_port: params.targetHandle || undefined,
    condition: 'always' as const,
    animated: false,
  }

  dag.edges.push(newEdge)
  // 保存更新
  dagStore.saveDAG(props.novelId)
}

function handleEdgeUpdate(event: EdgeChangeEvent) {
  // 边更新（拖拽重新连接）
  // TODO: 实现边更新逻辑
}

function handleNodesChange(changes: NodeChange[]) {
  // 节点位置变化 — 只处理位置拖拽
  for (const change of changes) {
    if (change.type === 'position' && change.position) {
      dagStore.updateNodePosition(change.id, change.position)
    }
  }
}
</script>

<style scoped>
.dag-canvas {
  width: 100%;
  height: 100%;
}

:deep(.vue-flow) {
  background: var(--n-color-modal, #1a1a2e);
}

:deep(.vue-flow__minimap) {
  border-radius: 8px;
  overflow: hidden;
}

:deep(.vue-flow__controls) {
  border-radius: 8px;
  overflow: hidden;
}

/* 连接桩样式 */
:deep(.vue-flow__handle) {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
</style>
