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

      <!-- 全托管写作遥测（与 /autopilot/.../status 同源） -->
      <div v-if="showWritingTelemetry" class="detail-section">
        <div class="section-title">全托管写作遥测</div>
        <n-text v-if="writingPollError" depth="3" style="font-size: 12px">{{ writingPollError }}</n-text>
        <div v-else-if="writingStatus" class="detail-grid">
          <span class="detail-label">阶段</span>
          <span>{{ writingStatus.current_stage || '—' }}</span>
          <span class="detail-label">子步骤</span>
          <span>{{ writingStatus.writing_substep_label || writingStatus.writing_substep || '—' }}</span>
          <span class="detail-label">章节字数</span>
          <span>{{ writingStatus.accumulated_words ?? 0 }} / {{ writingStatus.chapter_target_words ?? 0 }}</span>
          <span class="detail-label">节拍</span>
          <span>
            第 {{ (Number(writingStatus.current_beat_index) || 0) + 1 }} / {{ writingStatus.total_beats || 0 }} 节
            <template v-if="writingStatus.beat_target_words"> · 本拍目标 {{ writingStatus.beat_target_words }} 字</template>
          </span>
          <span class="detail-label">指挥相位</span>
          <span>{{ beatPhaseLabel }}</span>
          <span class="detail-label">硬上限 / 建议</span>
          <span>{{ writingStatus.beat_hard_cap ?? 0 }} / {{ writingStatus.beat_max_words_hint ?? 0 }} 字</span>
          <span class="detail-label">剩余预算</span>
          <span>{{ writingStatus.beat_remaining_budget ?? 0 }} 字</span>
          <span class="detail-label">上下文 token</span>
          <span>{{ writingStatus.context_tokens ?? 0 }}</span>
          <span class="detail-label">节拍焦点</span>
          <span>{{ writingStatus.beat_focus || '—' }}</span>
          <span class="detail-label">最近智能截断</span>
          <span>{{ lastTruncateLine || '无' }}</span>
        </div>
        <n-text v-else depth="3" style="font-size: 12px">加载中…</n-text>
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
import { computed, watch, ref, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import type { NodeMeta, NodePromptLive, NodeStatus } from '@/types/dag'
import { CATEGORY_LABELS } from '@/types/dag'
import { useDAGStore } from '@/stores/dagStore'
import { resolveHttpUrl } from '@/api/config'

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

/** GET /autopilot/{id}/status 拉取的实时块（写作/指挥/截断） */
const writingStatus = ref<Record<string, unknown> | null>(null)
const writingPollError = ref('')
let writingPollTimer: ReturnType<typeof setInterval> | null = null

const WRITING_TELEMETRY_TYPES = new Set(['exec_writer', 'exec_beat'])

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

// ─── 全托管写作遥测（依赖 meta，watch 须放在 meta 之后，避免 TDZ / immediate 读 meta 崩溃）───

const showWritingTelemetry = computed(() => {
  const t = meta.value?.node_type
  return Boolean(t && WRITING_TELEMETRY_TYPES.has(t))
})

const beatPhaseLabel = computed(() => {
  const raw = String(writingStatus.value?.beat_phase || '')
  const map: Record<string, string> = {
    unfurl: '铺陈 (unfurl)',
    converge: '收束 (converge)',
    land: '着陆 (land)',
  }
  return map[raw] || raw || '—'
})

const lastTruncateLine = computed(() => {
  const t = writingStatus.value?.last_smart_truncate
  if (!t || typeof t !== 'object') return ''
  const o = t as Record<string, unknown>
  const from = o.from_chars
  const to = o.to_chars
  const cap = o.hard_cap
  const bi = o.beat_index_1based
  const tb = o.total_beats
  const ph = o.phase
  if (from == null && to == null) return ''
  return `节拍 ${bi}/${tb} · ${from}→${to} 字 · 硬上限 ${cap} · 相位 ${ph}`
})

async function fetchWritingTelemetry() {
  if (!props.novelId || !showWritingTelemetry.value) return
  writingPollError.value = ''
  try {
    const res = await fetch(resolveHttpUrl(`/api/v1/autopilot/${props.novelId}/status`))
    if (res.status === 404) {
      writingStatus.value = null
      writingPollError.value = '该书暂无托管状态'
      return
    }
    if (!res.ok) {
      writingPollError.value = `状态 ${res.status}`
      return
    }
    writingStatus.value = (await res.json()) as Record<string, unknown>
  } catch (e) {
    writingPollError.value = e instanceof Error ? e.message : '网络错误'
  }
}

function clearWritingPoll() {
  if (writingPollTimer != null) {
    clearInterval(writingPollTimer)
    writingPollTimer = null
  }
}

watch(
  () => [props.show, props.novelId, meta.value?.node_type ?? ''] as const,
  ([open, nid, nodeType]) => {
    clearWritingPoll()
    writingStatus.value = null
    writingPollError.value = ''
    const telemetry = Boolean(nodeType && WRITING_TELEMETRY_TYPES.has(nodeType))
    if (!open || !nid || !telemetry) return
    void fetchWritingTelemetry()
    writingPollTimer = setInterval(() => void fetchWritingTelemetry(), 2500)
  },
  { immediate: true }
)

onUnmounted(() => clearWritingPoll())

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
