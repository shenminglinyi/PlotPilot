<template>
  <div class="dag-view-container">
    <!-- 顶部工具栏（纯展示状态） -->
    <DAGToolbar
      :novel-id="novelId"
      :dag-stats="dagStore.dagStats"
      :autopilot-status="autopilotStatus"
      :sse-connected="runStore.sseConnected"
      @switch-to-card="handleSwitchToCard"
    />

    <div v-if="dagStore.registryLinkageFailed" class="dag-banner">
      <n-alert type="warning" show-icon :bordered="false">
        <template #header>联动数据未完全加载</template>
        无法拉取「注册表联动」接口，已用本地注册表推断节点元数据；提示词广场映射可能不完整。
        <n-button text type="primary" size="tiny" style="margin-left: 8px" @click="retryHydrate">立即重试</n-button>
      </n-alert>
    </div>
    <div v-else-if="dagStore.registryGaps.length > 0" class="dag-banner">
      <n-alert type="error" show-icon :bordered="false">
        <template #header>有节点类型未在引擎中注册</template>
        以下画布节点在 NodeRegistry 中无实现，请在后端补充对应节点类并 import 到
        <code>application/engine/dag/nodes/__init__.py</code>：
        <span class="gap-list">{{ gapSummary }}</span>
      </n-alert>
    </div>

    <!-- DAG 画布 -->
    <div class="dag-canvas-wrapper">
      <DAGCanvas
        v-if="dagStore.dagDefinition"
        :novel-id="novelId"
        @contextmenu="handleCanvasContextMenu"
        @node-detail="handleNodeDetail"
      />
      <div v-else-if="dagStore.isLoading" class="dag-loading">
        <n-spin size="large" />
        <span class="dag-loading-text">正在加载 DAG 定义、节点注册表与联动数据…</span>
      </div>
      <div v-else-if="dagStore.error" class="dag-error">
        <n-result status="error" :title="dagStore.error">
          <template #footer>
            <n-button type="primary" @click="retryHydrate">重新加载 DAG</n-button>
          </template>
        </n-result>
      </div>
    </div>

    <!-- 右键菜单（精简） -->
    <NodeContextMenu
      v-if="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :node-id="contextMenu.nodeId"
      :node-enabled="contextMenu.nodeEnabled"
      :node-type="contextMenu.nodeType"
      @close="contextMenu.visible = false"
      @detail="handleNodeDetail"
      @toggle="handleToggleNode"
    />

    <!-- ★ 节点详情弹窗（主界面居中弹窗，仿 Dify） -->
    <NodeDetailPanel
      v-model:show="detailPanelVisible"
      :node-id="selectedDetailNodeId"
      :novel-id="novelId"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { useDAGStore } from '@/stores/dagStore'
import { useDAGRunStore } from '@/stores/dagRunStore'
import DAGToolbar from './DAGToolbar.vue'
import DAGCanvas from './DAGCanvas.vue'
import NodeContextMenu from './NodeContextMenu.vue'
import NodeDetailPanel from './NodeDetailPanel.vue'

const props = defineProps<{
  novelId: string
}>()

const dagStore = useDAGStore()
const runStore = useDAGRunStore()
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

// ★ 节点详情弹窗
const detailPanelVisible = ref(false)
const selectedDetailNodeId = ref<string | null>(null)

const gapSummary = computed(() =>
  dagStore.registryGaps.map(g => `${g.node_id} (${g.node_type})`).join('、'),
)

async function retryHydrate() {
  await dagStore.hydrateDagForNovel(props.novelId)
  await runStore.fetchStatus(props.novelId)
  await fetchAutopilotStatus()
}

onMounted(async () => {
  await dagStore.hydrateDagForNovel(props.novelId)
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

// ─── 事件处理 ───

/** ★ 单击节点 / 右键菜单"查看详情" → 打开主界面弹窗 */
function handleNodeDetail(nodeId: string) {
  selectedDetailNodeId.value = nodeId
  detailPanelVisible.value = true
}

async function handleToggleNode(nodeId: string) {
  await dagStore.toggleNode(props.novelId, nodeId)
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === nodeId)
  message.success(node?.enabled ? '节点已启用' : '节点已禁用')
}

/** ★ 切换到卡片视图 */
function handleSwitchToCard() {
  dagStore.switchView('card')
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

.dag-banner {
  padding: 8px 16px 0;
  flex-shrink: 0;
}

.dag-banner :deep(.n-alert) {
  font-size: 13px;
}

.gap-list {
  display: block;
  margin-top: 6px;
  font-family: var(--app-font-mono, ui-monospace, monospace);
  word-break: break-all;
}
</style>
