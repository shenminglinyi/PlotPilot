<template>
  <div class="autopilot-dashboard" :class="{ 'dashboard--dag': viewMode === 'dag' }">
    <!-- 顶部栏：标题 + Switch（仅卡片模式显示，DAG模式由 DAGToolbar 接管） -->
    <div v-if="viewMode !== 'dag'" class="dashboard-topbar">
      <n-text strong class="topbar-title">🧭 工作流监控</n-text>
      <n-switch
        v-model:value="isDagMode"
        size="small"
      >
        <template #checked>DAG</template>
        <template #unchecked>卡片</template>
      </n-switch>
    </div>

    <!-- DAG 视图 -->
    <AutopilotDAGView
      v-if="viewMode === 'dag'"
      :novel-id="novelId"
      @desk-refresh="handleMonitorRefresh"
      @switch-view="handleSwitchView"
    />

    <!-- 卡片视图（原有） -->
    <template v-else>
      <n-alert type="default" :show-icon="false" class="monitor-copy-hint">
        <n-text depth="3" style="font-size: 12px; line-height: 1.5">
          <strong>监控说明</strong>：「文风」卡片为按<strong>角色声线</strong>的偏离监测。全书<strong>作者文风指纹</strong>与侧栏「剧本基建」规划为不同能力，与此处互补。
        </n-text>
      </n-alert>
      <!-- 监控网格 -->
      <div class="monitor-grid">
        <!-- 第一行：张力图表 + 实时日志 -->
        <div class="grid-cell span-2">
          <TensionChart :novel-id="novelId" :refresh-key="chapterMetricsRefreshKey" />
        </div>
        <div class="grid-cell span-1 grid-cell--terminal">
          <AutopilotTerminalLog
            :novel-id="novelId"
            @desk-refresh="handleMonitorRefresh"
            @chapter-metrics-refresh="handleChapterMetricsRefresh"
          />
        </div>

        <!-- 第二行：文风警报 + 伏笔账本 + 熔断器 -->
        <div class="grid-cell">
          <VoiceDriftIndicator
            :novel-id="novelId"
            :refresh-key="monitorRefreshKey"
            @drift-alert="handleDriftAlert"
          />
        </div>
        <div class="grid-cell">
          <ForeshadowLedger :novel-id="novelId" :refresh-key="monitorRefreshKey" />
        </div>
        <div class="grid-cell">
          <CircuitBreakerStatus
            :novel-id="novelId"
            :refresh-key="monitorRefreshKey"
            @breaker-open="handleBreakerOpen"
            @breaker-reset="handleBreakerReset"
          />
        </div>
      </div>
    </template>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { useDAGRunStore } from '@/stores/dagRunStore'
import TensionChart from './TensionChart.vue'
import AutopilotTerminalLog from './AutopilotTerminalLog.vue'
import VoiceDriftIndicator from './VoiceDriftIndicator.vue'
import ForeshadowLedger from './ForeshadowLedger.vue'
import CircuitBreakerStatus from './CircuitBreakerStatus.vue'
import AutopilotDAGView from './AutopilotDAGView.vue'

const props = defineProps<{
  novelId: string
}>()

const emit = defineEmits<{
  'desk-refresh': []
}>()

const message = useMessage()
const runStore = useDAGRunStore()

// 视图模式：卡片 / DAG
const viewMode = ref<'card' | 'dag'>('card')
const isDagMode = computed({
  get: () => viewMode.value === 'dag',
  set: (val: boolean) => { viewMode.value = val ? 'dag' : 'card' },
})

// 🔥 监控面板统一刷新信号
const monitorRefreshKey = ref(0)
const chapterMetricsRefreshKey = ref(0)

// DAG 运行完成时自动刷新监控数据
runStore.onRunComplete(() => {
  monitorRefreshKey.value++
  chapterMetricsRefreshKey.value++
})

onMounted(() => {
  runStore.fetchStatus(props.novelId)
})

onUnmounted(() => {
  runStore.disconnectSSE()
})

function handleMonitorRefresh() {
  monitorRefreshKey.value++
  emit('desk-refresh')
}

function handleChapterMetricsRefresh() {
  chapterMetricsRefreshKey.value++
}

function handleDriftAlert(score: number, status: string) {
  if (status === 'danger') {
    message.error(`⚠️ 文风严重偏离 (${score.toFixed(1)})，建议立即处理`)
  } else if (status === 'warning') {
    message.warning(`⚡ 文风轻微偏离 (${score.toFixed(1)})，请注意观察`)
  }
}

function handleBreakerOpen() {
  message.error('🔌 熔断器已触发，连续错误过多，Autopilot 已自动停止')
}

function handleBreakerReset() {
  message.success('🔄 熔断器已重置，可以重新启动 Autopilot')
}

function handleSwitchView(mode: 'card' | 'dag') {
  viewMode.value = mode
}
</script>

<style scoped>
.autopilot-dashboard {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

/* DAG 视图：禁止外层滚动，画布自行平移/缩放 */
.dashboard--dag {
  overflow: hidden;
}

.dashboard-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-surface);
  min-height: 40px;
}

.topbar-title {
  font-size: 14px;
  color: var(--app-text-primary);
}

.monitor-copy-hint {
  margin: 0 4px 12px;
  padding: 8px 12px;
}

.monitor-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  padding: 4px;
}

.grid-cell {
  min-height: 280px;
}

.grid-cell--terminal {
  display: flex;
  flex-direction: column;
  align-self: start;
  width: 100%;
  min-width: 0;
  height: clamp(220px, 42vh, 340px);
  overflow: hidden;
}

.grid-cell.span-1 {
  grid-column: span 1;
}

.grid-cell.span-2 {
  grid-column: span 2;
}

@media (max-width: 1400px) {
  .monitor-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .grid-cell.span-2 {
    grid-column: span 2;
  }
}

@media (max-width: 900px) {
  .monitor-grid {
    grid-template-columns: 1fr;
  }

  .grid-cell.span-1,
  .grid-cell.span-2 {
    grid-column: span 1;
  }
}
</style>
