<template>
  <!-- 兼容旧引用：请改用 AutopilotWorkspace + Metrics / Operations 分页 -->
  <AutopilotMetricsDashboard
    v-if="surface === 'dashboard'"
    :novel-id="novelId"
    @desk-refresh="emit('desk-refresh')"
  />
  <AutopilotOperationsView
    v-else
    :novel-id="novelId"
    @desk-refresh="emit('desk-refresh')"
  />
</template>

<script setup lang="ts">
import AutopilotMetricsDashboard from './AutopilotMetricsDashboard.vue'
import AutopilotOperationsView from './AutopilotOperationsView.vue'

withDefaults(
  defineProps<{
    novelId: string
    /** dashboard = 指标卡；operations = 日志 + DAG */
    surface?: 'dashboard' | 'operations'
  }>(),
  { surface: 'dashboard' },
)

const emit = defineEmits<{
  'desk-refresh': []
}>()
</script>
