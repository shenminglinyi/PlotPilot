<template>
  <div class="log-panel">
    <div class="log-header">
      <div class="log-title-row">
        <span class="log-dot" aria-hidden="true" />
        <h3>实时日志</h3>
      </div>
      <n-space :size="8">
        <n-button size="tiny" secondary @click="clearLogs">清空</n-button>
        <n-button size="tiny" :type="autoScroll ? 'primary' : 'default'" @click="toggleAutoScroll">
          {{ autoScroll ? '自动滚屏开' : '自动滚屏关' }}
        </n-button>
      </n-space>
    </div>

    <div v-if="!logs.length" class="log-empty">连接建立后，后端日志会显示在这里</div>

    <n-scrollbar ref="scrollRef" class="log-content">
      <div class="log-list">
        <div
          v-for="(log, index) in logs"
          :key="index"
          class="log-item"
          :class="log.level"
        >
          <span class="log-time">{{ log.time }}</span>
          <span class="log-level">{{ log.level }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
    </n-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'

interface LogEntry {
  time: string
  level: 'INFO' | 'DEBUG' | 'ERROR' | 'WARNING'
  message: string
}

const logs = ref<LogEntry[]>([])
const scrollRef = ref<any>(null)
const autoScroll = ref(true)

const normalizeLevel = (level: string): LogEntry['level'] => {
  const u = (level || 'INFO').toUpperCase()
  if (u === 'DEBUG' || u === 'INFO' || u === 'WARNING' || u === 'ERROR') return u
  return 'INFO'
}

const addLog = (level: string, message: string) => {
  const now = new Date()
  const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`

  logs.value.push({ time, level: normalizeLevel(level), message })

  if (logs.value.length > 500) {
    logs.value.shift()
  }

  if (autoScroll.value) {
    nextTick(() => {
      scrollRef.value?.scrollTo({ top: 999999, behavior: 'smooth' })
    })
  }
}

const clearLogs = () => {
  logs.value = []
}

const toggleAutoScroll = () => {
  autoScroll.value = !autoScroll.value
}

defineExpose({
  addLog
})
</script>

<style scoped>
.log-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #1a1d24 0%, #0f1115 100%);
  color: #d4d4d4;
  font-family: 'JetBrains Mono', 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  border-left: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0;
}

.log-header {
  flex-shrink: 0;
  padding: 12px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(0, 0, 0, 0.25);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.log-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.log-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 10px rgba(34, 197, 94, 0.6);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}

.log-header h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary, #e2e8f0);
  letter-spacing: 0.02em;
}

.log-empty {
  padding: 12px 14px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

.log-content {
  flex: 1;
  min-height: 0;
  padding: 8px 10px 12px;
}

.log-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.log-item {
  display: flex;
  gap: 10px;
  padding: 5px 8px;
  border-radius: 3px;
  line-height: 1.5;
  transition: background 0.15s ease;
}

.log-item:hover {
  background: rgba(255, 255, 255, 0.04);
}

.log-time {
  color: #64748b;
  min-width: 64px;
  flex-shrink: 0;
}

.log-level {
  min-width: 60px;
  flex-shrink: 0;
  font-weight: 600;
  font-size: 11px;
}

.log-item.INFO .log-level {
  color: #4ec9b0;
}

.log-item.DEBUG .log-level {
  color: #9cdcfe;
}

.log-item.ERROR .log-level {
  color: #f48771;
}

.log-item.WARNING .log-level {
  color: #dcdcaa;
}

.log-message {
  flex: 1;
  word-break: break-all;
  color: var(--app-text-secondary, #cbd5e1);
}
</style>
