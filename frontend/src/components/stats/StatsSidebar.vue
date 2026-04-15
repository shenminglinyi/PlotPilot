<template>
  <aside class="stats-sidebar">
    <!-- Brand Header -->
    <header class="sidebar-brand">
      <div class="brand-logo">
        <span class="logo-icon">✦</span>
        <div class="brand-text">
          <h1 class="brand-name">PlotPilot</h1>
          <p class="brand-slogan">墨枢 · 作者的领航员</p>
        </div>
      </div>
    </header>

    <!-- Stats Overview -->
    <section class="stats-section">
      <div class="section-header">
        <h2 class="section-title">
          <span class="title-icon">📊</span>
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
          icon="📚"
          unit="本"
          :loading="loading"
        />
        <StatCard
          title="总章节数"
          :value="globalStats?.total_chapters ?? 0"
          icon="📄"
          unit="章"
          :loading="loading"
        />
        <StatCard
          title="总字数"
          :value="formatNumber(globalStats?.total_words ?? 0)"
          icon="✍️"
          unit="字"
          :loading="loading"
        />
      </div>

      <!-- Stage Distribution -->
      <div v-if="globalStats?.books_by_stage" class="stage-distribution">
        <h3 class="stage-title">各阶段书籍</h3>
        <div class="stage-list">
          <div
            v-for="(count, stage) in globalStats.books_by_stage"
            :key="stage"
            class="stage-item"
          >
            <span class="stage-dot" :class="`stage-${stage}`"></span>
            <span class="stage-name">{{ getStageLabel(stage as string) }}</span>
            <span class="stage-count">{{ count }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Quick Actions -->
    <section class="quick-actions">
      <h3 class="actions-title">
        <span class="title-icon">⚡</span>
        快捷操作
      </h3>
      <div class="actions-grid">
        <button class="action-btn" @click="$emit('create-book')">
          <span class="action-icon">✨</span>
          <span>新建书目</span>
        </button>
        <button class="action-btn" @click="$emit('refresh-list')">
          <span class="action-icon">🔄</span>
          <span>刷新列表</span>
        </button>
        <GlobalLLMEntryButton appearance="sidebar" />
        <PromptPlazaEntryButton appearance="sidebar" />
      </div>
    </section>

    <!-- Footer -->
    <footer class="sidebar-footer">
      <div class="footer-info">
        <span class="update-time">
          <span class="time-icon">🕐</span>
          {{ updateTimeText }}
        </span>
      </div>
      <a href="/architecture.html" target="_blank" class="footer-link">
        <span class="link-icon">📖</span>
        架构文档
      </a>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import StatCard from './StatCard.vue'
import { useStatsStore } from '@/stores/statsStore'
import GlobalLLMEntryButton from '@/components/global/GlobalLLMEntryButton.vue'
import PromptPlazaEntryButton from '@/components/global/PromptPlazaEntryButton.vue'

defineEmits<{
  (e: 'create-book'): void
  (e: 'refresh-list'): void
}>()

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
  background: linear-gradient(180deg, var(--app-surface-subtle) 0%, var(--app-border) 100%);
  border-right: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  z-index: 100;
}

/* Brand Header */
.sidebar-brand {
  padding: 28px 24px 24px;
  background: linear-gradient(135deg, var(--color-brand, #4f46e5) 0%, var(--color-brand-pressed, #7c3aed) 100%);
  position: relative;
  overflow: hidden;
}

.sidebar-brand::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -30%;
  width: 200px;
  height: 200px;
  background: radial-gradient(circle, var(--app-text-inverse, rgba(255,255,255,0.15)) 0%, transparent 70%);
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
  color: var(--app-text-secondary, rgba(255, 255, 255, 0.85));
  margin: 0;
  font-weight: 400;
}

/* Stats Section */
.stats-section {
  padding: 24px;
  flex: 1;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary);
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.title-icon {
  font-size: 16px;
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
  gap: 12px;
  margin-bottom: 20px;
}

/* Stage Distribution */
.stage-distribution {
  background: var(--app-surface);
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
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
  padding: 0 24px 24px;
}

.actions-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary);
  margin: 0 0 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.actions-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 14px 12px;
  background: var(--app-surface);
  border: 1px solid var(--app-border, rgba(15, 23, 42, 0.06));
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 12px;
  color: var(--app-text-secondary, #475569);
}

.action-btn:hover {
  background: var(--app-surface-subtle);
  border-color: var(--color-brand, #4f46e5);
  color: var(--color-brand, #4f46e5);
  transform: translateY(-1px);
}

.action-icon {
  font-size: 20px;
}

/* Footer */
.sidebar-footer {
  padding: 20px 24px;
  border-top: 1px solid var(--app-divider, rgba(15, 23, 42, 0.06));
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--app-surface-subtle, rgba(248, 250, 252, 0.8));
}

.footer-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.update-time {
  font-size: 12px;
  color: var(--app-text-secondary, #94a3b8);
  display: flex;
  align-items: center;
  gap: 6px;
}

.time-icon {
  font-size: 14px;
}

.footer-link {
  font-size: 12px;
  color: var(--app-text-muted, #64748b);
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--app-surface);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.footer-link:hover {
  color: var(--color-brand, #4f46e5);
  background: var(--app-surface-subtle);
}

.link-icon {
  font-size: 14px;
}
</style>
