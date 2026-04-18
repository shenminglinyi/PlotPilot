<template>
  <div class="autopilot-terminal">
    <div class="terminal-toolbar">
      <span class="led" :class="connectionStatus"></span>
      <span class="title">实时日志</span>
      <div class="toolbar-right">
        <span class="meta">{{ rows.length }} 行</span>
        <span class="meta dim">{{ statusHint }}</span>
        <n-tag
          size="medium"
          round
          bordered
          :type="stageTagType"
          class="stage-tag"
        >
          {{ behaviorLabel }}
        </n-tag>
      </div>
    </div>
    <div v-if="progressHint" class="progress-strip">{{ progressHint }}</div>
    <div
      ref="bodyRef"
      class="terminal-body"
      @scroll="onScroll"
    >
      <div
        v-for="row in rows"
        :key="row.id"
        class="line"
        :class="'line--' + row.kind"
      >
        <span class="time">{{ row.time }}</span>
        <span class="msg">{{ row.text }}</span>
      </div>
      <div v-if="rows.length === 0" class="empty">等待事件…</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { NTag } from 'naive-ui'

const props = defineProps<{ novelId: string }>()

const emit = defineEmits<{
  'desk-refresh': []
}>()

const MAX_ROWS = 100
const DISPLAY_MSG_MAX = 88

type RowKind = 'info' | 'ok' | 'warn' | 'err' | 'dim'

interface Row {
  id: string
  time: string
  text: string
  kind: RowKind
}

const rows = ref<Row[]>([])
const bodyRef = ref<HTMLElement | null>(null)
const connectionStatus = ref<'connected' | 'reconnecting' | 'disconnected' | 'ended'>('disconnected')
const streamEndedNormally = ref(false)
const lastLogSeq = ref(0)
const progressHint = ref('')
const autoScroll = ref(true)
let lastCompleteAt = 0

/** 当前阶段（英文 key，用于 tag 配色） */
const behaviorStageKey = ref('')
/** 托管状态 running / stopped / error */
const behaviorAutopilotStatus = ref('')
/** 工具栏右侧主标签：阶段中文或「运行中/已停止」等 */
const behaviorLabel = ref('—')

const stageTagType = computed(() => {
  if (connectionStatus.value === 'ended') {
    return 'default'
  }
  const ap = behaviorAutopilotStatus.value
  if (ap === 'error') {
    return 'error'
  }
  if (ap === 'stopped') {
    return 'default'
  }
  const s = behaviorStageKey.value
  if (s === 'writing') {
    return 'success'
  }
  if (s === 'auditing' || s === 'paused_for_review') {
    return 'warning'
  }
  if (s === 'completed') {
    return 'success'
  }
  if (s === 'macro_planning' || s === 'act_planning' || s === 'planning') {
    return 'info'
  }
  return 'primary'
})

function applyBehaviorFromMeta(meta?: Record<string, unknown>) {
  if (!meta) {
    return
  }
  if (meta.to_label != null) {
    behaviorStageKey.value = String(meta.to_stage ?? '')
    behaviorLabel.value = String(meta.to_label)
    return
  }
  const ap = meta.autopilot_status != null ? String(meta.autopilot_status) : ''
  if (ap) {
    behaviorAutopilotStatus.value = ap
  }
  if (meta.stage_label != null && ap) {
    behaviorStageKey.value = ap === 'running' ? String(meta.stage ?? '') : ap
    if (ap === 'running') {
      behaviorLabel.value = String(meta.stage_label)
    } else if (meta.autopilot_status_label != null) {
      behaviorLabel.value = String(meta.autopilot_status_label)
    } else {
      behaviorLabel.value = String(meta.stage_label)
    }
    return
  }
  if (meta.autopilot_status_label != null) {
    behaviorLabel.value = String(meta.autopilot_status_label)
  }
}

const statusHint = computed(() => {
  switch (connectionStatus.value) {
    case 'connected':
      return 'SSE'
    case 'reconnecting':
      return '重连…'
    case 'ended':
      return '已结束'
    case 'disconnected':
      return '未连接'
    default:
      return ''
  }
})

let eventSource: EventSource | null = null
let reconnectTimer: number | null = null

const pending: Array<{ data: Record<string, unknown> }> = []
let flushScheduled = false

function formatTime(iso: string) {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return '--:--:--'
  }
}

function clipForUi(s: string) {
  const t = (s || '').trim()
  if (t.length <= DISPLAY_MSG_MAX) return t
  return t.slice(0, DISPLAY_MSG_MAX - 1) + '…'
}

/** 与后端过滤互补：漏网的 StreamingBus 行不再入列 */
function isNoiseMessage(msg: string) {
  const m = msg || ''
  return m.includes('[StreamingBus]') && m.includes('publish:')
}

function kindForType(t: string, meta?: Record<string, unknown>): RowKind {
  if (t === 'beat_error' || t.includes('error')) return 'err'
  if (t === 'stage_change') return 'warn'
  if (t.includes('complete') && t !== 'autopilot_complete') return 'ok'
  if (t === 'log_line') {
    const lv = meta?.level
    if (lv === 'ERROR' || lv === 'CRITICAL') return 'err'
    if (lv === 'WARNING') return 'warn'
  }
  if (t === 'autopilot_complete') return 'dim'
  return 'info'
}

function pushRow(data: Record<string, unknown>) {
  const t = String(data.type || 'info')
  const message = String(data.message || '')
  const timestamp = String(data.timestamp || new Date().toISOString())
  const meta = data.metadata as Record<string, unknown> | undefined

  if (t === 'progress') {
    progressHint.value = clipForUi(message)
    applyBehaviorFromMeta(meta)
    return
  }

  if (t === 'log_line' && isNoiseMessage(message)) {
    return
  }

  if (t === 'stage_change') {
    applyBehaviorFromMeta(meta)
  }

  const kind = kindForType(t, meta)
  rows.value.push({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    time: formatTime(timestamp),
    text: clipForUi(message),
    kind,
  })
  if (rows.value.length > MAX_ROWS) {
    rows.value.splice(0, rows.value.length - MAX_ROWS)
  }

  if (t === 'stage_change' && meta?.to_stage === 'paused_for_review') {
    emit('desk-refresh')
  }
  if (t === 'beat_complete') {
    emit('desk-refresh')
  }
}

function scrollToBottom() {
  const el = bodyRef.value
  if (!el || !autoScroll.value) return
  el.scrollTop = el.scrollHeight
}

function flushPending() {
  flushScheduled = false
  const batch = pending.splice(0, pending.length)
  for (const item of batch) {
    pushRow(item.data)
  }
  if (!autoScroll.value) return
  nextTick(() => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        scrollToBottom()
      })
    })
  })
}

function scheduleFlush() {
  if (flushScheduled) return
  flushScheduled = true
  requestAnimationFrame(flushPending)
}

function onScroll() {
  if (!bodyRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = bodyRef.value
  autoScroll.value = scrollHeight - scrollTop - clientHeight < 48
}

function connect() {
  if (streamEndedNormally.value) return
  if (eventSource) eventSource.close()
  const q = lastLogSeq.value > 0 ? `?after_seq=${lastLogSeq.value}` : ''
  eventSource = new EventSource(`/api/v1/autopilot/${props.novelId}/stream${q}`)

  eventSource.onopen = () => {
    connectionStatus.value = 'connected'
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data) as Record<string, unknown>
      const typ = String(data.type || '')

      if (typ === 'heartbeat') return

      if (typ === 'connected') {
        applyBehaviorFromMeta(data.metadata as Record<string, unknown> | undefined)
        return
      }

      const seq = (data.metadata as { seq?: number } | undefined)?.seq
      if (typeof seq === 'number' && seq > lastLogSeq.value) {
        lastLogSeq.value = seq
      }

      if (typ === 'autopilot_complete') {
        const now = Date.now()
        if (now - lastCompleteAt < 1200) return
        lastCompleteAt = now
        connectionStatus.value = 'ended'
        streamEndedNormally.value = true
        const doneMeta = data.metadata as Record<string, unknown> | undefined
        const st = doneMeta?.status != null ? String(doneMeta.status) : ''
        if (st) {
          behaviorAutopilotStatus.value = st
          behaviorStageKey.value = 'idle'
        }
        if (doneMeta?.status_label != null) {
          behaviorLabel.value = String(doneMeta.status_label)
        }
        if (reconnectTimer) {
          clearTimeout(reconnectTimer)
          reconnectTimer = null
        }
      }

      pending.push({ data })
      scheduleFlush()

      if (typ === 'autopilot_complete' && eventSource) {
        eventSource.close()
        eventSource = null
      }
    } catch {
      /* ignore */
    }
  }

  eventSource.onerror = () => {
    if (streamEndedNormally.value) return
    connectionStatus.value = 'reconnecting'
    if (!reconnectTimer) {
      reconnectTimer = window.setTimeout(() => connect(), 3000)
    }
  }
}

onMounted(() => {
  connect()
})

watch(
  () => props.novelId,
  () => {
    rows.value = []
    progressHint.value = ''
    behaviorStageKey.value = ''
    behaviorAutopilotStatus.value = ''
    behaviorLabel.value = '—'
    lastLogSeq.value = 0
    streamEndedNormally.value = false
    connectionStatus.value = 'disconnected'
    lastCompleteAt = 0
    pending.length = 0
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    connect()
  }
)

onUnmounted(() => {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
})
</script>

<style scoped>
.autopilot-terminal {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
  height: 100%;
  max-height: 100%;
  border-radius: 8px;
  border: 1px solid rgba(15, 23, 42, 0.35);
  background: #0f172a;
  color: #e2e8f0;
  overflow: hidden;
}

.terminal-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  font-size: 12px;
  background: rgba(15, 23, 42, 0.95);
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

.led {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.led.connected {
  background: #22c55e;
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.6);
}
.led.reconnecting {
  background: #f59e0b;
  animation: pulse 1s infinite;
}
.led.disconnected {
  background: #ef4444;
}
.led.ended {
  background: #64748b;
}

@keyframes pulse {
  50% {
    opacity: 0.35;
  }
}

.title {
  font-weight: 600;
  letter-spacing: 0.02em;
}

.toolbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
  min-width: 0;
}

.meta {
  font-variant-numeric: tabular-nums;
  color: #94a3b8;
}
.meta.dim {
  opacity: 0.85;
}

.stage-tag {
  max-width: 11em;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.stage-tag :deep(.n-tag__content) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-strip {
  padding: 4px 10px;
  font-size: 11px;
  color: #a5b4fc;
  background: rgba(30, 41, 59, 0.9);
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.terminal-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: auto;
  overscroll-behavior: contain;
  padding: 8px 10px 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New',
    monospace;
  font-size: 11px;
  line-height: 1.55;
}

.line {
  display: flex;
  gap: 8px;
  padding: 2px 0;
  word-break: break-word;
}

.time {
  flex-shrink: 0;
  width: 64px;
  color: #64748b;
}

.msg {
  flex: 1;
  min-width: 0;
  color: #cbd5e1;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.line--ok .msg {
  color: #86efac;
}
.line--warn .msg {
  color: #fde047;
}
.line--err .msg {
  color: #fca5a5;
}
.line--dim .msg {
  color: #94a3b8;
}

.empty {
  color: #64748b;
  padding: 12px 0;
  text-align: center;
}

.terminal-body::-webkit-scrollbar {
  width: 6px;
}
.terminal-body::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.35);
  border-radius: 3px;
}
</style>
