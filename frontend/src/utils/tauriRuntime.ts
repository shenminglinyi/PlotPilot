let cachedTauriRuntime: boolean | null = null

/** 浏览器与 Tauri 桌面壳的唯一运行时判定。 */
export function isTauriRuntime(): boolean {
  if (cachedTauriRuntime !== null) return cachedTauriRuntime
  if (typeof window === 'undefined') return false
  const runtimeWindow = window as Window & {
    __TAURI__?: unknown
    __TAURI_INTERNALS__?: unknown
  }
  cachedTauriRuntime = Boolean(runtimeWindow.__TAURI__ || runtimeWindow.__TAURI_INTERNALS__)
  return cachedTauriRuntime
}
