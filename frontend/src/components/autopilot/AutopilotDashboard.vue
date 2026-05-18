<template>
  <div class="autopilot-dashboard" :class="{ 'dashboard--dag': viewMode === 'dag' }">
    <!-- 顶部栏：标题 + Switch（仅在卡片模式下显示，DAG 模式下 Switch 在 DAGToolbar 里） -->
    <div class="dashboard-topbar" v-if="viewMode !== 'dag'">
      <n-text strong class="topbar-title">
        🧭 工作流监控
      </n-text>
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
        <n-text depth="3" class="monitor-copy-hint__text">
          <strong>监控说明</strong>：「文风」卡片为按<strong>角色声线</strong>的偏离监测。全书<strong>作者文风指纹</strong>与侧栏「剧本基建」规划为不同能力，与此处互补。
        </n-text>
      </n-alert>
      <!-- 顶部：心电图 + 日志（独立占高，避免与下方卡片争 1fr 被压扁） -->
      <div class="monitor-stack">
        <div class="monitor-top-row">
          <div class="monitor-top-chart">
            <TensionChart :novel-id="novelId" :refresh-key="chapterMetricsRefreshKey" />
          </div>
          <div class="monitor-top-log">
            <AutopilotTerminalLog
              :novel-id="novelId"
              @desk-refresh="handleMonitorRefresh"
              @chapter-metrics-refresh="handleChapterMetricsRefresh"
            />
          </div>
        </div>
        <!-- 第二行：文风警报 + 伏笔账本 + 熔断器 -->
        <div class="monitor-bottom-row">
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
      </div>
    </template>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { useDAGRunStore } from '@/stores/dagRunStore'
import { useDAGStore } from '@/stores/dagStore'
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
const dagStore = useDAGStore()

// 使用 dagStore 的 viewMode 作为单一状态源
const viewMode = computed(() => dagStore.viewMode)

const isDagMode = computed({
  get: () => dagStore.viewMode === 'dag',
  set: (val: boolean) => { dagStore.switchView(val ? 'dag' : 'card') },
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
  dagStore.switchView(mode)
}
</script>

<style scoped>
.autopilot-dashboard {
  height: 100%;
  display: flex;
  flex-direction: column;
  /* 仅卡片根容器裁剪横向；纵向交给 monitor-stack 滚动，避免底部伏笔等卡片被裁掉 */
  overflow-x: hidden;
  overflow-y: hidden;
}

/* DAG 视图：同样禁止外层滚动 */
.dashboard--dag {
  overflow: hidden;
}

.dashboard-topbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-surface);
  min-height: 44px;
}

.topbar-title {
  font-size: var(--font-size-sm);
  color: var(--app-text-primary);
}

.monitor-copy-hint {
  flex-shrink: 0;
  margin: 10px 12px 0;
  padding: 12px 16px;
  border-radius: 10px;
}

.monitor-copy-hint :deep(.n-alert__content) {
  padding: 0 !important;
}

.monitor-copy-hint__text {
  font-size: 12px;
  line-height: 1.6;
  display: block;
}

/* 上：曲线+日志（高度有上限，避免占满视口把伏笔区顶出可视区）；下：三卡始终随内容完整占位，整块可滚动 */
.monitor-stack {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 14px 12px 20px;
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  scroll-padding-bottom: 16px;
}

.monitor-top-row {
  flex: 1 1 0;
  min-height: clamp(200px, 28vh, 380px);
  max-height: min(52vh, 600px);
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr);
  gap: 14px;
  min-width: 0;
}

.monitor-top-chart,
.monitor-top-log {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.monitor-bottom-row {
  flex: 0 0 auto;
  flex-shrink: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  min-width: 0;
}

.grid-cell {
  min-width: 0;
  min-height: 0;
  overflow: visible;
  display: flex;
  flex-direction: column;
}

@media (max-width: 1400px) {
  .monitor-bottom-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 1100px) {
  .monitor-top-row {
    grid-template-columns: 1fr;
    min-height: clamp(220px, 32vh, 400px);
    max-height: min(58vh, 640px);
  }
  .monitor-top-log {
    min-height: 200px;
    max-height: min(38vh, 360px);
  }
  .monitor-top-chart {
    min-height: 180px;
    flex: 1 1 55%;
  }
}

@media (max-width: 900px) {
  .monitor-bottom-row {
    grid-template-columns: 1fr;
  }
  .monitor-top-row {
    min-height: 260px;
    max-height: none;
  }
}
</style>
