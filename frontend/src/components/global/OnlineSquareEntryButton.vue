<template>
  <!-- 线上提示词广场入口（仅侧栏形态）：Tauri 下开独立 WebView 窗口，
       浏览器 dev 下退化为新标签页。与本地 PromptPlaza（提示词版本管理）
       分工：这里连的是线上社区广场（灵感/榜单/模板）。 -->
  <button
    type="button"
    class="online-square-btn"
    :class="{ 'is-opening': opening }"
    :disabled="opening"
    @click="openSquare"
  >
    <span class="online-square-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none">
        <path d="M12 3v10.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <path d="M8.5 7.5 12 4l3.5 3.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="6" cy="17.5" r="2.4" stroke="currentColor" stroke-width="1.8"/>
        <circle cx="18" cy="17.5" r="2.4" stroke="currentColor" stroke-width="1.8"/>
        <path d="M8.4 17.5h7.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
      </svg>
    </span>
    <span class="online-square-title">线上提示词广场</span>
    <span v-if="!isTauriRuntime" class="online-square-hint" aria-hidden="true">↗</span>
  </button>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

/** 线上广场地址：可用 VITE_SQUARE_ORIGIN 覆盖（联调指到本地 playground） */
const SQUARE_ORIGIN = (import.meta.env.VITE_SQUARE_ORIGIN as string | undefined || 'https://plotpilot.xyz').replace(/\/+$/, '')

const opening = ref(false)

/** 桌面壳检测：与 api/config.ts 同款探测，避免循环依赖 */
const isTauriRuntime = computed(() => {
  if (typeof window === 'undefined') return false
  const w = window as Window & { __TAURI__?: unknown; __TAURI_INTERNALS__?: unknown }
  return !!(w.__TAURI__ || w.__TAURI_INTERNALS__)
})

async function openSquare(): Promise<void> {
  opening.value = true
  try {
    if (isTauriRuntime.value) {
      // Tauri：独立 WebView 窗口（广场 cookie 在窗口内是第一方，登录态可用）
      const { invoke } = await import('@tauri-apps/api/core')
      await invoke('open_online_square', { url: SQUARE_ORIGIN })
    } else {
      // 浏览器 dev：退化为新标签页
      window.open(SQUARE_ORIGIN, '_blank', 'noopener')
    }
  } catch (e: unknown) {
    console.warn('[Square] 打开线上广场失败，回退浏览器:', e)
    window.open(SQUARE_ORIGIN, '_blank', 'noopener')
  } finally {
    opening.value = false
  }
}
</script>

<style scoped>
.online-square-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  box-sizing: border-box;
  min-height: 58px;
  padding: 0 14px;
  border-radius: 16px;
  border: 1px solid var(--app-border);
  background: var(--app-surface-subtle, transparent);
  color: var(--app-text-primary);
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease, transform 0.18s ease;
}

.online-square-btn:hover {
  border-color: var(--color-plaza, #059669);
  transform: translateY(-1px);
}

.online-square-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.online-square-icon {
  flex: none;
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--color-plaza, #059669);
}

.online-square-icon svg {
  width: 16px;
  height: 16px;
}

.online-square-title {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}

.online-square-hint {
  flex: none;
  font-size: 12px;
  color: var(--app-text-muted);
}
</style>
