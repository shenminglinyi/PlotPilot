import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { getVersion } from '@tauri-apps/api/app'
import { invoke } from '@tauri-apps/api/core'
import { relaunch } from '@tauri-apps/plugin-process'
import { check, type Update } from '@tauri-apps/plugin-updater'
import { storageKeys } from '@/config/storageKeys'
import { isTauriRuntime } from '@/utils/tauriRuntime'

export type AppUpdateStatus =
  | 'idle'
  | 'checking'
  | 'available'
  | 'downloading'
  | 'ready'
  | 'installing'
  | 'up-to-date'
  | 'error'

const DISMISS_DURATION_MS = 24 * 60 * 60 * 1000

function readDismissedUpdate(): { version: string; dismissedAt: number } | null {
  try {
    const raw = localStorage.getItem(storageKeys.dismissedAppUpdate)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { version?: unknown; dismissedAt?: unknown }
    if (typeof parsed.version !== 'string' || typeof parsed.dismissedAt !== 'number') return null
    return { version: parsed.version, dismissedAt: parsed.dismissedAt }
  } catch {
    return null
  }
}

export const useAppUpdateStore = defineStore('appUpdate', () => {
  const desktopRuntime = isTauriRuntime()
  const status = ref<AppUpdateStatus>('idle')
  const currentVersion = ref('')
  const update = shallowRef<Update | null>(null)
  const receivedBytes = ref(0)
  const totalBytes = ref(0)
  const errorText = ref('')
  const manualCheck = ref(false)

  const availableVersion = computed(() => update.value?.version ?? '')
  const releaseNotes = computed(() => update.value?.body ?? '')
  const progressPct = computed(() => {
    if (totalBytes.value <= 0) return 0
    return Math.min(100, Math.round(receivedBytes.value / totalBytes.value * 100))
  })
  const progressText = computed(() => {
    const received = (receivedBytes.value / 1048576).toFixed(1)
    if (totalBytes.value <= 0) return `${received} MB`
    return `${received} / ${(totalBytes.value / 1048576).toFixed(1)} MB`
  })

  function isDismissed(version: string): boolean {
    const dismissed = readDismissedUpdate()
    return Boolean(
      dismissed
      && dismissed.version === version
      && Date.now() - dismissed.dismissedAt < DISMISS_DURATION_MS,
    )
  }

  async function initialize(): Promise<void> {
    if (!desktopRuntime) return
    try {
      currentVersion.value = await getVersion()
    } catch {
      currentVersion.value = ''
    }
  }

  async function checkForUpdate(options: { manual?: boolean } = {}): Promise<void> {
    if (!desktopRuntime || status.value === 'downloading' || status.value === 'installing') return
    manualCheck.value = options.manual === true
    status.value = 'checking'
    errorText.value = ''
    try {
      const candidate = await check({ timeout: 30_000 })
      update.value = candidate
      if (!candidate) {
        status.value = manualCheck.value ? 'up-to-date' : 'idle'
        return
      }
      status.value = !manualCheck.value && isDismissed(candidate.version) ? 'idle' : 'available'
    } catch (error: unknown) {
      if (manualCheck.value) {
        errorText.value = error instanceof Error ? error.message : String(error)
        status.value = 'error'
      } else {
        status.value = 'idle'
      }
    }
  }

  async function downloadUpdate(): Promise<void> {
    if (!update.value || status.value === 'downloading') return
    status.value = 'downloading'
    receivedBytes.value = 0
    totalBytes.value = 0
    errorText.value = ''
    try {
      await update.value.download(event => {
        if (event.event === 'Started') totalBytes.value = event.data.contentLength ?? 0
        if (event.event === 'Progress') receivedBytes.value += event.data.chunkLength
      })
      status.value = 'ready'
    } catch (error: unknown) {
      errorText.value = error instanceof Error ? error.message : String(error)
      status.value = 'error'
    }
  }

  async function installAndRestart(): Promise<void> {
    if (!update.value || status.value !== 'ready') return
    status.value = 'installing'
    errorText.value = ''
    let backendStopped = false
    try {
      await invoke('prepare_for_update')
      backendStopped = true
      await update.value.install()
      await relaunch()
    } catch (error: unknown) {
      if (backendStopped) {
        try { await invoke('restart_backend') } catch { /* 安装失败时尽力恢复当前会话 */ }
      }
      errorText.value = error instanceof Error ? error.message : String(error)
      status.value = 'error'
    }
  }

  function dismiss(): void {
    if (update.value?.version) {
      localStorage.setItem(storageKeys.dismissedAppUpdate, JSON.stringify({
        version: update.value.version,
        dismissedAt: Date.now(),
      }))
    }
    status.value = 'idle'
    errorText.value = ''
  }

  return {
    desktopRuntime,
    status,
    currentVersion,
    availableVersion,
    releaseNotes,
    progressPct,
    progressText,
    errorText,
    initialize,
    checkForUpdate,
    downloadUpdate,
    installAndRestart,
    dismiss,
  }
})
