<template>
  <div v-if="loading" class="stats-top-bar loading">
    <n-spin size="medium" />
  </div>
  <div v-else-if="error" class="stats-top-bar error">
    <span>{{ error }}</span>
  </div>
  <div v-else class="stats-top-bar">
    <div class="topbar-center">
      <GlobalLLMEntryButton appearance="topbar" />
    </div>
    <div
      v-for="stat in stats"
      :key="stat.key"
      class="stat-item"
      role="group"
      :aria-label="stat.label"
    >
      <n-tooltip :show-arrow="false">
        <template #trigger>
          <div class="stat-content">
            <span class="stat-label">{{ stat.label }}</span>
            <span class="stat-value">{{ stat.value }}</span>
          </div>
        </template>
        <span>{{ stat.tooltip }}</span>
      </n-tooltip>
    </div>

    <div class="settings-trigger" @click="$emit('open-settings')" role="button" aria-label="LLM 设置">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20">
        <path fill="currentColor" d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6A3.6 3.6 0 1 1 12 8.4a3.6 3.6 0 0 1 0 7.2z"/>
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NTooltip, NSpin } from 'naive-ui'
import { useStatsStore } from '@/stores/statsStore'
import GlobalLLMEntryButton from '@/components/global/GlobalLLMEntryButton.vue'

const props = defineProps<{
  slug: string
}>()

defineEmits<{
  'open-settings': []
}>()

const statsStore = useStatsStore()

// Constants
const DECIMAL_PRECISION = 1
const MS_PER_DAY = 1000 * 60 * 60 * 24
const DAYS_THRESHOLD = 7

// State
const loading = ref(false)
const error = ref<string | null>(null)

// Fix: Remove .value before function call
const bookStats = computed(() => statsStore.getBookStats(props.slug))

const stats = computed(() => {
  if (!bookStats.value) return []

  const s = bookStats.value

  const totalWords = Number(s.total_words ?? 0)
  const rate = Number(s.completion_rate ?? 0)
  const avgWords = Number(s.avg_chapter_words ?? 0)
  const done = Number(s.completed_chapters ?? 0)
  const total = Number(s.total_chapters ?? 0)

  const formattedWords = totalWords.toLocaleString()
  const formattedCompletionRate = rate.toFixed(DECIMAL_PRECISION)
  const formattedAvgWords = avgWords.toLocaleString()

  return [
    {
      key: 'words',
      label: '总字数',
      value: formattedWords,
      tooltip: `当前书籍共 ${formattedWords} 字`
    },
    {
      key: 'chapters',
      label: '完成章节',
      value: `${done}/${total}`,
      tooltip: `已完成 ${done} 章，共 ${total} 章`
    },
    {
      key: 'completion',
      label: '完成率',
      value: `${formattedCompletionRate}%`,
      tooltip: `项目完成度：${formattedCompletionRate}%`
    },
    {
      key: 'avg',
      label: '平均字数',
      value: formattedAvgWords,
      tooltip: `每章平均 ${formattedAvgWords} 字`
    },
    {
      key: 'updated',
      label: '最后更新',
      value: formatDate(s.last_updated),
      tooltip: `最后更新时间：${s.last_updated}`
    }
  ]
})

function formatStatsError(err: unknown): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const data = (err as { response?: { data?: { detail?: unknown } } }).response?.data
    const d = data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) {
      return d
        .map((x: { msg?: string }) => (typeof x?.msg === 'string' ? x.msg : JSON.stringify(x)))
        .join('; ')
    }
  }
  if (err instanceof Error) return err.message
  return String(err)
}

function formatDate(dateStr: string | undefined): string {
  if (!dateStr) return '—'
  try {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffDays = Math.floor(diffMs / MS_PER_DAY)

    if (diffDays === 0) {
      return '今天'
    } else if (diffDays === 1) {
      return '昨天'
    } else if (diffDays < DAYS_THRESHOLD) {
      return `${diffDays}天前`
    } else {
      return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
    }
  } catch {
    return dateStr
  }
}

onMounted(async () => {
  loading.value = true
  error.value = null
  try {
    await statsStore.loadBookStats(props.slug)
  } catch (err) {
    console.error('Failed to load book stats:', err)
    error.value = `加载统计数据失败：${formatStatsError(err)}`
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.stats-top-bar {
  height: 80px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 0 24px;
  color: white;
  position: relative;
}

.topbar-center {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  z-index: 2;
  pointer-events: auto;
}

.stats-top-bar.loading,
.stats-top-bar.error {
  justify-content: center;
}

.stats-top-bar.error span {
  font-size: 14px;
  opacity: 0.9;
}

.stat-item {
  flex: 1;
  text-align: center;
  cursor: help;
}

.stat-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  opacity: 0.9;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
}

.stat-item:hover .stat-value {
  transform: scale(1.05);
  transition: transform 0.2s;
}

.settings-trigger {
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 0.15s ease;
  border-radius: 8px;
}

.settings-trigger:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.15);
}

/* Accessibility: Focus styles */
.stat-item:focus-within {
  outline: 2px solid rgba(255, 255, 255, 0.5);
  outline-offset: 4px;
  border-radius: 4px;
}

/* Responsive design */
@media (max-width: 768px) {
  .stats-top-bar {
    height: auto;
    flex-wrap: wrap;
    padding: 16px;
  }

  .stat-item {
    flex: 0 0 50%;
    margin-bottom: 12px;
  }

  .stat-value {
    font-size: 20px;
  }
}

@media (max-width: 480px) {
  .stat-item {
    flex: 0 0 100%;
  }
}
</style>
