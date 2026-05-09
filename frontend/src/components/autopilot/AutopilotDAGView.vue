<template>
  <div class="dag-view-container">
    <!-- 顶部工具栏 -->
    <DAGToolbar
      :novel-id="novelId"
      :view-mode="dagStore.viewMode"
      :dag-stats="dagStore.dagStats"
      :run-status="runStore.runStatus"
      :sse-connected="runStore.sseConnected"
      @switch-view="dagStore.switchView"
      @save="handleSave"
      @validate="handleValidate"
      @run="handleRun"
      @stop="handleStop"
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
        <span>加载 DAG 画布...</span>
      </div>
      <div v-else-if="dagStore.error" class="dag-error">
        <n-result status="error" :title="dagStore.error">
          <template #footer>
            <n-button @click="dagStore.loadDAG(novelId)">重试</n-button>
          </template>
        </n-result>
      </div>
    </div>

    <!-- 节点编辑器抽屉 -->
    <NodeEditorDrawer />

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
import { onMounted, reactive } from 'vue'
import { useMessage } from 'naive-ui'
import { useDAGStore } from '@/stores/dagStore'
import { useDAGRunStore } from '@/stores/dagRunStore'
import { useNodeEditorStore } from '@/stores/nodeEditorStore'
import { dagApi } from '@/api/dag'
import DAGToolbar from './DAGToolbar.vue'
import DAGCanvas from './DAGCanvas.vue'
import NodeEditorDrawer from './NodeEditorDrawer.vue'
import NodeContextMenu from './NodeContextMenu.vue'

const props = defineProps<{
  novelId: string
}>()

const emit = defineEmits<{
  'desk-refresh': []
}>()

const dagStore = useDAGStore()
const runStore = useDAGRunStore()
const editorStore = useNodeEditorStore()
const message = useMessage()

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

async function handleRun() {
  try {
    await runStore.startRun(props.novelId)
    message.info('DAG 运行已启动')
  } catch {
    message.error('启动 DAG 运行失败')
  }
}

async function handleStop() {
  try {
    await runStore.stopRun(props.novelId)
    message.info('DAG 运行已停止')
    emit('desk-refresh')
  } catch {
    message.error('停止 DAG 运行失败')
  }
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

  // 点击其他地方关闭菜单
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

function handleEditNode(nodeId: string) {
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === nodeId)
  if (node) {
    const meta = dagStore.nodeTypeRegistry[node.type]
    editorStore.open(
      props.novelId,
      nodeId,
      node.config.prompt_template || meta?.prompt_template || '',
      node.config.prompt_variables || {},
    )
  }
}

async function handleToggleNode(nodeId: string) {
  await dagStore.toggleNode(props.novelId, nodeId)
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === nodeId)
  message.success(node?.enabled ? '节点已启用' : '节点已禁用')
}

async function handleRerunNode(nodeId: string) {
  try {
    await dagApi.rerunFromNode(props.novelId, nodeId)
    message.info(`从节点 ${nodeId} 重新执行已启动`)
  } catch {
    message.error('重新执行失败')
  }
}

function handleViewUpstream(nodeId: string) {
  dagStore.selectNode(nodeId)
  // 高亮上游节点
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
  // 高亮下游节点
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
</script>

<style scoped>
.dag-view-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--n-color);
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
</style>
