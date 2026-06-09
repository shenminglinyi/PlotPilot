import { onScopeDispose, ref, type Ref } from 'vue'

export interface StartPollingOptions {
  immediate?: boolean
}

export interface UsePollingOptions extends StartPollingOptions {
  autoStart?: boolean
}

export interface UsePollingResult {
  isPolling: Ref<boolean>
  isExecuting: Ref<boolean>
  start: (options?: StartPollingOptions) => void
  stop: () => void
  restart: (options?: StartPollingOptions) => void
  execute: () => Promise<void>
}

export function usePolling(
  task: () => void | Promise<void>,
  intervalMs: number,
  options: UsePollingOptions = {},
): UsePollingResult {
  const isPolling = ref(false)
  const isExecuting = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let disposed = false

  function clearTimer() {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
  }

  function resolveIntervalMs(): number {
    return Math.max(0, Number.isFinite(intervalMs) ? intervalMs : 0)
  }

  function scheduleNext() {
    clearTimer()
    if (disposed || !isPolling.value || typeof window === 'undefined') return
    timer = window.setTimeout(() => {
      timer = null
      void execute().catch(() => undefined).finally(scheduleNext)
    }, resolveIntervalMs())
  }

  async function execute() {
    if (isExecuting.value) return
    isExecuting.value = true
    try {
      await task()
    } finally {
      isExecuting.value = false
    }
  }

  function stop() {
    clearTimer()
    isPolling.value = false
  }

  function start(startOptions: StartPollingOptions = {}) {
    if (disposed || isPolling.value || typeof window === 'undefined') return
    isPolling.value = true
    const shouldRunImmediately = startOptions.immediate ?? options.immediate ?? false
    if (shouldRunImmediately) {
      void execute().catch(() => undefined).finally(scheduleNext)
    } else {
      scheduleNext()
    }
  }

  function restart(startOptions: StartPollingOptions = {}) {
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
