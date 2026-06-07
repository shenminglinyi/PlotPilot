import { onScopeDispose, ref, type Ref } from 'vue'

export type AdaptivePollingDelay = number | (() => number)

export interface AdaptivePollingStartOptions {
  immediate?: boolean
}

export interface UseAdaptivePollingOptions extends AdaptivePollingStartOptions {
  autoStart?: boolean
  pauseWhenHidden?: boolean
  shouldContinue?: () => boolean
  onError?: (error: unknown) => void
}

export interface UseAdaptivePollingResult {
  isPolling: Ref<boolean>
  isExecuting: Ref<boolean>
  start: (options?: AdaptivePollingStartOptions) => void
  stop: () => void
  restart: (options?: AdaptivePollingStartOptions) => void
  execute: () => Promise<void>
}

function resolveDelayMs(delay: AdaptivePollingDelay): number {
  const value = typeof delay === 'function' ? delay() : delay
  return Math.max(0, Number.isFinite(value) ? value : 0)
}

function isDocumentHidden(): boolean {
  return typeof document !== 'undefined' && document.hidden
}

export function useAdaptivePolling(
  task: () => void | Promise<void>,
  delayMs: AdaptivePollingDelay,
  options: UseAdaptivePollingOptions = {},
): UseAdaptivePollingResult {
  const isPolling = ref(false)
  const isExecuting = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let disposed = false
  let listeningVisibility = false

  function clearTimer() {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
  }

  function canSchedule(): boolean {
    if (disposed || !isPolling.value || typeof window === 'undefined') return false
    if (options.shouldContinue && !options.shouldContinue()) return false
    if (options.pauseWhenHidden && isDocumentHidden()) return false
    return true
  }

  function scheduleNext() {
    clearTimer()
    if (!canSchedule()) return
    timer = window.setTimeout(() => {
      timer = null
      void execute().catch(() => undefined).finally(scheduleNext)
    }, resolveDelayMs(delayMs))
  }

  function handleVisibilityChange() {
    if (!options.pauseWhenHidden || !isPolling.value) return
    if (isDocumentHidden()) {
      clearTimer()
      return
    }
    void execute().catch(() => undefined).finally(scheduleNext)
  }

  function ensureVisibilityListener() {
    if (!options.pauseWhenHidden || listeningVisibility || typeof document === 'undefined') return
    document.addEventListener('visibilitychange', handleVisibilityChange)
    listeningVisibility = true
  }

  function removeVisibilityListener() {
    if (!listeningVisibility || typeof document === 'undefined') return
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    listeningVisibility = false
  }

  async function execute() {
    if (isExecuting.value) return
    isExecuting.value = true
    try {
      await task()
    } catch (error) {
      if (options.onError) {
        options.onError(error)
      } else {
        throw error
      }
    } finally {
      isExecuting.value = false
    }
  }

  function start(startOptions: AdaptivePollingStartOptions = {}) {
    if (disposed || typeof window === 'undefined') return
    isPolling.value = true
    ensureVisibilityListener()
    clearTimer()
    if (!canSchedule()) return

    const shouldRunImmediately = startOptions.immediate ?? options.immediate ?? false
    if (shouldRunImmediately) {
      void execute().catch(() => undefined).finally(scheduleNext)
    } else {
      scheduleNext()
    }
  }

  function stop() {
    clearTimer()
    isPolling.value = false
    removeVisibilityListener()
  }

  function restart(startOptions: AdaptivePollingStartOptions = {}) {
    stop()
    start(startOptions)
  }

  if (options.autoStart) {
    start()
  }

  onScopeDispose(() => {
    disposed = true
    stop()
  })

  return {
    isPolling,
    isExecuting,
    start,
    stop,
    restart,
    execute,
  }
}
