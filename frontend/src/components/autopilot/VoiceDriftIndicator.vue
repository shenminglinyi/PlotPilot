<template>
  <div class="voice-drift-indicator">
    <div class="indicator-header">
      <span class="indicator-title">🎭 文风警报器</span>
      <n-button v-if="isDanger" size="tiny" type="error" @click="showDetail">
        查看详情
      </n-button>
    </div>

    <div class="indicator-body">
      <!-- 圆形进度指示器 -->
      <div class="progress-circle">
        <n-progress
          type="circle"
          :percentage="driftPercentage"
          :color="driftColor"
          :rail-color="railColor"
          :stroke-width="8"
          :show-indicator="false"
          :style="{ width: '100px', height: '100px' }"
        />
        <div class="progress-center">
          <div class="drift-icon">{{ driftIcon }}</div>
          <div class="drift-score">{{ driftScore.toFixed(1) }}</div>
        </div>
      </div>

      <!-- 状态信息 -->
      <div class="status-info">
        <n-text :type="driftTextType" class="status-label">
          {{ driftLabel }}
        </n-text>
        <n-text depth="3" class="status-desc">
          {{ driftDescription }}
        </n-text>

        <!-- 最近检测时间 -->
        <n-text v-if="lastCheckTime" depth="3" class="last-check">
          最近检测: {{ formatTime(lastCheckTime) }}
        </n-text>
      </div>
    </div>

    <!-- 详情弹窗 -->
    <n-modal
      v-model:show="showDetailModal"
      preset="card"
      title="文风偏移详情"
      style="width: 600px"
    >
      <n-space vertical :size="12">
        <n-descriptions :column="2" bordered size="small">
          <n-descriptions-item label="当前偏移值">
            <n-text :type="driftTextType">{{ driftScore.toFixed(2) }}</n-text>
          </n-descriptions-item>
          <n-descriptions-item label="安全阈值">
            <n-text>{{ safeThreshold.toFixed(1) }}</n-text>
          </n-descriptions-item>
          <n-descriptions-item label="检测章节">
            第 {{ lastCheckChapter }} 章
          </n-descriptions-item>
          <n-descriptions-item label="状态">
            <n-tag :type="driftTextType" size="small">{{ driftLabel }}</n-tag>
          </n-descriptions-item>
        </n-descriptions>

        <n-card v-if="driftDetails" title="偏移分析" size="small">
          <n-space vertical :size="8">
            <div v-for="(item, index) in driftDetails" :key="index" class="drift-item">
              <n-text depth="2">{{ item.dimension }}:</n-text>
              <n-text :type="item.severity">{{ item.description }}</n-text>
            </div>
          </n-space>
        </n-card>

        <n-alert v-if="isDanger" type="error" :show-icon="true">
          <template #header>建议操作</template>
          <n-ul>
            <n-li>考虑回滚到最近的语义快照</n-li>
            <n-li>检查并调整 AI Prompt 参数</n-li>
            <n-li>手动审阅最近生成的章节</n-li>
          </n-ul>
        </n-alert>
      </n-space>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { resolveHttpUrl } from '@/api/config'

interface VoiceDriftData {
  drift_score: number
  status: 'safe' | 'warning' | 'danger'
  last_check_chapter: number
  last_check_time: string
  details?: Array<{
    dimension: string
    description: string
    severity: 'default' | 'warning' | 'error'
  }>
}

const props = defineProps<{
  novelId: string
  safeThreshold?: number  // 安全阈值，默认 3.0
  dangerThreshold?: number  // 危险阈值，默认 6.0
}>()

const emit = defineEmits<{
  'drift-alert': [score: number, status: string]
}>()

const driftData = ref<VoiceDriftData | null>(null)
const showDetailModal = ref(false)
const loading = ref(false)

let pollTimer: number | null = null

// 阈值
const safeThreshold = computed(() => props.safeThreshold ?? 3.0)
const dangerThreshold = computed(() => props.dangerThreshold ?? 6.0)

// 偏移分数
const driftScore = computed(() => driftData.value?.drift_score ?? 0)

// 偏移百分比（用于圆形进度条，最大值为 10）
const driftPercentage = computed(() => Math.min((driftScore.value / 10) * 100, 100))

// 状态
const driftStatus = computed(() => {
  if (driftScore.value >= dangerThreshold.value) return 'danger'
  if (driftScore.value >= safeThreshold.value) return 'warning'
  return 'safe'
})

const isDanger = computed(() => driftStatus.value === 'danger')
const isWarning = computed(() => driftStatus.value === 'warning')
const isSafe = computed(() => driftStatus.value === 'safe')

// 颜色
const driftColor = computed(() => {
  if (isDanger.value) return '#d03050'
  if (isWarning.value) return '#f0a020'
  return '#18a058'
})

const railColor = computed(() => {
  return 'rgba(255, 255, 255, 0.1)'
})

// 图标
const driftIcon = computed(() => {
  if (isDanger.value) return '⚠️'
  if (isWarning.value) return '⚡'
  return '✓'
})

// 标签
const driftLabel = computed(() => {
  if (isDanger.value) return '严重偏离'
  if (isWarning.value) return '轻微偏离'
  return '文风稳定'
})

// 描述
const driftDescription = computed(() => {
  if (isDanger.value) return '文风与基准差异过大，建议立即处理'
  if (isWarning.value) return '检测到文风波动，请注意观察'
  return '文风保持一致，无需干预'
})

// 文本类型
const driftTextType = computed(() => {
  if (isDanger.value) return 'error'
  if (isWarning.value) return 'warning'
  return 'success'
})

// 最近检测时间
const lastCheckTime = computed(() => driftData.value?.last_check_time)
const lastCheckChapter = computed(() => driftData.value?.last_check_chapter ?? 0)

// 偏移详情
const driftDetails = computed(() => driftData.value?.details ?? [])

// 加载文风偏移数据
async function loadDriftData() {
  loading.value = true
  try {
    const res = await fetch(
      resolveHttpUrl(`/api/v1/novels/${props.novelId}/monitor/voice-drift`),
    )
    if (res.ok) {
      const dataArray = await res.json()
      // 取第一个角色的数据（或者可以聚合多个角色）
      if (dataArray && dataArray.length > 0) {
        const firstChar = dataArray[0]
        // 转换新 API 格式到组件格式
        driftData.value = {
          drift_score: firstChar.drift_score * 10, // 转换 0-1 到 0-10
          status: firstChar.status === 'critical' ? 'danger' : firstChar.status === 'warning' ? 'warning' : 'safe',
          last_check_chapter: 0, // API 暂不提供
          last_check_time: new Date().toISOString(),
          details: []
        }

        // 触发警报
        if (isDanger.value || isWarning.value) {
          emit('drift-alert', driftScore.value, driftStatus.value)
        }
      }
    }
  } catch (err) {
    console.error('Failed to load voice drift data:', err)
  } finally {
    loading.value = false
  }
}

// 显示详情
function showDetail() {
  showDetailModal.value = true
}

// 格式化时间
function formatTime(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return '--'
  }
}

// 定时轮询（每 30 秒）
function startPolling() {
  loadDriftData()
  pollTimer = window.setInterval(() => {
    loadDriftData()
  }, 30000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 监听
watch(() => props.novelId, () => {
  stopPolling()
  startPolling()
})

// 生命周期
onMounted(() => {
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.voice-drift-indicator {
  background: var(--card-color);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px;
}

.indicator-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.indicator-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color-1);
}

.indicator-body {
  display: flex;
  align-items: center;
  gap: 16px;
}

.progress-circle {
  position: relative;
  flex-shrink: 0;
}

.progress-center {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}

.drift-icon {
  font-size: 24px;
  margin-bottom: 4px;
}

.drift-score {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color-1);
  font-variant-numeric: tabular-nums;
}

.status-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.status-label {
  font-size: 15px;
  font-weight: 600;
}

.status-desc {
  font-size: 12px;
  line-height: 1.5;
}

.last-check {
  font-size: 11px;
  margin-top: 4px;
}

.drift-item {
  display: flex;
  gap: 8px;
  font-size: 13px;
  line-height: 1.6;
}
</style>
