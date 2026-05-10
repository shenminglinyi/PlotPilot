<template>
  <n-modal
    :show="show"
    preset="card"
    :title="panelTitle"
    :style="{ maxWidth: '640px', width: '90vw' }"
    :bordered="true"
    :segmented="{ content: true, footer: true }"
    size="large"
    @update:show="$emit('update:show', $event)"
  >
    <div v-if="meta" class="node-detail">
      <!-- ★ Dify 风格：顶部状态条 -->
      <div class="detail-status-bar" :style="{ background: statusBarBg }">
        <span class="status-icon">{{ meta.icon || '📦' }}</span>
        <span class="status-label">{{ statusLabel }}</span>
        <n-tag v-if="!nodeEnabled" size="small" type="default" round>已禁用</n-tag>
        <n-tag v-else-if="isRunning" size="small" type="info" round>
          <template #icon><n-spin :size="12" /></template>
          运行中
        </n-tag>
      </div>

      <!-- 基本信息 -->
      <div class="detail-section">
        <div class="section-title">基本信息</div>
        <div class="detail-grid">
          <span class="detail-label">节点类型</span>
          <code>{{ meta.node_type }}</code>
          <span class="detail-label">分类</span>
          <n-tag size="small" :type="categoryTagType" round>{{ categoryLabel }}</n-tag>
          <span class="detail-label">描述</span>
          <n-text>{{ meta.description || '无' }}</n-text>
        </div>
      </div>

      <!-- CPMS 提示词来源 -->
      <div class="detail-section">
        <div class="section-title">提示词来源</div>
        <div v-if="promptLive" class="detail-grid">
          <span class="detail-label">CPMS Key</span>
          <code v-if="promptLive.cpms_node_key">{{ promptLive.cpms_node_key }}</code>
          <n-text v-else depth="3">无</n-text>
          <span class="detail-label">来源</span>
          <n-tag
            size="small"
            :type="promptLive.source === 'cpms' ? 'success' : promptLive.source === 'config' ? 'info' : promptLive.source === 'meta' ? 'default' : 'warning'"
            round
          >
            {{ sourceLabel }}
          </n-tag>
        </div>
        <n-text v-else-if="promptLoading" depth="3">加载中...</n-text>
        <n-text v-else depth="3">点击节点查看提示词来源</n-text>
      </div>

      <!-- 提示词内容预览 -->
      <div v-if="promptLive && promptLive.system" class="detail-section">
        <div class="section-title">提示词预览</div>
        <div class="prompt-preview">
          <pre>{{ promptLive.system.slice(0, 500) }}{{ promptLive.system.length > 500 ? '...' : '' }}</pre>
        </div>
      </div>

      <!-- 端口信息 -->
      <div class="detail-section">
        <div class="section-title">端口</div>
        <div v-if="meta.input_ports.length > 0" class="port-row">
          <n-text depth="3" style="font-size: 11px; width: 36px">输入：</n-text>
          <div class="port-tags">
            <n-tag v-for="p in meta.input_ports" :key="p.name" size="tiny" round>{{ p.name }}</n-tag>
          </div>
        </div>
        <div v-if="meta.output_ports.length > 0" class="port-row" style="margin-top: 4px">
          <n-text depth="3" style="font-size: 11px; width: 36px">输出：</n-text>
          <div class="port-tags">
            <n-tag v-for="p in meta.output_ports" :key="p.name" size="tiny" type="info" round>{{ p.name }}</n-tag>
          </div>
        </div>
      </div>

      <!-- 默认连线 -->
      <div v-if="meta.default_edges.length > 0" class="detail-section">
        <div class="section-title">默认下游</div>
        <div class="default-edges">
          <n-tag
            v-for="target in meta.default_edges"
            :key="target"
            size="small"
            type="info"
            round
          >
            {{ getNodeLabel(target) }}
          </n-tag>
        </div>
      </div>
    </div>

    <div v-else class="detail-empty">
      <n-text depth="3">未找到节点信息</n-text>
    </div>

    <template #footer>
      <div class="detail-footer">
        <!-- ★ 启用/禁用 Switch — 统一放在弹窗底部 -->
        <div class="footer-left" v-if="nodeId && meta?.can_disable">
          <n-text depth="3" style="font-size: 12px; margin-right: 8px">启用节点</n-text>
          <n-switch
            :value="nodeEnabled"
            @update:value="handleToggleNode"
            size="small"
          />
        </div>
        <div v-else />
        <n-button size="small" @click="$emit('update:show', false)">关闭</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import { useMessage } from 'naive-ui'
import type { NodeMeta, NodePromptLive, NodeStatus } from '@/types/dag'
import { CATEGORY_LABELS } from '@/types/dag'
import { useDAGStore } from '@/stores/dagStore'

const props = defineProps<{
  show: boolean
  nodeId: string | null
  novelId: string
}>()

defineEmits<{
  'update:show': [value: boolean]
}>()

const dagStore = useDAGStore()
const message = useMessage()

const promptLive = ref<NodePromptLive | null>(null)
const promptLoading = ref(false)

// ─── 节点基本信息 ───

const nodeDef = computed(() => {
  if (!props.nodeId) return null
  return dagStore.dagDefinition?.nodes.find(n => n.id === props.nodeId) || null
})

const nodeEnabled = computed(() => nodeDef.value?.enabled ?? true)

const meta = computed((): NodeMeta | null => {
  if (!nodeDef.value) return null
  return dagStore.nodeTypeRegistry[nodeDef.value.type] || null
})

const runState = computed(() => {
  if (!props.nodeId) return null
  return dagStore.nodeStates.get(props.nodeId) || null
})

const status = computed((): NodeStatus => {
  if (!nodeEnabled.value) return 'disabled'
  return runState.value?.status || 'idle'
})

const isRunning = computed(() => status.value === 'running')

// ─── 面板标题 ───

const panelTitle = computed(() => {
  if (!meta.value) return '节点详情'
  return `${meta.value.icon || '📦'} ${meta.value.display_name || props.nodeId}`
})

// ─── 状态条 ───

const STATUS_BAR_BG_MAP: Record<string, string> = {
  idle: 'var(--app-surface-subtle)',
  pending: 'var(--app-surface-subtle)',
  running: 'var(--color-brand-light)',
  success: 'var(--color-success-dim)',
  warning: 'var(--color-warning-dim)',
  error: 'var(--color-danger-dim)',
  bypassed: 'var(--app-divider)',
  disabled: 'var(--app-divider)',
  completed: 'var(--color-success-dim)',
}

const statusBarBg = computed(() => STATUS_BAR_BG_MAP[status.value] || 'var(--app-surface-subtle)')

const STATUS_LABEL_MAP: Record<string, string> = {
  idle: '⏹ 空闲',
  pending: '⏳ 等待中',
  running: '▶️ 运行中',
  success: '✅ 成功',
  warning: '⚠️ 警告',
  error: '❌ 错误',
  bypassed: '⏭ 已旁路',
  disabled: '⛔ 已禁用',
  completed: '✅ 已完成',
}

const statusLabel = computed(() => STATUS_LABEL_MAP[status.value] || status.value)

// ─── 分类 ───

const categoryTagType = computed(() => {
  const map: Record<string, 'default' | 'info' | 'success' | 'warning' | 'error'> = {
    context: 'default',
    execution: 'info',
    validation: 'warning',
    gateway: 'error',
  }
  return map[meta.value?.category || ''] || 'default'
})

const categoryLabel = computed(() => {
  if (!meta.value) return ''
  return CATEGORY_LABELS[meta.value.category] || meta.value.category
})

// ─── 提示词来源 ───

const sourceLabel = computed(() => {
  const map: Record<string, string> = {
    cpms: 'CPMS 广场',
    config: '节点配置',
    meta: '节点默认',
    none: '无',
  }
  return promptLive.value ? map[promptLive.value.source] || promptLive.value.source : ''
})

// 节点切换时加载实时提示词
watch(
  () => props.nodeId,
  async (newNodeId) => {
    promptLive.value = null
    if (newNodeId && props.show) {
      promptLoading.value = true
      promptLive.value = await dagStore.loadNodePromptLive(props.novelId, newNodeId)
      promptLoading.value = false
    }
  },
  { immediate: true }
)

// 面板打开时也加载
watch(
  () => props.show,
  async (newShow) => {
    if (newShow && props.nodeId) {
      promptLoading.value = true
      promptLive.value = await dagStore.loadNodePromptLive(props.novelId, props.nodeId)
      promptLoading.value = false
    }
  }
)

function getNodeLabel(type: string): string {
  const m = dagStore.nodeTypeRegistry[type]
  return m?.display_name || type
}

// ─── 节点启禁用 ───

async function handleToggleNode(enabled: boolean) {
  if (!props.nodeId) return
  await dagStore.toggleNode(props.novelId, props.nodeId)
  message.success(enabled ? '节点已启用' : '节点已禁用')
}
</script>

<style scoped>
.node-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Dify 风格状态条 ── */
.detail-status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--app-radius-sm);
  margin: -4px 0 0;
}

.status-icon {
  font-size: 18px;
}

.status-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
}

/* ── 区块 ── */
.detail-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-grid {
  display: grid;
  grid-template-columns: 80px 1fr;
  gap: 4px 12px;
  font-size: 12px;
  align-items: center;
}

.detail-label {
  color: var(--app-text-muted);
  font-size: 11px;
}

.detail-grid code {
  font-size: 11px;
  background: var(--app-surface-subtle);
  padding: 1px 4px;
  border-radius: 2px;
}

.prompt-preview {
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: 10px;
  max-height: 200px;
  overflow: auto;
}

.prompt-preview pre {
  font-size: 11px;
  font-family: var(--font-mono);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  color: var(--app-text-primary);
}

/* ── 端口 ── */
.port-row {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}

.port-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.default-edges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* ── 底部 ── */
.detail-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.footer-left {
  display: flex;
  align-items: center;
}

.detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 0;
}
</style>
