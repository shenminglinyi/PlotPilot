<template>
  <aside class="stats-sidebar" :class="{ 'is-collapsed': collapsed }">
    <!-- Brand Header -->
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
        <svg viewBox="0 0 24 24" fill="none" width="16" height="16">
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

    <!-- Stats Overview -->
    <section class="stats-section">
      <div class="section-header">
        <h2 class="section-title">
          <span class="title-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M4 19h16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
              <rect x="6" y="11" width="3.5" height="6" rx="1.2" stroke="currentColor" stroke-width="1.6"/>
              <rect x="10.5" y="8" width="3.5" height="9" rx="1.2" stroke="currentColor" stroke-width="1.6"/>
              <rect x="15" y="5" width="3.5" height="12" rx="1.2" stroke="currentColor" stroke-width="1.6"/>
            </svg>
          </span>
          数据概览
        </h2>
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

      <div class="stats-grid">
        <StatCard
          title="总书籍数"
          :value="globalStats?.total_books ?? 0"
          icon="books"
          unit="本"
          :loading="loading"
        />
        <StatCard
          title="总章节数"
          :value="globalStats?.total_chapters ?? 0"
          icon="chapters"
          unit="章"
          :loading="loading"
        />
        <StatCard
          title="总字数"
          :value="formatNumber(globalStats?.total_words ?? 0)"
          icon="words"
          unit="字"
          :loading="loading"
        />
      </div>

      <!-- 各阶段书籍：始终占位，避免异步出现后挤压下方快捷操作 / 弹层触发区 -->
      <div class="stage-distribution">
        <h3 class="stage-title">各阶段书籍</h3>
        <div v-if="loading" class="stage-list" aria-hidden="true">
          <div v-for="n in 4" :key="n" class="stage-item stage-item--skeleton">
            <span class="stage-dot stage-dot--placeholder" />
            <n-skeleton style="flex: 1; max-width: 68%" :height="14" round />
            <n-skeleton :width="40" :height="22" round />
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

    <!-- Quick Actions -->
    <section class="quick-actions">
      <h3 class="actions-title">
        <span class="title-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M13.5 3.5 7.8 12h4l-1.3 8.5 6.2-9h-4.3L13.5 3.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
          </svg>
        </span>
        快捷操作
      </h3>
      <div class="actions-grid">
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
        <button class="action-btn action-theme" type="button" @click="$emit('open-settings')">
          <span class="action-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M12 3a1 1 0 0 1 1 1v1.06a7.99 7.99 0 0 1 4.11 2.17l.75-.75a1 1 0 0 1 1.41 0l.71.71a1 1 0 0 1 0 1.41l-.75.75A7.99 7.99 0 0 1 20.94 11H22a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1h-1.06a7.99 7.99 0 0 1-1.71 4.41l.75.75a1 1 0 0 1 0 1.41l-.71.71a1 1 0 0 1-1.41 0l-.75-.75a7.99 7.99 0 0 1-4.41 1.71V22a1 1 0 0 1-1 1h-1a1 1 0 0 1-1-1v-1.06a7.99 7.99 0 0 1-4.41-1.71l-.75.75a1 1 0 0 1-1.41 0l-.71-.71a1 1 0 0 1 0-1.41l.75-.75A7.99 7.99 0 0 1 3.06 14H2a1 1 0 0 1-1-1v-1a1 1 0 0 1 1-1h1.06a7.99 7.99 0 0 1 1.71-4.41l-.75-.75a1 1 0 0 1 0-1.41l.71-.71a1 1 0 0 1 1.41 0l.75.75A7.99 7.99 0 0 1 11 5.06V4a1 1 0 0 1 1-1h1z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
              <circle cx="12" cy="13" r="3.2" stroke="currentColor" stroke-width="1.5"/>
            </svg>
          </span>
          <span>主题设置</span>
        </button>
        <GlobalLLMEntryButton appearance="sidebar" />
        <PromptPlazaEntryButton appearance="sidebar" />
      </div>
    </section>

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
import StatCard from './StatCard.vue'
import { useStatsStore } from '@/stores/statsStore'
import GlobalLLMEntryButton from '@/components/global/GlobalLLMEntryButton.vue'
import PromptPlazaEntryButton from '@/components/global/PromptPlazaEntryButton.vue'
const emit = defineEmits<{
  (e: 'create-book'): void
  (e: 'refresh-list'): void
  (e: 'open-settings'): void
  (e: 'collapsed-change', collapsed: boolean): void
}>()

const SIDEBAR_COLLAPSED_KEY = 'plotpilot_sidebar_collapsed'

const collapsed = ref(localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true')

function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed.value))
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
  }, 60000)
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
  const labels: Record<string, string> = {
    planning: '规划中',
    writing: '写作中',
    reviewing: '审稿中',
    completed: '已完成',
  }
  return labels[stage] || stage
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
  padding-top: env(safe-area-inset-top);
  background: linear-gradient(180deg, var(--app-surface-subtle) 0%, var(--app-border) 100%);
  border-right: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
  z-index: 100;
  transition: width 0.22s cubic-bezier(0.4, 0, 0.2, 1);
}

.stats-sidebar.is-collapsed {
  width: 52px;
  overflow: hidden;
}

/* Brand Header */
.sidebar-brand {
  min-height: 100px;
  padding: 20px 24px;
  background: linear-gradient(135deg, var(--color-brand, #4f46e5) 0%, var(--color-brand-pressed, #7c3aed) 100%);
  position: relative;
  overflow: visible;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

/* 折叠时 brand header 缩小 */
.is-collapsed .sidebar-brand {
  min-height: auto;
  padding: 12px 0;
  justify-content: center;
}

.is-collapsed .brand-text,
.is-collapsed .stats-section,
.is-collapsed .quick-actions,
.is-collapsed .sidebar-footer {
  display: none;
}

.is-collapsed .logo-icon {
  width: 36px;
  height: 36px;
  font-size: 18px;
}

/* 折叠/展开切换按钮 */
.collapse-toggle {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border: none;
  background: rgba(255, 255, 255, 0.18);
  border-radius: 8px;
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
  margin: 0 auto;
}

.sidebar-brand::before {
  content: '';
  position: absolute;
  top: -38%;
  right: -46%;
  width: 132px;
  height: 132px;
  background: radial-gradient(circle, var(--app-text-inverse, rgba(255,255,255,0.09)) 0%, transparent 72%);
  pointer-events: none;
}

.brand-logo {
  display: flex;
  align-items: center;
  gap: 14px;
}

.logo-icon {
  width: 44px;
  height: 44px;
  background: var(--color-brand-light, rgba(255, 255, 255, 0.2));
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  color: var(--app-text-inverse, #fff);
  backdrop-filter: blur(8px);
  border: 1px solid var(--app-text-inverse, rgba(255, 255, 255, 0.2));
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.brand-name {
  font-size: 22px;
  font-weight: 700;
  color: var(--app-text-inverse, #fff);
  margin: 0;
  letter-spacing: -0.02em;
}

.brand-slogan {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.82);
  margin: 0;
  font-weight: 400;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.16);
}

/* Stats Section */
.stats-section {
  padding: 16px;
  flex: 0 0 auto;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary);
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.title-icon {
  width: 16px;
  height: 16px;
  color: var(--app-text-secondary, #64748b);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.title-icon svg {
  width: 16px;
  height: 16px;
}

.refresh-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: var(--app-surface);
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--app-text-muted, #64748b);
  transition: all 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--app-surface-subtle);
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
  font-size: 16px;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.stats-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

/* Stage Distribution（固定占位高度，避免布局抖动） */
.stage-distribution {
  background: var(--app-surface);
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  min-height: 168px;
  box-sizing: border-box;
}

.stage-item--skeleton {
  padding: 6px 0;
}

.stage-dot--placeholder {
  background: var(--app-border, rgba(148, 163, 184, 0.35));
  opacity: 0.9;
}

.stage-list.stage-empty {
  min-height: 88px;
  justify-content: center;
  align-items: center;
}

.stage-empty-hint {
  font-size: 12px;
  color: var(--app-text-muted, #94a3b8);
}

.stage-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-muted, #64748b);
  margin: 0 0 12px;
}

.stage-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stage-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
}

.stage-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.stage-dot.stage-planning { background: #3b82f6; }
.stage-dot.stage-writing { background: #f59e0b; }
.stage-dot.stage-reviewing { background: #8b5cf6; }
.stage-dot.stage-completed { background: #10b981; }

.stage-name {
  flex: 1;
  font-size: 13px;
  color: var(--app-text-secondary);
}

.stage-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
  background: var(--app-surface-subtle);
  padding: 2px 10px;
  border-radius: 12px;
}

/* Quick Actions */
.quick-actions {
  padding: 0 16px 10px;
}

.actions-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary);
  margin: 0 0 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.actions-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.action-btn {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 58px;
  padding: 0 14px;
  background: linear-gradient(135deg, var(--color-brand-hover, #6366f1) 0%, var(--color-brand, #4f46e5) 55%, var(--color-brand-pressed, #4338ca) 100%);
  border: 1px solid color-mix(in srgb, var(--color-brand, #4f46e5) 52%, transparent);
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 15px;
  font-weight: 600;
  line-height: 1;
  color: var(--app-text-inverse, #ffffff);
  box-shadow: none;
  white-space: nowrap;
}

.action-btn.action-create {
  background: linear-gradient(135deg, var(--color-brand-hover, #6366f1) 0%, var(--color-brand, #4f46e5) 55%, var(--color-brand-pressed, #4338ca) 100%);
  border-color: color-mix(in srgb, var(--color-brand, #4f46e5) 52%, transparent);
}

.action-btn.action-refresh {
  background: linear-gradient(135deg, var(--color-brand-hover, #6366f1) 0%, var(--color-brand, #4f46e5) 55%, var(--color-brand-pressed, #4338ca) 100%);
  border-color: color-mix(in srgb, var(--color-brand, #4f46e5) 52%, transparent);
}

.action-btn.action-theme {
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--app-text-muted, #64748b) 28%, var(--color-brand-hover, #6366f1)) 0%,
    color-mix(in srgb, var(--app-text-secondary, #475569) 18%, var(--color-brand, #4f46e5)) 100%
  );
  border-color: color-mix(in srgb, var(--color-brand, #4f46e5) 38%, transparent);
}

.action-btn:hover {
  filter: none;
  transform: none;
  background: linear-gradient(135deg, var(--color-brand, #4f46e5) 0%, var(--color-brand-hover, #6366f1) 55%, var(--color-brand-pressed, #4338ca) 100%);
  box-shadow: none;
}

.action-icon {
  width: 16px;
  height: 16px;
  color: var(--app-text-inverse, #ffffff);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.action-icon svg {
  width: 16px;
  height: 16px;
}

[data-theme='anchor'] .action-btn:hover {
  transform: none;
  box-shadow: none;
}

/* Footer */
.sidebar-footer {
  margin-top: auto;
  padding: 10px 16px 12px;
  border-top: 1px solid var(--app-divider, rgba(15, 23, 42, 0.06));
  display: block;
  background: var(--app-surface-subtle, rgba(248, 250, 252, 0.8));
}

.footer-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.update-time {
  font-size: 12px;
  color: var(--app-text-muted, #64748b);
  display: flex;
  align-items: center;
  gap: 4px;
}

.time-icon {
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.time-icon svg {
  width: 14px;
  height: 14px;
}

.footer-link {
  font-size: 12px;
  color: var(--app-text-muted, #64748b);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 6px;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.footer-link:hover {
  color: var(--color-brand, #4f46e5);
  background: var(--app-surface-subtle);
}

.link-icon {
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.link-icon svg {
  width: 14px;
  height: 14px;
}
</style>
