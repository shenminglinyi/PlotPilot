<template>
  <div v-if="loading" class="stats-top-bar loading">
    <n-spin size="medium" />
  </div>
  <div v-else-if="error" class="stats-top-bar error">
    <span>{{ error }}</span>
  </div>
  <div v-else class="stats-top-bar">
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
            <span class="stat-value" :class="{ 'stat-value-date': stat.key === 'updated' }">{{ stat.value }}</span>
          </div>
        </template>
        <span>{{ stat.tooltip }}</span>
      </n-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NTooltip, NSpin } from 'naive-ui'
import { useStatsStore } from '@/stores/statsStore'

const props = defineProps<{
  slug: string
}>()

const statsStore = useStatsStore()

// Constants
const DECIMAL_PRECISION = 1

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
    if (isNaN(date.getTime())) return dateStr
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
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

.stat-value-date {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.stat-item:hover .stat-value {
  transform: scale(1.05);
  transition: transform 0.2s;
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
