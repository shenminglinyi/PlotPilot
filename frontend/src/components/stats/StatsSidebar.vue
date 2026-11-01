<template>
  <aside class="stats-sidebar" :class="{ 'is-collapsed': collapsed }">
    <!-- Brand Header（紧凑：一行 logo + 名称，双行文案收成单行副题） -->
    <header class="sidebar-brand">
      <div class="brand-logo">
        <span class="logo-icon">✦</span>
        <div class="brand-text">
          <h1 class="brand-name">PlotPilot</h1>
          <p class="brand-slogan">墨枢 · 作者的领航员</p>
        </div>
      </div>
      <button
        class="collapse-toggle"
        :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
        @click="toggleCollapse"
      >
        <svg viewBox="0 0 24 24" fill="none" width="14" height="14">
          <path
            :d="collapsed ? 'M9 18l6-6-6-6' : 'M15 18l-6-6 6-6'"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </header>

    <div class="sidebar-scroll">
      <!-- Stats Overview（紧凑：三指标一行 + 阶段分布收窄） -->
      <section class="stats-section">
        <div class="section-header">
          <h2 class="section-title">数据概览</h2>
          <button
            class="refresh-btn"
            @click="handleRefresh"
            :disabled="loading"
            :class="{ loading: loading }"
            aria-label="刷新数据"
          >
            <span class="refresh-icon">↻</span>
          </button>
        </div>

        <div class="stats-row">
          <div class="stat-metric" :class="{ loading }">
            <span class="metric-value">{{ globalStats?.total_books ?? 0 }}</span>
            <span class="metric-label">本书</span>
          </div>
          <div class="metric-divider" />
          <div class="stat-metric" :class="{ loading }">
            <span class="metric-value">{{ globalStats?.total_chapters ?? 0 }}</span>
            <span class="metric-label">章</span>
          </div>
          <div class="metric-divider" />
          <div class="stat-metric" :class="{ loading }">
            <span class="metric-value">{{ formatNumber(globalStats?.total_words ?? 0) }}</span>
            <span class="metric-label">字</span>
          </div>
        </div>

        <!-- 各阶段书籍：始终占位，避免异步出现后挤压下方功能区 -->
        <div class="stage-distribution">
          <h3 class="stage-title">各阶段</h3>
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
              <span class="stage-count">{{ count }}</span>
            </div>
          </div>
          <div v-else class="stage-list stage-empty">
            <span class="stage-empty-hint">暂无分阶段统计</span>
          </div>
        </div>
      </section>

      <!-- 快捷操作（紧凑主按钮一行两个） -->
      <section class="quick-actions">
        <button class="action-btn action-create" @click="$emit('create-book')">
          <span class="action-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
          </span>
          <span>新建书目</span>
        </button>
        <button class="action-btn action-refresh" @click="$emit('refresh-list')">
          <span class="action-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M20 7v5h-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M4 17v-5h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M7.6 8.6a6 6 0 0 1 9.9 1.6M16.4 15.4a6 6 0 0 1-9.9-1.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
          </span>
          <span>刷新列表</span>
        </button>
      </section>

      <!-- 功能入口（紧凑导航行，不再是渐变大按钮） -->
      <section class="entry-nav">
        <h3 class="entry-title">功能入口</h3>
        <GlobalLLMEntryButton appearance="sidebar" />
        <PromptPlazaEntryButton appearance="sidebar" />
        <OnlineSquareEntryButton />
      </section>
    </div>

    <!-- Footer -->
    <footer class="sidebar-footer">
      <div class="footer-info">
        <span class="update-time">
          <span class="time-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="8.2" stroke="currentColor" stroke-width="1.8"/>
              <path d="M12 8v4.2l2.6 1.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </span>
          {{ updateTimeText }}
        </span>
        <a href="/architecture.html" target="_blank" class="footer-link">
          <span class="link-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M6.5 5.5h8.5a3 3 0 0 1 3 3v10H9.5a3 3 0 0 0-3 3V5.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
              <path d="M6.5 5.5v16M9.5 21.5h8.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
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

function toggleCollapse() {
  collapsed.value = !collapsed.value
  writeStorageBoolean(storageKeys.statsSidebarCollapsed, collapsed.value)
  emit('collapsed-change', collapsed.value)
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

  // Update time display every minute
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
      minute: '2-digit'
    })
  }
}

const updateTimeText = computed(() => formatTime(lastUpdateTime.value))
</script>

<style scoped>
.stats-sidebar {
  position: fixed;
  left: 0;
  top: 0;
  width: 300px;
  height: 100vh;
  box-sizing: border-box;
  background: var(--app-surface);
  border-right: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  z-index: 100;
  transition: width 0.22s cubic-bezier(0.4, 0, 0.2, 1);
}

.stats-sidebar.is-collapsed {
  width: 52px;
}

/* 中段可滚动，品牌与页脚钉住：高窗口不空、矮窗口不挤 */
.sidebar-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.is-collapsed .sidebar-scroll {
  overflow: hidden;
}

/* Brand Header（64px 紧凑条） */
.sidebar-brand {
  min-height: 64px;
  padding: 12px 16px;
  background: linear-gradient(135deg, var(--color-brand, #4f46e5) 0%, var(--color-brand-pressed, #7c3aed) 100%);
  position: relative;
  overflow: visible;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.sidebar-brand::before {
  content: '';
  position: absolute;
  top: -60%;
  right: -40%;
  width: 120px;
  height: 120px;
  background: radial-gradient(circle, var(--app-text-inverse, rgba(255,255,255,0.1)) 0%, transparent 70%);
  pointer-events: none;
}

.is-collapsed .sidebar-brand {
  min-height: 0;
  padding: 14px 0 12px;
  flex-direction: column;
  gap: 10px;
  justify-content: center;
}

.is-collapsed .brand-text,
.is-collapsed .sidebar-scroll,
.is-collapsed .sidebar-footer {
  display: none;
}

.is-collapsed .logo-icon {
  width: 32px;
  height: 32px;
  font-size: 16px;
  border-radius: 9px;
}

.collapse-toggle {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border: none;
  background: rgba(255, 255, 255, 0.18);
  border-radius: 7px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  transition: background 0.18s ease;
  padding: 0;
}

.collapse-toggle:hover {
  background: rgba(255, 255, 255, 0.32);
}

.is-collapsed .collapse-toggle {
  /* 收起态仍可点击展开：logo 下方纵向排列，不隐藏 */
  margin: 0;
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
  background: var(--color-brand-light, rgba(255, 255, 255, 0.2));
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  color: var(--app-text-inverse, #fff);
  backdrop-filter: blur(8px);
  border: 1px solid var(--app-text-inverse, rgba(255, 255, 255, 0.2));
  flex: none;
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.brand-name {
  font-size: 17px;
  font-weight: 700;
  color: var(--app-text-inverse, #fff);
  margin: 0;
  letter-spacing: -0.01em;
  line-height: 1.1;
}

.brand-slogan {
  font-size: 10.5px;
  color: rgba(255, 255, 255, 0.82);
  margin: 0;
  font-weight: 400;
  white-space: nowrap;
}

/* Stats Section */
.stats-section {
  padding: 14px 16px 4px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.section-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--app-text-muted);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.refresh-btn {
  width: 26px;
  height: 26px;
  border: none;
  background: var(--app-surface-subtle);
  border-radius: 7px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--app-text-muted, #64748b);
  transition: all 0.2s ease;
  padding: 0;
}

.refresh-btn:hover:not(:disabled) {
  background: var(--app-surface);
  color: var(--color-brand, #4f46e5);
}

.refresh-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.refresh-btn.loading .refresh-icon {
  animation: spin 1s linear infinite;
}

.refresh-icon {
  font-size: 13px;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 三指标一行（替代原三张纵排大卡） */
.stats-row {
  display: flex;
  align-items: stretch;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  border-radius: 12px;
  padding: 10px 6px;
  margin-bottom: 12px;
}

.stat-metric {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 0;
}

.stat-metric.loading .metric-value {
  opacity: 0.35;
}

.metric-value {
  font-size: 19px;
  font-weight: 800;
  color: var(--app-text-primary);
  letter-spacing: -0.02em;
  line-height: 1.1;
  white-space: nowrap;
}

.metric-label {
  font-size: 11px;
  color: var(--app-text-muted);
}

.metric-divider {
  width: 1px;
  background: var(--app-border);
  margin: 2px 0;
  flex: none;
}

/* Stage Distribution（固定占位高度，避免布局抖动） */
.stage-distribution {
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  border-radius: 12px;
  padding: 12px 14px;
  min-height: 128px;
  box-sizing: border-box;
}

.stage-item--skeleton {
  padding: 5px 0;
}

.stage-dot--placeholder {
  background: var(--app-border, rgba(148, 163, 184, 0.35));
  opacity: 0.9;
}

.stage-list.stage-empty {
  min-height: 64px;
  justify-content: center;
  align-items: center;
}

.stage-empty-hint {
  font-size: 12px;
  color: var(--app-text-muted, #94a3b8);
}

.stage-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--app-text-muted, #64748b);
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
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
  padding: 6px 0;
}

.stage-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.stage-dot.stage-planning { background: #3b82f6; }
.stage-dot.stage-writing { background: #f59e0b; }
.stage-dot.stage-reviewing { background: #8b5cf6; }
.stage-dot.stage-completed { background: #10b981; }

.stage-name {
  flex: 1;
  font-size: 12.5px;
  color: var(--app-text-secondary);
}

.stage-count {
  font-size: 12px;
  font-weight: 700;
  color: var(--app-text-primary);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  padding: 1px 8px;
  border-radius: 999px;
}

/* Quick Actions（紧凑 38px 一行两个） */
.quick-actions {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 7px;
  padding: 12px 16px 0;
}

.action-btn {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 38px;
  padding: 0 10px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.16s ease;
  font-size: 12.5px;
  font-weight: 600;
  line-height: 1;
  color: var(--app-text-secondary);
  white-space: nowrap;
}

.action-btn:hover {
  border-color: var(--color-brand, #4f46e5);
  color: var(--color-brand, #4f46e5);
  transform: translateY(-1px);
}

.action-btn.action-create {
  background: linear-gradient(135deg, var(--color-brand-hover, #6366f1) 0%, var(--color-brand, #4f46e5) 100%);
  border-color: color-mix(in srgb, var(--color-brand, #4f46e5) 52%, transparent);
  color: var(--app-text-inverse, #ffffff);
}

.action-btn.action-create:hover {
  filter: brightness(1.08);
  border-color: var(--color-brand-hover, #6366f1);
  color: var(--app-text-inverse, #ffffff);
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

/* 功能入口（紧凑导航行） */
.entry-nav {
  padding: 14px 16px 6px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.entry-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--app-text-muted);
  margin: 0 0 1px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

/* Footer */
.sidebar-footer {
  flex-shrink: 0;
  padding: 9px 16px 10px;
  border-top: 1px solid var(--app-divider, rgba(15, 23, 42, 0.06));
  display: block;
  background: var(--app-surface);
}

.footer-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.update-time {
  font-size: 11.5px;
  color: var(--app-text-muted, #64748b);
  display: flex;
  align-items: center;
  gap: 4px;
}

.time-icon {
  width: 13px;
  height: 13px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.time-icon svg {
  width: 13px;
  height: 13px;
}

.footer-link {
  font-size: 11.5px;
  color: var(--app-text-muted, #64748b);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 7px;
  border-radius: 6px;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.footer-link:hover {
  color: var(--color-brand, #4f46e5);
  background: var(--app-surface-subtle);
}

.link-icon {
  width: 13px;
  height: 13px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.link-icon svg {
  width: 13px;
  height: 13px;
}
</style>
