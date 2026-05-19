<template>
  <div class="dag-canvas">
    <VueFlow
      v-model:nodes="flowNodes"
      v-model:edges="flowEdges"
      :default-viewport="{ zoom: 0.8, x: 0, y: 0 }"
      :min-zoom="0.3"
      :max-zoom="2"
      :connect-on-click="false"
      :nodes-draggable="false"
      :nodes-connectable="false"
      :edges-deletable="false"
      :elements-selectable="false"
      fit-view-on-init
      @node-click="handleNodeClick"
      @node-context-menu="handleNodeContextMenu as any"
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
      <Background :gap="20" :size="1" :style="{ backgroundColor: 'transparent' }" />
      <!-- 控制面板 -->
      <Controls position="bottom-right" />
      <!-- 小地图 -->
      <MiniMap position="bottom-left" :pannable="true" :zoomable="true" />
    </VueFlow>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { VueFlow } from '@vue-flow/core'
import type { Edge, Node } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import { useDAGStore } from '@/stores/dagStore'
import CustomNode from './CustomNode.vue'
import CustomEdge from './CustomEdge.vue'

const props = defineProps<{
  novelId: string
}>()

const emit = defineEmits<{
  contextmenu: [event: MouseEvent, nodeId: string, enabled: boolean]
  /** ★ 单击节点 → 打开详情弹窗 */
  nodeDetail: [nodeId: string]
}>()

const dagStore = useDAGStore()

/** Pinia 里是只读 computed；Vue Flow 的 v-model 会写入节点/边，必须用可写 ref 承接再单向从 Store 同步 */
const flowNodes = ref<Node[]>([])
const flowEdges = ref<Edge[]>([])

function cloneNodesForFlow(nodes: Node[]): Node[] {
  return nodes.map((n) => ({
    ...n,
    position: { ...n.position },
    data: n.data != null && typeof n.data === 'object' ? { ...(n.data as object) } : n.data,
  }))
}

function cloneEdgesForFlow(edges: Edge[]): Edge[] {
  return edges.map((e) => ({
    ...e,
    style: e.style != null && typeof e.style === 'object' ? { ...(e.style as object) } : e.style,
    data: e.data != null && typeof e.data === 'object' ? { ...(e.data as object) } : e.data,
  }))
}

watch(
  () => dagStore.vueFlowNodes,
  (next) => {
    flowNodes.value = cloneNodesForFlow(next as Node[])
  },
  { immediate: true },
)

watch(
  () => dagStore.vueFlowEdges,
  (next) => {
    flowEdges.value = cloneEdgesForFlow(next as Edge[])
  },
  { immediate: true },
)

// SSE / 托管日志桥接在 AutopilotWorkspace 中统一挂载，避免切页时断开导致节点状态卡住

// ─── 事件处理 ───

/** ★ 单击节点 → 直接打开详情弹窗（仿 Dify） */
function handleNodeClick(event: { node: { id: string } }) {
  dagStore.selectNode(event.node.id)
  emit('nodeDetail', event.node.id)
}

function handleNodeContextMenu(event: any) {
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === event.node.id)
  if (node) {
    emit('contextmenu', event.event, node.id, node.enabled)
  }
}

function handleCustomNodeContextmenu(event: MouseEvent) {
  // CustomNode 内部触发 contextmenu 时的事件
}
</script>

<style scoped>
.dag-canvas {
  width: 100%;
  height: 100%;
  background: var(--dag-canvas-bg);
}

/* ── Vue Flow 画布主体 ── */
:deep(.vue-flow) {
  background: var(--dag-canvas-bg);
}

/* ── 背景网格点 ── */
:deep(.vue-flow__background) {
  background: transparent;
}
:deep(.vue-flow__background line) {
  stroke: var(--dag-canvas-grid);
}

/* ── 小地图 ── */
:deep(.vue-flow__minimap) {
  border-radius: var(--app-radius-sm);
  overflow: hidden;
  border: 1px solid var(--app-border);
  background: var(--dag-node-bg);
  box-shadow: var(--app-shadow-md);
}

/* ── 控制面板 ── */
:deep(.vue-flow__controls) {
  border-radius: var(--app-radius-sm);
  overflow: hidden;
  border: 1px solid var(--app-border);
  background: var(--dag-toolbar-bg);
  box-shadow: var(--app-shadow-md);
}
:deep(.vue-flow__controls-button) {
  background: var(--dag-toolbar-bg);
  border-bottom: 1px solid var(--app-divider);
  fill: var(--app-text-secondary);
}
:deep(.vue-flow__controls-button:hover) {
  background: var(--dag-menu-hover);
}
:deep(.vue-flow__controls-button svg) {
  fill: var(--app-text-secondary);
}

/* ── 连接桩（Handle） ── */
:deep(.vue-flow__handle) {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 2px solid var(--dag-node-bg);
}

/* ── 连线拖拽预览 ── */
:deep(.vue-flow__connection-line) {
  stroke: var(--color-brand);
  stroke-width: 2;
}

/* ── 选中框 ── */
:deep(.vue-flow__selection) {
  border: 1px dashed var(--color-brand);
  background: var(--color-brand-light);
}

/* ── 画布视口过渡 ── */
:deep(.vue-flow__transformationpane) {
  transition: none;
}

/* 控件/小地图沉在工具栏之下，避免与顶栏视觉上「叠在一起」 */
:deep(.vue-flow__panel) {
  z-index: 4;
}
</style>
