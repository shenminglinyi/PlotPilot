<template>
  <div class="autopilot-terminal">
    <div class="terminal-toolbar">
      <span class="led" :class="connectionStatus"></span>
      <span class="title">实时日志</span>
      <div class="toolbar-right">
        <span class="meta">{{ filteredRows.length }} / {{ rows.length }} 行</span>
        <span class="meta dim">{{ statusHint }}</span>
        <button
          v-if="!autoScroll"
          type="button"
          class="stick-bottom-btn"
          @click="scrollToBottomManual"
        >
          回到底部
        </button>
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
    <div class="terminal-controls">
      <input
        v-model="searchText"
        class="log-search"
        type="search"
        placeholder="搜索来源 / 内容 / 路径"
      />
      <button
        type="button"
        class="filter-chip"
        :class="{ 'is-active': hideHttp }"
        @click="hideHttp = !hideHttp"
      >
        隐藏 HTTP
      </button>
      <button
        type="button"
        class="filter-chip"
        :class="{ 'is-active': importantOnly }"
        @click="importantOnly = !importantOnly"
      >
        只看重要
      </button>
    </div>
    <div v-if="progressHint" class="progress-strip">
      <span class="progress-text">{{ progressHint }}</span>
      <div v-if="wordProgressPct > 0" class="progress-bar-mini">
        <div class="progress-bar-fill" :style="{ width: wordProgressPct + '%' }"></div>
      </div>
    </div>
    <div
      ref="bodyRef"
      class="terminal-body"
      @scroll="onScroll"
    >
      <div
        v-for="row in visibleRows"
        :key="row.id"
        class="line"
        :class="['line--' + row.kind, { 'line--expanded': expandedRows.has(row.id) }]"
        :title="row.detail"
        @click="toggleExpanded(row.id)"
      >
        <span class="time">{{ row.time }}</span>
        <span class="level">{{ row.level }}</span>
        <span class="source">{{ row.source }}</span>
        <span class="msg">
          <template v-if="row.kind === 'http' && row.httpMethod">
            <span class="http-method">{{ row.httpMethod }}</span>
            <span class="http-path">{{ row.httpPath }}</span>
            <span class="http-status" :class="'http-status--' + row.httpStatusKind">{{ row.httpStatus }}</span>
          </template>
          <template v-else>
            {{ expandedRows.has(row.id) ? row.detail : row.text }}
          </template>
        </span>
      </div>
      <div v-if="rows.length === 0" class="empty">等待事件…</div>
      <div v-else-if="filteredRows.length === 0" class="empty">当前筛选没有匹配日志</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { NTag } from 'naive-ui'
import { resolveHttpUrl } from '@/api/config'

const props = defineProps<{ novelId: string }>()

const emit = defineEmits<{
  'desk-refresh': []
  /** 张力打分结果 / 单章审计完成等：驱动张力心电图等「按章更新即可」的指标 */
  'chapter-metrics-refresh': []
}>()

const MAX_ROWS = 1000
const MAX_RENDERED_ROWS = 260
const DISPLAY_MSG_MAX = 4000

type RowKind = 'info' | 'ok' | 'warn' | 'err' | 'dim' | 'debug' | 'http'
type HttpStatusKind = 'ok' | 'redirect' | 'warn' | 'err' | 'unknown'

interface Row {
  id: string
  time: string
  level: string
  source: string
  text: string
  detail: string
  kind: RowKind
  searchable: string
  httpMethod?: string
  httpPath?: string
  httpStatus?: string
  httpStatusKind?: HttpStatusKind
}

const rows = ref<Row[]>([])
const bodyRef = ref<HTMLElement | null>(null)
const connectionStatus = ref<'connected' | 'reconnecting' | 'disconnected'>('disconnected')
const lastLogSeq = ref(0)
const progressHint = ref('')
const progressMeta = ref<Record<string, unknown> | undefined>(undefined)
const autoScroll = ref(true)
const searchText = ref('')
const hideHttp = ref(false)
const importantOnly = ref(false)
const expandedRows = ref<Set<string>>(new Set())

/** 程序设置 scrollTop 时仍会触发 scroll；此期间忽略 onScroll，避免误判为「用户离开底部」 */
let scrollingProgrammatically = false
let scrollLockToken = 0

/** 当前阶段（英文 key，用于 tag 配色） */
const behaviorStageKey = ref('')
/** 托管状态 running / stopped / error */
const behaviorAutopilotStatus = ref('')
/** 工具栏右侧主标签：阶段中文或「运行中/已停止」等 */
const behaviorLabel = ref('—')

/** 字数进度百分比（用于迷你进度条） */
const wordProgressPct = computed(() => {
  const m = progressMeta.value
  if (!m) return 0
  const acc = Number(m.accumulated_words || 0)
  const target = Number(m.chapter_target_words || 0)
  if (target <= 0 || acc <= 0) return 0
  return Math.min(100, Math.round(acc / target * 100))
})

const stageTagType = computed(() => {
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
      const subLabel = String(meta.writing_substep_label || '').trim()
      const sub = String(meta.writing_substep || '').trim()
      behaviorLabel.value =
        subLabel && (sub === 'outline_planning' || sub === 'context_assembly' || sub === 'beat_magnification')
          ? subLabel
          : String(meta.stage_label)
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
      if (
        behaviorAutopilotStatus.value === 'stopped' ||
        behaviorAutopilotStatus.value === 'error'
      ) {
        return 'SSE · 继续监听'
      }
      return 'SSE'
    case 'reconnecting':
      return '重连…'
    case 'disconnected':
      return '未连接'
    default:
      return ''
  }
})

let eventSource: EventSource | null = null
let reconnectTimer: number | null = null
/** 日志 SSE 重连退避（onerror 在部分浏览器上较频繁，避免打满连接） */
let logStreamReconnectFailCount = 0
const LOG_STREAM_MAX_BACKOFF_MS = 30_000

// 🔥 desk-refresh 去抖：300ms 内多次事件只触发一次 emit，避免短时间内连续 loadDesk
let deskRefreshDebounceTimer: number | null = null
function scheduleDeskRefresh() {
  if (deskRefreshDebounceTimer != null) return  // 已有待执行的，跳过
  deskRefreshDebounceTimer = window.setTimeout(() => {
    deskRefreshDebounceTimer = null
    emit('desk-refresh')
  }, 300)
}

function scheduleLogStreamReconnect() {
  logStreamReconnectFailCount = Math.min(logStreamReconnectFailCount + 1, 12)
  const delay = Math.min(3000 * 2 ** (logStreamReconnectFailCount - 1), LOG_STREAM_MAX_BACKOFF_MS)
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    connect()
  }, delay)
}

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

function stripLogIcons(s: string) {
  return (s || '').replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu, '').trim()
}

function normalizeLevel(level: string) {
  const lv = (level || 'INFO').toUpperCase()
  if (lv === 'WARNING') return 'WARN'
  if (lv === 'CRITICAL') return 'CRIT'
  return lv
}

function compactLogger(logger: string) {
  const raw = (logger || '').trim()
  if (!raw || raw === 'file') return 'runtime'
  if (raw === 'uvicorn.access' || raw.includes('httptools')) return 'uvicorn.access'
  const aliases: Record<string, string> = {
    'interfaces.api.v1.engine.autopilot_routes': 'engine.autopilot',
    'application.engine.services.persistence_queue': 'engine.persist',
    'application.engine.services.streaming_bus': 'engine.stream',
    'application.engine.services.novel_stop_signal': 'engine.signal',
    'application.engine.services.context_budget_allocator': 'engine.budget',
    'infrastructure.database.connection': 'db.connection',
    'infrastructure.database.query_optimizations': 'db.query',
  }
  if (aliases[raw]) return aliases[raw]
  const parts = raw.split('.').filter(Boolean)
  if (parts.length <= 2) return raw
  return parts.slice(-3).join('.')
}

function statusKind(status: string): HttpStatusKind {
  const n = Number(status)
  if (!Number.isFinite(n)) return 'unknown'
  if (n >= 500) return 'err'
  if (n >= 400) return 'warn'
  if (n >= 300) return 'redirect'
  if (n >= 200) return 'ok'
  return 'unknown'
}

function parseHttpAccess(text: string) {
  const m = text.match(/"([A-Z]+)\s+([^"\s]+)(?:\s+HTTP\/[\d.]+)?"\s+(\d{3})/)
  if (!m) return null
  return {
    method: m[1],
    path: m[2],
    status: m[3],
    statusKind: statusKind(m[3]),
  }
}

function parseRawLogMessage(message: string, defaultLevel: string, defaultLogger: string) {
  let text = stripLogIcons(message)
  let level = normalizeLevel(defaultLevel)
  let logger = defaultLogger || ''
  let parsedTime = ''

  const full = text.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})(?:\.\d+)?\s+(INFO|DEBUG|WARN|WARNING|ERROR|CRITICAL|HTTP)\s+(?:pid=\d+\s+)?([^\s]+)\s+([\s\S]*)$/)
  if (full) {
    parsedTime = full[2]
    level = normalizeLevel(full[3])
    logger = full[4]
    text = full[5].trim()
  } else {
    const compact = text.match(/^(\d{2}:\d{2}:\d{2})\s+(INFO|DEBUG|WARN|WARNING|ERROR|CRITICAL|HTTP)\s+([^\s]+)\s+([\s\S]*)$/)
    if (compact) {
      parsedTime = compact[1]
      level = normalizeLevel(compact[2])
      logger = compact[3]
      text = compact[4].trim()
    }
  }

  if (logger === 'access' || logger.includes('httptools')) {
    logger = 'uvicorn.access'
    level = 'HTTP'
  }

  const http = parseHttpAccess(text)
  if (http || logger === 'uvicorn.access') {
    level = 'HTTP'
  }

  return { text, level, logger, parsedTime, http }
}

function buildDisplayRow(data: Record<string, unknown>): Row {
  const t = String(data.type || 'info')
  const message = stripLogIcons(String(data.message || ''))
  const timestamp = String(data.timestamp || new Date().toISOString())
  const meta = data.metadata as Record<string, unknown> | undefined
  const defaultLevel = String(meta?.level || '')
  const defaultLogger = String(meta?.logger || '')
  const parsed = parseRawLogMessage(message, defaultLevel, defaultLogger)
  const kind = kindForType(t, { ...meta, level: parsed.level, logger: parsed.logger }, parsed.http)
  const source = compactLogger(parsed.logger)
  const detail = parsed.text || message
  const time = parsed.parsedTime || formatTime(timestamp)
  const text = clipForUi(detail)

  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    time,
    level: parsed.level || 'INFO',
    source,
    text,
    detail,
    kind,
    searchable: `${parsed.level} ${source} ${detail}`.toLowerCase(),
    httpMethod: parsed.http?.method,
    httpPath: parsed.http?.path,
    httpStatus: parsed.http?.status,
    httpStatusKind: parsed.http?.statusKind,
  }
}

/** 构建细化的进度提示：子步骤 + 节拍进度 + 字数进度 */
function buildDetailedProgressHint(message: string, meta?: Record<string, unknown>): string {
  if (!meta) return clipForUi(message)

  const substepLabel = String(meta.writing_substep_label || '')
  const totalBeats = Number(meta.total_beats || 0)
  const beatIdx = Number(meta.current_beat_index_1based || 0)
  const accumulatedWords = Number(meta.accumulated_words || 0)
  const chapterTargetWords = Number(meta.chapter_target_words || 0)
  const beatFocus = String(meta.beat_focus || '')
  const contextTokens = Number(meta.context_tokens || 0)
  const stage = String(meta.stage || '')

  const parts: string[] = []

  // 子步骤（所有阶段通用）
  if (substepLabel) {
    parts.push(substepLabel)
  }

  // writing 阶段特有信息
  if (stage === 'writing') {
    // 节拍进度
    if (totalBeats > 0 && beatIdx > 0) {
      parts.push(`节拍 ${beatIdx}/${totalBeats}`)
    }

    // 字数进度
    if (accumulatedWords > 0 && chapterTargetWords > 0) {
      const pct = Math.min(100, Math.round(accumulatedWords / chapterTargetWords * 100))
      parts.push(`${accumulatedWords}/${chapterTargetWords}字(${pct}%)`)
    }

    // 节拍焦点
    if (beatFocus) {
      const focusClip = beatFocus.length > 16 ? beatFocus.slice(0, 15) + '…' : beatFocus
      parts.push(`[${focusClip}]`)
    }

    // 上下文 tokens
    if (contextTokens > 0) {
      parts.push(`${contextTokens}tok`)
    }
  }

  if (parts.length === 0) {
    return clipForUi(message)
  }

  return parts.join(' · ')
}

/** 与后端过滤互补：漏网的 StreamingBus 行不再入列 */
function isNoiseMessage(msg: string) {
  const m = msg || ''
  if (m.includes('[StreamingBus]') && m.includes('publish:')) return true
  if (m.includes('[SSE]') && m.includes('发送') && m.toLowerCase().includes('chapter')) return true
  return false
}

function kindForType(t: string, meta?: Record<string, unknown>, http?: ReturnType<typeof parseHttpAccess>): RowKind {
  if (t === 'beat_error' || t.includes('error')) return 'err'
  if (t === 'stage_change') return 'warn'
  if (t.includes('complete') && t !== 'autopilot_complete') return 'ok'
  if (t === 'log_line') {
    const lv = normalizeLevel(String(meta?.level || ''))
    const logger = String(meta?.logger || '')
    if (http || lv === 'HTTP' || logger === 'uvicorn.access') return 'http'
    if (lv === 'ERROR' || lv === 'CRIT') return 'err'
    if (lv === 'WARN') return 'warn'
    if (lv === 'DEBUG') return 'debug'
  }
  if (t === 'autopilot_complete') return 'dim'
  return 'info'
}

function pushRow(data: Record<string, unknown>) {
  const t = String(data.type || 'info')
  const message = String(data.message || '')
  const meta = data.metadata as Record<string, unknown> | undefined

  if (t === 'progress') {
    progressHint.value = buildDetailedProgressHint(message, meta)
    progressMeta.value = meta
    applyBehaviorFromMeta(meta)
    return
  }

  if (t === 'log_line' && isNoiseMessage(message)) {
    return
  }

  if (t === 'stage_change') {
    applyBehaviorFromMeta(meta)
  }

  rows.value.push(buildDisplayRow(data))
  if (rows.value.length > MAX_ROWS) {
    rows.value.splice(0, rows.value.length - MAX_ROWS)
  }

  // 🔥 统一刷新策略：所有「会改变侧栏结构/章节列表」的事件都触发 desk-refresh
  // 使用去抖合并，避免短时间内（如幕级规划↔审阅来回）连续触发多次 loadDesk
  const needsDeskRefresh =
    t === 'stage_change' ||           // 阶段变更（规划→写作→审计→审阅）
    t === 'beat_complete' ||          // 节拍完成（字数变化）
    t === 'autopilot_complete'        // 全书完成/停止
  if (needsDeskRefresh) {
    scheduleDeskRefresh()
  }
  if (t === 'autopilot_complete') {
    emit('chapter-metrics-refresh')
  }
  // 🔥 审计事件：张力打分结果优先驱动心电图（不必等整段审计收尾）；audit_complete 再刷一次侧栏/曲线
  if (t === 'audit_event') {
    const evtType = meta?.event_type ?? (data as Record<string, unknown>).event_type
    if (evtType === 'audit_tension_result') {
      emit('chapter-metrics-refresh')
    }
    if (evtType === 'audit_complete') {
      scheduleDeskRefresh()
      emit('chapter-metrics-refresh')
    }
  }
}

const filteredRows = computed(() => {
  const q = searchText.value.trim().toLowerCase()
  return rows.value.filter((row) => {
    if (hideHttp.value && row.kind === 'http') return false
    if (importantOnly.value && !['warn', 'err'].includes(row.kind)) return false
    if (q && !row.searchable.includes(q)) return false
    return true
  })
})

const visibleRows = computed(() => {
  const list = filteredRows.value
  if (list.length <= MAX_RENDERED_ROWS) return list
  return list.slice(list.length - MAX_RENDERED_ROWS)
})

function toggleExpanded(id: string) {
  const next = new Set(expandedRows.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  expandedRows.value = next
}

function scrollToBottom() {
  const el = bodyRef.value
  if (!el || !autoScroll.value) return
  const token = ++scrollLockToken
  scrollingProgrammatically = true
  el.scrollTop = el.scrollHeight
  nextTick(() => {
    el.scrollTop = el.scrollHeight
    window.setTimeout(() => {
      if (token === scrollLockToken) {
        scrollingProgrammatically = false
      }
    }, 220)
  })
}

function scrollToBottomManual() {
  autoScroll.value = true
  const el = bodyRef.value
  if (!el) return
  const token = ++scrollLockToken
  scrollingProgrammatically = true
  nextTick(() => {
    el.scrollTop = el.scrollHeight
    window.setTimeout(() => {
      if (token === scrollLockToken) {
        scrollingProgrammatically = false
      }
    }, 220)
  })
}

function scheduleFlush() {
  if (flushScheduled) return
  flushScheduled = true
  queueMicrotask(() => {
    flushScheduled = false
    const batch = pending.splice(0, pending.length)
    for (const item of batch) {
      pushRow(item.data)
    }
    if (!autoScroll.value) return
    nextTick(() => scrollToBottom())
  })
}

function onScroll() {
  if (!bodyRef.value || scrollingProgrammatically) return
  const { scrollTop, scrollHeight, clientHeight } = bodyRef.value
  const gap = scrollHeight - scrollTop - clientHeight
  autoScroll.value = gap < 80
}

function connect() {
  if (eventSource) eventSource.close()
  const q = lastLogSeq.value > 0 ? `?after_seq=${lastLogSeq.value}` : ''
  const url = resolveHttpUrl(`/api/v1/autopilot/${props.novelId}/stream${q}`)
  eventSource = new EventSource(url)

  eventSource.onopen = () => {
    connectionStatus.value = 'connected'
    logStreamReconnectFailCount = 0
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
    } catch {
      /* ignore */
    }
  }

  eventSource.onerror = () => {
    connectionStatus.value = 'reconnecting'
    if (eventSource) {
      try {
        eventSource.close()
      } catch {
        /* ignore */
      }
      eventSource = null
    }
    if (reconnectTimer != null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    scheduleLogStreamReconnect()
  }
}

onMounted(() => {
  connect()
})

watch(
  () => props.novelId,
  () => {
    rows.value = []
    expandedRows.value = new Set()
    searchText.value = ''
    progressHint.value = ''
    behaviorStageKey.value = ''
    behaviorAutopilotStatus.value = ''
    behaviorLabel.value = '—'
    lastLogSeq.value = 0
    connectionStatus.value = 'disconnected'
    logStreamReconnectFailCount = 0
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
  if (deskRefreshDebounceTimer) {
    clearTimeout(deskRefreshDebounceTimer)
    deskRefreshDebounceTimer = null
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
  gap: 10px;
  padding: 10px 14px;
  font-size: 12px;
  background: rgba(15, 23, 42, 0.95);
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

.terminal-controls {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: #111827;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.log-search {
  flex: 1;
  min-width: 160px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 6px;
  color: #dbeafe;
  background: rgba(15, 23, 42, 0.78);
  outline: none;
}

.log-search::placeholder {
  color: #64748b;
}

.log-search:focus {
  border-color: rgba(96, 165, 250, 0.65);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.14);
}

.filter-chip {
  flex-shrink: 0;
  height: 28px;
  padding: 0 10px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 6px;
  color: #94a3b8;
  background: rgba(15, 23, 42, 0.62);
  cursor: pointer;
}

.filter-chip:hover,
.filter-chip.is-active {
  color: #dbeafe;
  border-color: rgba(96, 165, 250, 0.55);
  background: rgba(30, 64, 175, 0.34);
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
  gap: 10px;
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

.stick-bottom-btn {
  flex-shrink: 0;
  padding: 2px 8px;
  font-size: 11px;
  line-height: 1.3;
  color: #a5b4fc;
  background: rgba(79, 70, 229, 0.2);
  border: 1px solid rgba(129, 140, 248, 0.45);
  border-radius: 6px;
  cursor: pointer;
}
.stick-bottom-btn:hover {
  background: rgba(79, 70, 229, 0.35);
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
  padding: 8px 14px;
  font-size: 11px;
  color: #a5b4fc;
  background: rgba(30, 41, 59, 0.9);
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-text {
  flex-shrink: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.progress-bar-mini {
  flex-shrink: 0;
  width: 60px;
  height: 4px;
  background: rgba(148, 163, 184, 0.2);
  border-radius: 2px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #818cf8, #a78bfa);
  border-radius: 2px;
  transition: width 0.4s ease;
}

.terminal-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: auto;
  overscroll-behavior: contain;
  padding: 10px 10px 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New',
    monospace;
  font-size: 11px;
  line-height: 1.5;
}

.line {
  display: grid;
  grid-template-columns: 58px 52px minmax(180px, 260px) minmax(0, 1fr);
  align-items: start;
  gap: 8px;
  min-height: 28px;
  padding: 5px 8px;
  border-left: 2px solid transparent;
  border-radius: 6px;
  word-break: normal;
  cursor: default;
}

.line:hover {
  background: rgba(30, 41, 59, 0.68);
}

.line--expanded {
  background: rgba(30, 41, 59, 0.74);
}

.time {
  color: #64748b;
  font-variant-numeric: tabular-nums;
}

.level {
  justify-self: start;
  min-width: 42px;
  padding: 1px 6px;
  border-radius: 4px;
  color: #94a3b8;
  background: rgba(148, 163, 184, 0.08);
  text-align: center;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0;
}

.source {
  min-width: 0;
  color: #93c5fd;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: normal;
}

.msg {
  min-width: 0;
  color: #cbd5e1;
  overflow-wrap: anywhere;
  word-break: normal;
  white-space: pre-wrap;
  overflow: visible;
  text-overflow: clip;
}

.line--ok .msg {
  color: #86efac;
}
.line--debug {
  opacity: 0.74;
}
.line--debug .level {
  color: #94a3b8;
}
.line--http {
  opacity: 0.66;
}
.line--http .level {
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.12);
}
.line--http .source {
  color: #64748b;
}
.line--warn {
  border-left-color: #f59e0b;
  background: rgba(245, 158, 11, 0.08);
}
.line--warn .level {
  color: #fbbf24;
  background: rgba(245, 158, 11, 0.14);
}
.line--warn .msg {
  color: #fef3c7;
}
.line--err {
  border-left-color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}
.line--err .level {
  color: #fecaca;
  background: rgba(239, 68, 68, 0.18);
}
.line--err .msg {
  color: #fca5a5;
}
.line--dim .msg {
  color: #94a3b8;
}

.http-method {
  display: inline-block;
  width: 42px;
  color: #bfdbfe;
  font-weight: 700;
}

.http-path {
  color: #cbd5e1;
}

.http-status {
  display: inline-block;
  min-width: 32px;
  margin-left: 8px;
  padding: 0 5px;
  border-radius: 4px;
  text-align: center;
  font-size: 10px;
  font-weight: 700;
}

.http-status--ok {
  color: #bbf7d0;
  background: rgba(34, 197, 94, 0.14);
}

.http-status--redirect {
  color: #fde68a;
  background: rgba(245, 158, 11, 0.14);
}

.http-status--warn,
.http-status--err {
  color: #fecaca;
  background: rgba(239, 68, 68, 0.18);
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

@media (max-width: 760px) {
  .terminal-controls {
    flex-wrap: wrap;
  }

  .line {
    grid-template-columns: 54px 46px minmax(0, 1fr);
  }

  .source {
    display: none;
  }
}
</style>
