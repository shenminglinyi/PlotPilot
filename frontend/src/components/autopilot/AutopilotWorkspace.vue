<template>
  <div class="ap-workspace">
    <AutopilotShellNav />

    <div class="ap-workspace__body">
      <!-- 三页均 v-show 保持挂载：章节 SSE、DAG SSE、轮询不因切页断开 -->
      <section
        v-show="workspace.activeTab === 'cockpit'"
        class="ap-workspace__pane ap-workspace__pane--cockpit"
        aria-label="全托管驾驶"
      >
        <n-alert type="success" :show-icon="true" class="ap-workspace__hint">
          <strong>全托管模式</strong>：后端守护进程自动宏观规划、幕级规划、章节撰写与审计。启动后可在「仪表盘」看质量指标，在「监控 · DAG」看日志与画布。
        </n-alert>
        <AutopilotPanel
          class="ap-workspace__cockpit-panel"
          :novel-id="novelId"
          @status-change="onStatusChange"
          @chapter-content-update="onChapterContentUpdate"
          @chapter-chunk="onChapterChunk"
          @desk-refresh="onDeskRefresh"
          @beats-planned="onBeatsPlanned"
        />
      </section>

      <section
        v-show="workspace.activeTab === 'dashboard'"
        class="ap-workspace__pane"
        aria-label="仪表盘"
      >
        <AutopilotMetricsDashboard
          ref="metricsRef"
          :novel-id="novelId"
          @desk-refresh="onMetricsDeskRefresh"
        />
      </section>

      <section
        v-show="workspace.activeTab === 'operations'"
        class="ap-workspace__pane ap-workspace__pane--ops"
        aria-label="监控与 DAG"
      >
        <AutopilotOperationsView
          :novel-id="novelId"
          @desk-refresh="onOpsDeskRefresh"
          @chapter-metrics-refresh="onChapterMetricsRefresh"
        />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef } from 'vue'
import { useAutopilotWorkspaceStore } from '@/stores/autopilotWorkspaceStore'
import { useDAGSSE } from '@/composables/useDAGSSE'
import AutopilotShellNav from './AutopilotShellNav.vue'
import AutopilotPanel from './AutopilotPanel.vue'
import AutopilotMetricsDashboard from './AutopilotMetricsDashboard.vue'
import AutopilotOperationsView from './AutopilotOperationsView.vue'

const props = defineProps<{
  novelId: string
}>()

const emit = defineEmits<{
  'status-change': [status: Record<string, unknown>]
  'chapter-content-update': [data: { chapterNumber: number; content: string; wordCount: number }]
  'chapter-chunk': [data: { chunk: string; beatIndex: number; content: string; chapterNumber: number }]
  'desk-refresh': []
  'beats-planned': [payload: { chapterNumber: number; beats: Array<Record<string, unknown>> }]
  'chapter-metrics-refresh': []
}>()

const workspace = useAutopilotWorkspaceStore()
const metricsRef = ref<InstanceType<typeof AutopilotMetricsDashboard> | null>(null)

/** 工作区级 DAG SSE，切页不断连 */
useDAGSSE(toRef(props, 'novelId'))

function onOpsDeskRefresh() {
  emit('desk-refresh')
}

function onMetricsDeskRefresh() {
  emit('desk-refresh')
}

function onChapterMetricsRefresh() {
  metricsRef.value?.bumpRefresh?.()
  emit('chapter-metrics-refresh')
}

function onStatusChange(status: Record<string, unknown>) {
  emit('status-change', status)
}

function onChapterContentUpdate(data: { chapterNumber: number; content: string; wordCount: number }) {
  emit('chapter-content-update', data)
}

function onChapterChunk(data: { chunk: string; beatIndex: number; content: string; chapterNumber: number }) {
  emit('chapter-chunk', data)
}

function onDeskRefresh() {
  emit('desk-refresh')
}

function onBeatsPlanned(payload: { chapterNumber: number; beats: Array<Record<string, unknown>> }) {
  emit('beats-planned', payload)
}
</script>

<style scoped>
.ap-workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-page-bg);
}

.ap-workspace__body {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.ap-workspace__pane {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
}

.ap-workspace__pane--cockpit {
  overflow-y: auto;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--color-success, #16a34a) 4%, var(--app-surface)) 0%,
    var(--app-surface) 120px
  );
}

.ap-workspace__hint {
  flex-shrink: 0;
  margin: 12px 16px 0;
  font-size: 12px;
  line-height: 1.55;
}

.ap-workspace__cockpit-panel {
  flex-shrink: 0;
}

.ap-workspace__pane--ops {
  background: var(--app-surface-subtle);
}
</style>
