<template>
  <div class="ap-metrics">
    <header class="ap-metrics__head">
      <h2 class="ap-metrics__title">仪表盘</h2>
      <p class="ap-metrics__desc">张力走势、文风偏离、伏笔账本与熔断状态</p>
    </header>

    <div class="ap-metrics__stack">
      <section class="ap-metrics__hero" aria-label="张力曲线">
        <TensionChart :novel-id="novelId" :refresh-key="chapterMetricsRefreshKey" />
      </section>

      <section class="ap-metrics__grid" aria-label="质量指标">
        <div class="ap-metrics__cell">
          <VoiceDriftIndicator
            :novel-id="novelId"
            :refresh-key="monitorRefreshKey"
            @drift-alert="handleDriftAlert"
          />
        </div>
        <div class="ap-metrics__cell">
          <ForeshadowLedger :novel-id="novelId" :refresh-key="monitorRefreshKey" />
        </div>
        <div class="ap-metrics__cell">
          <CircuitBreakerStatus
            :novel-id="novelId"
            :refresh-key="monitorRefreshKey"
            @breaker-open="handleBreakerOpen"
            @breaker-reset="handleBreakerReset"
          />
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { useDAGRunStore } from '@/stores/dagRunStore'
import TensionChart from './TensionChart.vue'
import VoiceDriftIndicator from './VoiceDriftIndicator.vue'
import ForeshadowLedger from './ForeshadowLedger.vue'
import CircuitBreakerStatus from './CircuitBreakerStatus.vue'

const props = defineProps<{
  novelId: string
}>()

const emit = defineEmits<{
  'desk-refresh': []
}>()

const message = useMessage()
const runStore = useDAGRunStore()

const monitorRefreshKey = ref(0)
const chapterMetricsRefreshKey = ref(0)

runStore.onRunComplete(() => {
  monitorRefreshKey.value++
  chapterMetricsRefreshKey.value++
})

onMounted(() => {
  runStore.fetchStatus(props.novelId)
})

function handleMonitorRefresh() {
  monitorRefreshKey.value++
  chapterMetricsRefreshKey.value++
  emit('desk-refresh')
}

function handleDriftAlert(score: number, status: string) {
  if (status === 'danger') {
    message.error(`文风严重偏离 (${score.toFixed(1)})，建议立即处理`)
  } else if (status === 'warning') {
    message.warning(`文风轻微偏离 (${score.toFixed(1)})，请注意观察`)
  }
}

function handleBreakerOpen() {
  message.error('熔断器已触发，连续错误过多，Autopilot 已自动停止')
}

function handleBreakerReset() {
  message.success('熔断器已重置，可以重新启动 Autopilot')
}

defineExpose({ bumpRefresh: handleMonitorRefresh })
</script>

<style scoped>
.ap-metrics {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface-subtle);
}

.ap-metrics__head {
  flex-shrink: 0;
  margin: 14px 16px 0;
  padding-bottom: 4px;
}

.ap-metrics__title {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  color: var(--app-text-primary);
  letter-spacing: -0.02em;
}

.ap-metrics__desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.5;
}

.ap-metrics__stack {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 14px 16px 20px;
  overflow-y: auto;
}

.ap-metrics__hero {
  flex: 0 0 auto;
  min-height: clamp(220px, 34vh, 420px);
  display: flex;
  flex-direction: column;
}

.ap-metrics__grid {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.ap-metrics__cell {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

@media (max-width: 1200px) {
  .ap-metrics__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .ap-metrics__grid {
    grid-template-columns: 1fr;
  }
}
</style>
