<template>
  <div v-if="loading" class="stats-top-bar loading">
    <n-spin size="medium" />
  </div>
  <div v-else-if="error" class="stats-top-bar error">
    <span>{{ error }}</span>
    <n-button size="small" secondary style="margin-left: 12px" @click="retryLoad">重试</n-button>
  </div>
  <div v-else class="stats-top-bar">
    <!-- 左侧：AI 工具统一入口（隐藏原始按钮，通过 ref 触发） -->
    <div class="topbar-left">
      <!-- 隐藏的原始组件，仅用于保留其 drawer/modal 功能 -->
      <div class="ai-hidden-entries" aria-hidden="true">
        <GlobalLLMEntryButton ref="llmRef" appearance="topbar" />
        <PromptPlazaEntryButton ref="plazaRef" appearance="topbar" />
      </div>

      <!-- 可见的统一触发按钮 -->
      <n-dropdown
        trigger="click"
        placement="bottom-start"
        :options="aiToolsOptions"
        @select="handleAiToolSelect"
      >
        <div class="ai-tools-trigger" role="button" aria-label="AI 工具">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16">
            <path fill="currentColor" d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1v2h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2v-2h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 10 4a2 2 0 0 1 2-2m0 2a.5.5 0 0 0 0 1 .5.5 0 0 0 0-1M7.5 13a5 5 0 0 0-4.95 4.5H21.45A5 5 0 0 0 16.5 13h-9M9 18v1h2v-1H9m4 0v1h2v-1h-2z"/>
          </svg>
          <span class="ai-tools-label">AI 工具</span>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="12" height="12">
            <path fill="currentColor" d="M7 10l5 5 5-5z"/>
          </svg>
        </div>
      </n-dropdown>
    </div>

    <!-- 中间：统计数据 -->
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
              <span class="stat-value">{{ stat.value }}</span>
            </div>
          </template>
          <span>{{ stat.tooltip }}</span>
        </n-tooltip>
      </div>
    </div>

    <!-- 右侧：操作按钮 -->
    <div class="top-bar-actions">
      <!-- 导出按钮 -->
      <n-dropdown 
        trigger="click" 
        placement="bottom-end"
        :options="exportOptions"
        @select="handleExport"
      >
        <div class="action-trigger" role="button" aria-label="导出">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20">
            <path fill="currentColor" d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
          </svg>
        </div>
      </n-dropdown>

      <!-- 设置按钮 -->
      <div class="settings-trigger" @click="$emit('open-settings')" role="button" aria-label="打开设置">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18">
          <path fill="currentColor" d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6A3.6 3.6 0 1 1 12 8.4a3.6 3.6 0 0 1 0 7.2z"/>
        </svg>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NTooltip, NSpin, NDropdown, NButton, useMessage } from 'naive-ui'
import { useStatsStore } from '@/stores/statsStore'
import { novelApi } from '@/api/novel'
import GlobalLLMEntryButton from '@/components/global/GlobalLLMEntryButton.vue'
import PromptPlazaEntryButton from '@/components/global/PromptPlazaEntryButton.vue'

const props = defineProps<{
  slug: string
}>()

defineEmits<{
  'open-settings': []
}>()

const message = useMessage()

// AI 工具组件引用（用于以编程方式触发各组件内部按钮）
const llmRef = ref<{ $el: HTMLElement } | null>(null)
const plazaRef = ref<{ $el: HTMLElement } | null>(null)

const aiToolsOptions = [
  { label: '⚙️ AI 控制台', key: 'llm' },
  { label: '✦ 提示词广场', key: 'plaza' },
]

function handleAiToolSelect(key: string) {
  if (key === 'llm') {
    llmRef.value?.$el?.querySelector('button')?.click()
  } else if (key === 'plaza') {
    plazaRef.value?.$el?.querySelector('button')?.click()
  }
}

// 导出选项
const exportOptions = [
  { label: '📱 EPUB (电子书)', key: 'epub' },
  { label: '📄 PDF (打印)', key: 'pdf' },
  { label: '📝 DOCX (Word)', key: 'docx' },
  { label: '📋 Markdown', key: 'markdown' }
]

async function handleExport(format: string) {
  try {
    message.info(`开始导出为 ${format} 格式...`)
    const blob = await novelApi.exportNovel(props.slug, format)
    
    // 创建下载链接
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `novel-${props.slug}.${format}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    
    message.success(`导出 ${format} 格式成功！`)
  } catch (error) {
    console.error('导出失败:', error)
    message.error('导出失败，请稍后重试')
  }
}

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
/* ═══════════════════════════════════════════════════
   StatsTopBar — 与 AI 控制台一体化的顶部导航栏
   使用 CSS 变量，自动适配亮/暗主题
   ═══════════════════════════════════════════════════ */
.stats-top-bar {
  height: 64px;
  background: var(--stats-bar-gradient);
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  color: var(--nav-hero-text, #ffffff);
  position: relative;
  gap: 16px;
  min-width: 0;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
  border-bottom: 1px solid var(--app-border, rgba(255, 255, 255, 0.08));
  box-shadow:
    var(--app-shadow-sm, 0 1px 3px rgba(0, 0, 0, 0.08)),
    0 4px 16px var(--color-brand-border, rgba(79, 70, 229, 0.08));
}

/* 左侧：AI 控制台入口 */
.topbar-left {
  flex-shrink: 0;
  z-index: 2;
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: center;
  gap: 10px;
}

/* 隐藏的 AI 入口组件（仅保留功能，不参与布局） */
.ai-hidden-entries {
  position: absolute;
  visibility: hidden;
  pointer-events: none;
  width: 0;
  height: 0;
  overflow: hidden;
  top: -9999px;
}

/* 统一 AI 工具触发按钮 */
.ai-tools-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: var(--app-radius-md);
  cursor: pointer;
  background: var(--nav-hero-pill-bg-top, rgba(255, 255, 255, 0.16));
  border: 1px solid var(--nav-hero-pill-border, rgba(255, 255, 255, 0.28));
  color: var(--nav-hero-text, #ffffff);
  transition: all var(--app-transition);
  white-space: nowrap;
  box-shadow: var(--nav-hero-shadow);
  user-select: none;
}

.ai-tools-trigger:hover {
  background: rgba(255, 255, 255, 0.24);
}

.ai-tools-label {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

/* 中间：统计数据 */
.topbar-center {
  flex: 1;
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-width: 0;
  z-index: 1;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
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
  flex: 0 0 auto;
  text-align: center;
  cursor: help;
  padding: 4px 10px;
  border-radius: var(--app-radius-sm);
  transition: background 0.2s ease;
}

.stat-item:hover {
  background: rgba(255, 255, 255, 0.12);
}

.stat-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
}

.stat-label {
  font-size: 12px;
  opacity: 0.92;
  font-weight: 600;
  letter-spacing: 0.03em;
  white-space: nowrap;
  color: var(--nav-hero-text-muted, rgba(255, 255, 255, 0.86));
}

.stat-value {
  font-size: 20px;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.2;
  color: var(--nav-hero-text, #ffffff);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
}

.stat-item:hover .stat-value {
  transform: scale(1.04);
  transition: transform 0.2s ease;
}

/* 右侧：操作按钮 */
.top-bar-actions {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  gap: 8px;
  flex: 0 0 auto;
  align-items: center;
}

.action-trigger {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0.9;
  transition: all 0.18s ease;
  border-radius: var(--app-radius-sm);
  color: inherit;
}

.action-trigger:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.16);
  transform: rotate(45deg);
}

/* 右侧：设置触发器 */
.settings-trigger {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0.9;
  transition: all 0.18s ease;
  border-radius: var(--app-radius-sm);
  color: inherit;
}

.settings-trigger:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.16);
  transform: rotate(45deg);
}

.dropdown-item-icon {
  margin-right: 8px;
  font-size: 16px;
}

/* Accessibility: Focus styles */
.stat-item:focus-within {
  outline: 2px solid rgba(255, 255, 255, 0.55);
  outline-offset: 4px;
  border-radius: 4px;
}

.settings-trigger:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.55);
  outline-offset: 2px;
}

/* Responsive design — 全程单行横向，窄屏可横向滚动 */
@media (max-width: 900px) {
  .stats-top-bar {
    height: 56px;
    flex-wrap: nowrap;
    padding: 8px 12px;
    gap: 8px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: thin;
  }

  .topbar-left {
    flex-shrink: 0;
  }

  .topbar-left :deep(.global-llm-main.variant-topbar),
  .topbar-left :deep(.plaza-main.variant-topbar) {
    min-height: 42px;
    padding: 6px 10px;
  }

  .topbar-center {
    justify-content: flex-end;
    flex: 1 1 auto;
  }

  .stat-value {
    font-size: 15px;
  }

  .settings-trigger {
    position: static;
    transform: none;
  }

  .settings-trigger:hover {
    transform: rotate(45deg);
  }
}

@media (max-width: 480px) {
  .stat-item {
    flex: 0 0 33%;
  }

  .stat-value {
    font-size: 14px;
  }

  .stat-label {
    font-size: 12px;
  }
}
</style>
