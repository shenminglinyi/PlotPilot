<template>
  <!-- 移动端窄屏顶部汉堡触发钮（<768px 显示，保证窄屏主内容 100% 宽度不被挤压） -->
  <button
    v-if="!mobileOpen"
    type="button"
    class="mobile-sidebar-trigger"
    aria-label="打开导航栏"
    @click="mobileOpen = true"
  >
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" aria-hidden="true">
      <path
        d="M3 5.5h14M3 10h14M3 14.5h14"
        stroke="currentColor"
        stroke-width="1.7"
        stroke-linecap="round"
      />
    </svg>
  </button>

  <div
    v-if="mobileOpen"
    class="mobile-sidebar-mask"
    aria-hidden="true"
    @click="mobileOpen = false"
  />

  <aside
    class="stats-sidebar"
    :class="{ 'is-collapsed': collapsed, 'is-mobile-open': mobileOpen }"
  >
    <header class="sidebar-brand">
      <div class="brand-logo">
        <span
          class="logo-icon"
          :class="{ 'is-expandable': collapsed }"
          :role="collapsed ? 'button' : undefined"
          :aria-label="collapsed ? '展开侧边栏' : undefined"
          :tabindex="collapsed ? 0 : undefined"
          @click="onSealClick"
          @keydown.enter.prevent="onSealClick"
        >
          墨
        </span>
        <div class="brand-text">
          <span class="brand-name">PlotPilot</span>
          <p class="brand-slogan">墨枢 · 长篇叙事工作台</p>
        </div>
      </div>

      <button
        type="button"
        class="collapse-toggle"
        :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
        @click="handleToggleClick"
      >
        <svg viewBox="0 0 24 24" fill="none" width="15" height="15">
          <path
            :d="collapsed ? 'M9 18l6-6-6-6' : 'M15 18l-6-6 6-6'"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </header>

    <div class="sidebar-scroll">
      <section class="stats-section">
        <div class="section-header">
          <h2 class="section-title">创作概览</h2>
          <button
            type="button"
            class="refresh-btn"
            :disabled="loading"
            :class="{ loading }"
            aria-label="刷新统计数据"
            @click="handleRefresh"
          >
            <svg viewBox="0 0 20 20" fill="none" width="13" height="13" class="refresh-svg">
              <path
                d="M16.2 6.2v3.6h-3.6M3.8 13.8v-3.6h3.6M5.8 7.2a5.2 5.2 0 0 1 8.5 1.3M14.2 12.8a5.2 5.2 0 0 1-8.5-1.3"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>
        </div>

        <div class="stats-row">
          <div class="stat-metric" :class="{ loading }">
            <span class="metric-value numeric">{{ globalStats?.total_books ?? 0 }}</span>
            <span class="metric-label">书目</span>
          </div>
          <div class="metric-divider" />
          <div class="stat-metric" :class="{ loading }">
            <span class="metric-value numeric">{{ globalStats?.total_chapters ?? 0 }}</span>
            <span class="metric-label">章节</span>
          </div>
          <div class="metric-divider" />
          <div class="stat-metric" :class="{ loading }">
            <span class="metric-value numeric">{{ formatNumber(globalStats?.total_words ?? 0) }}</span>
            <span class="metric-label">总字数</span>
          </div>
        </div>

        <div class="stage-distribution">
          <h3 class="stage-title">创作阶段</h3>
          <div v-if="loading" class="stage-list" aria-hidden="true">
            <div v-for="n in 4" :key="n" class="stage-item stage-item--skeleton">
              <span class="stage-dot stage-dot--placeholder" />
              <n-skeleton style="flex: 1; max-width: 68%" :height="12" round />
              <n-skeleton :width="28" :height="18" round />
            </div>
          </div>
          <div
            v-else-if="globalStats?.books_by_stage && Object.keys(globalStats.books_by_stage).length > 0"
            class="stage-list"
          >
            <div
              v-for="(count, stage) in globalStats.books_by_stage"
              :key="stage"
              class="stage-item"
            >
              <span class="stage-dot" :class="`stage-${stage}`" />
              <span class="stage-name">{{ getStageLabel(stage as string) }}</span>
              <span class="stage-count numeric">{{ count }}</span>
            </div>
          </div>
          <div v-else class="stage-list stage-empty">
            <span class="stage-empty-hint">暂无分阶段统计</span>
          </div>
        </div>
      </section>

      <section class="quick-actions">
        <button
          type="button"
          class="action-btn action-create"
          @click="onCreateBook"
        >
          <span class="action-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
            </svg>
          </span>
          <span>新建书目</span>
        </button>
        <button
          type="button"
          class="action-btn action-refresh"
          @click="onRefreshList"
        >
          <span class="action-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M20 7v5h-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              <path d="M4 17v-5h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              <path d="M7.6 8.6a6 6 0 0 1 9.9 1.6M16.4 15.4a6 6 0 0 1-9.9-1.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
            </svg>
          </span>
          <span>刷新书架</span>
        </button>
      </section>

      <section class="entry-nav">
        <h3 class="entry-title">引擎与开源生态</h3>
        <GlobalLLMEntryButton appearance="sidebar" />
        <PromptPlazaEntryButton appearance="sidebar" />
        <OnlineSquareEntryButton />
      </section>
    </div>

    <footer class="sidebar-footer">
      <div class="footer-info">
        <span class="update-time">
          <span class="time-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="8.2" stroke="currentColor" stroke-width="1.8" />
              <path d="M12 8v4.2l2.6 1.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </span>
          {{ updateTimeText }}
        </span>
        <a href="/architecture.html" target="_blank" class="footer-link">
          <span class="link-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M6.5 5.5h8.5a3 3 0 0 1 3 3v10H9.5a3 3 0 0 0-3 3V5.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
              <path d="M6.5 5.5v16M9.5 21.5h8.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
            </svg>
          </span>
          架构文档
        </a>
      </div>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { NSkeleton } from 'naive-ui'
import { useStatsStore } from '@/stores/statsStore'
import GlobalLLMEntryButton from '@/components/global/GlobalLLMEntryButton.vue'
import PromptPlazaEntryButton from '@/components/global/PromptPlazaEntryButton.vue'
import OnlineSquareEntryButton from '@/components/global/OnlineSquareEntryButton.vue'
import { storageKeys } from '@/config/storageKeys'
import { runtimePerformance } from '@/config/performance'
import { readStorageBoolean, writeStorageBoolean } from '@/utils/storage'
import { getNovelStageLabel } from '@/domain/novel'

const emit = defineEmits<{
  (e: 'create-book'): void
  (e: 'refresh-list'): void
  (e: 'collapsed-change', collapsed: boolean): void
}>()

const collapsed = ref(readStorageBoolean(storageKeys.statsSidebarCollapsed))
const mobileOpen = ref(false)

function toggleCollapse() {
  collapsed.value = !collapsed.value
  writeStorageBoolean(storageKeys.statsSidebarCollapsed, collapsed.value)
  emit('collapsed-change', collapsed.value)
}

function handleToggleClick() {
  if (window.innerWidth <= 768) {
    mobileOpen.value = false
    return
  }
  toggleCollapse()
}

function onSealClick() {
  if (collapsed.value) toggleCollapse()
}

function onCreateBook() {
  mobileOpen.value = false
  emit('create-book')
}

function onRefreshList() {
  mobileOpen.value = false
  emit('refresh-list')
}

const statsStore = useStatsStore()
const { globalStats, loading } = storeToRefs(statsStore)

const lastUpdateTime = ref<Date | null>(null)
let updateInterval: number | null = null

onMounted(async () => {
  try {
    await statsStore.loadGlobalStats()
    lastUpdateTime.value = new Date()
  } catch (error) {
    console.error('Failed to load stats:', error)
  }

  updateInterval = window.setInterval(() => {
    lastUpdateTime.value = new Date()
  }, runtimePerformance.stats.sidebarClockTickMs)
})

onUnmounted(() => {
  if (updateInterval) {
    clearInterval(updateInterval)
  }
})

async function handleRefresh() {
  try {
    await statsStore.loadGlobalStats(true)
    lastUpdateTime.value = new Date()
  } catch (error) {
    console.error('Failed to refresh stats:', error)
    window.$message?.error('刷新失败，请稍后重试')
  }
}

function formatNumber(num: number): string {
  if (num >= 10000) {
    return (num / 10000).toFixed(1) + '万'
  }
  return num.toLocaleString()
}

function getStageLabel(stage: string): string {
  return getNovelStageLabel(stage)
}

function formatTime(date: Date | null): string {
  if (!date) return '未更新'

  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMinutes = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)

  if (diffMinutes < 1) {
    return '刚刚'
  } else if (diffMinutes < 60) {
    return `${diffMinutes}分钟前`
  } else if (diffHours < 24) {
    return `${diffHours}小时前`
  } else {
    return date.toLocaleDateString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
}

const updateTimeText = computed(() => formatTime(lastUpdateTime.value))
</script>

<style scoped>
.numeric {
  font-variant-numeric: tabular-nums;
}

.mobile-sidebar-trigger {
  display: none;
}

.mobile-sidebar-mask {
  display: none;
}

.stats-sidebar {
  position: fixed;
  left: 0;
  top: 0;
  width: 284px;
  height: 100vh;
  box-sizing: border-box;
  background: var(--app-surface-subtle);
  border-right: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  z-index: 100;
  transition: width 0.2s ease, transform 0.22s ease;
}

.stats-sidebar.is-collapsed {
  width: 56px;
}

.sidebar-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.is-collapsed .sidebar-scroll {
  overflow: hidden;
}

/* ── 品牌头部（克制纸墨色阶，去紫渐变） ── */
.sidebar-brand {
  min-height: 62px;
  padding: 12px 16px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--app-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.is-collapsed .sidebar-brand {
  min-height: 62px;
  padding: 12px 0;
  justify-content: center;
}

.is-collapsed .brand-text,
.is-collapsed .sidebar-scroll,
.is-collapsed .sidebar-footer,
.is-collapsed .collapse-toggle {
  display: none;
}

.brand-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.logo-icon {
  width: 34px;
  height: 34px;
  background: var(--color-brand);
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 700;
  color: var(--app-text-inverse);
  flex: none;
  user-select: none;
}

.is-collapsed .logo-icon {
  cursor: pointer;
}

.is-collapsed .logo-icon:hover {
  background: var(--color-brand-hover);
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.brand-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--app-text-primary);
  line-height: 1.15;
}

.brand-slogan {
  font-size: 11.5px;
  color: var(--app-text-muted);
  margin: 0;
  white-space: nowrap;
}

.collapse-toggle {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border: 1px solid var(--app-border);
  background: var(--app-surface-subtle);
  border-radius: 7px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--app-text-secondary);
  padding: 0;
}

.collapse-toggle:hover {
  border-color: var(--color-brand);
  color: var(--color-brand);
}

/* ── 数据概览 ── */
.stats-section {
  padding: 16px 16px 6px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.section-title,
.stage-title,
.entry-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-muted);
  margin: 0;
}

.stage-title {
  margin-bottom: 8px;
}

.refresh-btn {
  width: 26px;
  height: 26px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  border-radius: 7px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--app-text-muted);
  padding: 0;
}

.refresh-btn:hover:not(:disabled) {
  border-color: var(--color-brand);
  color: var(--color-brand);
}

.refresh-btn.loading .refresh-svg {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.stats-row {
  display: flex;
  align-items: stretch;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 11px 6px;
  margin-bottom: 12px;
}

.stat-metric {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  min-width: 0;
}

.stat-metric.loading .metric-value {
  opacity: 0.35;
}

.metric-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--app-text-primary);
  line-height: 1.15;
  white-space: nowrap;
}

.metric-label {
  font-size: 11.5px;
  color: var(--app-text-muted);
}

.metric-divider {
  width: 1px;
  background: var(--app-border);
  margin: 2px 0;
  flex: none;
}

.stage-distribution {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 12px 14px;
  min-height: 116px;
  box-sizing: border-box;
}

.stage-item--skeleton {
  padding: 5px 0;
}

.stage-dot--placeholder {
  background: var(--app-border);
}

.stage-list.stage-empty {
  min-height: 60px;
  justify-content: center;
  align-items: center;
}

.stage-empty-hint {
  font-size: 12px;
  color: var(--app-text-muted);
}

.stage-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stage-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 5px 0;
}

.stage-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--app-text-muted);
}

.stage-dot.stage-planning {
  background: #475569;
}
.stage-dot.stage-writing {
  background: #b45309;
}
.stage-dot.stage-reviewing {
  background: #1f5e5b;
}
.stage-dot.stage-completed {
  background: #15803d;
}

.stage-name {
  flex: 1;
  font-size: 13px;
  color: var(--app-text-secondary);
}

.stage-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-primary);
  background: var(--app-surface-subtle);
  padding: 1px 8px;
  border-radius: 999px;
}

/* ── 快捷操作（修复原 3 列留空 bug，改为标准双列等宽） ── */
.quick-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 12px 16px 0;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 38px;
  padding: 0 10px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 9px;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background-color 0.15s ease;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-secondary);
  white-space: nowrap;
}

.action-btn:hover {
  border-color: var(--color-brand);
  color: var(--color-brand);
}

.action-btn.action-create {
  background: var(--color-brand);
  border-color: var(--color-brand);
  color: var(--app-text-inverse);
}

.action-btn.action-create:hover {
  background: var(--color-brand-hover);
  border-color: var(--color-brand-hover);
  color: var(--app-text-inverse);
}

.action-icon {
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
}

.action-icon svg {
  width: 14px;
  height: 14px;
}

.entry-nav {
  padding: 16px 16px 8px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.entry-title {
  margin-bottom: 2px;
}

.sidebar-footer {
  flex-shrink: 0;
  padding: 10px 16px;
  border-top: 1px solid var(--app-border);
  background: var(--app-surface);
}

.footer-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.update-time {
  font-size: 12px;
  color: var(--app-text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
}

.time-icon,
.link-icon {
  width: 13px;
  height: 13px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.time-icon svg,
.link-icon svg {
  width: 13px;
  height: 13px;
}

.footer-link {
  font-size: 12px;
  color: var(--app-text-muted);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  border-radius: 6px;
  white-space: nowrap;
}

.footer-link:hover {
  color: var(--color-brand);
  background: var(--app-surface-subtle);
}

/* ── 窄屏手机抽屉态（<=768px 零常驻遮挡） ── */
@media (max-width: 768px) {
  .mobile-sidebar-trigger {
    position: fixed;
    top: 14px;
    left: 14px;
    z-index: 95;
    width: 38px;
    height: 38px;
    border-radius: 9px;
    border: 1px solid var(--app-border);
    background: var(--app-surface);
    color: var(--app-text-primary);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
  }

  .mobile-sidebar-mask {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 98;
    background: rgba(15, 15, 14, 0.42);
  }

  .stats-sidebar,
  .stats-sidebar.is-collapsed {
    width: 280px;
    transform: translateX(-100%);
    z-index: 100;
  }

  .stats-sidebar.is-mobile-open {
    transform: translateX(0);
  }

  .stats-sidebar.is-mobile-open .brand-text,
  .stats-sidebar.is-mobile-open .sidebar-scroll,
  .stats-sidebar.is-mobile-open .sidebar-footer,
  .stats-sidebar.is-mobile-open .collapse-toggle {
    display: flex;
  }

  .stats-sidebar.is-mobile-open .sidebar-scroll,
  .stats-sidebar.is-mobile-open .sidebar-footer {
    display: block;
  }
}
</style>
