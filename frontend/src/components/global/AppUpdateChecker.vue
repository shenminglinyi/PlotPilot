<template>
  <!-- 应用自更新（仅 Tauri 桌面模式；浏览器渲染 null）。
       启动即静默检查 + 每 4 小时复查；发现新版本右下角浮条推送，
       下载带进度，装完 relaunch。 -->
  <teleport v-if="banner" to="body">
    <div class="app-update-tray" role="status" aria-live="polite">
      <div class="app-update-card">
        <div class="app-update-head">
          <span class="app-update-dot" :class="{ 'is-downloading': state === 'downloading' }" />
          <div class="app-update-title">
            <template v-if="state === 'downloading'">
              正在下载 {{ banner.version }} · {{ progressText }}
            </template>
            <template v-else-if="state === 'installing'">正在安装，即将重启…</template>
            <template v-else-if="state === 'error'">更新失败</template>
            <template v-else>发现新版本 {{ banner.version }}</template>
          </div>
          <button v-if="state === 'available'" type="button" class="app-update-close" aria-label="暂不更新" @click="dismiss">×</button>
        </div>
        <p v-if="state === 'error'" class="app-update-note error">{{ errorText }}</p>
        <p v-else-if="state === 'downloading'" class="app-update-note">
          <span class="app-update-progress"><i :style="{ width: progressPct + '%' }" /></span>
        </p>
        <p v-else-if="banner?.body" class="app-update-note">{{ banner.body }}</p>
        <div v-if="state === 'available'" class="app-update-actions">
          <button type="button" class="app-update-btn ghost" @click="dismiss">稍后提醒</button>
          <button type="button" class="app-update-btn primary" @click="downloadAndInstall">立即更新</button>
        </div>
        <div v-else-if="state === 'error'" class="app-update-actions">
          <button type="button" class="app-update-btn ghost" @click="dismiss">关闭</button>
          <button type="button" class="app-update-btn primary" @click="downloadAndInstall">重试</button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { check, type Update } from '@tauri-apps/plugin-updater'
import { relaunch } from '@tauri-apps/plugin-process'

type UpdateState = 'available' | 'downloading' | 'installing' | 'error'

/** 桌面壳检测：与 api/config.ts 同款探测，避免循环依赖 */
function isTauriRuntime(): boolean {
  if (typeof window === 'undefined') return false
  const w = window as Window & { __TAURI__?: unknown; __TAURI_INTERNALS__?: unknown }
  return !!(w.__TAURI__ || w.__TAURI_INTERNALS__)
}

const banner = ref<Update | null>(null)
const state = ref<UpdateState>('available')
const errorText = ref('')
const receivedBytes = ref(0)
const totalBytes = ref(0)

const progressPct = computed(() => {
  if (totalBytes.value <= 0) return 0
  return Math.min(100, Math.round((receivedBytes.value / totalBytes.value) * 100))
})
const progressText = computed(() => {
  if (totalBytes.value > 0) {
    return `${(receivedBytes.value / 1048576).toFixed(1)} / ${(totalBytes.value / 1048576).toFixed(1)} MB`
  }
  return `${(receivedBytes.value / 1048576).toFixed(1)} MB`
})

let periodicTimer: ReturnType<typeof setInterval> | undefined
const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000

// 1. 启动静默检查 + 周期复查；失败静默（离线/无发布都正常，不打扰）
async function checkForUpdate(): Promise<void> {
  if (!isTauriRuntime() || state.value === 'downloading' || state.value === 'installing') return
  try {
    const update = await check()
    if (update) {
      banner.value = update
      state.value = 'available'
    }
  } catch {
    // 网络不可达 / 端点未发布：静默，下轮再查
  }
}

// 2. 下载并安装：进度回调驱动进度条；完成后 relaunch 进新版本
async function downloadAndInstall(): Promise<void> {
  const update = banner.value
  if (!update || state.value === 'downloading' || state.value === 'installing') return
  state.value = 'downloading'
  errorText.value = ''
  try {
    await update.downloadAndInstall((event) => {
      switch (event.event) {
        case 'Started':
          totalBytes.value = event.data.contentLength ?? 0
          break
        case 'Progress':
          receivedBytes.value += event.data.chunkLength
          break
        case 'Finished':
          break
      }
    })
    state.value = 'installing'
    await relaunch()
  } catch (e: unknown) {
    state.value = 'error'
    const msg = e instanceof Error ? e.message : String(e)
    errorText.value = msg || '下载或安装失败，请检查网络后重试'
  }
}

function dismiss(): void {
  banner.value = null
  state.value = 'available'
  errorText.value = ''
}

onMounted(() => {
  if (!isTauriRuntime()) return
  void checkForUpdate()
  periodicTimer = setInterval(() => void checkForUpdate(), CHECK_INTERVAL_MS)
})

onBeforeUnmount(() => {
  if (periodicTimer) clearInterval(periodicTimer)
})
</script>

<style scoped>
.app-update-tray {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 3000;
}

.app-update-card {
  width: 320px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--app-border, rgba(15, 23, 42, 0.12));
  background: var(--app-surface, #fff);
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.18);
  animation: app-update-rise 0.28s ease both;
}

@keyframes app-update-rise {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.app-update-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-update-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #10b981;
}

.app-update-dot.is-downloading {
  background: var(--color-brand, #4f46e5);
  animation: app-update-pulse 1.1s ease infinite;
}

@keyframes app-update-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.app-update-title {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary, #0f172a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-update-close {
  flex: none;
  border: none;
  background: transparent;
  font-size: 18px;
  line-height: 1;
  color: var(--app-text-muted, #64748b);
  cursor: pointer;
  padding: 0 2px;
}

.app-update-close:hover {
  color: var(--app-text-primary);
}

.app-update-note {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--app-text-muted, #64748b);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.app-update-note.error {
  color: var(--color-danger, #dc2626);
}

.app-update-progress {
  display: block;
  height: 5px;
  border-radius: 3px;
  background: var(--app-surface-subtle, #f1f5f9);
  overflow: hidden;
}

.app-update-progress i {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: var(--color-brand, #4f46e5);
  transition: width 0.2s ease;
}

.app-update-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.app-update-btn {
  border: none;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: filter 0.15s ease, opacity 0.15s ease;
}

.app-update-btn.ghost {
  background: var(--app-surface-subtle, #f1f5f9);
  color: var(--app-text-secondary, #475569);
}

.app-update-btn.ghost:hover {
  filter: brightness(0.96);
}

.app-update-btn.primary {
  background: var(--color-brand, #4f46e5);
  color: #fff;
}

.app-update-btn.primary:hover {
  filter: brightness(1.08);
}

@media (prefers-reduced-motion: reduce) {
  .app-update-card { animation: none; }
  .app-update-dot.is-downloading { animation: none; }
}
</style>
