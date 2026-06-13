<template>
  <n-card v-if="status" class="job-status-indicator">
    <div class="job-header">
      <n-spin size="small" />
      <span class="job-type">{{ jobTypeLabel }}</span>
    </div>
    <div class="job-message">{{ status.message }}</div>
    <n-progress
      v-if="status.phase && !status.done"
      type="line"
      :percentage="calculateProgress()"
      :show-indicator="true"
    />
    <n-button
      v-if="!status.done"
      size="small"
      @click="handleCancel"
      aria-label="取消任务"
    >
      取消
    </n-button>
  </n-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NCard, NProgress, NButton, NSpin, useMessage } from 'naive-ui'
import { workflowApi } from '../../api/workflow'
import { runtimePerformance } from '../../config/performance'
import { usePolling } from '../../composables/usePolling'
import type { JobStatusResponse } from '../../types/api'

interface Props {
  jobId: string
}

const props = defineProps<Props>()
const message = useMessage()

const emit = defineEmits<{
  completed: [status: JobStatusResponse]
}>()

const status = ref<JobStatusResponse | null>(null)

const jobTypeLabel = computed(() => {
  if (!status.value) return ''
  const labels: Record<string, string> = {
    plan: '规划中',
    write: '写作中',
    run: '执行中'
  }
  return labels[status.value.kind] || status.value.kind
})

const calculateProgress = (): number => {
  if (!status.value) return 0
  if (status.value.done) return 100

  // Use phase if available for more accurate progress
  if (status.value.phase) {
    const phaseProgress: Record<string, number> = {
      'queued': 10,
      'planning': 30,
      'writing': 60,
      'reviewing': 80,
      'running': 50
    }
    return phaseProgress[status.value.phase] || 50
  }

  // Fallback to simple status-based progress
  return status.value.status === 'queued' ? 10 : 50
}

const pollStatus = async () => {
  try {
    const result = await workflowApi.getJobStatus(props.jobId)
    status.value = result

    if (result.done) {
      stopPolling()
      emit('completed', result)
    }
  } catch (error) {
    console.error('Failed to poll job status:', error)
    // Continue polling even on error - the job might still be running
  }
}

const stopPolling = () => {
  polling.stop()
}

const polling = usePolling(pollStatus, runtimePerformance.jobs.statusPollMs)

const handleCancel = async () => {
  if (!props.jobId) return

  // Stop polling optimistically
  stopPolling()

  try {
    await workflowApi.cancelJob(props.jobId)
  } catch (error) {
    console.error('Failed to cancel job:', error)
        message.error('取消任务失败，请稍后重试')
    // Don't restart polling - user intended to cancel
  }
}

onMounted(() => {
  polling.start({ immediate: true })
})
</script>

<style scoped>
.job-status-indicator {
  margin-bottom: 16px;
}

.job-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.job-type {
  font-weight: 600;
  color: #667eea;
}

.job-message {
  margin-bottom: 12px;
  color: #666;
  font-size: 14px;
}
</style>
