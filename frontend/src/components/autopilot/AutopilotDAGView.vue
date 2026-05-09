<template>
  <div class="dag-view-container">
    <!-- 顶部工具栏 -->
    <DAGToolbar
      :novel-id="novelId"
      :view-mode="dagStore.viewMode"
      :dag-stats="dagStore.dagStats"
      :autopilot-status="autopilotStatus"
      :sse-connected="runStore.sseConnected"
      :has-unsaved-changes="dagStore.hasUnsavedChanges"
      @save="handleSave"
      @validate="handleValidate"
      @open-plaza="handleOpenPlaza"
    />

    <!-- DAG 画布 -->
    <div class="dag-canvas-wrapper">
      <DAGCanvas
        v-if="dagStore.dagDefinition"
        :novel-id="novelId"
        @contextmenu="handleCanvasContextMenu"
      />
      <div v-else-if="dagStore.isLoading" class="dag-loading">
        <n-spin size="large" />
        <span class="dag-loading-text">加载 DAG 画布...</span>
      </div>
      <div v-else-if="dagStore.error" class="dag-error">
        <n-result status="error" :title="dagStore.error">
          <template #footer>
            <n-button @click="dagStore.loadDAG(novelId)">重试</n-button>
          </template>
        </n-result>
      </div>
    </div>

    <!-- 右键菜单 -->
    <NodeContextMenu
      v-if="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :node-id="contextMenu.nodeId"
      :node-enabled="contextMenu.nodeEnabled"
      :node-type="contextMenu.nodeType"
      @close="contextMenu.visible = false"
      @edit="handleEditNode"
      @toggle="handleToggleNode"
      @rerun="handleRerunNode"
      @view-upstream="handleViewUpstream"
      @view-downstream="handleViewDownstream"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { useDAGStore } from '@/stores/dagStore'
import { useDAGRunStore } from '@/stores/dagRunStore'
import { usePromptPlazaBridge } from '@/stores/promptPlazaBridge'
import { dagApi } from '@/api/dag'
import DAGToolbar from './DAGToolbar.vue'
import DAGCanvas from './DAGCanvas.vue'
import NodeContextMenu from './NodeContextMenu.vue'

const props = defineProps<{
  novelId: string
}>()

const emit = defineEmits<{
  'desk-refresh': []
}>()

const dagStore = useDAGStore()
const runStore = useDAGRunStore()
const plazaBridge = usePromptPlazaBridge()
const message = useMessage()

// ★ 托管模式状态（从后端获取，DAG只是展示层）
const autopilotStatus = ref<'idle' | 'running' | 'paused' | 'completed' | 'error'>('idle')

// 右键菜单状态
const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  nodeId: '',
  nodeEnabled: true,
  nodeType: '',
})

onMounted(async () => {
  await dagStore.loadDAG(props.novelId)
  await dagStore.loadNodeTypeRegistry()
  await runStore.fetchStatus(props.novelId)
  await fetchAutopilotStatus()
})

// ★ 监听托管模式 SSE 日志更新状态
watch(() => runStore.runStatus, (status) => {
  if (status === 'running') {
    autopilotStatus.value = 'running'
  } else if (status === 'completed') {
    autopilotStatus.value = 'completed'
  } else if (status === 'error') {
    autopilotStatus.value = 'error'
  }
})

// ─── 工具栏事件 ───

async function handleSave() {
  await dagStore.saveDAG(props.novelId)
  message.success('DAG 保存成功')
}

async function handleValidate() {
  const result = await dagStore.validateDAG(props.novelId)
  if (result.is_valid) {
    message.success(result.summary)
  } else {
    message.error(result.summary)
  }
}

/** ★ 打开提示词广场 */
function handleOpenPlaza() {
  plazaBridge.openPromptInPlaza('', false)
}

// ─── 画布右键菜单 ───

function handleCanvasContextMenu(event: MouseEvent, nodeId: string, enabled: boolean) {
  event.preventDefault()
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === nodeId)
  contextMenu.visible = true
  contextMenu.x = event.clientX
  contextMenu.y = event.clientY
  contextMenu.nodeId = nodeId
  contextMenu.nodeEnabled = enabled
  contextMenu.nodeType = node?.type || ''

  const closeHandler = () => {
    contextMenu.visible = false
    document.removeEventListener('click', closeHandler)
    document.removeEventListener('contextmenu', closeHandler)
  }
  setTimeout(() => {
    document.addEventListener('click', closeHandler, { once: true })
    document.addEventListener('contextmenu', closeHandler, { once: true })
  }, 0)
}

// ─── 右键菜单事件 ───

/** ★ 编辑节点 → 跳转提示词广场 */
function handleEditNode(nodeId: string) {
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === nodeId)
  if (node) {
    plazaBridge.openPromptInPlaza(node.type, true)
  }
}

async function handleToggleNode(nodeId: string) {
  await dagStore.toggleNode(props.novelId, nodeId)
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === nodeId)
  message.success(node?.enabled ? '节点已启用' : '节点已禁用')
}

async function handleRerunNode(nodeId: string) {
  // ★ DAG 是纯展示层，"从此节点重跑"走的是托管模式
  message.info('提示：DAG 为可视化展示，重跑请使用全托管面板')
}

function handleViewUpstream(nodeId: string) {
  dagStore.selectNode(nodeId)
  const dag = dagStore.dagDefinition
  if (dag) {
    const predecessors = dag.get_predecessors(nodeId)
    if (predecessors.length === 0) {
      message.info(`${nodeId} 是入口节点，无上游`)
    } else {
      message.info(`上游节点: ${predecessors.join(', ')}`)
    }
  }
}

function handleViewDownstream(nodeId: string) {
  dagStore.selectNode(nodeId)
  const dag = dagStore.dagDefinition
  if (dag) {
    const successors = dag.get_successors(nodeId)
    if (successors.length === 0) {
      message.info(`${nodeId} 是终端节点，无下游`)
    } else {
      message.info(`下游节点: ${successors.join(', ')}`)
    }
  }
}

// ─── 获取托管模式状态 ───

async function fetchAutopilotStatus() {
  try {
    const { apiClient } = await import('@/api/config')
    const result = await apiClient.get(`/autopilot/${props.novelId}/status`) as Record<string, unknown>
    const status = String(result.autopilot_status || result.status || 'idle')
    if (['running', 'paused_for_review', 'completed', 'error'].includes(status)) {
      autopilotStatus.value = status === 'paused_for_review' ? 'paused' : status as typeof autopilotStatus.value
    } else {
      autopilotStatus.value = 'idle'
    }
  } catch {
    autopilotStatus.value = 'idle'
  }
}
</script>

<style scoped>
.dag-view-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--dag-canvas-bg);
}

.dag-canvas-wrapper {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.dag-loading,
.dag-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 16px;
}

.dag-loading-text {
  color: var(--app-text-muted);
  font-size: var(--font-size-sm);
}
</style>
