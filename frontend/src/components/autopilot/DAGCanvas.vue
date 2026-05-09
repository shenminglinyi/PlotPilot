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
      <Background :gap="20" :size="1" :style="{ backgroundColor: 'transparent' }" />
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
import { usePromptPlazaBridge } from '@/stores/promptPlazaBridge'
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
const plazaBridge = usePromptPlazaBridge()

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
    // ★ 双击节点 → 跳转提示词广场（而不是本地编辑器）
    const meta = dagStore.nodeTypeRegistry[node.type]
    if (meta?.is_configurable) {
      plazaBridge.openPromptInPlaza(node.type, true)
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
}

function handleConnect(params: Connection) {
  if (!params.source || !params.target) return

  const dag = dagStore.dagDefinition
  if (!dag) return

  const edgeCount = dag.edges.length + 1
  const edgeId = `edge_${String(edgeCount).padStart(2, '0')}_${params.source}_${params.target}`

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
  dagStore.saveDAG(props.novelId)
}

function handleEdgeUpdate(event: EdgeChangeEvent) {
  // TODO: 实现边更新逻辑
}

function handleNodesChange(changes: NodeChange[]) {
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
</style>
