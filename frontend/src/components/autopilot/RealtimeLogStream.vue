<template>
  <div class="realtime-log-stream">
    <n-card title="📡 实时日志" size="small" :bordered="true">
      <template #header-extra>
        <n-space :size="8" align="center">
          <span class="status-dot" :class="connectionStatus"></span>
          <n-text depth="3" style="font-size: 12px">{{ statusText }}</n-text>
          <n-tag size="tiny" :bordered="false">{{ logEvents.length }} 条</n-tag>
          <n-button
            size="tiny"
            quaternary
            :title="logCollapsed ? '展开时间线' : '只折叠下方日志时间线，写作进度仍显示'"
            @click="logCollapsed = !logCollapsed"
          >
            {{ logCollapsed ? '展开日志' : '折叠日志' }}
          </n-button>
        </n-space>
      </template>

      <!-- 托管运行时的进度条（由 SSE progress 更新，约每 2 秒） -->
      <div v-if="latestProgress" class="progress-strip">
        <div class="progress-strip-head">
          <span class="progress-strip-title">写作进度</span>
          <n-text depth="3" class="progress-strip-pct">
            {{ progressPctDisplay }}%
          </n-text>
        </div>
        <n-progress
          type="line"
          :percentage="progressBarPct"
          :height="10"
          :border-radius="4"
          indicator-placement="inside"
          processing
        />
        <n-text depth="2" class="progress-strip-caption">
          {{ latestProgress.message }}
        </n-text>
      </div>

      <!-- 实时写作进度（显示字数、速率、光标 + 滚动流式文字） -->
      <div v-if="isWritingContent" class="writing-stream-bar">
        <div class="stream-header-line">
          <span class="stream-cursor">▋</span>
          <span class="stream-info">
            正在生成第 {{ writingChapterNumber }} 章
            <span v-if="writingBeatIndex > 0" class="beat-badge">节拍 {{ writingBeatIndex }}</span>
          </span>
          <span class="stream-stats">
            {{ writingWordCount }} 字
            <span v-if="writingSpeed > 0" class="speed">· {{ writingSpeed }} 字/秒</span>
          </span>
        </div>
        <div ref="scrollContainer2" class="stream-content-preview">
          <pre class="content-text">{{ streamingText }}<span class="cursor-inline">▋</span></pre>
        </div>
      </div>

      <!-- 仅折叠时间线；写作进度条与卡片标题始终可见 -->
      <n-collapse-transition :show="!logCollapsed">
        <div class="stream-wrap">
          <!-- 日志流容器 -->
          <div ref="scrollContainer" class="stream-body" @scroll="handleScroll">
            <n-timeline>
              <n-timeline-item
                v-for="event in logEvents"
                :key="event.id"
                :type="getEventType(event)"
                :time="formatTime(event.timestamp)"
              >
                <template #icon>
                  <span class="event-icon">{{ getEventIcon(event) }}</span>
                </template>
                <div
                  class="event-content"
                  :class="`event-content--${event.type}`"
                >
                  <n-text :type="getEventTextType(event)" class="event-message">
                    {{ event.message }}
                  </n-text>
                  <n-text
                    v-if="metaLine(event)"
                    depth="3"
                    class="event-metadata"
                  >
                    {{ metaLine(event) }}
                  </n-text>
                </div>
              </n-timeline-item>
            </n-timeline>

            <!-- 空状态 -->
            <n-empty v-if="logEvents.length === 0" description="等待日志流..." size="small" />
          </div>

          <!-- 悬浮的"新日志"提示按钮 -->
          <transition name="fade">
            <div
              v-if="!isAutoScroll && hasNewLogs && !logCollapsed"
              class="new-logs-indicator"
              @click="() => scrollToBottom()"
            >
              <n-button size="small" type="success" circle>
                <template #icon>
                  <span>⬇️</span>
                </template>
              </n-button>
              <span class="new-logs-text">新日志</span>
            </div>
          </transition>
        </div>
      </n-collapse-transition>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'

interface LogEvent {
  id: string
  type: string
  message: string
  timestamp: string
  metadata?: Record<string, any>
}

interface ProgressPayload {
  message: string
  metadata?: {
    progress_pct?: number
    completed_chapters?: number
    target_chapters?: number
    [k: string]: unknown
  }
}

const props = defineProps<{
  novelId: string
  writingContent?: string
  writingChapterNumber?: number
  writingBeatIndex?: number
}>()

const emit = defineEmits<{
  /** 宏观/幕级规划落库并进入待审阅时，通知工作台刷新结构树（与 HTTP 轮询解耦，避免日志已变而侧栏仍旧） */
  'desk-refresh': []
}>()

// 状态管理
const logEvents = ref<LogEvent[]>([])
const scrollContainer = ref<HTMLElement | null>(null)
const isAutoScroll = ref(true)
const hasNewLogs = ref(false)
const connectionStatus = ref<'connected' | 'reconnecting' | 'disconnected' | 'ended'>('disconnected')
/** 服务端已发送 autopilot_complete 并关闭流，属正常结束，禁止重连刷屏 */
const streamEndedNormally = ref(false)
const endedSummary = ref('')
/** 仅折叠下方时间线，不折叠写作进度与标题栏 */
const logCollapsed = ref(false)
/** 最新一条 progress 事件，用于顶部进度条（不入时间线，避免刷屏） */
const latestProgress = ref<ProgressPayload | null>(null)

// 写作速率计算
const lastWordCount = ref(0)
const lastTimestamp = ref(0)
const writingSpeed = ref(0)

// 滚动流式显示：只显示最近的增量文字
const lastContentLength = ref(0)
const streamingText = ref('')
const scrollContainer2 = ref<HTMLElement | null>(null)

const isWritingContent = computed(() => props.writingContent && props.writingContent.length > 0 && (props.writingChapterNumber || 0) > 0)
const writingWordCount = computed(() => props.writingContent?.length || 0)
const writingChapterNumber = computed(() => props.writingChapterNumber || 0)
const writingBeatIndex = computed(() => props.writingBeatIndex || 0)

const progressBarPct = computed(() => {
  const p = latestProgress.value?.metadata?.progress_pct
  if (typeof p === 'number' && !Number.isNaN(p)) {
    return Math.min(100, Math.max(0, p))
  }
  return 0
})

const progressPctDisplay = computed(() => {
  const p = latestProgress.value?.metadata?.progress_pct
  if (typeof p === 'number' && !Number.isNaN(p)) {
    return p.toFixed(1)
  }
  return '0.0'
})

let eventSource: EventSource | null = null
let reconnectTimer: number | null = null

// 状态文本
const statusText = computed(() => {
  switch (connectionStatus.value) {
    case 'connected':
      return '正在接收'
    case 'reconnecting':
      return '重新连接中...'
    case 'disconnected':
      return '已断开'
    case 'ended':
      return endedSummary.value || '流已结束'
    default:
      return '未知'
  }
})

// 连接 SSE
function connectSSE() {
  if (streamEndedNormally.value) {
    return
  }
  if (eventSource) {
    eventSource.close()
  }

  try {
    eventSource = new EventSource(`/api/v1/autopilot/${props.novelId}/stream`)

    eventSource.onopen = () => {
      connectionStatus.value = 'connected'
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    eventSource.onmessage = async (e) => {
      try {
        const data = JSON.parse(e.data)

        if (data.type === 'heartbeat') {
          return
        }

        if (data.type === 'progress') {
          latestProgress.value = {
            message: data.message || '',
            metadata: data.metadata
          }
          return
        }

        if (data.type === 'autopilot_complete') {
          endedSummary.value = data.message || '自动驾驶已结束'
          streamEndedNormally.value = true
          connectionStatus.value = 'ended'
          if (reconnectTimer) {
            clearTimeout(reconnectTimer)
            reconnectTimer = null
          }
        }

        // 添加新日志（从底部添加）
        const newEvent: LogEvent = {
          id: `${Date.now()}-${Math.random()}`,
          type: data.type || 'info',
          message: data.message || '未知事件',
          timestamp: data.timestamp || new Date().toISOString(),
          metadata: data.metadata
        }

        logEvents.value.push(newEvent)

        // 限制日志条数（保留最新 100 条）
        if (logEvents.value.length > 100) {
          logEvents.value.shift()
        }

        if (data.type === 'stage_change' && data.metadata?.to_stage === 'paused_for_review') {
          emit('desk-refresh')
        }
        // beat 级增量落库会影响章节字数/“已收稿”标签；收到 beat_complete 主动触发一次软刷新
        if (data.type === 'beat_complete') {
          emit('desk-refresh')
        }

        // 如果用户没有手动滚动，自动滚到底部
        if (isAutoScroll.value) {
          await nextTick()
          scrollToBottom(true)
        } else {
          hasNewLogs.value = true
        }

        if (data.type === 'autopilot_complete' && eventSource) {
          eventSource.close()
          eventSource = null
        }
      } catch (err) {
        console.error('Failed to parse SSE message:', err)
      }
    }

    eventSource.onerror = () => {
      if (streamEndedNormally.value) {
        return
      }
      connectionStatus.value = 'reconnecting'

      // 3秒后尝试重连
      if (!reconnectTimer) {
        reconnectTimer = window.setTimeout(() => {
          connectSSE()
        }, 3000)
      }
    }
  } catch (err) {
    console.error('Failed to create EventSource:', err)
    connectionStatus.value = 'disconnected'
  }
}

// 滚动到底部
function scrollToBottom(smooth = false) {
  if (!scrollContainer.value) return

  scrollContainer.value.scrollTo({
    top: scrollContainer.value.scrollHeight,
    behavior: smooth ? 'smooth' : 'auto'
  })

  isAutoScroll.value = true
  hasNewLogs.value = false
}

// 处理用户手动滚动
function handleScroll() {
  if (!scrollContainer.value) return

  const { scrollTop, scrollHeight, clientHeight } = scrollContainer.value
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight

  // 如果距离底部超过 50px，认为用户在查看历史日志
  if (distanceFromBottom > 50) {
    isAutoScroll.value = false
  } else {
    isAutoScroll.value = true
    hasNewLogs.value = false
  }
}

// 获取事件类型（Timeline 颜色）
function getEventType(event: LogEvent): 'success' | 'error' | 'warning' | 'info' {
  if (event.type === 'stage_change') return 'warning'
  if (event.type.includes('error')) return 'error'
  if (event.type === 'autopilot_complete') return 'info'
  if (event.type.includes('complete')) return 'success'
  if (event.type.includes('warning')) return 'warning'
  return 'info'
}

// 获取事件图标
function getEventIcon(event: LogEvent): string {
  if (event.type === 'stage_change') return '🔄'
  if (event.type === 'connected') return '🔌'
  if (event.type.includes('error')) return '❌'
  if (event.type === 'autopilot_complete') return '⏹'
  if (event.type.includes('complete')) return '✅'
  if (event.type.includes('start')) return '✍️'
  if (event.type.includes('warning')) return '⚠️'
  return '📝'
}

// 获取事件文本类型
function getEventTextType(event: LogEvent): 'success' | 'error' | 'warning' | 'default' {
  if (event.type.includes('error')) return 'error'
  if (event.type === 'autopilot_complete') return 'warning'
  if (event.type.includes('complete')) return 'success'
  if (event.type.includes('warning')) return 'warning'
  return 'default'
}

// 格式化时间
function formatTime(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    return date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch {
    return '--:--:--'
  }
}

function metaLine(event: LogEvent): string {
  return formatMetadata(event.metadata, event.type)
}

// 格式化元数据（主文案已为中文时不再重复英文键）
function formatMetadata(metadata: Record<string, any> | undefined, eventType: string): string {
  if (!metadata) return ''
  if (
    eventType === 'stage_change' ||
    eventType === 'beat_start' ||
    eventType === 'beat_complete' ||
    eventType === 'beat_error' ||
    eventType === 'connected' ||
    eventType === 'autopilot_complete'
  ) {
    return ''
  }
  try {
    const entries = Object.entries(metadata)
      .filter(([key]) => !['timestamp', 'type', 'status'].includes(key))
      .map(([key, value]) => `${key}: ${value}`)
    return entries.join(' · ')
  } catch {
    return ''
  }
}

// 生命周期
onMounted(() => {
  connectSSE()
})

watch(
  () => props.novelId,
  () => {
    streamEndedNormally.value = false
    endedSummary.value = ''
    logCollapsed.value = false
    latestProgress.value = null
    logEvents.value = []
    connectionStatus.value = 'disconnected'
    lastWordCount.value = 0
    lastTimestamp.value = 0
    writingSpeed.value = 0
    lastContentLength.value = 0
    streamingText.value = ''
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    connectSSE()
  }
)

// 计算写作速率
watch(
  () => props.writingContent,
  (content) => {
    if (!content) {
      lastWordCount.value = 0
      lastTimestamp.value = 0
      writingSpeed.value = 0
      lastContentLength.value = 0
      streamingText.value = ''
      return
    }
    const now = Date.now()
    const currentCount = content.length

    // 计算速率
    if (lastTimestamp.value > 0 && lastWordCount.value > 0) {
      const timeDiff = (now - lastTimestamp.value) / 1000 // 秒
      const wordDiff = currentCount - lastWordCount.value
      if (timeDiff > 0 && wordDiff > 0) {
        writingSpeed.value = Math.round(wordDiff / timeDiff)
      }
    }

    // 流式滚动显示：只显示最近的文字（避免内容无限累积导致重复显示）
    if (currentCount > lastContentLength.value) {
      // 只保留最后 500 个字符，避免内容过长
      const displayLimit = 500
      if (currentCount > displayLimit) {
        streamingText.value = content.slice(-displayLimit)
      } else {
        streamingText.value = content
      }
      lastContentLength.value = currentCount

      // 自动滚动到底部
      nextTick(() => {
        if (scrollContainer2.value) {
          scrollContainer2.value.scrollTop = scrollContainer2.value.scrollHeight
        }
      })
    }

    lastWordCount.value = currentCount
    lastTimestamp.value = now
  }
)

// 监听章节变化，清空滚动文本
watch(
  () => props.writingChapterNumber,
  () => {
    streamingText.value = ''
    lastContentLength.value = 0
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
.realtime-log-stream {
  position: relative;
}

.stream-wrap {
  position: relative;
}

.progress-strip {
  padding: 10px 12px 12px;
  margin: 0 0 8px;
  border-radius: 8px;
  background: linear-gradient(
    135deg,
    rgba(24, 160, 88, 0.08) 0%,
    rgba(32, 128, 240, 0.06) 100%
  );
  border: 1px solid var(--border-color);
}

.progress-strip-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.progress-strip-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-color-2);
}

.progress-strip-pct {
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.progress-strip-caption {
  display: block;
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
}

/* 实时写作进度条 */
.writing-stream-bar {
  margin-bottom: 8px;
  background: linear-gradient(135deg, rgba(24, 160, 88, 0.06) 0%, rgba(24, 160, 88, 0.02) 100%);
  border: 1px solid rgba(24, 160, 88, 0.15);
  border-radius: 6px;
  overflow: hidden;
}

.writing-stream-bar .stream-header-line {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 12px;
}

.writing-stream-bar .stream-cursor {
  color: #18a058;
  animation: blink 1s step-end infinite;
  font-size: 14px;
}

@keyframes blink {
  50% { opacity: 0; }
}

.writing-stream-bar .stream-info {
  flex: 1;
  color: var(--text-color-2);
}

.writing-stream-bar .beat-badge {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(24, 160, 88, 0.15);
  color: #18a058;
  font-size: 11px;
}

.writing-stream-bar .stream-stats {
  color: var(--text-color-3);
  font-variant-numeric: tabular-nums;
}

.writing-stream-bar .speed {
  color: #18a058;
}

.writing-stream-bar .stream-content-preview {
  max-height: 120px;
  overflow-y: auto;
  padding: 6px 10px;
  border-top: 1px solid rgba(24, 160, 88, 0.1);
  background: rgba(0, 0, 0, 0.02);
}

.writing-stream-bar .content-text {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-color-2);
  font-family: var(--font-mono);
}

.writing-stream-bar .cursor-inline {
  color: #18a058;
  animation: blink 1s step-end infinite;
  font-size: 13px;
}

/* 顶部状态栏 */
.stream-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: var(--card-color);
  border-bottom: 1px solid var(--border-color);
  font-size: 12px;
  color: var(--text-color-2);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  transition: all 0.3s;
}

.status-dot.connected {
  background: #18a058;
  box-shadow: 0 0 8px rgba(24, 160, 88, 0.5);
  animation: pulse-green 2s infinite;
}

.status-dot.reconnecting {
  background: #f0a020;
  animation: blink-yellow 1s infinite;
}

.status-dot.disconnected {
  background: #d03050;
}

.status-dot.ended {
  background: #2080f0;
}

@keyframes pulse-green {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes blink-yellow {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.status-text {
  color: var(--text-color-2);
  font-weight: 500;
}

.log-count {
  margin-left: auto;
  color: var(--text-color-3);
  font-size: 11px;
}

/* 日志流主体 */
.stream-body {
  height: 280px;
  overflow-y: auto;
  padding: 12px 16px;
  scroll-behavior: smooth;
  font-family: ui-sans-serif, system-ui, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.stream-body::-webkit-scrollbar {
  width: 6px;
}

.stream-body::-webkit-scrollbar-track {
  background: var(--scrollbar-color);
}

.stream-body::-webkit-scrollbar-thumb {
  background: var(--scrollbar-color-hover);
  border-radius: 3px;
}

.stream-body::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-color-hover);
}

/* Timeline 样式覆盖 */
.stream-body :deep(.n-timeline) {
  padding-left: 0;
}

.stream-body :deep(.n-timeline-item) {
  padding-bottom: 12px;
}

.stream-body :deep(.n-timeline-item__timeline) {
  width: 2px;
  background: var(--border-color);
}

.event-icon {
  font-size: 14px;
}

.event-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.event-message {
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-color-1);
  letter-spacing: 0.02em;
}

.event-content--stage_change .event-message {
  font-weight: 600;
}

.event-content--beat_start .event-message,
.event-content--beat_complete .event-message {
  font-size: 12.5px;
}

.event-metadata {
  font-size: 11px;
  color: var(--text-color-3);
}

/* 新日志指示器 */
.new-logs-indicator {
  position: absolute;
  bottom: 16px;
  right: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(24, 160, 88, 0.9);
  border-radius: 20px;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  transition: all 0.3s;
  z-index: 10;
}

.new-logs-indicator:hover {
  background: rgba(24, 160, 88, 1);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.new-logs-text {
  color: white;
  font-size: 12px;
  font-weight: 500;
}

/* 过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s, transform 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
