import { onScopeDispose, ref, type Ref } from 'vue'

export type DebouncedTaskDelay = number | (() => number)

export interface UseDebouncedTaskOptions {
  onError?: (error: unknown) => void
}

export interface UseDebouncedTaskResult {
  isScheduled: Ref<boolean>
  isExecuting: Ref<boolean>
  schedule: (delayOverrideMs?: number) => void
  cancel: () => void
  flush: () => Promise<void>
}

function resolveDelayMs(delay: DebouncedTaskDelay): number {
  const value = typeof delay === 'function' ? delay() : delay
  return Math.max(0, Number.isFinite(value) ? value : 0)
}

export function useDebouncedTask(
  task: () => void | Promise<void>,
  delayMs: DebouncedTaskDelay,
  options: UseDebouncedTaskOptions = {},
): UseDebouncedTaskResult {
  const isScheduled = ref(false)
  const isExecuting = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let rerunAfterCurrent = false
  let disposed = false

  function clearTimer() {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
    isScheduled.value = false
  }

  async function runNow() {
    if (disposed) return
    if (isExecuting.value) {
      rerunAfterCurrent = true
      return
    }
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
      if (rerunAfterCurrent) {
        rerunAfterCurrent = false
        schedule()
      }
    }
  }

  function schedule(delayOverrideMs?: number) {
    if (disposed || typeof window === 'undefined') return
    clearTimer()
    isScheduled.value = true
    const delay = delayOverrideMs ?? resolveDelayMs(delayMs)
    timer = window.setTimeout(() => {
      clearTimer()
      void runNow().catch(() => undefined)
    }, delay)
  }

  function cancel() {
    clearTimer()
    rerunAfterCurrent = false
  }

  async function flush() {
    clearTimer()
    await runNow()
  }

  onScopeDispose(() => {
    disposed = true
    cancel()
  })

  return {
    isScheduled,
    isExecuting,
    schedule,
    cancel,
    flush,
  }
}
