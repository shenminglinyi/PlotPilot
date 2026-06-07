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
  let timer: ReturnType<typeof setInterval> | null = null

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
    if (timer != null) {
      clearInterval(timer)
      timer = null
    }
    isPolling.value = false
  }

  function start(startOptions: StartPollingOptions = {}) {
    if (isPolling.value || typeof window === 'undefined') return
    isPolling.value = true
    const shouldRunImmediately = startOptions.immediate ?? options.immediate ?? false
    if (shouldRunImmediately) {
      void execute()
    }
    timer = window.setInterval(() => {
      void execute()
    }, intervalMs)
  }

  function restart(startOptions: StartPollingOptions = {}) {
    stop()
    start(startOptions)
  }

  if (options.autoStart) {
    start()
  }

  onScopeDispose(stop)

  return {
    isPolling,
    isExecuting,
    start,
    stop,
    restart,
    execute,
  }
}
