<template>
  <div class="ap-ops" :class="{ 'ap-ops--dag': subview === 'dag' }">
    <header class="ap-ops__bar">
      <n-text strong class="ap-ops__title">工作流监控</n-text>
      <n-switch
        :value="subview === 'dag'"
        size="medium"
        @update:value="onSubviewSwitch"
      >
        <template #checked>DAG 画布</template>
        <template #unchecked>实时日志</template>
      </n-switch>
    </header>

    <AutopilotDAGView
      v-if="subview === 'dag'"
      :novel-id="novelId"
      @desk-refresh="handleMonitorRefresh"
    />

    <div v-else class="ap-ops__monitor">
      <n-alert type="default" :show-icon="false" class="ap-ops__hint">
        <n-text depth="3" style="font-size: 12px; line-height: 1.55">
          <strong>实时监控</strong>：引擎子步骤、节拍与章节流日志。DAG 节点高亮与画布请打开右侧开关。
        </n-text>
      </n-alert>
      <AutopilotTerminalLog
        class="ap-ops__log"
        :novel-id="novelId"
        @desk-refresh="handleMonitorRefresh"
        @chapter-metrics-refresh="handleChapterMetricsRefresh"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useAutopilotWorkspaceStore } from '@/stores/autopilotWorkspaceStore'
import AutopilotTerminalLog from './AutopilotTerminalLog.vue'
import AutopilotDAGView from './AutopilotDAGView.vue'

const props = defineProps<{
  novelId: string
}>()

const emit = defineEmits<{
  'desk-refresh': []
  'chapter-metrics-refresh': []
}>()

const workspace = useAutopilotWorkspaceStore()
const { operationsSubview: subview } = storeToRefs(workspace)

function onSubviewSwitch(isDag: boolean) {
  workspace.setOperationsSubview(isDag ? 'dag' : 'monitor')
}

function handleMonitorRefresh() {
  emit('desk-refresh')
}

function handleChapterMetricsRefresh() {
  emit('chapter-metrics-refresh')
}
</script>

<style scoped>
.ap-ops {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
}

.ap-ops--dag {
  min-height: 0;
}

.ap-ops__bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-surface);
}

.ap-ops__title {
  font-size: var(--font-size-sm);
}

.ap-ops__monitor {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.ap-ops__hint {
  flex-shrink: 0;
  margin: 10px 14px 0;
  border-radius: var(--app-radius-md);
}

.ap-ops__log {
  flex: 1;
  min-height: 0;
  padding: 10px 14px 14px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.ap-ops__log :deep(.terminal-log-root),
.ap-ops__log :deep(.terminal-log) {
  flex: 1;
  min-height: 0;
}
</style>
