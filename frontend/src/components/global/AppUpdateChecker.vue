<template>
  <!-- 应用自更新（仅 Tauri 桌面模式；浏览器渲染 null）。
       启动即静默检查 + 每 4 小时复查；发现新版本右下角浮条推送，
       下载带进度，装完 relaunch。 -->
  <teleport v-if="showBanner" to="body">
    <div class="app-update-tray" role="status" aria-live="polite">
      <div class="app-update-card">
        <div class="app-update-head">
          <span class="app-update-dot" :class="{ 'is-downloading': status === 'downloading' }" />
          <div class="app-update-title">
            <template v-if="status === 'downloading'">
              正在下载 {{ availableVersion }} · {{ progressText }}
            </template>
            <template v-else-if="status === 'ready'">{{ availableVersion }} 已准备好</template>
            <template v-else-if="status === 'installing'">正在安全退出并安装…</template>
            <template v-else-if="status === 'error'">更新失败</template>
            <template v-else>发现新版本 {{ availableVersion }}</template>
          </div>
          <button v-if="status === 'available'" type="button" class="app-update-close" aria-label="暂不更新" @click="dismiss">×</button>
        </div>
        <p v-if="status === 'error'" class="app-update-note error">{{ errorText }}</p>
        <p v-else-if="status === 'downloading'" class="app-update-note">
          <span class="app-update-progress"><i :style="{ width: progressPct + '%' }" /></span>
        </p>
        <p v-else-if="status === 'ready'" class="app-update-note">安装前会安全关闭写作后端并保存数据库，然后重启应用。</p>
        <p v-else-if="releaseNotes" class="app-update-note">{{ releaseNotes }}</p>
        <div v-if="status === 'available'" class="app-update-actions">
          <button type="button" class="app-update-btn ghost" @click="dismiss">稍后提醒</button>
          <button type="button" class="app-update-btn primary" @click="downloadUpdate">下载更新</button>
        </div>
        <div v-else-if="status === 'ready'" class="app-update-actions">
          <button type="button" class="app-update-btn primary" @click="installAndRestart">安装并重启</button>
        </div>
        <div v-else-if="status === 'error'" class="app-update-actions">
          <button type="button" class="app-update-btn ghost" @click="dismiss">关闭</button>
          <button type="button" class="app-update-btn primary" @click="checkForUpdate({ manual: true })">重试</button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppUpdateStore } from '@/stores/appUpdateStore'

const updater = useAppUpdateStore()
const {
  status,
  availableVersion,
  releaseNotes,
  progressPct,
  progressText,
  errorText,
} = storeToRefs(updater)
const { checkForUpdate, dismiss, downloadUpdate, initialize, installAndRestart } = updater

const showBanner = computed(() => (
  status.value === 'available'
  || status.value === 'downloading'
  || status.value === 'ready'
  || status.value === 'installing'
  || (status.value === 'error' && Boolean(availableVersion.value))
))

let periodicTimer: ReturnType<typeof setInterval> | undefined
const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000

onMounted(() => {
  if (!updater.desktopRuntime) return
  void initialize().then(() => checkForUpdate())
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
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--app-text-primary, #0f172a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-update-close {
  flex: none;
  border: none;
  background: transparent;
  font-size: var(--font-size-xl);
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
  font-size: var(--font-size-xs);
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
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
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
