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
  overflow: hidden;       /* 面板自身不滚动；内部各区域自管高度 */
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
  padding: 5px 14px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-surface);
  min-height: 36px;
}

.topbar-title {
  font-size: var(--font-size-sm);
  color: var(--app-text-primary);
}

/* 说明行：单行紧凑，不占多余高度 */
.monitor-copy-hint {
  flex-shrink: 0;
  margin: 4px 4px 5px;
  padding: 4px 10px;
}

.monitor-copy-hint :deep(.n-alert__content) {
  font-size: var(--font-size-xs) !important;
  line-height: 1.45;
}

/* 主网格：填满剩余高度 */
.monitor-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  /* 第一行（图表+日志）弹性拉伸；第二行（三小卡）按内容自然高度 */
  grid-template-rows: minmax(0, 1fr) auto;
  gap: 8px;
  padding: 0 4px 4px;
  overflow: hidden;
}

/* 网格单元：无固定高度，跟随行高 */
.grid-cell {
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 第一行单元：让内容 card 填满整格 */
.grid-cell.span-2,
.grid-cell--terminal {
  height: 100%;
}

.grid-cell--terminal {
  width: 100%;
  min-width: 0;
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
    grid-template-rows: none;
    overflow-y: auto;
  }
  .grid-cell,
  .grid-cell.span-1,
  .grid-cell.span-2 {
    grid-column: span 1;
    height: auto;
  }
}
</style>
