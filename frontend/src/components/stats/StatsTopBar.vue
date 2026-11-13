<template>
  <div v-if="loading" class="stats-top-bar loading">
    <n-spin size="small" />
  </div>
  <div v-else-if="error" class="stats-top-bar error">
    <span>{{ error }}</span>
    <n-button size="small" secondary style="margin-left: 12px" @click="retryLoad">重试</n-button>
  </div>
  <div v-else class="stats-top-bar">
    <!-- 左侧：返回首页 + AI 控制台 + 模组中心直达入口 -->
    <div class="topbar-left">
      <div class="ai-hidden-entries" aria-hidden="true">
        <GlobalLLMEntryButton ref="llmRef" appearance="topbar" />
        <PromptPlazaEntryButton ref="plazaRef" appearance="topbar" />
      </div>

      <button
        type="button"
        class="topbar-pill-btn"
        aria-label="打开 AI 控制台"
        @click="openLlmConsole"
      >
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <circle cx="10" cy="10" r="2.8" stroke="currentColor" stroke-width="1.6" />
          <path
            d="M10 3v1.8M10 15.2V17M17 10h-1.8M4.8 10H3M14.95 5.05l-1.27 1.27M6.32 13.68l-1.27 1.27M14.95 14.95l-1.27-1.27M6.32 6.32 5.05 5.05"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
          />
        </svg>
        <span>AI 控制台</span>
      </button>

      <button
        type="button"
        class="topbar-pill-btn modhub-pill"
        aria-label="打开墨枢模组中心"
        @click="openModHub"
      >
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path
            d="M6.5 3v3M13.5 3v3M4.5 6h11v3.5a5.5 5.5 0 0 1-11 0V6ZM10 15v2"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <span>模组中心</span>
        <span v-if="modHubStore.installedCount > 0" class="pill-count numeric">
          {{ modHubStore.installedCount }}
        </span>
      </button>
    </div>

    <!-- 中间：书籍统计指标 -->
    <div class="topbar-center">
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
              <span class="stat-value numeric">{{ stat.value }}</span>
            </div>
          </template>
          <span>{{ stat.tooltip }}</span>
        </n-tooltip>
      </div>
    </div>

    <!-- 右侧：专注模式 + 导出 + 设置 -->
    <div class="top-bar-actions">
      <button
        type="button"
        class="topbar-pill-btn zen-btn"
        :class="{ active: zenMode }"
        :aria-pressed="Boolean(zenMode)"
        title="专注写作模式 (Alt+Z)"
        @click="$emit('toggle-zen')"
      >
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path
            v-if="!zenMode"
            d="M3.5 7V4.5a1 1 0 0 1 1-1H7M13 3.5h2.5a1 1 0 0 1 1 1V7M16.5 13v2.5a1 1 0 0 1-1 1H13M7 16.5H4.5a1 1 0 0 1-1-1V13"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            v-else
            d="M7 3.5v3.5H3.5M13 3.5v3.5h3.5M13 16.5V13h3.5M7 16.5V13H3.5"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <span class="zen-label">{{ zenMode ? '退出专注' : '专注模式' }}</span>
      </button>

      <n-dropdown
        trigger="click"
        placement="bottom-end"
        :options="exportOptions"
        @select="handleExport"
      >
        <button type="button" class="icon-btn" aria-label="导出书稿" title="导出书稿">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path
              d="M10 3.5v8.5m0 0L6.75 8.75M10 12l3.25-3.25M4 14.5v1a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-1"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </button>
      </n-dropdown>

      <button
        type="button"
        class="icon-btn"
        aria-label="打开设置"
        title="应用设置"
        @click="$emit('open-settings')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
          <path
            fill="currentColor"
            d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6A3.6 3.6 0 1 1 12 8.4a3.6 3.6 0 0 1 0 7.2z"
          />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NTooltip, NSpin, NDropdown, NButton, useMessage } from 'naive-ui'
import { useStatsStore } from '@/stores/statsStore'
import { useModHubStore } from '@/stores/modHubStore'
import { novelApi } from '@/api/novel'
import GlobalLLMEntryButton from '@/components/global/GlobalLLMEntryButton.vue'
import PromptPlazaEntryButton from '@/components/global/PromptPlazaEntryButton.vue'

const props = defineProps<{
  slug: string
  zenMode?: boolean
}>()

defineEmits<{
  'open-settings': []
  'toggle-zen': []
}>()

const message = useMessage()
const statsStore = useStatsStore()
const modHubStore = useModHubStore()

const llmRef = ref<{ $el: HTMLElement } | null>(null)
const plazaRef = ref<{ $el: HTMLElement } | null>(null)

function openLlmConsole() {
  llmRef.value?.$el?.querySelector('button')?.click()
}

function openModHub() {
  plazaRef.value?.$el?.querySelector('button')?.click()
}

const exportOptions = [
  { label: 'EPUB 电子书', key: 'epub' },
  { label: 'PDF 打印稿', key: 'pdf' },
  { label: 'DOCX 文档', key: 'docx' },
  { label: 'Markdown 原稿', key: 'markdown' },
]

async function handleExport(format: string) {
  try {
    message.info(`开始导出为 ${format} 格式...`)
    const blob = await novelApi.exportNovel(props.slug, format)

    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `novel-${props.slug}.${format}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    message.success(`导出 ${format} 格式成功`)
  } catch (error) {
    console.error('导出失败:', error)
    message.error('导出失败，请稍后重试')
  }
}

const DECIMAL_PRECISION = 1
const MS_PER_DAY = 1000 * 60 * 60 * 24
const DAYS_THRESHOLD = 7

const loading = ref(false)
const error = ref<string | null>(null)

const bookStats = computed(() => statsStore.getBookStats(props.slug))

const stats = computed(() => {
  if (!bookStats.value) return []

  const s = bookStats.value
  const totalWords = Number(s.total_words ?? 0)
  const avgWords = Number(s.avg_chapter_words ?? 0)
  const done = Number(s.completed_chapters ?? 0)
  const total = Number(s.total_chapters ?? 0)
  const apiRate = Number(s.completion_rate ?? 0)
  const plannedCompletionRate =
    total > 0
      ? Math.min(100, Math.max(0, (done / total) * 100))
      : Math.min(100, Math.max(0, apiRate <= 1 ? apiRate * 100 : apiRate))

  const formattedWords = totalWords.toLocaleString()
  const formattedCompletionRate = plannedCompletionRate.toFixed(DECIMAL_PRECISION)
  const formattedAvgWords = avgWords.toLocaleString()

  return [
    {
      key: 'words',
      label: '总字数',
      value: formattedWords,
      tooltip: `当前书籍共 ${formattedWords} 字`,
    },
    {
      key: 'chapters',
      label: '已收稿 / 规划',
      value: `${done}/${total}`,
      tooltip: `当前规划 ${total} 章，其中 ${done} 章已收稿`,
    },
    {
      key: 'completion',
      label: '收稿率',
      value: `${formattedCompletionRate}%`,
      tooltip: `已收稿章节 ÷ 当前规划章节：${done}/${total}`,
    },
    {
      key: 'avg',
      label: '均章字数',
      value: formattedAvgWords,
      tooltip: `每章平均 ${formattedAvgWords} 字`,
    },
    {
      key: 'updated',
      label: '更新于',
      value: formatDate(s.last_updated),
      tooltip: `最后更新时间：${s.last_updated}`,
    },
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

    if (diffDays === 0) return '今天'
    if (diffDays === 1) return '昨天'
    if (diffDays < DAYS_THRESHOLD) return `${diffDays}天前`
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return dateStr
  }
}

async function loadStats() {
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
}

async function retryLoad() {
  await loadStats()
}

onMounted(loadStats)
</script>

<style scoped>
.stats-top-bar {
  height: var(--plotpilot-topbar-height, 54px);
  background: var(--app-surface);
  color: var(--app-text-primary);
  border-bottom: 1px solid var(--app-border);
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  gap: 12px;
  min-width: 0;
  overflow: hidden;
}

.stats-top-bar.loading,
.stats-top-bar.error {
  justify-content: center;
}

.stats-top-bar.error span {
  font-size: 14px;
  color: var(--app-text-secondary);
}

.numeric {
  font-variant-numeric: tabular-nums;
}

.topbar-left {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.ai-hidden-entries {
  position: absolute;
  visibility: hidden;
  pointer-events: none;
  width: 0;
  height: 0;
  overflow: hidden;
  top: -9999px;
}

.topbar-pill-btn {
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface-subtle);
  color: var(--app-text-primary);
  font-size: 13px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease;
}

.topbar-pill-btn svg {
  width: 15px;
  height: 15px;
  color: var(--app-text-secondary);
  flex: none;
}

.topbar-pill-btn:hover {
  border-color: var(--color-brand);
  color: var(--color-brand);
}

.topbar-pill-btn:hover svg {
  color: var(--color-brand);
}

.topbar-pill-btn.active {
  background: var(--color-brand);
  border-color: var(--color-brand);
  color: var(--app-text-inverse);
}

.topbar-pill-btn.active svg {
  color: var(--app-text-inverse);
}

.pill-count {
  font-size: 11px;
  font-weight: 700;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-brand-light);
  color: var(--color-brand);
}

.topbar-center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}

.stat-item {
  flex: 0 1 auto;
  padding: 4px 10px;
  border-radius: 7px;
  cursor: help;
  transition: background-color 0.15s ease;
}

.stat-item:hover {
  background: var(--app-surface-subtle);
}

.stat-content {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.stat-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--app-text-muted);
  white-space: nowrap;
}

.stat-value {
  font-size: 14px;
  font-weight: 700;
  color: var(--app-text-primary);
  white-space: nowrap;
}

.top-bar-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.icon-btn {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background-color 0.15s ease;
}

.icon-btn svg {
  width: 17px;
  height: 17px;
}

.icon-btn:hover {
  border-color: var(--color-brand);
  color: var(--color-brand);
  background: var(--app-surface-subtle);
}

@media (max-width: 960px) {
  .stat-content {
    flex-direction: column;
    align-items: center;
    gap: 1px;
  }

  .zen-label {
    display: none;
  }
}

@media (max-width: 680px) {
  .topbar-center {
    display: none;
  }
}
</style>
