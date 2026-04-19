<template>
  <div class="circuit-breaker-status">
    <div class="breaker-header">
      <span class="breaker-title">🔌 熔断保护</span>
      <n-tag
        :type="statusTagType"
        :bordered="false"
        size="small"
      >
        {{ statusLabel }}
      </n-tag>
    </div>
    <n-text depth="3" style="font-size: 11px; line-height: 1.45; display: block; margin: -4px 0 8px">
      单本连续失败达到阈值会挂起；未启动托管时多为「正常」。
      守护进程内另有<strong>全局</strong> LLM 熔断（防 API 雪崩），本卡无法显示其开闭；若所有书长时间不推进，请查看
      <code style="font-size:10px">logs/autopilot_daemon.log</code>
      或重启守护进程并等待冷却。
    </n-text>

    <div class="breaker-body">
      <!-- 状态指示器 -->
      <div class="status-indicator">
        <div class="indicator-ring" :class="statusClass">
          <div class="indicator-core">
            <div class="status-icon">{{ statusIcon }}</div>
          </div>
        </div>
        <div class="status-text">
          <n-text :type="statusTextType" class="status-main">
            {{ statusDescription }}
          </n-text>
          <n-text depth="3" class="status-sub">
            {{ statusSubtext }}
          </n-text>
        </div>
      </div>

      <!-- 错误计数器 -->
      <div class="error-counter">
        <div class="counter-bar">
          <div
            class="counter-fill"
            :style="{ width: errorPercentage + '%' }"
            :class="errorLevelClass"
          />
        </div>
        <div class="counter-label">
          <n-text depth="3" style="font-size: 11px">
            连续错误: {{ errorCount }} / {{ maxErrors }}
          </n-text>
          <n-text
            v-if="errorCount > 0"
            :type="errorCount >= maxErrors ? 'error' : 'warning'"
            style="font-size: 11px; font-weight: 600"
          >
            {{ errorCount >= maxErrors ? '已触发熔断' : `距离熔断 ${maxErrors - errorCount} 次` }}
          </n-text>
        </div>
      </div>

      <!-- 最近错误 -->
      <div v-if="lastError" class="last-error">
        <n-text depth="3" style="font-size: 11px; margin-bottom: 4px">
          最近错误:
        </n-text>
        <n-text type="error" style="font-size: 12px">
          {{ lastError.message }}
        </n-text>
        <n-text depth="3" style="font-size: 10px; margin-top: 4px">
          {{ formatTime(lastError.timestamp) }}
        </n-text>
      </div>

      <!-- 操作按钮 -->
      <n-space v-if="isOpen" :size="8" style="margin-top: 8px">
        <n-button size="small" type="primary" @click="handleReset">
          🔄 重置熔断器
        </n-button>
        <n-button size="small" quaternary @click="showErrorHistory">
          查看错误历史
        </n-button>
      </n-space>
    </div>

    <!-- 错误历史弹窗 -->
    <n-modal
      v-model:show="showHistoryModal"
      preset="card"
      title="错误历史"
      style="width: 600px; max-height: 70vh"
    >
      <div class="error-history">
        <n-empty
          v-if="errorHistory.length === 0"
          description="暂无错误记录"
          size="small"
        />
        <div
          v-else
          v-for="(error, index) in errorHistory"
          :key="index"
          class="error-item"
        >
          <div class="error-item-header">
            <n-tag type="error" size="tiny" :bordered="false">
              错误 #{{ errorHistory.length - index }}
            </n-tag>
            <n-text depth="3" style="font-size: 11px">
              {{ formatTime(error.timestamp) }}
            </n-text>
          </div>
          <n-text class="error-item-message">
            {{ error.message }}
          </n-text>
          <n-text v-if="error.context" depth="3" class="error-item-context">
            {{ error.context }}
          </n-text>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { resolveHttpUrl } from '@/api/config'

interface ErrorRecord {
  message: string
  timestamp: string
  context?: string
}

interface CircuitBreakerData {
  status: 'closed' | 'open' | 'half_open'
  error_count: number
  max_errors: number
  last_error?: ErrorRecord
  error_history?: ErrorRecord[]
}

const props = defineProps<{
  novelId: string
}>()

const emit = defineEmits<{
  'breaker-open': []
  'breaker-reset': []
}>()

const breakerData = ref<CircuitBreakerData>({
  status: 'closed',
  error_count: 0,
  max_errors: 3
})
const showHistoryModal = ref(false)
const loading = ref(false)

let pollTimer: number | null = null
/** 该书在库中不存在(404)时不再轮询，避免旧标签页刷屏 */
let pollStopped404 = false

// 状态
const status = computed(() => breakerData.value.status)
const errorCount = computed(() => breakerData.value.error_count)
const maxErrors = computed(() => breakerData.value.max_errors)
const lastError = computed(() => breakerData.value.last_error)
const errorHistory = computed(() => breakerData.value.error_history || [])

const isClosed = computed(() => status.value === 'closed')
const isOpen = computed(() => status.value === 'open')
const isHalfOpen = computed(() => status.value === 'half_open')

// 错误百分比
const errorPercentage = computed(() => {
  return Math.min((errorCount.value / maxErrors.value) * 100, 100)
})

// 错误等级样式
const errorLevelClass = computed(() => {
  if (errorCount.value >= maxErrors.value) return 'level-critical'
  if (errorCount.value >= maxErrors.value * 0.66) return 'level-high'
  if (errorCount.value > 0) return 'level-medium'
  return 'level-safe'
})

// 状态样式
const statusClass = computed(() => {
  if (isOpen.value) return 'status-open'
  if (isHalfOpen.value) return 'status-half-open'
  return 'status-closed'
})

const statusIcon = computed(() => {
  if (isOpen.value) return '⚠️'
  if (isHalfOpen.value) return '🔄'
  return '✓'
})

const statusLabel = computed(() => {
  if (isOpen.value) return '已熔断'
  if (isHalfOpen.value) return '半开'
  return '正常'
})

const statusTagType = computed(() => {
  if (isOpen.value) return 'error'
  if (isHalfOpen.value) return 'warning'
  return 'success'
})

const statusTextType = computed(() => {
  if (isOpen.value) return 'error'
  if (isHalfOpen.value) return 'warning'
  return 'success'
})

const statusDescription = computed(() => {
  if (isOpen.value) return '熔断器已打开'
  if (isHalfOpen.value) return '正在尝试恢复'
  return '系统运行正常'
})

const statusSubtext = computed(() => {
  if (isOpen.value) return '连续错误过多，已停止生成'
  if (isHalfOpen.value) return '允许少量请求测试恢复'
  return '无异常错误，保护待命'
})

// 加载熔断器数据
async function loadBreakerData() {
  loading.value = true
  try {
    const res = await fetch(
      resolveHttpUrl(`/api/v1/autopilot/${props.novelId}/circuit-breaker`),
    )
    if (res.status === 404) {
      stopPolling()
      pollStopped404 = true
      return
    }
    if (res.ok) {
      const data = await res.json()
      const prevStatus = breakerData.value.status
      breakerData.value = data

      // 触发熔断事件
      if (prevStatus !== 'open' && data.status === 'open') {
        emit('breaker-open')
      }
    }
  } catch (err) {
    console.error('Failed to load circuit breaker data:', err)
  } finally {
    loading.value = false
  }
}

// 重置熔断器
async function handleReset() {
  try {
    const res = await fetch(
      resolveHttpUrl(`/api/v1/autopilot/${props.novelId}/circuit-breaker/reset`),
      { method: 'POST' },
    )
    if (res.ok) {
      await loadBreakerData()
      emit('breaker-reset')
      window.$message?.success('熔断器已重置')
    } else {
      window.$message?.error('重置失败')
    }
  } catch (err) {
    console.error('Failed to reset circuit breaker:', err)
    window.$message?.error('重置失败')
  }
}

// 显示错误历史
function showErrorHistory() {
  showHistoryModal.value = true
}

// 格式化时间
function formatTime(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch {
    return '--'
  }
}

// 定时轮询（每 10 秒）；先等首包再挂 interval，避免 404 后仍启动定时器
async function startPolling() {
  stopPolling()
  pollStopped404 = false
  await loadBreakerData()
  if (pollStopped404) return
  pollTimer = window.setInterval(() => {
    void loadBreakerData()
  }, 10000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 监听
watch(() => props.novelId, () => {
  void startPolling()
})

// 生命周期
onMounted(() => {
  void startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.circuit-breaker-status {
  background: var(--card-color);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px;
}

.breaker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.breaker-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color-1);
}

.breaker-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
}

.indicator-ring {
  position: relative;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.indicator-ring::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 3px solid;
  opacity: 0.3;
}

.indicator-ring.status-closed::before {
  border-color: #18a058;
}

.indicator-ring.status-half-open::before {
  border-color: #f0a020;
}

.indicator-ring.status-open::before {
  border-color: #d03050;
  animation: pulse-error 2s infinite;
}

.indicator-core {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-target-modal);
}

.status-icon {
  font-size: 24px;
}

.status-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.status-main {
  font-size: 14px;
  font-weight: 600;
}

.status-sub {
  font-size: 12px;
  line-height: 1.4;
}

.error-counter {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.counter-bar {
  height: 8px;
  background: var(--color-target-modal);
  border-radius: 4px;
  overflow: hidden;
}

.counter-fill {
  height: 100%;
  transition: width 0.3s, background-color 0.3s;
  border-radius: 4px;
}

.counter-fill.level-safe {
  background: #18a058;
}

.counter-fill.level-medium {
  background: #f0a020;
}

.counter-fill.level-high {
  background: #f08020;
}

.counter-fill.level-critical {
  background: #d03050;
  animation: pulse-fill 1s infinite;
}

.counter-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.last-error {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  background: rgba(208, 48, 80, 0.1);
  border: 1px solid rgba(208, 48, 80, 0.2);
  border-radius: 6px;
}

/* 错误历史 */
.error-history {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 500px;
  overflow-y: auto;
  padding: 8px;
}

.error-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  background: rgba(208, 48, 80, 0.05);
  border: 1px solid rgba(208, 48, 80, 0.15);
  border-radius: 6px;
}

.error-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.error-item-message {
  font-size: 13px;
  line-height: 1.5;
  color: #d03050;
}

.error-item-context {
  font-size: 12px;
  line-height: 1.4;
}

/* 动画 */
@keyframes pulse-error {
  0%, 100% {
    opacity: 0.3;
    transform: scale(1);
  }
  50% {
    opacity: 0.6;
    transform: scale(1.05);
  }
}

@keyframes pulse-fill {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
  }
}
</style>
