<template>
  <n-modal
    v-model:show="show"
    preset="card"
    title="配置管理"
    style="width: min(560px, 96vw)"
    :mask-closable="false"
    :segmented="{ content: 'soft', footer: 'soft' }"
  >
    <!-- ═══ 主题选择 ═══ -->
    <div class="theme-section">
      <div class="theme-preview-bar">
        <div class="theme-preview-card" :class="{ 'is-dark': themeStore.isDark }">
          <div class="preview-header">
            <span class="preview-dot"></span>
            <span class="preview-dot"></span>
            <span class="preview-dot"></span>
          </div>
          <div class="preview-body">
            <div class="preview-line long"></div>
            <div class="preview-line medium"></div>
            <div class="preview-line short"></div>
          </div>
        </div>
      </div>

      <div class="theme-mode-cards">
        <div
          v-for="option in themeOptions"
          :key="option.value"
          class="theme-mode-card"
          :class="{ active: themeStore.mode === option.value }"
          @click="handleThemeChange(option.value)"
        >
          <div class="mode-card-icon" v-html="option.icon"></div>
          <div class="mode-card-info">
            <div class="mode-card-name">{{ option.label }}</div>
            <div class="mode-card-desc">{{ option.desc }}</div>
          </div>
          <div v-if="themeStore.mode === option.value" class="mode-card-check">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
          </div>
        </div>
      </div>

      <n-alert type="info" style="margin-top: 20px" :bordered="false">
        主题切换会立即生效并自动保存。选择「跟随系统」时，将根据操作系统的亮/暗模式自动切换。
      </n-alert>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useThemeStore, type ThemeMode } from '@/stores/themeStore'

const show = defineModel<boolean>('show', { default: false })
const message = useMessage()
const themeStore = useThemeStore()

const themeOptions = computed(() => [
  {
    value: 'light' as ThemeMode,
    label: '浅色',
    desc: '清爽明亮的默认主题',
    icon: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="26" height="26"><circle cx="12" cy="12" r="5" fill="#f59e0b"/><path d="M12 2v2m0 16v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M2 12h2m16 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" stroke="#f59e0b" stroke-width="2" stroke-linecap="round"/></svg>',
  },
  {
    value: 'dark' as ThemeMode,
    label: '深色',
    desc: '护眼暗色主题，适合夜间写作',
    icon: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="26" height="26"><path d="M12 3a9 9 0 109 9c0-.46-.04-.92-.1-1.36A7 7 0 0112 3z" fill="#818cf8"/></svg>',
  },
  {
    value: 'auto' as ThemeMode,
    label: '跟随系统',
    desc: '自动匹配操作系统偏好设置',
    icon: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="26" height="26"><rect x="2" y="4" width="20" height="16" rx="2" stroke="#94a3b8" stroke-width="2" fill="none"/><path d="M8 14h8M10 10h4" stroke="#94a3b8" stroke-width="2" stroke-linecap="round"/></svg>',
  },
])

function handleThemeChange(newMode: ThemeMode) {
  themeStore.setTheme(newMode)
  const opt = themeOptions.value.find((o) => o.value === newMode)
  message.success(`已切换到${opt?.label ?? newMode}主题`)
}
</script>

<style scoped>
.theme-section {
  min-height: 200px;
}

/* ── 预览卡片 ──────────────────────────────────────── */
.theme-preview-bar {
  display: flex;
  justify-content: center;
  margin-bottom: 28px;
}

.theme-preview-card {
  width: 260px;
  height: 148px;
  border-radius: 14px;
  overflow: hidden;
  border: 2px solid var(--app-border, #e2e8f0);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow:
    0 4px 16px rgba(15, 23, 42, 0.06),
    0 1px 3px rgba(15, 23, 42, 0.04);
}

.theme-preview-card.is-dark {
  background: #0c1222;
  border-color: #334155;
  box-shadow:
    0 4px 24px rgba(0, 0, 0, 0.35),
    0 2px 8px rgba(0, 0, 0, 0.2);
}

.preview-header {
  display: flex;
  gap: 6px;
  padding: 11px 13px;
  background: var(--app-surface-subtle);
  transition: background 0.4s ease;
}

.is-dark .preview-header {
  background: #1a2332;
}

.preview-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #cbd5e1;
  transition: background 0.4s ease;
}

.is-dark .preview-dot {
  background: #374151;
}

.preview-body {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  background: var(--app-surface);
  transition: background 0.4s ease;
}

.is-dark .preview-body {
  background: #0c1222;
}

.preview-line {
  height: 8px;
  border-radius: 4px;
  background: #e2e8f0;
  transition: background 0.4s ease;
}

.is-dark .preview-line {
  background: #1e293b;
}

.preview-line.long { width: 100%; }
.preview-line.medium { width: 70%; }
.preview-line.short { width: 42%; }

/* ── 三选卡 ────────────────────────────────────────── */
.theme-mode-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.theme-mode-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 15px 18px;
  border-radius: 13px;
  border: 1.5px solid var(--app-border, #e2e8f0);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  background: var(--app-surface);
}

.theme-mode-card:hover {
  border-color: #a5b4fc;
  background: rgba(79, 70, 229, 0.02);
  box-shadow: 0 2px 8px rgba(79, 70, 229, 0.08);
}

.theme-mode-card.active {
  border-color: #4f46e5;
  background: rgba(79, 70, 229, 0.05);
  box-shadow:
    0 0 0 3px rgba(79, 70, 229, 0.08),
    0 2px 8px rgba(79, 70, 229, 0.1);
}

.mode-card-icon {
  flex-shrink: 0;
  width: 46px;
  height: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border, #e2e8f0);
  transition: all 0.2s ease;
}

.theme-mode-card.active .mode-card-icon {
  background: rgba(79, 70, 229, 0.1);
  border-color: rgba(79, 70, 229, 0.2);
}

.mode-card-info {
  flex: 1;
  min-width: 0;
}

.mode-card-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary, #0f172a);
}

.mode-card-desc {
  font-size: 12.5px;
  color: var(--color-text-secondary, #64748b);
  margin-top: 3px;
}

.mode-card-check {
  flex-shrink: 0;
  color: #4f46e5;
  display: flex;
  align-items: center;
}
</style>
